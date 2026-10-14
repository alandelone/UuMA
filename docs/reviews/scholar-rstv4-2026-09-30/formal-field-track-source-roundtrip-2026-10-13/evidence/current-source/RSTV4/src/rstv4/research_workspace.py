"""Explicit, atomic metadata edits for the global research overview.

These operations never approve a candidate, adopt a snapshot, change scientific
scope, or advance a research milestone. Request receipts are immutable.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from .database import WORKSPACE_ACTION_SCHEMA
from .models import (
    FieldInput,
    StrictModel,
    TrackFirstTopicInput,
    TrackFirstTrackInput,
    new_id,
)


class ActionRequest(StrictModel):
    request_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")


class CreateField(ActionRequest, FieldInput):
    operation: Literal["CREATE_FIELD"]


class EditField(ActionRequest, FieldInput):
    operation: Literal["EDIT_FIELD"]
    field_id: str
    expected_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class CreateTopic(ActionRequest, TrackFirstTopicInput):
    operation: Literal["CREATE_TOPIC"]


class LinkTopic(ActionRequest):
    operation: Literal["LINK_TOPIC"]
    field_id: str
    topic_id: str


class EditTopic(ActionRequest, FieldInput):
    operation: Literal["EDIT_TOPIC"]
    field_id: str
    topic_id: str
    expected_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class CreateTrack(ActionRequest, TrackFirstTrackInput):
    operation: Literal["CREATE_TRACK"]


class EditTrack(ActionRequest):
    operation: Literal["EDIT_TRACK"]
    field_id: str
    track_id: str
    title: str = Field(min_length=1, max_length=500)
    expected_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


WorkspaceAction = Annotated[
    CreateField | EditField | CreateTopic | LinkTopic | EditTopic | CreateTrack | EditTrack,
    Field(discriminator="operation"),
]


class WorkspaceError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(message)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def metadata_digest(conn: sqlite3.Connection, kind: str, row: dict[str, Any]) -> str:
    """Detect external edits too; returning to an old name cannot revive a draft."""
    object_id = row[f"{kind}_id"]
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_workspace_actions'"
    ).fetchone()
    last_seq = 0
    if exists:
        last_seq = conn.execute(
            "SELECT COALESCE(MAX(action_seq),0) FROM research_workspace_actions "
            "WHERE object_type=? AND object_id=?", (kind, object_id),
        ).fetchone()[0]
    return hashlib.sha256(_json({"record": row, "metadata_sequence": last_seq}).encode()).hexdigest()


def _require(conn: sqlite3.Connection, kind: str, object_id: str) -> dict[str, Any]:
    table = {"field": "research_fields", "topic": "topics", "track": "research_tracks"}[kind]
    row = conn.execute(f"SELECT * FROM {table} WHERE {kind}_id=?", (object_id,)).fetchone()
    if row is None:
        raise WorkspaceError(404, f"{kind} does not exist")
    return dict(row)


def _topic_in_field(conn: sqlite3.Connection, field_id: str, topic_id: str) -> None:
    _require(conn, "field", field_id)
    _require(conn, "topic", topic_id)
    if not conn.execute(
        "SELECT 1 FROM field_topics WHERE field_id=? AND topic_id=?", (field_id, topic_id),
    ).fetchone():
        raise WorkspaceError(409, "Topic is not explicitly associated with this Field")


def _check_digest(conn: sqlite3.Connection, kind: str, row: dict[str, Any], expected: str) -> None:
    if metadata_digest(conn, kind, row) != expected:
        raise WorkspaceError(409, "This object changed. Refresh and compare before editing again.")


def _unique_name(conn: sqlite3.Connection, kind: str, name: str, object_id: str = "") -> str:
    normalized = " ".join(name.casefold().split())
    table = "research_fields" if kind == "field" else "topics"
    if conn.execute(
        f"SELECT 1 FROM {table} WHERE normalized_name=? AND {kind}_id!=?",
        (normalized, object_id),
    ).fetchone():
        message = "A Field with this name already exists"
        if kind == "topic":
            message = "A Topic with this name already exists. Explicitly link the existing Topic."
        raise WorkspaceError(409, message)
    return normalized


def record_workspace_action(path: Path, action: WorkspaceAction) -> dict[str, Any]:
    if not path.is_file():
        raise WorkspaceError(503, "Catalog database is unavailable")
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        # Install only this additive table on explicit write, never on a GET.
        conn.execute("BEGIN IMMEDIATE")
        for statement in WORKSPACE_ACTION_SCHEMA.split(";"):
            if statement.strip():
                conn.execute(statement)
        request_json = _json(action.model_dump(mode="json"))
        previous = conn.execute(
            "SELECT request_json,result_json FROM research_workspace_actions WHERE request_id=?",
            (action.request_id,),
        ).fetchone()
        if previous:
            if previous["request_json"] != request_json:
                raise WorkspaceError(409, "This request ID was already used for a different action")
            conn.rollback()
            return json.loads(previous["result_json"])

        now = datetime.now(UTC).isoformat()
        operation = action.operation
        if isinstance(action, (CreateField, EditField)):
            kind = "field"
            object_id = action.field_id if isinstance(action, EditField) else new_id(kind)
            if isinstance(action, EditField):
                before = _require(conn, kind, object_id)
                _check_digest(conn, kind, before, action.expected_digest)
            normalized = _unique_name(conn, kind, action.name, object_id)
            if isinstance(action, CreateField):
                conn.execute(
                    "INSERT INTO research_fields VALUES(?,?,?,?,?,?)",
                    (object_id, normalized, action.name, action.description, now, now),
                )
            else:
                conn.execute(
                    "UPDATE research_fields SET normalized_name=?,name=?,description=?,updated_at=? "
                    "WHERE field_id=?",
                    (normalized, action.name, action.description, now, object_id),
                )
        elif isinstance(action, (CreateTopic, EditTopic, LinkTopic)):
            kind = "topic"
            _require(conn, "field", action.field_id)
            object_id = new_id(kind) if isinstance(action, CreateTopic) else action.topic_id
            if isinstance(action, (EditTopic, LinkTopic)):
                before = _require(conn, kind, object_id)
            if isinstance(action, EditTopic):
                _topic_in_field(conn, action.field_id, object_id)
                _check_digest(conn, kind, before, action.expected_digest)
            if not isinstance(action, LinkTopic):
                normalized = _unique_name(conn, kind, action.name, object_id)
                if isinstance(action, CreateTopic):
                    conn.execute(
                        "INSERT INTO topics VALUES(?,?,?,?,?,?)",
                        (object_id, normalized, action.name, action.description, now, now),
                    )
                else:
                    conn.execute(
                        "UPDATE topics SET normalized_name=?,name=?,description=?,updated_at=? "
                        "WHERE topic_id=?",
                        (normalized, action.name, action.description, now, object_id),
                    )
            if isinstance(action, (CreateTopic, LinkTopic)):
                conn.execute(
                    "INSERT OR IGNORE INTO field_topics VALUES(?,?,?)", (action.field_id, object_id, now),
                )
        else:
            kind = "track"
            if isinstance(action, CreateTrack):
                _topic_in_field(conn, action.field_id, action.primary_topic_id)
                for topic_id in action.secondary_topic_ids:
                    _require(conn, "topic", topic_id)
                object_id = new_id(kind)
                conn.execute(
                    "INSERT INTO research_tracks VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (object_id, action.field_id, action.primary_topic_id, action.title, action.scope,
                     action.research_type.value, "ACTIVE", "MAPPED", 1, now, now),
                )
                conn.execute(
                    "INSERT INTO track_topics VALUES(?,?,'PRIMARY',?)",
                    (object_id, action.primary_topic_id, now),
                )
                for topic_id in dict.fromkeys(action.secondary_topic_ids):
                    conn.execute(
                        "INSERT OR IGNORE INTO track_topics VALUES(?,?,'SECONDARY',?)",
                        (object_id, topic_id, now),
                    )
            else:
                object_id = action.track_id
                before = _require(conn, kind, object_id)
                if before["field_id"] != action.field_id:
                    raise WorkspaceError(404, "Track does not belong to this Field")
                _check_digest(conn, kind, before, action.expected_digest)
                conn.execute(
                    "UPDATE research_tracks SET title=?,updated_at=? WHERE track_id=?",
                    (action.title, now, object_id),
                )

        result = {"operation": operation, "object_type": kind, "object_id": object_id,
                  "object": _require(conn, kind, object_id), "request_id": action.request_id}
        if hasattr(action, "field_id"):
            result["field_id"] = action.field_id
        seq = conn.execute(
            "SELECT COALESCE(MAX(action_seq),0)+1 FROM research_workspace_actions"
        ).fetchone()[0]
        result["action_seq"] = seq
        result["metadata_digest"] = hashlib.sha256(
            _json({"record": result["object"], "metadata_sequence": seq}).encode()
        ).hexdigest()
        conn.execute(
            "INSERT INTO research_workspace_actions(action_seq,request_id,request_json,object_type,"
            "object_id,result_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (seq, action.request_id, request_json, kind, object_id, _json(result), now),
        )
        conn.commit()
        return result
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
