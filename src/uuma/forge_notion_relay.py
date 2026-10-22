"""Scoped workstation Notion access for the server-owned Forge journal.

The Notion secret stays in the workstation Hermes configuration. The server sends
named journal operations with a scoped Forge identity, never arbitrary URLs/headers.
Each request has a durable receipt; uncertain requests are not automatically replayed.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import sqlite3
import time
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import anyio
import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .auth import TokenRegistry
from .control_client import validate_endpoint
from .remote_mcp import AgentAuthentication

MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_TTL_SECONDS = 1800
UPSTREAM = "https://api.notion.com/v1"
ARGUMENTS = {
    "query_data_source": ({"data_source_id"}, {"filter_body"}),
    "retrieve_page": ({"page_id"}, set()),
    "list_children": ({"block_id"}, set()),
    "snapshot": ({"page_id"}, set()),
    "create_page": ({"data_source_id", "properties", "children"}, set()),
    "update_page": ({"page_id", "properties"}, set()),
    "append_children": ({"page_id", "children"}, set()),
    "delete_block": ({"block_id"}, set()),
    "set_sync_status": ({"page_id", "status"}, set()),
}


class RelayCall(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    operation: str
    arguments: dict[str, Any]
    expires_at: float


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _identity(value: str) -> str:
    return str(UUID(value))


class ReceiptStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS relay_receipts (request_id TEXT PRIMARY KEY, "
                "digest TEXT NOT NULL, state TEXT NOT NULL, response_json TEXT, "
                "created_at REAL NOT NULL, updated_at REAL NOT NULL)"
            )
            db.commit()
        if os.name != "nt":
            path.chmod(0o600)

    def reserve(self, call: RelayCall) -> tuple[bool, dict]:
        digest = hashlib.sha256(_canonical({
            "operation": call.operation, "arguments": call.arguments,
        }).encode()).hexdigest()
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT digest,state,response_json FROM relay_receipts WHERE request_id=?",
                (call.request_id,),
            ).fetchone()
            if row:
                if row[0] != digest:
                    raise ValueError("Request identity already belongs to different arguments")
                return False, {
                    "request_id": call.request_id,
                    "state": row[1],
                    "result": json.loads(row[2]) if row[2] else None,
                }
            now = time.time()
            db.execute(
                "INSERT INTO relay_receipts VALUES (?,?,'IN_FLIGHT',NULL,?,?)",
                (call.request_id, digest, now, now),
            )
            db.commit()
            return True, {}

    def finish(self, request_id: str, state: str, result: Any) -> dict:
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(
                "UPDATE relay_receipts SET state=?,response_json=?,updated_at=? WHERE request_id=?",
                (state, _canonical(result), time.time(), request_id),
            )
            db.commit()
        return {"request_id": request_id, "state": state, "result": result}

    def get(self, request_id: str) -> dict | None:
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute(
                "SELECT state,response_json FROM relay_receipts WHERE request_id=?", (request_id,)
            ).fetchone()
        return (
            {"request_id": request_id, "state": row[0],
             "result": json.loads(row[1]) if row[1] else None}
            if row else None
        )


class JournalOperations:
    def __init__(self, notion, *, logs_data_source: str, candidates_data_source: str):
        self.notion = notion
        self.logs = _identity(logs_data_source)
        self.candidates = _identity(candidates_data_source)
        # No request can choose an upstream host, headers, or an access token.
        self.notion.api_root = UPSTREAM

    def _source(self, value: str) -> str:
        source = _identity(value)
        if source not in {self.logs, self.candidates}:
            raise PermissionError("Notion source is outside the Forge journal")
        return source

    def _page(self, page_id: str) -> tuple[str, dict]:
        page = self.notion.retrieve_page(_identity(page_id))
        parent = page.get("parent") or {}
        source = parent.get("data_source_id")
        if not source:
            raise PermissionError("Page is not a Forge data-source page")
        return self._source(source), page

    def _block(self, block_id: str) -> tuple[str, dict]:
        current = _identity(block_id)
        seen = set()
        for _ in range(32):
            if current in seen:
                break
            seen.add(current)
            block = self.notion._request("GET", "blocks/" + current)
            parent = block.get("parent") or {}
            if parent.get("page_id"):
                return self._page(parent["page_id"])
            if not parent.get("block_id"):
                break
            current = _identity(parent["block_id"])
        raise PermissionError("Block is outside the Forge journal")

    def _properties(self, source: str, properties: Any) -> None:
        if not isinstance(properties, dict):
            raise TypeError("Properties must be an object")
        status = properties.get("Status")
        if (source == self.candidates and status is not None
                and status != {"select": {"name": "Candidate"}}):
            raise PermissionError("Forge may only write Candidate engineering knowledge")

    def call(self, operation: str, arguments: dict) -> Any:
        if operation not in ARGUMENTS:
            raise PermissionError("Unknown journal operation")
        required, optional = ARGUMENTS[operation]
        if not required <= arguments.keys() or arguments.keys() - required - optional:
            raise ValueError("Unexpected journal operation arguments")
        args = dict(arguments)
        if "data_source_id" in args:
            source = self._source(args["data_source_id"])
            args["data_source_id"] = source
        elif "page_id" in args:
            source, page = self._page(args["page_id"])
            args["page_id"] = _identity(args["page_id"])
        elif operation == "list_children":
            source, page = self._page(args["block_id"])
            args["block_id"] = _identity(args["block_id"])
        elif operation == "delete_block":
            source, page = self._block(args["block_id"])
            args["block_id"] = _identity(args["block_id"])
        else:
            raise PermissionError("Journal operation has no scoped target")
        if "properties" in args:
            self._properties(source, args["properties"])
        if (operation in {"update_page", "append_children", "delete_block"}
                and source == self.candidates):
            status = ((page.get("properties") or {}).get("Status") or {}).get("select") or {}
            if status.get("name") != "Candidate":
                raise PermissionError("Forge cannot mutate reviewed engineering knowledge")
        if (operation == "create_page" and source == self.candidates
                and args["properties"].get("Status") != {"select": {"name": "Candidate"}}):
            raise PermissionError("New engineering knowledge must be Candidate")
        if (operation == "set_sync_status" and
                (source != self.logs or args["status"] not in {"Queued", "Failed", "Conflict", "Synced"})):
            raise PermissionError("Invalid Forge log synchronization status")
        if "children" in args and not isinstance(args["children"], list):
            raise ValueError("Children must be a list")
        method = getattr(self.notion, operation)
        inspect.signature(method).bind(**args)
        return method(**args)


def create_app(*, tokens: TokenRegistry, notion, receipts: Path):
    from .forge_journal_runner import DEFAULT_CANDIDATES_DATA_SOURCE, DEFAULT_LOGS_DATA_SOURCE

    store = ReceiptStore(receipts)
    operations = JournalOperations(
        notion, logs_data_source=DEFAULT_LOGS_DATA_SOURCE,
        candidates_data_source=DEFAULT_CANDIDATES_DATA_SOURCE,
    )

    def execute(call: RelayCall) -> tuple[dict, int]:
        try:
            fresh, existing = store.reserve(call)
        except ValueError:
            return {"detail": "Request identity conflicts with an existing receipt"}, 409
        if not fresh:
            return existing, 200 if existing["state"] == "COMPLETE" else 409
        try:
            result = operations.call(call.operation, call.arguments)
        except (PermissionError, ValueError, TypeError):
            result = store.finish(call.request_id, "REJECTED", {"detail": "Journal scope rejected"})
            return result, 403
        except Exception:  # noqa: BLE001 - persist uncertainty before any retry can occur.
            # Notion could have applied a write before its response was lost.
            result = store.finish(
                call.request_id, "UNCERTAIN", {"detail": "Check the remote journal before retrying"}
            )
            return result, 409
        return store.finish(call.request_id, "COMPLETE", result), 200

    async def call(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY_BYTES:
                return JSONResponse({"detail": "Journal request is too large"}, 413)
        try:
            payload = RelayCall.model_validate_json(body)
        except ValidationError:
            return JSONResponse({"detail": "Invalid journal request"}, 422)
        now = time.time()
        if payload.expires_at <= now or payload.expires_at > now + MAX_TTL_SECONDS:
            return JSONResponse({"detail": "Journal request expired or has invalid lifetime"}, 409)
        result, status = await anyio.to_thread.run_sync(execute, payload)
        return JSONResponse(result, status)

    async def receipt(request: Request):
        result = store.get(request.path_params["request_id"])
        return JSONResponse(result or {"detail": "Receipt not found"}, 200 if result else 404)

    app = Starlette(routes=[
        Route("/call", call, methods=["POST"]),
        Route("/receipts/{request_id}", receipt, methods=["GET"]),
    ])
    return AgentAuthentication(app, tokens, allowed={"forge-lab-bot"})


class NotionRelayError(RuntimeError):
    def __init__(self, request_id: str):
        super().__init__("Notion relay did not confirm completion; check receipt " + request_id)
        self.request_id = request_id


class NotionRelayClient:
    def __init__(self, url: str, token: str, *, transport=None):
        self.url = validate_endpoint(url)
        if not token:
            raise PermissionError("Forge Notion relay requires a scoped credential")
        self._token = token
        self._transport = transport
        self._execution_id = None

    @contextmanager
    def execution(self, job_id: str):
        previous = self._execution_id
        self._execution_id = job_id
        try:
            yield
        finally:
            self._execution_id = previous

    @classmethod
    def from_env(cls):
        if os.environ.get("UUMA_AGENT_ID") != "forge-lab-bot":
            raise PermissionError("Forge Notion relay requires the Forge identity")
        path = os.environ.get("UUMA_FORGE_NOTION_RELAY_TOKEN_FILE") or os.environ.get(
            "UUMA_IDENTITY_TOKEN_FILE", ""
        )
        if not path:
            raise PermissionError("Forge Notion relay token file is required")
        return cls(
            os.environ["UUMA_FORGE_NOTION_RELAY_URL"],
            Path(path).read_text(encoding="utf-8").strip(),
        )

    def _call(self, operation: str, **arguments):
        mutating = operation not in {"query_data_source", "retrieve_page", "list_children", "snapshot"}
        request_id = (
            hashlib.sha256(_canonical({"job": self._execution_id,
                "operation": operation, "arguments": arguments}).encode()).hexdigest()[:32]
            if self._execution_id and mutating else uuid4().hex
        )
        payload = {"request_id": request_id, "operation": operation, "arguments": arguments,
                   "expires_at": time.time() + MAX_TTL_SECONDS - 5}
        try:
            with httpx.Client(
                transport=self._transport, timeout=120, follow_redirects=False,
                headers={"Authorization": "Bearer " + self._token,
                         "X-Uuma-Identity": "forge-lab-bot"},
            ) as client:
                response = client.post(self.url + "/call", json=payload)
                if response.status_code != 200:
                    raise NotionRelayError(request_id)
                receipt = response.json()
                if receipt.get("state") != "COMPLETE" or receipt.get("request_id") != request_id:
                    raise NotionRelayError(request_id)
                return receipt["result"]
        except httpx.HTTPError as exc:
            raise NotionRelayError(request_id) from exc

    def query_data_source(self, data_source_id: str, filter_body=None):
        return self._call("query_data_source", data_source_id=data_source_id, filter_body=filter_body)

    def retrieve_page(self, page_id: str):
        return self._call("retrieve_page", page_id=page_id)

    def list_children(self, block_id: str):
        return self._call("list_children", block_id=block_id)

    def snapshot(self, page_id: str):
        return self._call("snapshot", page_id=page_id)

    def create_page(self, data_source_id: str, properties: dict, children: list):
        return self._call("create_page", data_source_id=data_source_id,
                          properties=properties, children=children)

    def update_page(self, page_id: str, properties: dict):
        return self._call("update_page", page_id=page_id, properties=properties)

    def append_children(self, page_id: str, children: list):
        return self._call("append_children", page_id=page_id, children=children)

    def delete_block(self, block_id: str):
        return self._call("delete_block", block_id=block_id)

    def set_sync_status(self, page_id: str, status: str):
        return self._call("set_sync_status", page_id=page_id, status=status)

    def page_record(self, page: dict, journal_kind: str):
        from .forge_journal_runner import NotionJournalClient
        return NotionJournalClient.page_record(self, page, journal_kind)

    @staticmethod
    def contains_marker(blocks: list, marker: str) -> bool:
        from .forge_journal_runner import NotionJournalClient
        return NotionJournalClient.contains_marker(blocks, marker)

    def find_by_marker(self, data_source_id: str, title_property: str, title: str,
                       marker: str):
        from .forge_journal_runner import NotionJournalClient
        return NotionJournalClient.find_by_marker(
            self, data_source_id, title_property, title, marker
        )


def main():
    import uvicorn

    from .forge_journal_runner import NotionJournalClient, load_notion_connection

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token-registry", type=Path, required=True)
    parser.add_argument("--hermes-config", type=Path, required=True)
    parser.add_argument("--receipts", type=Path, required=True)
    args = parser.parse_args()
    if not args.token_registry.is_file() or not args.hermes_config.is_file():
        parser.error("Existing identity registry and workstation Hermes configuration are required")
    notion = NotionJournalClient(load_notion_connection(args.hermes_config))
    uvicorn.run(
        create_app(tokens=TokenRegistry(args.token_registry), notion=notion, receipts=args.receipts),
        host="127.0.0.1", port=args.port,
    )


if __name__ == "__main__":
    main()
