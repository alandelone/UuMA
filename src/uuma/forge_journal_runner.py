from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import socket
import sqlite3
import subprocess
import time
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar, Self
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from ruamel.yaml import YAML

from .forge_journal import ForgeJournalStore, JournalSyncError, _notion_id

LOGGER = logging.getLogger(__name__)
DEFAULT_LOGS_DATA_SOURCE = "06d7c1c5-a614-4577-ab62-a238ce376675"
DEFAULT_CANDIDATES_DATA_SOURCE = "b68cd096-9176-4571-83f7-ddfa7c082bc7"
SYNC_MARKER_PREFIX = "LAB_BOT Sync:"
_VOLATILE_KEYS = {
    "created_by",
    "created_time",
    "expiry_time",
    "id",
    "last_edited_by",
    "last_edited_time",
    "object",
    "parent",
    "request_id",
    "url",
}
_VOLATILE_PROPERTIES = {"Created", "Last Updated", "Sync Status"}


class NotionApiError(RuntimeError):
    def __init__(self, status: int, code: str, message: str, retry_after: int | None = None) -> None:
        super().__init__(f"Notion API {status} {code}: {message}".strip())
        self.status = status
        self.code = code
        self.retry_after = retry_after


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sanitize(value: Any, *, parent_key: str = "") -> Any:
    if isinstance(value, list):
        return [_sanitize(item, parent_key=parent_key) for item in value]
    if not isinstance(value, dict):
        return value
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key in _VOLATILE_KEYS:
            continue
        if parent_key == "properties" and key in _VOLATILE_PROPERTIES:
            continue
        if key == "file" and isinstance(item, dict):
            result[key] = {name: data for name, data in item.items() if name not in {"url", "expiry_time"}}
            continue
        result[key] = _sanitize(item, parent_key=key)
    return result


def _plain_text(items: list[dict[str, Any]] | None) -> str:
    return "".join(str(item.get("plain_text") or "") for item in (items or []))


def _property_text(prop: dict[str, Any] | None) -> str:
    if not prop:
        return ""
    kind = str(prop.get("type") or "")
    if kind in {"title", "rich_text"}:
        return _plain_text(prop.get(kind) or [])
    if kind == "select":
        return str((prop.get("select") or {}).get("name") or "")
    return ""


def _text_objects(text: str) -> list[dict[str, Any]]:
    content = str(text)
    return [
        {"type": "text", "text": {"content": content[index : index + 1900]}}
        for index in range(0, len(content), 1900)
    ] or [{"type": "text", "text": {"content": ""}}]


def _paragraph(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _text_objects(text)}}


def _heading(text: str, *, level: int = 2) -> dict[str, Any]:
    kind = f"heading_{level}"
    return {"object": "block", "type": kind, kind: {"rich_text": _text_objects(text)}}


class _RunnerInstanceLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None

    def __enter__(self) -> Self:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise RuntimeError("Another Forge Journal runner process is already active.") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps({"pid": os.getpid()}).encode("utf-8"))
        handle.flush()
        self._handle = handle
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._handle is None:
            return
        try:
            self._handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None


def load_notion_connection(default_config: Path) -> dict[str, str]:
    """Load OpenClaw's internal `notion` connection without copying its secret."""
    payload = YAML(typ="safe").load(default_config.read_text(encoding="utf-8")) or {}
    server = (payload.get("mcp_servers") or {}).get("notion") or {}
    raw_headers = (server.get("env") or {}).get("OPENAPI_MCP_HEADERS")
    if not isinstance(raw_headers, str):
        raise TypeError("The Hermes `notion` connection has no OPENAPI_MCP_HEADERS value.")
    headers = json.loads(raw_headers)
    if not isinstance(headers, dict) or not str(headers.get("Authorization") or "").startswith(
        "Bearer "
    ):
        raise RuntimeError("The Hermes `notion` connection has no usable bearer authorization.")
    headers = {str(key): str(value) for key, value in headers.items()}
    headers.setdefault("Notion-Version", "2025-09-03")
    headers["Content-Type"] = "application/json"
    return headers


class NotionJournalClient:
    def __init__(
        self,
        headers: dict[str, str],
        *,
        api_root: str = "https://api.notion.com/v1",
        request_timeout: int = 60,
        opener=urlopen,
    ) -> None:
        self.headers = dict(headers)
        self.api_root = api_root.rstrip("/")
        self.request_timeout = request_timeout
        self.opener = opener

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        body = None if payload is None else _canonical_json(payload).encode("utf-8")
        request = Request(
            f"{self.api_root}/{path.lstrip('/')}",
            data=body,
            headers=self.headers,
            method=method,
        )
        try:
            with self.opener(request, timeout=self.request_timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            raw = exc.read()
            try:
                detail = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                detail = {}
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            raise NotionApiError(
                exc.code,
                str(detail.get("code") or "request_failed"),
                str(detail.get("message") or exc.reason),
                int(retry_after) if retry_after and retry_after.isdigit() else None,
            ) from exc
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def query_data_source(
        self, data_source_id: str, *, filter_body: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        cursor = ""
        while True:
            payload: dict[str, Any] = {"page_size": 100}
            if filter_body:
                payload["filter"] = filter_body
            if cursor:
                payload["start_cursor"] = cursor
            response = self._request("POST", f"data_sources/{data_source_id}/query", payload)
            results.extend(response.get("results") or [])
            if not response.get("has_more"):
                return results
            cursor = str(response.get("next_cursor") or "")
            if not cursor:
                return results

    def retrieve_page(self, page_id: str) -> dict[str, Any]:
        return self._request("GET", f"pages/{page_id}")

    def list_children(self, block_id: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        cursor = ""
        while True:
            suffix = "?page_size=100"
            if cursor:
                suffix += "&" + urlencode({"start_cursor": cursor})
            response = self._request("GET", f"blocks/{block_id}/children{suffix}")
            for block in response.get("results") or []:
                item = dict(block)
                if block.get("has_children"):
                    item["children"] = self.list_children(str(block["id"]))
                results.append(item)
            if not response.get("has_more"):
                return results
            cursor = str(response.get("next_cursor") or "")
            if not cursor:
                return results

    def snapshot(self, page_id: str) -> dict[str, Any]:
        page = self.retrieve_page(page_id)
        blocks = self.list_children(page_id)
        return {
            "properties": _sanitize(page.get("properties") or {}, parent_key="properties"),
            "blocks": _sanitize(blocks),
        }

    def create_page(
        self,
        data_source_id: str,
        properties: dict[str, Any],
        children: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "pages",
            {
                "parent": {"type": "data_source_id", "data_source_id": data_source_id},
                "properties": properties,
                "children": children,
            },
        )

    def update_page(self, page_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"pages/{page_id}", {"properties": properties})

    def append_children(
        self, page_id: str, children: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        response = self._request("PATCH", f"blocks/{page_id}/children", {"children": children})
        return list(response.get("results") or [])

    def delete_block(self, block_id: str) -> None:
        self._request("DELETE", f"blocks/{block_id}")

    def set_sync_status(self, page_id: str, status: str) -> None:
        self.update_page(page_id, {"Sync Status": {"select": {"name": status}}})

    def page_record(self, page: dict[str, Any], journal_kind: str) -> dict[str, Any]:
        properties = page.get("properties") or {}
        title_property = "Name" if journal_kind == "LOG" else "Statement"
        return {
            "notion_page_id": str(page["id"]),
            "notion_url": str(page.get("url") or ""),
            "title": _property_text(properties.get(title_property)),
            "project_system": _property_text(properties.get("Project / System")),
            "entry_type": _property_text(properties.get("Type")),
            "remote_edited_at": str(page.get("last_edited_time") or ""),
            "journal_kind": journal_kind,
        }

    @staticmethod
    def contains_marker(blocks: list[dict[str, Any]], marker: str) -> bool:
        def walk(items: list[dict[str, Any]]) -> bool:
            for block in items:
                kind = str(block.get("type") or "")
                data = block.get(kind) or {}
                if marker in _plain_text(data.get("rich_text") or []):
                    return True
                if walk(block.get("children") or []):
                    return True
            return False

        return walk(blocks)

    def find_by_marker(
        self,
        data_source_id: str,
        title_property: str,
        title: str,
        marker: str,
    ) -> dict[str, Any] | None:
        filter_body = {"property": title_property, "title": {"equals": title}}
        for page in self.query_data_source(data_source_id, filter_body=filter_body):
            if self.contains_marker(self.list_children(str(page["id"])), marker):
                return page
        return None


class HermesRouteResolver:
    SUPPORTED: ClassVar[set[str]] = {
        "discord",
        "google_chat",
        "qqbot",
        "signal",
        "slack",
        "teams",
        "telegram",
        "whatsapp",
        "yuanbao",
    }

    def __init__(self, state_databases: list[Path], explicit_target: str = "") -> None:
        self.state_databases = state_databases
        self.explicit_target = explicit_target.strip()

    def target(self) -> str | None:
        if self.explicit_target:
            return self.explicit_target
        candidates: list[tuple[float, str]] = []
        for path in self.state_databases:
            if not path.is_file():
                continue
            uri = path.resolve().as_uri() + "?mode=ro"
            with sqlite3.connect(uri, uri=True) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    """
                    SELECT source, chat_id, thread_id,
                           COALESCE(last_activity_at, started_at) AS activity
                    FROM sessions
                    WHERE chat_id IS NOT NULL AND archived = 0
                    ORDER BY activity DESC LIMIT 20
                    """
                ).fetchall()
            for row in rows:
                source = str(row["source"] or "").strip()
                if source not in self.SUPPORTED:
                    continue
                parts = [source, str(row["chat_id"])]
                if row["thread_id"]:
                    parts.append(str(row["thread_id"]))
                candidates.append((float(row["activity"] or 0), ":".join(parts)))
        return max(candidates, default=(0, ""))[1] or None


class ForgeJournalNotificationDispatcher:
    def __init__(
        self,
        store: ForgeJournalStore,
        hermes_executable: Path,
        profile_home: Path,
        route_resolver: HermesRouteResolver,
        *,
        command_runner=subprocess.run,
        worker_id: str = "forge-journal-notifier",
    ) -> None:
        self.store = store
        self.hermes_executable = hermes_executable
        self.profile_home = profile_home
        self.route_resolver = route_resolver
        self.command_runner = command_runner
        self.worker_id = worker_id

    def dispatch_one(self) -> bool:
        notice = self.store.claim_notification(self.worker_id)
        if notice is None:
            return False
        target = self.route_resolver.target()
        if not target:
            self.store.finish_notification(
                str(notice["notification_id"]),
                sent=False,
                worker_id=self.worker_id,
                error="No eligible Hermes conversation route is available.",
            )
            return True
        journal = self.store.get_page(str(notice["journal_id"]))
        message = self._message(notice, journal)
        environment = os.environ.copy()
        environment["HERMES_HOME"] = str(self.profile_home)
        try:
            result = self.command_runner(
                [str(self.hermes_executable), "send", "--to", target, "--quiet", message],
                env=environment,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "Hermes send failed.").strip()
                raise RuntimeError(detail[:2000])
        except Exception as exc:  # noqa: BLE001 - the durable outbox owns delivery failures.
            self.store.finish_notification(
                str(notice["notification_id"]),
                sent=False,
                worker_id=self.worker_id,
                error=str(exc),
            )
        else:
            self.store.finish_notification(
                str(notice["notification_id"]), sent=True, worker_id=self.worker_id
            )
        return True

    @staticmethod
    def _message(notice: dict[str, Any], journal: dict[str, Any]) -> str:
        payload = json.dumps(notice["payload"], ensure_ascii=False, sort_keys=True)
        return (
            "LAB_BOT Forge Journal update\n"
            f"Log: {journal.get('title') or journal['journal_id']}\n"
            f"Event: {notice['event_type']}\n"
            f"Current sync state: {journal['sync_status']}\n"
            f"Details: {payload}"
        )


class ForgeJournalRunner:
    def __init__(
        self,
        store: ForgeJournalStore,
        notion: NotionJournalClient,
        dispatcher: ForgeJournalNotificationDispatcher,
        *,
        logs_data_source: str = DEFAULT_LOGS_DATA_SOURCE,
        candidates_data_source: str = DEFAULT_CANDIDATES_DATA_SOURCE,
        worker_id: str | None = None,
    ) -> None:
        self.store = store
        self.notion = notion
        self.dispatcher = dispatcher
        self.logs_data_source = logs_data_source
        self.candidates_data_source = candidates_data_source
        self.worker_id = worker_id or f"forge-journal:{socket.gethostname()}:{os.getpid()}"

    def reconcile(self) -> dict[str, int]:
        counts = {"logs": 0, "candidates": 0, "conflicts": 0}
        local_pages = {
            str(page.get("notion_page_id") or ""): page
            for page in self.store.status(limit=1000)["pages"]
            if page.get("notion_page_id")
        }
        for data_source, kind, counter in (
            (self.logs_data_source, "LOG", "logs"),
            (self.candidates_data_source, "KNOWLEDGE_CANDIDATE", "candidates"),
        ):
            for page in self.notion.query_data_source(data_source):
                if page.get("in_trash") or page.get("archived"):
                    continue
                page_id = str(page["id"])
                local = local_pages.get(_notion_id(page_id))
                remote_edited_at = str(page.get("last_edited_time") or "")
                if (
                    local is not None
                    and str(local.get("remote_edited_at") or "") == remote_edited_at
                    and local["sync_status"] == "SYNCED"
                ):
                    counts[counter] += 1
                    if kind == "LOG":
                        properties = page.get("properties") or {}
                        if _property_text(properties.get("Sync Status")) != "Synced":
                            self.notion.set_sync_status(page_id, "Synced")
                    continue
                snapshot = self.notion.snapshot(page_id)
                record = self.notion.page_record(page, kind)
                result = self.store.register_snapshot(
                    record["notion_page_id"],
                    record["notion_url"],
                    record["title"],
                    _digest(snapshot),
                    remote_edited_at=record["remote_edited_at"],
                    journal_kind=kind,
                    project_system=record["project_system"],
                    entry_type=record["entry_type"],
                    snapshot=snapshot,
                    actor_id="openclaw",
                )
                counts[counter] += 1
                counts["conflicts"] += int(bool(result["conflict"]))
                if kind == "LOG":
                    status = {
                        "SYNCED": "Synced",
                        "QUEUED": "Queued",
                        "CONFLICT": "Conflict",
                    }[str(result["sync_status"])]
                    properties = page.get("properties") or {}
                    if _property_text(properties.get("Sync Status")) != status:
                        self.notion.set_sync_status(page_id, status)
        return counts

    def process_one(self) -> dict[str, Any] | None:
        job = self.store.claim_write(self.worker_id, lease_seconds=300)
        if job is None:
            return None
        journal = self.store.get_page(str(job["journal_id"]))
        try:
            return self._execute(job, journal)
        except NotionApiError as exc:
            conflict = exc.status == 409
            result = self.store.finish_write(
                str(job["sync_job_id"]),
                succeeded=False,
                worker_id=self.worker_id,
                error=str(exc),
                conflict=conflict,
            )
            self._best_effort_status(journal, "Conflict" if conflict else result["status"].title())
            return result
        except PermissionError as exc:
            result = self.store.finish_write(
                str(job["sync_job_id"]),
                succeeded=False,
                worker_id=self.worker_id,
                error=str(exc),
                conflict=True,
            )
            self._best_effort_status(journal, "Conflict")
            return result
        except Exception as exc:  # noqa: BLE001 - retries belong in the durable queue.
            result = self.store.finish_write(
                str(job["sync_job_id"]),
                succeeded=False,
                worker_id=self.worker_id,
                error=str(exc),
            )
            self._best_effort_status(journal, str(result["status"]).title())
            return result

    def _execute(self, job: dict[str, Any], journal: dict[str, Any]) -> dict[str, Any]:
        operation = str(job["operation"])
        payload = job["payload"]
        marker = f"{SYNC_MARKER_PREFIX} {job['idempotency_key']}"
        page_id = str(journal.get("notion_page_id") or "")

        if operation == "REFRESH_PAGE":
            if not page_id:
                raise JournalSyncError("REFRESH_PAGE requires a registered Notion page.")
            return self._refresh_and_finish(job, journal, page_id)

        if page_id:
            current = self.notion.snapshot(page_id)
            current_hash = _digest(current)
            base_hash = str(job.get("base_remote_content_hash") or "")
            if base_hash and current_hash != base_hash:
                result = self.store.finish_write(
                    str(job["sync_job_id"]),
                    succeeded=False,
                    worker_id=self.worker_id,
                    error="Notion changed after this write was queued.",
                    conflict=True,
                )
                self._best_effort_status(journal, "Conflict")
                return result

        appended_ids: list[str] = []
        if operation == "CREATE_LOG":
            title = str(payload.get("title") or journal.get("title") or "Untitled Forge Log")
            existing = self.notion.find_by_marker(
                self.logs_data_source, "Name", title, marker
            )
            if existing is None:
                created = self.notion.create_page(
                    self.logs_data_source,
                    self._log_properties(payload, title),
                    self._new_log_blocks(payload, marker),
                )
                page_id = str(created["id"])
            else:
                page_id = str(existing["id"])
        elif operation == "PATCH_LOG":
            if not page_id:
                raise JournalSyncError("PATCH_LOG requires a registered Notion page.")
            blocks = self.notion.list_children(page_id)
            if not self.notion.contains_marker(blocks, marker):
                self.notion.set_sync_status(page_id, "Queued")
                appended = self.notion.append_children(
                    page_id, self._patch_blocks(payload, marker)
                )
                appended_ids = [str(block["id"]) for block in appended if block.get("id")]
        elif operation == "UPSERT_CANDIDATE":
            title = str(payload.get("statement") or journal.get("title") or "Untitled Candidate")
            if page_id:
                remote = self.notion.retrieve_page(page_id)
                status = _property_text((remote.get("properties") or {}).get("Status"))
                if status and status != "Candidate":
                    raise PermissionError(
                        "LAB_BOT cannot modify knowledge after reviewer lifecycle transition."
                    )
                self.notion.update_page(page_id, self._candidate_properties(payload, title))
                blocks = self.notion.list_children(page_id)
                if not self.notion.contains_marker(blocks, marker):
                    appended = self.notion.append_children(page_id, [_paragraph(marker)])
                    appended_ids = [str(block["id"]) for block in appended if block.get("id")]
            else:
                existing = self.notion.find_by_marker(
                    self.candidates_data_source, "Statement", title, marker
                )
                if existing is None:
                    created = self.notion.create_page(
                        self.candidates_data_source,
                        self._candidate_properties(payload, title),
                        [_paragraph(marker)],
                    )
                    page_id = str(created["id"])
                else:
                    page_id = str(existing["id"])
        else:
            raise JournalSyncError(f"Unsupported journal operation: {operation}")

        if operation in {"CREATE_LOG", "PATCH_LOG"}:
            self.notion.set_sync_status(page_id, "Synced")
        result = self._refresh_and_finish(job, journal, page_id)
        result["appended_block_ids"] = appended_ids
        return result

    def _refresh_and_finish(
        self, job: dict[str, Any], journal: dict[str, Any], page_id: str
    ) -> dict[str, Any]:
        remote = self.notion.retrieve_page(page_id)
        snapshot = self.notion.snapshot(page_id)
        content_hash = _digest(snapshot)
        record = self.notion.page_record(remote, str(journal["journal_kind"]))
        result = self.store.finish_write(
            str(job["sync_job_id"]),
            succeeded=True,
            worker_id=self.worker_id,
            remote_page_id=record["notion_page_id"],
            remote_url=record["notion_url"],
            remote_edited_at=record["remote_edited_at"],
            remote_content_hash=content_hash,
        )
        try:
            self.store.register_snapshot(
                record["notion_page_id"],
                record["notion_url"],
                record["title"],
                content_hash,
                remote_edited_at=record["remote_edited_at"],
                journal_kind=str(journal["journal_kind"]),
                project_system=record["project_system"],
                entry_type=record["entry_type"],
                snapshot=snapshot,
                actor_id="openclaw",
            )
        except Exception:
            LOGGER.exception(
                "Write completed but the local snapshot refresh failed journal=%s",
                journal["journal_id"],
            )
        return result

    def _best_effort_status(self, journal: dict[str, Any], status: str) -> None:
        page_id = str(journal.get("notion_page_id") or "")
        if page_id and journal.get("journal_kind") == "LOG" and status in {
            "Queued",
            "Failed",
            "Conflict",
        }:
            try:
                self.notion.set_sync_status(page_id, status)
            except Exception:
                LOGGER.exception("Unable to project sync status to Notion page=%s", page_id)

    @staticmethod
    def _log_properties(payload: dict[str, Any], title: str) -> dict[str, Any]:
        entry_type = str(payload.get("type") or "Quick Log")
        return {
            "Name": {"title": _text_objects(title)},
            "Project / System": {
                "rich_text": _text_objects(str(payload.get("project_system") or ""))
            },
            "Type": {"select": {"name": entry_type}},
            "Status": {"select": {"name": str(payload.get("status") or "Inbox")}},
            "Source": {"select": {"name": "LAB_BOT"}},
            "Sync Status": {"select": {"name": "Queued"}},
            "Date": {"date": {"start": str(payload.get("date") or datetime.now(UTC).date())}},
        }

    @staticmethod
    def _new_log_blocks(payload: dict[str, Any], marker: str) -> list[dict[str, Any]]:
        raw_note = str(payload.get("raw_note") or "")
        return [
            _heading("Raw Note"),
            _paragraph(raw_note),
            _heading("Process"),
            _paragraph(str(payload.get("process") or "")),
            _heading("Result"),
            _paragraph(str(payload.get("result") or "")),
            _heading("Verification"),
            _paragraph(str(payload.get("verification") or "")),
            _heading("Next Step"),
            _paragraph(str(payload.get("next_step") or "")),
            _heading("Candidate Lesson"),
            _paragraph(str(payload.get("candidate_lesson") or "")),
            _heading("Change Notice", level=3),
            _paragraph(
                "Created by LAB_BOT. "
                f"Reason: {payload.get('change_reason') or 'Structured journal capture.'}\n{marker}"
            ),
        ]

    @staticmethod
    def _patch_blocks(payload: dict[str, Any], marker: str) -> list[dict[str, Any]]:
        labels = (
            ("Observation", "observation"),
            ("Hypothesis", "hypothesis"),
            ("Confirmed Cause", "confirmed_cause"),
            ("Action", "action"),
            ("Result", "result"),
            ("Verification", "verification"),
            ("Next Step", "next_step"),
            ("Candidate Lesson", "candidate_lesson"),
        )
        details = [
            f"{label}: {payload[key]}"
            for label, key in labels
            if str(payload.get(key) or "").strip()
        ]
        if not details:
            details.append(str(payload.get("enrichment") or "No additional structured fields."))
        return [
            _heading("LAB_BOT Enrichment"),
            _paragraph("\n".join(details)),
            {"object": "block", "type": "divider", "divider": {}},
            _heading("Change Notice", level=3),
            _paragraph(
                f"Changed: {payload['change_summary']}\n"
                f"Reason: {payload['change_reason']}\n{marker}"
            ),
        ]

    @staticmethod
    def _candidate_properties(payload: dict[str, Any], title: str) -> dict[str, Any]:
        status = str(payload.get("status") or "Candidate")
        if status.upper() != "CANDIDATE":
            raise PermissionError("LAB_BOT may only write Candidate engineering knowledge.")
        properties: dict[str, Any] = {
            "Statement": {"title": _text_objects(title)},
            "Kind": {"select": {"name": str(payload.get("kind") or "Lesson")}},
            "Status": {"select": {"name": "Candidate"}},
            "Scope": {"rich_text": _text_objects(str(payload.get("scope") or ""))},
            "Confidence": {
                "select": {"name": str(payload.get("confidence") or "Medium")}
            },
            "Conditions / Exceptions": {
                "rich_text": _text_objects(str(payload.get("conditions_exceptions") or ""))
            },
        }
        source_logs = payload.get("source_logs") or []
        if source_logs:
            properties["Source Logs"] = {
                "relation": [{"id": str(page_id)} for page_id in source_logs]
            }
        return properties

    def drain(self, *, max_jobs: int = 100, max_notifications: int = 100) -> dict[str, int]:
        jobs = 0
        notices = 0
        while jobs < max_jobs and self.process_one() is not None:
            jobs += 1
        while notices < max_notifications and self.dispatcher.dispatch_one():
            notices += 1
        return {"jobs": jobs, "notifications": notices}

    def acceptance(self) -> dict[str, Any]:
        pages = [
            page
            for page in self.store.status(sync_status="SYNCED", limit=1000)["pages"]
            if page["journal_kind"] == "LOG" and page.get("notion_page_id")
        ]
        if not pages:
            raise RuntimeError("No synchronized Forge Log is available for reversible acceptance.")
        journal = pages[0]
        page_id = str(journal["notion_page_id"])
        before_snapshot = self.notion.snapshot(page_id)
        before_hash = _digest(before_snapshot)
        before_ids = {str(block["id"]) for block in self.notion.list_children(page_id)}
        acceptance_id = uuid4().hex
        job = self.store.queue_write(
            "PATCH_LOG",
            {
                "change_summary": "Ran the reversible Forge Journal transport acceptance.",
                "change_reason": "Verify OpenClaw delivery, remote hashing, and cleanup.",
                "enrichment": f"Temporary acceptance marker {acceptance_id}; removed after verification.",
            },
            f"forge-journal-acceptance:{acceptance_id}",
            journal_id=str(journal["journal_id"]),
            max_attempts=1,
            actor_id="forge-journal-acceptance",
        )
        result: dict[str, Any] | None = None
        added_ids: set[str] = set()
        try:
            result = self.process_one()
            if result is None or result.get("status") != "SYNCED":
                raise RuntimeError(f"Acceptance write did not synchronize: {result}")
            after_blocks = self.notion.list_children(page_id)
            added_ids = {str(block["id"]) for block in after_blocks} - before_ids
            marker = f"{SYNC_MARKER_PREFIX} {job['idempotency_key']}"
            if not added_ids or not self.notion.contains_marker(after_blocks, marker):
                raise RuntimeError("Acceptance write has no verifiable remote marker.")
        finally:
            if not added_ids:
                try:
                    added_ids = {
                        str(block["id"]) for block in self.notion.list_children(page_id)
                    } - before_ids
                except Exception:
                    LOGGER.exception("Unable to discover temporary acceptance blocks for cleanup")
            for block_id in added_ids:
                self.notion.delete_block(block_id)

        restored_snapshot = self.notion.snapshot(page_id)
        restored_hash = _digest(restored_snapshot)
        if restored_hash != before_hash:
            raise RuntimeError("Acceptance cleanup did not restore the original remote content hash.")
        remote = self.notion.retrieve_page(page_id)
        record = self.notion.page_record(remote, "LOG")
        self.notion.set_sync_status(page_id, "Synced")
        self.store.register_snapshot(
            page_id,
            record["notion_url"],
            record["title"],
            restored_hash,
            remote_edited_at=record["remote_edited_at"],
            journal_kind="LOG",
            project_system=record["project_system"],
            entry_type=record["entry_type"],
            snapshot=restored_snapshot,
            actor_id="forge-journal-acceptance",
        )
        notice = self.store.enqueue_notification(
            str(journal["journal_id"]),
            "ACCEPTANCE_PASSED",
            f"acceptance:{acceptance_id}",
            {
                "acceptance_id": acceptance_id,
                "body_restored": True,
                "sync_status": "Synced",
            },
            actor_id="forge-journal-acceptance",
        )
        self.dispatcher.dispatch_one()
        delivered = next(
            item
            for item in self.store.list_notifications(limit=1000)
            if item["notification_id"] == notice["notification_id"]
        )
        if delivered["status"] != "SENT":
            raise RuntimeError(
                "Acceptance write passed, but the LAB_BOT notification was not delivered."
            )
        return {
            "acceptance_id": acceptance_id,
            "journal_id": journal["journal_id"],
            "notion_page_id": page_id,
            "write_status": result["status"] if result else "UNKNOWN",
            "body_restored": True,
            "notification_status": delivered["status"],
        }


def _configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.disable(logging.NOTSET)
    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
        existing.close()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    LOGGER.disabled = False
    LOGGER.propagate = True


def _append_lifecycle_event(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists() and log_path.stat().st_size >= 1_000_000:
        rotated = log_path.with_suffix(log_path.suffix + ".1")
        rotated.unlink(missing_ok=True)
        log_path.replace(rotated)
    timestamp = datetime.now(UTC).isoformat()
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def build_runner(
    profile_home: Path,
    default_hermes_home: Path,
    data_dir: Path,
    logs_data_source: str,
    candidates_data_source: str,
) -> ForgeJournalRunner:
    database = data_dir / "forge-lab-bot" / "lab.db"
    headers = load_notion_connection(default_hermes_home / "config.yaml")
    store = ForgeJournalStore(database)
    resolver = HermesRouteResolver(
        [profile_home / "state.db", default_hermes_home / "state.db"],
        explicit_target=os.environ.get("FORGE_JOURNAL_NOTIFY_TO", ""),
    )
    hermes = default_hermes_home / "hermes-agent" / "venv" / "Scripts" / "hermes.exe"
    dispatcher = ForgeJournalNotificationDispatcher(store, hermes, profile_home, resolver)
    return ForgeJournalRunner(
        store,
        NotionJournalClient(headers),
        dispatcher,
        logs_data_source=logs_data_source,
        candidates_data_source=candidates_data_source,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Forge Journal OpenClaw synchronization runner")
    parser.add_argument("--profile-home", type=Path, required=True)
    parser.add_argument("--default-hermes-home", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--logs-data-source", default=DEFAULT_LOGS_DATA_SOURCE)
    parser.add_argument("--candidates-data-source", default=DEFAULT_CANDIDATES_DATA_SOURCE)
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--reconcile-seconds", type=int, default=900)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--acceptance", action="store_true")
    args = parser.parse_args()
    lifecycle_log = args.data_dir / "logs" / "forge-journal-runner-lifecycle.log"
    _append_lifecycle_event(lifecycle_log, "python-start")
    _configure_logging(args.data_dir / "logs" / "forge-journal-runner.log")
    LOGGER.info(
        "Forge Journal runner starting once=%s acceptance=%s poll_seconds=%s reconcile_seconds=%s",
        args.once,
        args.acceptance,
        args.poll_seconds,
        args.reconcile_seconds,
    )
    runner = build_runner(
        args.profile_home,
        args.default_hermes_home,
        args.data_dir,
        args.logs_data_source,
        args.candidates_data_source,
    )
    with runner.store.connect() as connection:
        queued_at_start = connection.execute(
            "SELECT COUNT(*) FROM forge_journal_sync_jobs WHERE status = 'QUEUED'"
        ).fetchone()[0]
        pages_at_start = connection.execute(
            "SELECT COUNT(*) FROM forge_journal_pages"
        ).fetchone()[0]
        sqlite_path = connection.execute("PRAGMA database_list").fetchone()[2]
    database_stat = runner.store.database_path.stat()
    _append_lifecycle_event(
        lifecycle_log,
        "runner-built "
        f"database={runner.store.database_path} sqlite_path={sqlite_path} "
        f"size={database_stat.st_size} mtime_ns={database_stat.st_mtime_ns} "
        f"pages={pages_at_start} queued={queued_at_start}",
    )
    lock_path = args.data_dir / "locks" / "forge-journal-runner.lock"
    with _RunnerInstanceLock(lock_path):
        _append_lifecycle_event(lifecycle_log, "lock-acquired")
        if args.acceptance:
            print(json.dumps(runner.acceptance(), sort_keys=True))
            return
        if args.once:
            output = {**runner.drain(), "reconciliation": runner.reconcile()}
            _append_lifecycle_event(
                lifecycle_log,
                f"scheduled-once-complete result={_canonical_json(output)}",
            )
            print(json.dumps(output, sort_keys=True))
            return
        reconcile_interval = max(300, int(args.reconcile_seconds))
        poll_interval = max(5, int(args.poll_seconds))
        next_reconcile = 0.0
        first_iteration = True
        while True:
            if first_iteration:
                _append_lifecycle_event(lifecycle_log, "queue-drain-start")
            drain_result: dict[str, int] | None = None
            try:
                drain_result = runner.drain(max_jobs=20, max_notifications=20)
            except Exception:
                LOGGER.exception("Forge Journal queue iteration failed")
            if first_iteration:
                _append_lifecycle_event(
                    lifecycle_log,
                    f"queue-drain-complete result={_canonical_json(drain_result)}",
                )
            reconciliation_result: dict[str, int] | None = None
            if time.monotonic() >= next_reconcile:
                next_reconcile = time.monotonic() + reconcile_interval
                try:
                    reconciliation_result = runner.reconcile()
                    LOGGER.info("Reconciliation result: %s", reconciliation_result)
                except Exception:
                    LOGGER.exception("Forge Journal reconciliation failed")
            if first_iteration:
                _append_lifecycle_event(
                    lifecycle_log,
                    "reconciliation-complete "
                    f"result={_canonical_json(reconciliation_result)}",
                )
                first_iteration = False
            time.sleep(poll_interval)


if __name__ == "__main__":
    main()
