"""Durable, source-bound discussion and annotation; no scientific write actions."""
from __future__ import annotations

import json
import sqlite3
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import ConfigDict, Field

from . import studio_discussions as studio_chat
from .fieldkg import digest
from .model_gateway import CONTRACTS, UnlimitedLLMGateway
from .models import StrictModel, new_id
from .research_context import (
    DiscussionTarget,
    freeze_quote,
    resolve_context,
    scope_key,
    target_data,
)
from .research_workspace import WorkspaceError

SCHEMA = """
CREATE TABLE IF NOT EXISTS research_discussion_requests (
 request_id TEXT PRIMARY KEY,operation TEXT NOT NULL,request_json TEXT NOT NULL,
 scope_key TEXT NOT NULL,object_id TEXT NOT NULL,created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_discussion_messages (
 seq INTEGER PRIMARY KEY AUTOINCREMENT,message_id TEXT NOT NULL UNIQUE,
 request_id TEXT NOT NULL REFERENCES research_discussion_requests(request_id),
 reply_to TEXT REFERENCES research_discussion_messages(message_id),actor TEXT NOT NULL,
 scope_key TEXT NOT NULL,context_json TEXT NOT NULL,quote_json TEXT NOT NULL,
 additional_sources_json TEXT NOT NULL,content TEXT NOT NULL,status TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS research_discussion_scope ON research_discussion_messages(scope_key,seq);
CREATE TABLE IF NOT EXISTS research_discussion_annotations (
 seq INTEGER PRIMARY KEY AUTOINCREMENT,annotation_id TEXT NOT NULL UNIQUE,
 request_id TEXT NOT NULL REFERENCES research_discussion_requests(request_id),
 scope_key TEXT NOT NULL,context_json TEXT NOT NULL,quote_json TEXT NOT NULL,
 comment TEXT NOT NULL,created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_discussion_jobs (
 request_id TEXT PRIMARY KEY REFERENCES research_discussion_requests(request_id),
 author_message_id TEXT NOT NULL REFERENCES research_discussion_messages(message_id),
 status TEXT NOT NULL,input_json TEXT NOT NULL,input_sha256 TEXT NOT NULL,
 requested_contract_json TEXT NOT NULL,response_json TEXT,model_contract_json TEXT,
 raw_response_json TEXT,error_json TEXT,started_at TEXT,completed_at TEXT
);
"""


class QuoteInput(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    text: str = Field(default="", max_length=50000)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)
    offset_unit: Literal["utf16"] | None = None
    annotation: str = Field(default="", max_length=8000)


class SourceSelection(StrictModel):
    target: DiscussionTarget
    expected_context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    quote: QuoteInput | None = None
    history_message_id: str | None = None
    history_source_index: int = Field(default=0, ge=0, le=8)


class DiscussionInput(StrictModel):
    request_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{8,128}$")
    content: str = Field(min_length=1, max_length=12000)
    source: SourceSelection
    additional_sources: list[SourceSelection] = Field(default_factory=list, max_length=8)
    allow_cross_scope: bool = False
    parent_message_id: str | None = Field(default=None, min_length=1, max_length=128)


class AnnotationInput(StrictModel):
    request_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{8,128}$")
    source: SourceSelection
    comment: str = Field(min_length=1, max_length=8000)


class DiscussionHistoryRequest(StrictModel):
    target: DiscussionTarget
    before: int | None = Field(default=None, ge=1)
    annotations_before: int | None = Field(default=None, ge=1)
    limit: int = Field(default=50, ge=1, le=200)
    current_object_only: bool = False


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _has_schema(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_discussion_requests'").fetchone() is not None


def _message(row: sqlite3.Row) -> dict:
    data = dict(row)
    for key in ["context_json", "quote_json", "additional_sources_json"]:
        data[key.removesuffix("_json")] = json.loads(data.pop(key))
    for source in [{"context": data["context"], "quote": data["quote"]}, *data["additional_sources"]]:
        _verify_source(source)
    return data


def _verify_source(source: dict) -> None:
    try:
        context, quote = source["context"], source["quote"]
        if digest({key: value for key, value in context.items() if key != "context_sha256"}) != context["context_sha256"]:
            raise ValueError("Saved context digest differs")
        supplied = {key: quote[key] for key in ["text", "start", "end", "offset_unit", "annotation"] if key in quote}
        if freeze_quote(context, supplied) != quote:
            raise ValueError("Saved quote differs from its source")
    except (ValueError, TypeError, KeyError) as exc:
        raise WorkspaceError(410, "The saved historical source or selection is inconsistent") from exc


def _input_sources(model_input: dict):
    yield model_input["source"]
    yield from model_input["additional_sources"]
    for message in model_input.get("conversation", []):
        yield {"context": message["context"], "quote": message["quote"]}
        yield from message["additional_sources"]


def _verified_message(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    """Match historical words and parent links to the immutable call receipt."""
    try:
        return _checked_message(conn, row)
    except (ValueError, TypeError, KeyError) as exc:
        raise WorkspaceError(410, "The saved historical discussion record is inconsistent") from exc


def _checked_message(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    message = _message(row)
    job = conn.execute("SELECT * FROM research_discussion_jobs WHERE request_id=?", (message["request_id"],)).fetchone()
    if job is None:
        raise WorkspaceError(410, "The historical discussion call is unavailable")
    model_input = json.loads(job["input_json"])
    if digest(model_input) != job["input_sha256"]:
        raise WorkspaceError(410, "The saved model input is inconsistent")
    for source in _input_sources(model_input):
        _verify_source(source)
    primary = model_input["source"]
    request = conn.execute("SELECT * FROM research_discussion_requests WHERE request_id=?", (message["request_id"],)).fetchone()
    if request is None or request["scope_key"] != primary["context"]["scope_key"] or message["scope_key"] != primary["context"]["scope_key"] or request["object_id"] != job["author_message_id"]:
        raise WorkspaceError(410, "The historical discussion owner differs from its call")
    expected = (primary["context"], primary["quote"], model_input["additional_sources"])
    if (message["context"], message["quote"], message["additional_sources"]) != expected:
        raise WorkspaceError(410, "The historical discussion source differs from its call")
    if message["actor"] == "AUTHOR":
        conversation = model_input.get("conversation", [])
        parent = conversation[-1]["message_id"] if conversation else None
        if message["message_id"] != job["author_message_id"] or message["content"] != model_input["question"] or message["reply_to"] != parent:
            raise WorkspaceError(410, "The historical question or parent differs from its call")
        statuses = {"COMPLETE": "ANSWERED", "FAILED": "AGENT_FAILED", "QUEUED": "QUEUED", "RUNNING": "RUNNING"}
        if message["status"] != statuses.get(job["status"]):
            raise WorkspaceError(410, "The historical question status differs from its call")
    elif message["actor"] == "AGENT":
        response = json.loads(job["response_json"]) if job["response_json"] else {}
        answer = response.get("answer")
        if job["status"] != "COMPLETE" or message["status"] != "DISCUSSION" or message["reply_to"] != job["author_message_id"] or not isinstance(answer, str) or message["content"] != answer.strip():
            raise WorkspaceError(410, "The historical reply differs from its call")
    else:
        raise WorkspaceError(410, "The historical discussion role is inconsistent")
    message["call_record"] = {
        "status": job["status"], "input_sha256": job["input_sha256"],
        "model_contract": json.loads(job["model_contract_json"]) if job["model_contract_json"] else None,
        "error": json.loads(job["error_json"]) if job["error_json"] else None,
    }
    return message


class TracedResearchGateway(UnlimitedLLMGateway):
    """Keep the actual HTTP answer even when JSON parsing subsequently fails."""
    def __init__(self, root: Path):
        super().__init__(root)
        self.trace = threading.local()

    def _request_http(self, tier: str, prompt: str) -> tuple[str, dict[str, Any]]:
        text, metadata = super()._request_http(tier, prompt)
        self.trace.value = {"text": text, "metadata": metadata}
        return text, metadata


class ResearchDiscussionService:
    def __init__(self, root: Path, gateway: Any | None = None):
        self.root = Path(root).resolve()
        self.db_path = self.root / "data/catalog.db"
        self.gateway = gateway
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="research-discussion")
        self._futures: dict[str, Future] = {}
        self._lock = threading.Lock()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)

    @contextmanager
    def _read(self):
        if not self.db_path.is_file():
            raise WorkspaceError(503, "Catalog database is unavailable")
        conn = sqlite3.connect(f"{self.db_path.as_uri()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN")
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _write(self):
        if not self.db_path.is_file():
            raise WorkspaceError(503, "Catalog database is unavailable")
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("BEGIN IMMEDIATE")
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    conn.execute(statement)
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def context(self, target: DiscussionTarget) -> dict:
        with self._read() as conn:
            return resolve_context(conn, target)

    def _selection(self, conn: sqlite3.Connection, selected: SourceSelection) -> dict:
        if selected.history_message_id:
            row = conn.execute("SELECT * FROM research_discussion_messages WHERE message_id=?", (selected.history_message_id,)).fetchone() if _has_schema(conn) else None
            if row is None:
                raise WorkspaceError(404, "This historical discussion does not belong to this scope")
            message = _verified_message(conn, row)
            selections = [{"context": message["context"], "quote": message["quote"]}, *message["additional_sources"]]
            if selected.history_source_index >= len(selections):
                raise WorkspaceError(404, "This historical source is unavailable")
            context = selections[selected.history_source_index]["context"]
            if context["target"] != target_data(selected.target):
                raise WorkspaceError(404, "The historical source points to a different object")
            if digest({key: value for key, value in context.items() if key != "context_sha256"}) != context["context_sha256"]:
                raise WorkspaceError(410, "The saved historical context is inconsistent")
        else:
            context = resolve_context(conn, selected.target)
        if context["context_sha256"] != selected.expected_context_sha256:
            raise WorkspaceError(409, "The object or source changed. Compare the current version before sending.")
        quote = selected.quote.model_dump(exclude_none=True) if selected.quote else None
        return {"context": context, "quote": freeze_quote(context, quote)}

    def _conversation(self, conn: sqlite3.Connection, parent: str | None, owner: str) -> list[dict]:
        history, seen = [], set()
        while parent:
            if parent in seen:
                raise WorkspaceError(410, "The historical discussion contains a parent cycle")
            if len(history) >= 64:
                raise WorkspaceError(422, "This discussion is too long. Start a new discussion; no history was truncated.")
            seen.add(parent)
            row = conn.execute("SELECT * FROM research_discussion_messages WHERE message_id=? AND scope_key=?", (parent, owner)).fetchone()
            if row is None:
                raise WorkspaceError(404, "This parent discussion does not belong to this scope")
            message = _verified_message(conn, row)
            if not history and not (message["actor"] == "AGENT" and message["call_record"]["status"] == "COMPLETE" or message["actor"] == "AUTHOR" and message["call_record"]["status"] == "FAILED"):
                raise WorkspaceError(409, "Wait for the original reply or failure before continuing this discussion")
            history.append({key: message[key] for key in ["message_id", "request_id", "reply_to", "actor", "content", "context", "quote", "additional_sources", "call_record"]})
            parent = message["reply_to"]
        history.reverse()
        return history

    def annotate(self, payload: AnnotationInput) -> dict:
        if not payload.comment.strip():
            raise WorkspaceError(422, "Annotation is empty")
        request_data = payload.model_dump(mode="json")
        request_data["source"]["target"] = target_data(payload.source.target)
        request_json = _json(request_data)
        with self._write() as conn:
            prior = conn.execute("SELECT * FROM research_discussion_requests WHERE request_id=?", (payload.request_id,)).fetchone()
            if prior:
                if prior["operation"] != "ANNOTATE" or prior["request_json"] != request_json:
                    raise WorkspaceError(409, "This request ID belongs to another operation")
                row = conn.execute("SELECT * FROM research_discussion_annotations WHERE request_id=?", (payload.request_id,)).fetchone()
                return self._annotation(row)
            selection = self._selection(conn, payload.source)
            annotation_id, now = new_id("research_annotation"), _now()
            conn.execute("INSERT INTO research_discussion_requests VALUES(?,?,?,?,?,?)", (payload.request_id, "ANNOTATE", request_json, scope_key(payload.source.target), annotation_id, now))
            conn.execute("INSERT INTO research_discussion_annotations(annotation_id,request_id,scope_key,context_json,quote_json,comment,created_at) VALUES(?,?,?,?,?,?,?)", (annotation_id, payload.request_id, scope_key(payload.source.target), _json(selection["context"]), _json(selection["quote"]), payload.comment.strip(), now))
            return self._annotation(conn.execute("SELECT * FROM research_discussion_annotations WHERE annotation_id=?", (annotation_id,)).fetchone())

    @staticmethod
    def _annotation(row: sqlite3.Row) -> dict:
        result = dict(row)
        for name in ["context_json", "quote_json"]:
            result[name.removesuffix("_json")] = json.loads(result.pop(name))
        _verify_source(result)
        return result

    def submit(self, payload: DiscussionInput) -> dict:
        if not payload.content.strip():
            raise WorkspaceError(422, "Message is empty")
        request_data = payload.model_dump(mode="json")
        request_data["source"]["target"] = target_data(payload.source.target)
        for item, selected in zip(request_data["additional_sources"], payload.additional_sources):
            item["target"] = target_data(selected.target)
        # The earlier fixed-source protocol had no parent field. Its exact retry
        # still denotes the same operation when the optional parent is absent.
        if payload.parent_message_id is None:
            request_data.pop("parent_message_id")
        request_json = _json(request_data)
        with self._write() as conn:
            prior = conn.execute("SELECT * FROM research_discussion_requests WHERE request_id=?", (payload.request_id,)).fetchone()
            if prior:
                if prior["operation"] != "DISCUSS" or prior["request_json"] != request_json:
                    raise WorkspaceError(409, "This request ID belongs to a different discussion")
            else:
                primary = self._selection(conn, payload.source)
                extra = [self._selection(conn, item) for item in payload.additional_sources]
                conversation = self._conversation(conn, payload.parent_message_id, primary["context"]["scope_key"])
                model_input = {"question": payload.content.strip(), "source": primary, "additional_sources": extra, "conversation": conversation, "constraint": "Ordinary discussion only; no scientific or document changes."}
                if not payload.allow_cross_scope and any(item["context"]["scope_key"] != primary["context"]["scope_key"] for item in _input_sources(model_input)):
                    raise WorkspaceError(422, "Adding another scope requires an explicit cross-scope selection")
                is_studio = payload.source.target.module == "STUDIO"
                contract = CONTRACTS["writing_chat" if is_studio else "research_chat"]
                actual_input = model_input
                if is_studio:
                    actual_input = studio_chat.prepare_payload(conn, model_input)
                    model_input.update(writing_payload=actual_input, studio_call_id=new_id("model_call"))
                if max(1, len(_json(actual_input)) // 4) > contract.max_input_tokens:
                    raise WorkspaceError(422, "This fixed object exceeds the discussion budget. Select a narrower original source object.")
                message_id, now = new_id("research_message"), _now()
                conn.execute("INSERT INTO research_discussion_requests VALUES(?,?,?,?,?,?)", (payload.request_id, "DISCUSS", request_json, primary["context"]["scope_key"], message_id, now))
                conn.execute("INSERT INTO research_discussion_messages(message_id,request_id,reply_to,actor,scope_key,context_json,quote_json,additional_sources_json,content,status,created_at) VALUES(?,?,?,'AUTHOR',?,?,?,?,?,'QUEUED',?)", (message_id, payload.request_id, payload.parent_message_id, primary["context"]["scope_key"], _json(primary["context"]), _json(primary["quote"]), _json(extra), payload.content.strip(), now))
                requested = {"task": contract.name, "tier": contract.tier, "prompt_version": contract.version, "instruction": contract.instruction, "max_input_tokens": contract.max_input_tokens}
                conn.execute("INSERT INTO research_discussion_jobs(request_id,author_message_id,status,input_json,input_sha256,requested_contract_json) VALUES(?,?,'QUEUED',?,?,?)", (payload.request_id, message_id, _json(model_input), digest(model_input), _json(requested)))
                if is_studio:
                    studio_chat.author_projection(conn, model_input, payload.request_id, message_id, payload.parent_message_id, now)
        self._schedule(payload.request_id)
        return self.request(payload.request_id, scope_key(payload.source.target))

    def _schedule(self, request_id: str) -> None:
        with self._lock:
            if request_id not in self._futures or self._futures[request_id].done():
                self._futures[request_id] = self._executor.submit(self._answer, request_id)

    def _answer(self, request_id: str) -> None:
        with self._write() as conn:
            job = conn.execute("SELECT * FROM research_discussion_jobs WHERE request_id=?", (request_id,)).fetchone()
            if job is None or job["status"] != "QUEUED":
                return
            started_at = _now()
            conn.execute("UPDATE research_discussion_jobs SET status='RUNNING',started_at=? WHERE request_id=? AND status='QUEUED'", (started_at, request_id))
            conn.execute("UPDATE research_discussion_messages SET status='RUNNING' WHERE message_id=?", (job["author_message_id"],))
            model_input = json.loads(job["input_json"])
            if "writing_payload" in model_input:
                conn.execute("UPDATE studio_chat_messages SET status='RUNNING' WHERE message_id=?", (job["author_message_id"],))
        response = None
        actual_contract = None
        trace = None
        try:
            if digest(model_input) != job["input_sha256"]:
                raise ValueError("The saved model input is inconsistent")
            for source in _input_sources(model_input):
                _verify_source(source)
            if self.gateway is None:
                with self._lock:
                    if self.gateway is None:
                        self.gateway = TracedResearchGateway(self.root)
            trace = getattr(self.gateway, "trace", None)
            if trace is not None:
                trace.value = None
            is_studio = "writing_payload" in model_input
            response = self.gateway.analyze("writing_chat" if is_studio else "research_chat", model_input["writing_payload"] if is_studio else model_input)
            actual_contract = response.get("_contract") if isinstance(response, dict) else None
            if not isinstance(response, dict) or not isinstance(response.get("answer"), str) or not response["answer"].strip():
                raise ValueError("The model returned no textual answer")
            source_ids = response.get("source_ids", [])
            known_ids = {item["context"]["context_sha256"] for item in _input_sources(model_input)}
            if not isinstance(source_ids, list) or any(not isinstance(value, str) or value not in known_ids for value in source_ids):
                raise ValueError("The answer cites a source not supplied in this fixed discussion")
            if is_studio:
                response = {**response, "_validated_studio_suggestions": studio_chat.validated_suggestions(response, model_input["writing_payload"])}
            with self._write() as conn:
                author = conn.execute("SELECT * FROM research_discussion_messages WHERE message_id=?", (job["author_message_id"],)).fetchone()
                agent_id, completed_at = new_id("research_message"), _now()
                conn.execute("INSERT INTO research_discussion_messages(message_id,request_id,reply_to,actor,scope_key,context_json,quote_json,additional_sources_json,content,status,created_at) VALUES(?,?,?,'AGENT',?,?,?,?,?,'DISCUSSION',?)", (agent_id, request_id, author["message_id"], author["scope_key"], author["context_json"], author["quote_json"], author["additional_sources_json"], response["answer"].strip(), completed_at))
                if is_studio:
                    studio_chat.call_projection(conn, model_input, author["message_id"], response, actual_contract, None, started_at, completed_at)
                    studio_chat.agent_projection(conn, model_input, request_id, author["message_id"], agent_id, response, completed_at)
                conn.execute("UPDATE research_discussion_jobs SET status='COMPLETE',response_json=?,model_contract_json=?,raw_response_json=?,completed_at=? WHERE request_id=?", (_json(response), _json(actual_contract) if actual_contract else None, _json(getattr(trace, "value", None)) if trace and getattr(trace, "value", None) else None, _now(), request_id))
                conn.execute("UPDATE research_discussion_messages SET status='ANSWERED' WHERE message_id=?", (author["message_id"],))
        except Exception as exc:  # noqa: BLE001 - durable worker failures must retain their actual cause
            with self._write() as conn:
                error, completed_at = {"type": type(exc).__name__, "detail": str(exc)[:2000]}, _now()
                conn.execute("UPDATE research_discussion_jobs SET status='FAILED',response_json=?,model_contract_json=?,raw_response_json=?,error_json=?,completed_at=? WHERE request_id=?", (_json(response) if response is not None else None, _json(actual_contract) if actual_contract else None, _json(getattr(trace, "value", None)) if trace and getattr(trace, "value", None) else None, _json(error), completed_at, request_id))
                conn.execute("UPDATE research_discussion_messages SET status='AGENT_FAILED' WHERE message_id=?", (job["author_message_id"],))
                if "writing_payload" in model_input:
                    studio_chat.call_projection(conn, model_input, job["author_message_id"], response, actual_contract, error, started_at, completed_at)
                    conn.execute("UPDATE studio_chat_messages SET status='AGENT_FAILED' WHERE message_id=?", (job["author_message_id"],))

    def request(self, request_id: str, owner: str) -> dict:
        with self._read() as conn:
            prior = conn.execute("SELECT * FROM research_discussion_requests WHERE request_id=? AND scope_key=?", (request_id, owner)).fetchone() if _has_schema(conn) else None
            if prior is None or prior["operation"] != "DISCUSS":
                raise WorkspaceError(404, "This discussion request does not belong to this scope")
            job = dict(conn.execute("SELECT * FROM research_discussion_jobs WHERE request_id=?", (request_id,)).fetchone())
            for key in ["input_json", "requested_contract_json", "response_json", "model_contract_json", "raw_response_json", "error_json"]:
                value = job.pop(key)
                job[key.removesuffix("_json")] = json.loads(value) if value else None
            if digest(job["input"]) != job["input_sha256"]:
                raise WorkspaceError(410, "The saved model input is inconsistent")
            for source in _input_sources(job["input"]):
                _verify_source(source)
            messages = [_verified_message(conn, row) for row in conn.execute("SELECT * FROM research_discussion_messages WHERE request_id=? ORDER BY seq", (request_id,))]
            projected = studio_chat.studio_messages(conn, request_id) if job["input"]["source"]["context"]["target"]["module"] == "STUDIO" else []
        with self._lock:
            future = self._futures.get(request_id)
            live = future is not None and not future.done()
        return {"request_id": request_id, "job": job, "messages": messages, "studio_messages": projected, "execution_observation": "LIVE_WORKER" if live else "NOT_OBSERVED_IN_THIS_PROCESS"}

    def history(self, target: DiscussionTarget, before: int | None = None, limit: int = 50, current_object_only: bool = False, annotations_before: int | None = None) -> dict:
        if not 1 <= limit <= 200:
            raise WorkspaceError(422, "Invalid history page size")
        with self._read() as conn:
            # Require the owning scope, but retain discussions of deleted objects.
            if target.module == "CATALOG":
                _require_scope = conn.execute("SELECT 1 FROM papers WHERE paper_id=?", (target.paper_id,)).fetchone()
            elif target.module == "STUDIO":
                _require_scope = conn.execute("SELECT 1 FROM manuscripts WHERE manuscript_id=?", (target.manuscript_id,)).fetchone()
            else:
                table, column, owner = ("research_fields", "field_id", target.field_id) if target.module == "FIELDKG" else ("research_tracks", "track_id", target.track_id)
                _require_scope = conn.execute(f"SELECT 1 FROM {table} WHERE {column}=?", (owner,)).fetchone()
            if not _require_scope:
                raise WorkspaceError(404, "This discussion scope is unavailable")
            if not _has_schema(conn):
                return {"messages": [], "annotations": [], "has_more": False, "next_before": None, "annotations_has_more": False, "next_annotations_before": None}
            filters = "scope_key=?"
            params: list[Any] = [scope_key(target)]
            if before is not None:
                filters += " AND seq<?"
                params.append(before)
            if current_object_only:
                filters += " AND json_extract(context_json,'$.target.object_kind')=? AND json_extract(context_json,'$.target.object_id')=?"
                params.extend([target.object_kind, target.object_id])
                for key in ["part", "page_number", "snapshot_id", "document_revision", "generated_version_id"]:
                    filters += f" AND json_extract(context_json,'$.target.{key}') IS ?"
                    params.append(getattr(target, key))
            records = conn.execute(f"SELECT * FROM research_discussion_messages WHERE {filters} ORDER BY seq DESC LIMIT ?", (*params, limit + 1)).fetchall()
            more = len(records) > limit
            messages = [_verified_message(conn, row) for row in records[:limit]]
            annotation_filter, annotation_params = "scope_key=?", [scope_key(target)]
            if annotations_before is not None:
                annotation_filter += " AND seq<?"
                annotation_params.append(annotations_before)
            if current_object_only:
                annotation_filter += " AND json_extract(context_json,'$.target.object_kind')=? AND json_extract(context_json,'$.target.object_id')=?"
                annotation_params.extend([target.object_kind, target.object_id])
                for key in ["part", "page_number", "snapshot_id", "document_revision", "generated_version_id"]:
                    annotation_filter += f" AND json_extract(context_json,'$.target.{key}') IS ?"
                    annotation_params.append(getattr(target, key))
            records = conn.execute(f"SELECT * FROM research_discussion_annotations WHERE {annotation_filter} ORDER BY seq DESC LIMIT ?", (*annotation_params, limit + 1)).fetchall()
            annotation_more = len(records) > limit
            annotations = [self._annotation(row) for row in records[:limit]]
            return {"messages": messages, "annotations": annotations, "has_more": more, "next_before": messages[-1]["seq"] if more else None, "annotations_has_more": annotation_more, "next_annotations_before": annotations[-1]["seq"] if annotation_more else None}

    def historical_context(self, owner: str, message_id: str) -> dict:
        with self._read() as conn:
            row = conn.execute("SELECT * FROM research_discussion_messages WHERE message_id=? AND scope_key=?", (message_id, owner)).fetchone() if _has_schema(conn) else None
            if row is None:
                raise WorkspaceError(404, "This historical discussion does not belong to this scope")
            message = _verified_message(conn, row)
            observation = []
            for item in [{"context": message["context"], "quote": message["quote"]}, *message["additional_sources"]]:
                if digest({key: value for key, value in item["context"].items() if key != "context_sha256"}) != item["context"]["context_sha256"]:
                    raise WorkspaceError(410, "The saved historical context is inconsistent")
                try:
                    latest = resolve_context(conn, DiscussionTarget.model_validate(item["context"]["target"]))
                    state = "CURRENT" if latest["context_sha256"] == item["context"]["context_sha256"] else "OLD_VERSION"
                    target = item["context"]["target"]
                    if target["module"] == "STUDIO":
                        current = conn.execute("SELECT revision,active_generated_version_id FROM studio_documents WHERE manuscript_id=?", (target["manuscript_id"],)).fetchone()
                        if current is None:
                            state = "SOURCE_UNAVAILABLE"
                        elif target["object_kind"].startswith("generated_"):
                            original_revision = item["context"]["record"]["generated"]["input_revision"]
                            if current["active_generated_version_id"] != target["generated_version_id"] or original_revision is not None and current["revision"] != original_revision:
                                state = "OLD_VERSION"
                        else:
                            current_target = {**target, "document_revision": current["revision"]}
                            latest = resolve_context(conn, DiscussionTarget.model_validate(current_target))
                            state = "CURRENT" if latest["context_sha256"] == item["context"]["context_sha256"] else "OLD_VERSION"
                except (WorkspaceError, ValueError, TypeError, sqlite3.Error):
                    state = "SOURCE_UNAVAILABLE"
                observation.append({**item, "current_source_state": state})
            conversation = self._conversation(conn, message_id, owner) if message["actor"] == "AGENT" or message["call_record"]["status"] == "FAILED" else []
            return {"message": message, "sources": observation, "conversation": conversation}
