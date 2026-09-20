from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import EventEnvelope

ProjectionCallback = Callable[[sqlite3.Connection, EventEnvelope], None]
GENESIS_HASH = "0" * 64


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def task_request_digest(contract: dict[str, Any]) -> str:
    """Hash the stable request body, excluding server-generated identity and time fields."""
    material = dict(contract)
    material.pop("task_id", None)
    material.pop("created_at", None)
    for set_field in ("required_capabilities", "required_tools"):
        values = material.get(set_field)
        if isinstance(values, list):
            material[set_field] = sorted(values)
    return hashlib.sha256(_canonical_json(material).encode("utf-8")).hexdigest()


def task_idempotency_scope(contract: dict[str, Any], actor_id: str) -> str:
    return f"{contract.get('source', 'orchestrator')}:{actor_id}"


class EventStore:
    """Append-only, hash-chained event log with rebuildable projections."""

    def __init__(self, path: str | Path, projector: ProjectionCallback | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.projector = projector
        self._lock = threading.RLock()
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = FULL")
        conn.execute("PRAGMA busy_timeout = 30000")
        try:
            yield conn
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    actor_type TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    correlation_id TEXT,
                    causation_id TEXT,
                    payload_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE
                );
                CREATE INDEX IF NOT EXISTS idx_events_aggregate
                    ON events(aggregate_type, aggregate_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_events_correlation
                    ON events(correlation_id, sequence);

                CREATE TRIGGER IF NOT EXISTS events_no_update
                BEFORE UPDATE ON events
                BEGIN
                    SELECT RAISE(ABORT, 'events are immutable');
                END;

                CREATE TRIGGER IF NOT EXISTS events_no_delete
                BEFORE DELETE ON events
                BEGIN
                    SELECT RAISE(ABORT, 'events are immutable');
                END;

                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    definition_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    updated_sequence INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    assignee TEXT,
                    contract_json TEXT NOT NULL,
                    external_ref TEXT,
                    idempotency_scope TEXT,
                    idempotency_key TEXT,
                    request_digest TEXT,
                    current_run_id TEXT,
                    execution_epoch INTEGER NOT NULL DEFAULT 0,
                    state_version INTEGER NOT NULL DEFAULT 1,
                    updated_sequence INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    execution_class TEXT NOT NULL,
                    external_run_ref TEXT,
                    execution_epoch INTEGER NOT NULL DEFAULT 0,
                    progress_json TEXT NOT NULL,
                    result_json TEXT,
                    result_digest TEXT,
                    result_version INTEGER NOT NULL DEFAULT 0,
                    updated_sequence INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_id);
                CREATE INDEX IF NOT EXISTS idx_runs_agent_status ON runs(agent_id, status);

                CREATE TABLE IF NOT EXISTS graph_nodes (
                    node_id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    data_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS graph_edges (
                    edge_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    edge_type TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    data_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_edges_source ON graph_edges(source_id, edge_type);
                CREATE INDEX IF NOT EXISTS idx_edges_target ON graph_edges(target_id, edge_type);

                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    operation_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    digest TEXT NOT NULL,
                    task_id TEXT,
                    run_id TEXT,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS verifications (
                    verification_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    acceptance_digest TEXT NOT NULL,
                    result_digest TEXT NOT NULL,
                    approved INTEGER NOT NULL,
                    record_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_verifications_run
                    ON verifications(run_id, updated_sequence);

                CREATE TABLE IF NOT EXISTS external_snapshots (
                    source TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    snapshot_hash TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    updated_sequence INTEGER NOT NULL,
                    PRIMARY KEY(source, external_id)
                );
                """
            )
            conn.execute("BEGIN IMMEDIATE")
            try:
                self._migrate_schema(conn)
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table: str,
        column: str,
        declaration: str,
    ) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        task_columns = {
            "idempotency_scope": "TEXT",
            "idempotency_key": "TEXT",
            "request_digest": "TEXT",
            "current_run_id": "TEXT",
            "execution_epoch": "INTEGER NOT NULL DEFAULT 0",
            "state_version": "INTEGER NOT NULL DEFAULT 1",
        }
        run_columns = {
            "execution_epoch": "INTEGER NOT NULL DEFAULT 0",
            "result_digest": "TEXT",
            "result_version": "INTEGER NOT NULL DEFAULT 0",
        }
        for column, declaration in task_columns.items():
            self._ensure_column(conn, "tasks", column, declaration)
        for column, declaration in run_columns.items():
            self._ensure_column(conn, "runs", column, declaration)

        task_rows = conn.execute(
            """
            SELECT task_id, contract_json, status, current_run_id,
                   idempotency_scope, request_digest
            FROM tasks
            """
        ).fetchall()
        for row in task_rows:
            contract = json.loads(row["contract_json"])
            key = contract.get("idempotency_key")
            actor_row = conn.execute(
                """
                SELECT actor_id FROM events
                WHERE event_type='TASK_CREATED' AND aggregate_id=?
                ORDER BY sequence LIMIT 1
                """,
                (row["task_id"],),
            ).fetchone()
            actor_id = actor_row["actor_id"] if actor_row else str(contract.get("requested_by", "user"))
            scope = row["idempotency_scope"] or (
                task_idempotency_scope(contract, actor_id) if key else None
            )
            digest = row["request_digest"] or task_request_digest(contract)
            conn.execute(
                """
                UPDATE tasks
                SET idempotency_scope=?, idempotency_key=?, request_digest=?
                WHERE task_id=?
                """,
                (scope, key, digest, row["task_id"]),
            )
            requires_approval = (
                contract.get("user_visible_structure_change")
                or contract.get("risk_level") == "COMMITTING"
            )
            approved = conn.execute(
                """
                SELECT 1 FROM events
                WHERE event_type='TASK_APPROVED' AND aggregate_id=?
                LIMIT 1
                """,
                (row["task_id"],),
            ).fetchone()
            if requires_approval and approved is None and row["status"] != "PROPOSED":
                if row["status"] == "TODO" and row["current_run_id"] is None:
                    conn.execute(
                        "UPDATE tasks SET status='PROPOSED' WHERE task_id=?",
                        (row["task_id"],),
                    )
                else:
                    raise RuntimeError(
                        "Task history contains a committing or structural transition without "
                        f"an approval event and requires manual reconciliation: {row['task_id']}."
                    )

        duplicate = conn.execute(
            """
            SELECT idempotency_scope, idempotency_key, COUNT(*) AS count
            FROM tasks
            WHERE idempotency_key IS NOT NULL
            GROUP BY idempotency_scope, idempotency_key
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        ).fetchone()
        if duplicate is not None:
            raise RuntimeError(
                "Ambiguous task idempotency history requires manual reconciliation: "
                f"scope={duplicate['idempotency_scope']!r}, "
                f"key={duplicate['idempotency_key']!r}, count={duplicate['count']}."
            )

        registration_order: dict[str, int] = {}
        for event_row in conn.execute(
            "SELECT sequence, payload_json FROM events WHERE event_type='RUN_REGISTERED' ORDER BY sequence"
        ):
            registration = json.loads(event_row["payload_json"]).get("registration", {})
            run_id = registration.get("run_id")
            if run_id:
                registration_order[str(run_id)] = int(event_row["sequence"])

        task_ids = [row["task_id"] for row in conn.execute("SELECT task_id FROM tasks")]
        terminal = {"COMPLETED", "FAILED", "CANCELLED", "SUPERSEDED"}
        for task_id in task_ids:
            runs = conn.execute(
                """
                SELECT run_id, status, result_json, result_digest,
                       result_version, updated_sequence
                FROM runs WHERE task_id=?
                """,
                (task_id,),
            ).fetchall()
            ordered = sorted(
                runs,
                key=lambda row: (
                    registration_order.get(row["run_id"], int(row["updated_sequence"])),
                    row["run_id"],
                ),
            )
            active = [row["run_id"] for row in ordered if row["status"] not in terminal]
            if len(active) > 1:
                raise RuntimeError(
                    "Ambiguous active Run history requires manual reconciliation for "
                    f"task {task_id}: {active}."
                )
            for epoch, run in enumerate(ordered, start=1):
                result_json = run["result_json"]
                computed_digest = (
                    hashlib.sha256(result_json.encode("utf-8")).hexdigest()
                    if result_json
                    else None
                )
                result_digest = run["result_digest"] or computed_digest
                result_version = max(
                    int(run["result_version"]),
                    int(result_json is not None),
                )
                conn.execute(
                    """
                    UPDATE runs
                    SET execution_epoch=?, result_digest=?, result_version=?
                    WHERE run_id=?
                    """,
                    (epoch, result_digest, result_version, run["run_id"]),
                )
            if ordered:
                conn.execute(
                    """
                    UPDATE tasks
                    SET current_run_id=?, execution_epoch=?
                    WHERE task_id=?
                    """,
                    (ordered[-1]["run_id"], len(ordered), task_id),
                )

        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_idempotency
            ON tasks(idempotency_scope, idempotency_key)
            WHERE idempotency_key IS NOT NULL
            """
        )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Hold the cross-process SQLite write boundary for checks and event projection."""
        with self._lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    def append(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        actor_type: str,
        actor_id: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        event_id: str | None = None,
        occurred_at: datetime | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> EventEnvelope:
        event_id = event_id or f"evt_{uuid4().hex}"
        occurred_at = occurred_at or datetime.now(UTC)
        metadata = metadata or {}

        if conn is not None:
            return self._append_to_connection(
                conn,
                event_type=event_type,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                actor_type=actor_type,
                actor_id=actor_id,
                payload=payload,
                metadata=metadata,
                correlation_id=correlation_id,
                causation_id=causation_id,
                event_id=event_id,
                occurred_at=occurred_at,
            )
        with self.transaction() as transaction_conn:
            return self._append_to_connection(
                transaction_conn,
                event_type=event_type,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                actor_type=actor_type,
                actor_id=actor_id,
                payload=payload,
                metadata=metadata,
                correlation_id=correlation_id,
                causation_id=causation_id,
                event_id=event_id,
                occurred_at=occurred_at,
            )

    def _append_to_connection(
        self,
        conn: sqlite3.Connection,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        actor_type: str,
        actor_id: str,
        payload: dict[str, Any],
        metadata: dict[str, Any],
        correlation_id: str | None,
        causation_id: str | None,
        event_id: str,
        occurred_at: datetime,
    ) -> EventEnvelope:
        row = conn.execute("SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1").fetchone()
        previous_hash = row["event_hash"] if row else GENESIS_HASH
        hash_material = {
            "event_id": event_id,
            "event_type": event_type,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "occurred_at": occurred_at.isoformat(),
            "correlation_id": correlation_id,
            "causation_id": causation_id,
            "payload": payload,
            "metadata": metadata,
            "previous_hash": previous_hash,
        }
        event_hash = hashlib.sha256(_canonical_json(hash_material).encode("utf-8")).hexdigest()
        cursor = conn.execute(
            """
            INSERT INTO events(
                event_id, event_type, aggregate_type, aggregate_id,
                actor_type, actor_id, occurred_at, correlation_id,
                causation_id, payload_json, metadata_json,
                previous_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event_type,
                aggregate_type,
                aggregate_id,
                actor_type,
                actor_id,
                occurred_at.isoformat(),
                correlation_id,
                causation_id,
                _canonical_json(payload),
                _canonical_json(metadata),
                previous_hash,
                event_hash,
            ),
        )
        event = EventEnvelope(
            sequence=int(cursor.lastrowid),
            event_id=event_id,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            actor_type=actor_type,
            actor_id=actor_id,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            causation_id=causation_id,
            payload=payload,
            metadata=metadata,
            previous_hash=previous_hash,
            event_hash=event_hash,
        )
        if self.projector is not None:
            self.projector(conn, event)
        return event

    def iter_events(self, after_sequence: int = 0) -> Iterator[EventEnvelope]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE sequence > ? ORDER BY sequence", (after_sequence,)
            ).fetchall()
        for row in rows:
            yield self._row_to_event(row)

    def get_event(self, event_id: str) -> EventEnvelope | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        return self._row_to_event(row) if row else None

    def verify_chain(self) -> tuple[bool, int | None, str | None]:
        previous_hash = GENESIS_HASH
        for event in self.iter_events():
            material = {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "aggregate_type": event.aggregate_type,
                "aggregate_id": event.aggregate_id,
                "actor_type": event.actor_type,
                "actor_id": event.actor_id,
                "occurred_at": event.occurred_at.isoformat(),
                "correlation_id": event.correlation_id,
                "causation_id": event.causation_id,
                "payload": event.payload,
                "metadata": event.metadata,
                "previous_hash": previous_hash,
            }
            expected = hashlib.sha256(_canonical_json(material).encode("utf-8")).hexdigest()
            if event.previous_hash != previous_hash or event.event_hash != expected:
                return False, event.sequence, event.event_id
            previous_hash = event.event_hash
        return True, None, None

    def rebuild_projections(self) -> int:
        if self.projector is None:
            return 0
        projection_tables = (
            "agents",
            "tasks",
            "runs",
            "graph_nodes",
            "graph_edges",
            "operations",
            "artifacts",
            "verifications",
            "external_snapshots",
        )
        with self._lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for table in projection_tables:
                    conn.execute(f"DELETE FROM {table}")
                rows = conn.execute("SELECT * FROM events ORDER BY sequence").fetchall()
                for row in rows:
                    self.projector(conn, self._row_to_event(row))
                conn.execute("COMMIT")
                return len(rows)
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> EventEnvelope:
        return EventEnvelope(
            sequence=row["sequence"],
            event_id=row["event_id"],
            event_type=row["event_type"],
            aggregate_type=row["aggregate_type"],
            aggregate_id=row["aggregate_id"],
            actor_type=row["actor_type"],
            actor_id=row["actor_id"],
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
            correlation_id=row["correlation_id"],
            causation_id=row["causation_id"],
            payload=json.loads(row["payload_json"]),
            metadata=json.loads(row["metadata_json"]),
            previous_hash=row["previous_hash"],
            event_hash=row["event_hash"],
        )
