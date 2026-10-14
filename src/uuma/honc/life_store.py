"""Versioned life records in honc.db; never attach another agent's database.

This module is internal storage. It is not a raw database tool exposed to the model.
All writes, receipt creation and head changes share one BEGIN IMMEDIATE transaction.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .store import HoncStore


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class LifeStore:
    def __init__(self, ledger: HoncStore) -> None:
        if ledger.path.name.casefold() != "honc.db":
            raise ValueError("life records require the isolated honc.db ledger")
        self.ledger = ledger
        self._initialize()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.ledger.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def _initialize(self) -> None:
        statements = [
            """CREATE TABLE IF NOT EXISTS honc_life_schema_migrations (
                version INTEGER PRIMARY KEY, description TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS life_sources (
                source_ref TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL, profile TEXT NOT NULL, session_id TEXT NOT NULL,
                adapter_id TEXT NOT NULL, source_event_id TEXT NOT NULL,
                raw_content TEXT NOT NULL, received_at TEXT NOT NULL,
                grants_json TEXT NOT NULL,
                UNIQUE(owner_id, profile, adapter_id, source_event_id))""",
            """CREATE TABLE IF NOT EXISTS life_requests (
                request_ref TEXT PRIMARY KEY,
                source_ref TEXT NOT NULL REFERENCES life_sources(source_ref),
                operation_name TEXT NOT NULL,
                UNIQUE(source_ref, operation_name))""",
            """CREATE TABLE IF NOT EXISTS life_operations (
                operation_id TEXT PRIMARY KEY,
                request_ref TEXT NOT NULL UNIQUE REFERENCES life_requests(request_ref),
                owner_id TEXT NOT NULL, payload_digest TEXT NOT NULL,
                result_json TEXT NOT NULL, committed_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS life_objects (
                object_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('habit_definition','habit','body','diary','settings')),
                head_revision INTEGER NOT NULL CHECK(head_revision >= 1))""",
            """CREATE TABLE IF NOT EXISTS life_revisions (
                object_id TEXT NOT NULL REFERENCES life_objects(object_id),
                revision INTEGER NOT NULL CHECK(revision >= 1),
                source_ref TEXT NOT NULL REFERENCES life_sources(source_ref),
                operation_id TEXT NOT NULL REFERENCES life_operations(operation_id)
                    DEFERRABLE INITIALLY DEFERRED,
                status TEXT NOT NULL CHECK(status IN ('active','paused','retired','recorded','void')),
                payload_json TEXT NOT NULL, recorded_at TEXT NOT NULL,
                PRIMARY KEY(object_id, revision))""",
            """CREATE INDEX IF NOT EXISTS life_objects_owner_kind
                ON life_objects(owner_id, kind)""",
            """CREATE TRIGGER IF NOT EXISTS life_objects_identity_immutable
                BEFORE UPDATE OF object_id, owner_id, kind ON life_objects
                BEGIN SELECT RAISE(ABORT, 'life identity is immutable'); END""",
            """CREATE TRIGGER IF NOT EXISTS life_objects_no_delete BEFORE DELETE ON life_objects
                BEGIN SELECT RAISE(ABORT, 'life objects cannot be deleted'); END""",
        ]
        for table in ("life_sources", "life_requests", "life_operations", "life_revisions"):
            for action in ("UPDATE", "DELETE"):
                statements.append(
                    f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} "
                    f"BEFORE {action} ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'life history is immutable'); END"
                )
        with self.transaction() as connection:
            for statement in statements:
                connection.execute(statement)
            if "source_origin" not in {
                row[1] for row in connection.execute("PRAGMA table_info(life_sources)")
            }:
                connection.execute(
                    "ALTER TABLE life_sources ADD COLUMN source_origin TEXT NOT NULL DEFAULT 'user_message' "
                    "CHECK(source_origin IN ('user_message','configuration_import'))"
                )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS life_history_key (singleton INTEGER PRIMARY KEY CHECK(singleton=1), value BLOB NOT NULL)"
            )
            connection.execute(
                "INSERT OR IGNORE INTO life_history_key VALUES (1, ?)", (secrets.token_bytes(32),)
            )
            connection.execute(
                "INSERT OR IGNORE INTO honc_life_schema_migrations(version, description) "
                "VALUES (1, 'Versioned life records and source-bound operation receipts')"
            )

    @staticmethod
    def get_object(
        connection: sqlite3.Connection,
        owner_id: str,
        object_id: str,
        revision: int | None = None,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT o.object_id, o.kind, o.head_revision, r.revision, r.status, "
            "r.source_ref, r.operation_id, r.payload_json, r.recorded_at "
            "FROM life_objects o JOIN life_revisions r ON r.object_id = o.object_id "
            "AND r.revision = COALESCE(?, o.head_revision) "
            "WHERE o.owner_id = ? AND o.object_id = ?",
            (revision, owner_id, object_id),
        ).fetchone()
        return LifeStore.decode_object(row) if row else None

    @staticmethod
    def decode_object(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["payload"] = json.loads(value.pop("payload_json"))
        return value

    @staticmethod
    def append_revision(
        connection: sqlite3.Connection,
        *,
        owner_id: str,
        object_id: str,
        kind: str,
        expected_revision: int,
        source_ref: str,
        operation_id: str,
        status: str,
        payload: dict[str, Any],
        recorded_at: str,
    ) -> int:
        revision = expected_revision + 1
        if expected_revision == 0:
            connection.execute(
                "INSERT INTO life_objects(object_id, owner_id, kind, head_revision) "
                "VALUES (?, ?, ?, ?)",
                (object_id, owner_id, kind, revision),
            )
        else:
            changed = connection.execute(
                "UPDATE life_objects SET head_revision = ? "
                "WHERE object_id = ? AND owner_id = ? AND kind = ? AND head_revision = ?",
                (revision, object_id, owner_id, kind, expected_revision),
            ).rowcount
            if changed != 1:
                raise ValueError("concurrent life revision changed")
        connection.execute(
            "INSERT INTO life_revisions(object_id, revision, source_ref, operation_id, "
            "status, payload_json, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                object_id,
                revision,
                source_ref,
                operation_id,
                status,
                canonical(payload),
                recorded_at,
            ),
        )
        return revision
