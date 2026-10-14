from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import (
    ActualKind,
    CompletionAssessment,
    DailyReport,
    ExecutionEvent,
    HabitDefinition,
    OutboxItem,
    ProjectionBinding,
    Round,
    RoundSegment,
    TaskSnapshot,
    TrustedInput,
    canonical_json,
    get_timezone,
)

SCHEMA_VERSION = 1


class HoncStore:
    """Isolated, append-only SQLite store for the honc execution ledger."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
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

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    def _initialize(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS honc_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL,
                    description TEXT NOT NULL
                )
                """
            )
            cur = conn.execute("SELECT MAX(version) FROM honc_schema_migrations")
            row = cur.fetchone()
            current_v = row[0] if row and row[0] is not None else 0

            if current_v < 1:
                self._apply_migration_v1(conn)

    def _apply_migration_v1(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS trusted_inputs (
                input_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                entrypoint TEXT NOT NULL,
                profile TEXT NOT NULL,
                session_id TEXT,
                source_receipt_id TEXT,
                raw_content TEXT NOT NULL,
                received_at TEXT NOT NULL,
                source_digest TEXT NOT NULL UNIQUE,
                metadata_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_trusted_inputs_user_received
                ON trusted_inputs(user_id, received_at);

            CREATE TABLE IF NOT EXISTS task_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                graph_database_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                portfolio_role TEXT,
                graph_version INTEGER NOT NULL,
                task_status TEXT NOT NULL,
                title TEXT NOT NULL,
                done_when TEXT,
                snapshot_digest TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_task_snapshots_node
                ON task_snapshots(graph_database_id, node_id, created_at);

            CREATE TABLE IF NOT EXISTS rounds (
                round_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                task_id TEXT,
                target_outcome TEXT NOT NULL,
                tiny_step TEXT NOT NULL,
                mode TEXT NOT NULL,
                timer_budget_minutes INTEGER NOT NULL DEFAULT 25,
                criteria_snapshot TEXT,
                status TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                closed_at TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_rounds_active_user
                ON rounds(user_id)
                WHERE status IN ('PREPARED', 'RUNNING', 'PAUSED', 'AWAITING_CHECK');

            CREATE TABLE IF NOT EXISTS round_segments (
                segment_id TEXT PRIMARY KEY,
                round_id TEXT NOT NULL REFERENCES rounds(round_id),
                started_at TEXT NOT NULL,
                ended_at TEXT,
                interruption_reason TEXT,
                time_source TEXT NOT NULL,
                duration_seconds INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_round_segments_round
                ON round_segments(round_id, started_at);

            CREATE TABLE IF NOT EXISTS habits (
                habit_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                field_type TEXT NOT NULL,
                unit TEXT,
                daily_target REAL NOT NULL DEFAULT 1.0,
                max_per_day INTEGER NOT NULL DEFAULT 10,
                description TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS execution_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                timezone TEXT NOT NULL,
                trusted_input_id TEXT REFERENCES trusted_inputs(input_id),
                task_id TEXT,
                round_id TEXT REFERENCES rounds(round_id),
                habit_id TEXT,
                outcome TEXT,
                next_step TEXT,
                blocker TEXT,
                state TEXT,
                actual_kind TEXT NOT NULL,
                actual_duration_seconds INTEGER,
                correction_ref_id TEXT REFERENCES execution_events(event_id),
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_round ON execution_events(round_id);
            CREATE INDEX IF NOT EXISTS idx_events_task ON execution_events(task_id);
            CREATE INDEX IF NOT EXISTS idx_events_occurred ON execution_events(occurred_at);

            CREATE TRIGGER IF NOT EXISTS execution_events_no_update
            BEFORE UPDATE ON execution_events
            BEGIN
                SELECT RAISE(ABORT, 'execution_events are immutable');
            END;

            CREATE TRIGGER IF NOT EXISTS execution_events_no_delete
            BEFORE DELETE ON execution_events
            BEGIN
                SELECT RAISE(ABORT, 'execution_events are immutable');
            END;

            CREATE TABLE IF NOT EXISTS completion_assessments (
                assessment_id TEXT PRIMARY KEY,
                granularity TEXT NOT NULL,
                task_id TEXT NOT NULL,
                criteria_snapshot TEXT NOT NULL,
                satisfied_items_json TEXT NOT NULL,
                missing_items_json TEXT NOT NULL,
                evidence TEXT NOT NULL,
                trusted_input_id TEXT REFERENCES trusted_inputs(input_id),
                result TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_assessments_task
                ON completion_assessments(task_id, created_at);

            CREATE TABLE IF NOT EXISTS outbox (
                outbox_id TEXT PRIMARY KEY,
                target_system TEXT NOT NULL,
                operation_id TEXT NOT NULL UNIQUE,
                content_digest TEXT NOT NULL,
                preceding_version INTEGER,
                status TEXT NOT NULL,
                retry_count INTEGER NOT NULL DEFAULT 0,
                lease_expires_at TEXT,
                last_error TEXT,
                receipt_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_outbox_status_updated
                ON outbox(status, updated_at);

            CREATE TABLE IF NOT EXISTS projection_bindings (
                binding_id TEXT PRIMARY KEY,
                scope_type TEXT NOT NULL,
                scope_id TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                remote_digest TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(scope_type, scope_id, target_type)
            );

            INSERT INTO honc_schema_migrations (version, applied_at, description)
            VALUES (1, datetime('now'), 'Initial honc execution ledger schema');
            """
        )

    # -------------------------------------------------------------------------
    # Trusted Inputs
    # -------------------------------------------------------------------------

    def record_trusted_input(self, inp: TrustedInput) -> TrustedInput:
        """Record a verified user input, deduplicating by source_digest."""
        with self.transaction() as conn:
            cur = conn.execute(
                "SELECT input_id, user_id, entrypoint, profile, session_id, "
                "source_receipt_id, raw_content, received_at, source_digest, metadata_json "
                "FROM trusted_inputs WHERE source_digest = ?",
                (inp.source_digest,),
            )
            row = cur.fetchone()
            if row:
                return self._row_to_trusted_input(row)

            conn.execute(
                """
                INSERT INTO trusted_inputs (
                    input_id, user_id, entrypoint, profile, session_id,
                    source_receipt_id, raw_content, received_at, source_digest, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    inp.input_id,
                    inp.user_id,
                    inp.entrypoint,
                    inp.profile,
                    inp.session_id,
                    inp.source_receipt_id,
                    inp.raw_content,
                    inp.received_at,
                    inp.source_digest,
                    canonical_json(inp.metadata),
                ),
            )
            return inp

    def get_trusted_input(self, input_id: str) -> TrustedInput | None:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT input_id, user_id, entrypoint, profile, session_id, "
                "source_receipt_id, raw_content, received_at, source_digest, metadata_json "
                "FROM trusted_inputs WHERE input_id = ?",
                (input_id,),
            )
            row = cur.fetchone()
            return self._row_to_trusted_input(row) if row else None

    @staticmethod
    def _row_to_trusted_input(row: sqlite3.Row) -> TrustedInput:
        return TrustedInput(
            input_id=row["input_id"],
            user_id=row["user_id"],
            entrypoint=row["entrypoint"],
            profile=row["profile"],
            session_id=row["session_id"],
            source_receipt_id=row["source_receipt_id"],
            raw_content=row["raw_content"],
            received_at=row["received_at"],
            source_digest=row["source_digest"],
            metadata=json.loads(row["metadata_json"]),
        )

    # -------------------------------------------------------------------------
    # Task Snapshots
    # -------------------------------------------------------------------------

    def save_task_snapshot(self, snapshot: TaskSnapshot) -> TaskSnapshot:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO task_snapshots (
                    snapshot_id, graph_database_id, node_id, portfolio_role,
                    graph_version, task_status, title, done_when, snapshot_digest, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.graph_database_id,
                    snapshot.node_id,
                    snapshot.portfolio_role,
                    snapshot.graph_version,
                    snapshot.task_status,
                    snapshot.title,
                    snapshot.done_when,
                    snapshot.snapshot_digest,
                    snapshot.created_at,
                ),
            )
            return snapshot

    def get_task_snapshot(self, snapshot_id: str) -> TaskSnapshot | None:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT snapshot_id, graph_database_id, node_id, portfolio_role, "
                "graph_version, task_status, title, done_when, snapshot_digest, created_at "
                "FROM task_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            )
            row = cur.fetchone()
            return self._row_to_task_snapshot(row) if row else None

    def get_latest_task_snapshot(self, graph_database_id: str, node_id: str) -> TaskSnapshot | None:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT snapshot_id, graph_database_id, node_id, portfolio_role, "
                "graph_version, task_status, title, done_when, snapshot_digest, created_at "
                "FROM task_snapshots "
                "WHERE graph_database_id = ? AND node_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (graph_database_id, node_id),
            )
            row = cur.fetchone()
            return self._row_to_task_snapshot(row) if row else None

    @staticmethod
    def _row_to_task_snapshot(row: sqlite3.Row) -> TaskSnapshot:
        return TaskSnapshot(
            snapshot_id=row["snapshot_id"],
            graph_database_id=row["graph_database_id"],
            node_id=row["node_id"],
            portfolio_role=row["portfolio_role"],
            graph_version=row["graph_version"],
            task_status=row["task_status"],
            title=row["title"],
            done_when=row["done_when"],
            snapshot_digest=row["snapshot_digest"],
            created_at=row["created_at"],
        )

    # -------------------------------------------------------------------------
    # Rounds & Segments
    # -------------------------------------------------------------------------

    def create_round(self, round_obj: Round) -> Round:
        """Create a new round, enforcing at most one active round per user."""
        with self.transaction() as conn:
            # Check if active round exists
            cur = conn.execute(
                "SELECT round_id FROM rounds WHERE user_id = ? AND status IN "
                "('PREPARED', 'RUNNING', 'PAUSED', 'AWAITING_CHECK')",
                (round_obj.user_id,),
            )
            if cur.fetchone():
                raise ValueError(
                    f"User {round_obj.user_id} already has an active round. "
                    "Close or cancel it before starting a new round."
                )

            conn.execute(
                """
                INSERT INTO rounds (
                    round_id, user_id, task_id, target_outcome, tiny_step,
                    mode, timer_budget_minutes, criteria_snapshot, status,
                    revision, created_at, updated_at, closed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    round_obj.round_id,
                    round_obj.user_id,
                    round_obj.task_id,
                    round_obj.target_outcome,
                    round_obj.tiny_step,
                    round_obj.mode,
                    round_obj.timer_budget_minutes,
                    round_obj.criteria_snapshot,
                    round_obj.status,
                    round_obj.revision,
                    round_obj.created_at,
                    round_obj.updated_at,
                    round_obj.closed_at,
                ),
            )
            return round_obj

    def get_round(self, round_id: str) -> Round | None:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT round_id, user_id, task_id, target_outcome, tiny_step, "
                "mode, timer_budget_minutes, criteria_snapshot, status, revision, "
                "created_at, updated_at, closed_at "
                "FROM rounds WHERE round_id = ?",
                (round_id,),
            )
            row = cur.fetchone()
            return self._row_to_round(row) if row else None

    def get_active_round(self, user_id: str) -> Round | None:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT round_id, user_id, task_id, target_outcome, tiny_step, "
                "mode, timer_budget_minutes, criteria_snapshot, status, revision, "
                "created_at, updated_at, closed_at "
                "FROM rounds WHERE user_id = ? AND status IN "
                "('PREPARED', 'RUNNING', 'PAUSED', 'AWAITING_CHECK')",
                (user_id,),
            )
            row = cur.fetchone()
            return self._row_to_round(row) if row else None

    def update_round_status(
        self,
        round_id: str,
        expected_revision: int,
        new_status: str,
        closed_at: str | None = None,
    ) -> Round:
        """Update round status with optimistic revision checking."""
        with self.transaction() as conn:
            cur = conn.execute(
                "SELECT revision, status FROM rounds WHERE round_id = ?", (round_id,)
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Round {round_id} does not exist.")
            if row["revision"] != expected_revision:
                raise ValueError(
                    f"Revision conflict on round {round_id}: expected {expected_revision}, "
                    f"found {row['revision']}."
                )

            now_iso = datetime.now(UTC).isoformat()
            new_rev = expected_revision + 1
            conn.execute(
                """
                UPDATE rounds
                SET status = ?, revision = ?, updated_at = ?, closed_at = COALESCE(?, closed_at)
                WHERE round_id = ? AND revision = ?
                """,
                (new_status, new_rev, now_iso, closed_at, round_id, expected_revision),
            )
            cur = conn.execute(
                "SELECT round_id, user_id, task_id, target_outcome, tiny_step, "
                "mode, timer_budget_minutes, criteria_snapshot, status, revision, "
                "created_at, updated_at, closed_at "
                "FROM rounds WHERE round_id = ?",
                (round_id,),
            )
            updated_row = cur.fetchone()
            if not updated_row:
                raise RuntimeError("Failed to retrieve updated round.")
            return self._row_to_round(updated_row)

    @staticmethod
    def _row_to_round(row: sqlite3.Row) -> Round:
        return Round(
            round_id=row["round_id"],
            user_id=row["user_id"],
            task_id=row["task_id"],
            target_outcome=row["target_outcome"],
            tiny_step=row["tiny_step"],
            mode=row["mode"],
            timer_budget_minutes=row["timer_budget_minutes"],
            criteria_snapshot=row["criteria_snapshot"],
            status=row["status"],
            revision=row["revision"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
        )

    def add_round_segment(self, segment: RoundSegment) -> RoundSegment:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO round_segments (
                    segment_id, round_id, started_at, ended_at,
                    interruption_reason, time_source, duration_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    segment.segment_id,
                    segment.round_id,
                    segment.started_at,
                    segment.ended_at,
                    segment.interruption_reason,
                    segment.time_source,
                    segment.duration_seconds,
                ),
            )
            return segment

    def close_active_round_segment(
        self, round_id: str, ended_at: str, reason: str | None = None
    ) -> RoundSegment | None:
        """Close the currently active segment of a round, calculating duration."""
        with self.transaction() as conn:
            cur = conn.execute(
                "SELECT segment_id, round_id, started_at, ended_at, interruption_reason, "
                "time_source, duration_seconds "
                "FROM round_segments WHERE round_id = ? AND ended_at IS NULL "
                "ORDER BY started_at DESC LIMIT 1",
                (round_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            start_dt = datetime.fromisoformat(row["started_at"])
            end_dt = datetime.fromisoformat(ended_at)
            duration_secs = max(0, int((end_dt - start_dt).total_seconds()))

            conn.execute(
                """
                UPDATE round_segments
                SET ended_at = ?, interruption_reason = ?, duration_seconds = ?
                WHERE segment_id = ?
                """,
                (ended_at, reason, duration_secs, row["segment_id"]),
            )
            return RoundSegment(
                segment_id=row["segment_id"],
                round_id=round_id,
                started_at=row["started_at"],
                ended_at=ended_at,
                interruption_reason=reason,
                time_source=row["time_source"],
                duration_seconds=duration_secs,
            )

    def get_round_segments(self, round_id: str) -> list[RoundSegment]:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT segment_id, round_id, started_at, ended_at, interruption_reason, "
                "time_source, duration_seconds "
                "FROM round_segments WHERE round_id = ? ORDER BY started_at ASC",
                (round_id,),
            )
            return [
                RoundSegment(
                    segment_id=row["segment_id"],
                    round_id=row["round_id"],
                    started_at=row["started_at"],
                    ended_at=row["ended_at"],
                    interruption_reason=row["interruption_reason"],
                    time_source=row["time_source"],
                    duration_seconds=row["duration_seconds"],
                )
                for row in cur.fetchall()
            ]

    def calculate_round_duration(self, round_id: str) -> int:
        segments = self.get_round_segments(round_id)
        return sum(s.duration_seconds or 0 for s in segments)

    # -------------------------------------------------------------------------
    # Habits
    # -------------------------------------------------------------------------

    def register_habit(self, habit: HabitDefinition) -> HabitDefinition:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO habits (
                    habit_id, name, field_type, unit, daily_target, max_per_day, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(habit_id) DO UPDATE SET
                    name = excluded.name,
                    field_type = excluded.field_type,
                    unit = excluded.unit,
                    daily_target = excluded.daily_target,
                    max_per_day = excluded.max_per_day,
                    description = excluded.description
                """,
                (
                    habit.habit_id,
                    habit.name,
                    habit.field_type,
                    habit.unit,
                    habit.daily_target,
                    habit.max_per_day,
                    habit.description,
                ),
            )
            return habit

    def get_habit(self, habit_id: str) -> HabitDefinition | None:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT habit_id, name, field_type, unit, daily_target, max_per_day, description "
                "FROM habits WHERE habit_id = ?",
                (habit_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return HabitDefinition(
                habit_id=row["habit_id"],
                name=row["name"],
                field_type=row["field_type"],
                unit=row["unit"],
                daily_target=row["daily_target"],
                max_per_day=row["max_per_day"],
                description=row["description"],
            )

    def list_habits(self) -> list[HabitDefinition]:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT habit_id, name, field_type, unit, daily_target, max_per_day, description "
                "FROM habits ORDER BY habit_id ASC"
            )
            return [
                HabitDefinition(
                    habit_id=row["habit_id"],
                    name=row["name"],
                    field_type=row["field_type"],
                    unit=row["unit"],
                    daily_target=row["daily_target"],
                    max_per_day=row["max_per_day"],
                    description=row["description"],
                )
                for row in cur.fetchall()
            ]

    # -------------------------------------------------------------------------
    # Execution Events
    # -------------------------------------------------------------------------

    def record_execution_event(self, event: ExecutionEvent) -> ExecutionEvent:
        """Append an immutable execution event."""
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO execution_events (
                    event_id, event_type, occurred_at, recorded_at, timezone,
                    trusted_input_id, task_id, round_id, habit_id, outcome,
                    next_step, blocker, state, actual_kind,
                    actual_duration_seconds, correction_ref_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.event_type,
                    event.occurred_at,
                    event.recorded_at,
                    event.timezone,
                    event.trusted_input_id,
                    event.task_id,
                    event.round_id,
                    event.habit_id,
                    event.outcome,
                    event.next_step,
                    event.blocker,
                    event.state,
                    event.actual_kind,
                    event.actual_duration_seconds,
                    event.correction_ref_id,
                    canonical_json(event.payload),
                ),
            )
            return event

    def get_event(self, event_id: str) -> ExecutionEvent | None:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT event_id, event_type, occurred_at, recorded_at, timezone, "
                "trusted_input_id, task_id, round_id, habit_id, outcome, "
                "next_step, blocker, state, actual_kind, actual_duration_seconds, "
                "correction_ref_id, payload_json "
                "FROM execution_events WHERE event_id = ?",
                (event_id,),
            )
            row = cur.fetchone()
            return self._row_to_event(row) if row else None

    def list_events(
        self,
        task_id: str | None = None,
        round_id: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
    ) -> list[ExecutionEvent]:
        conditions = []
        params = []
        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)
        if round_id:
            conditions.append("round_id = ?")
            params.append(round_id)
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)

        clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM execution_events {clause} ORDER BY occurred_at DESC LIMIT ?"
        params.append(limit)

        with self.connect() as conn:
            cur = conn.execute(query, tuple(params))
            return [self._row_to_event(row) for row in cur.fetchall()]

    def get_correction_chain(self, event_id: str) -> list[ExecutionEvent]:
        """Fetch an event and all events correcting it or corrected by it."""
        events: list[ExecutionEvent] = []
        with self.connect() as conn:
            # First, get the target event
            cur = conn.execute("SELECT * FROM execution_events WHERE event_id = ?", (event_id,))
            row = cur.fetchone()
            if not row:
                return []
            events.append(self._row_to_event(row))

            # Fetch any events that corrected this event
            cur = conn.execute(
                "SELECT * FROM execution_events WHERE correction_ref_id = ? "
                "ORDER BY occurred_at ASC",
                (event_id,),
            )
            events.extend(self._row_to_event(r) for r in cur.fetchall())
        return events

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> ExecutionEvent:
        return ExecutionEvent(
            event_id=row["event_id"],
            event_type=row["event_type"],
            occurred_at=row["occurred_at"],
            recorded_at=row["recorded_at"],
            timezone=row["timezone"],
            trusted_input_id=row["trusted_input_id"],
            task_id=row["task_id"],
            round_id=row["round_id"],
            habit_id=row["habit_id"],
            outcome=row["outcome"],
            next_step=row["next_step"],
            blocker=row["blocker"],
            state=row["state"],
            actual_kind=row["actual_kind"],
            actual_duration_seconds=row["actual_duration_seconds"],
            correction_ref_id=row["correction_ref_id"],
            payload=json.loads(row["payload_json"]),
        )

    # -------------------------------------------------------------------------
    # Completion Assessments
    # -------------------------------------------------------------------------

    def save_assessment(self, assessment: CompletionAssessment) -> CompletionAssessment:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO completion_assessments (
                    assessment_id, granularity, task_id, criteria_snapshot,
                    satisfied_items_json, missing_items_json, evidence,
                    trusted_input_id, result, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assessment.assessment_id,
                    assessment.granularity,
                    assessment.task_id,
                    assessment.criteria_snapshot,
                    canonical_json(assessment.satisfied_items),
                    canonical_json(assessment.missing_items),
                    assessment.evidence,
                    assessment.trusted_input_id,
                    assessment.result,
                    assessment.created_at,
                ),
            )
            return assessment

    def get_assessment(self, assessment_id: str) -> CompletionAssessment | None:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT * FROM completion_assessments WHERE assessment_id = ?",
                (assessment_id,),
            )
            row = cur.fetchone()
            return self._row_to_assessment(row) if row else None

    def list_assessments(
        self, task_id: str | None = None, limit: int = 20
    ) -> list[CompletionAssessment]:
        query = "SELECT * FROM completion_assessments"
        params: list[Any] = []
        if task_id:
            query += " WHERE task_id = ?"
            params.append(task_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self.connect() as conn:
            cur = conn.execute(query, tuple(params))
            return [self._row_to_assessment(row) for row in cur.fetchall()]

    @staticmethod
    def _row_to_assessment(row: sqlite3.Row) -> CompletionAssessment:
        return CompletionAssessment(
            assessment_id=row["assessment_id"],
            granularity=row["granularity"],
            task_id=row["task_id"],
            criteria_snapshot=row["criteria_snapshot"],
            satisfied_items=json.loads(row["satisfied_items_json"]),
            missing_items=json.loads(row["missing_items_json"]),
            evidence=row["evidence"],
            trusted_input_id=row["trusted_input_id"],
            result=row["result"],
            created_at=row["created_at"],
        )

    # -------------------------------------------------------------------------
    # Outbox
    # -------------------------------------------------------------------------

    def enqueue_outbox(self, item: OutboxItem) -> OutboxItem:
        """Enqueue an outbox mutation. Idempotent by operation_id."""
        with self.transaction() as conn:
            cur = conn.execute("SELECT * FROM outbox WHERE operation_id = ?", (item.operation_id,))
            row = cur.fetchone()
            if row:
                if row["content_digest"] != item.content_digest:
                    raise ValueError(
                        f"Operation ID conflict for {item.operation_id}: content digest differs."
                    )
                return self._row_to_outbox(row)

            conn.execute(
                """
                INSERT INTO outbox (
                    outbox_id, target_system, operation_id, content_digest,
                    preceding_version, status, retry_count, lease_expires_at,
                    last_error, receipt_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.outbox_id,
                    item.target_system,
                    item.operation_id,
                    item.content_digest,
                    item.preceding_version,
                    item.status,
                    item.retry_count,
                    item.lease_expires_at,
                    item.last_error,
                    item.receipt_json,
                    item.created_at,
                    item.updated_at,
                ),
            )
            return item

    def get_outbox(self, operation_id: str) -> OutboxItem | None:
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM outbox WHERE operation_id = ?", (operation_id,))
            row = cur.fetchone()
            return self._row_to_outbox(row) if row else None

    def list_pending_outbox(self, limit: int = 10) -> list[OutboxItem]:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT * FROM outbox WHERE status IN ('PENDING', 'FAILED') "
                "ORDER BY updated_at ASC LIMIT ?",
                (limit,),
            )
            return [self._row_to_outbox(row) for row in cur.fetchall()]

    def update_outbox_status(
        self,
        operation_id: str,
        status: str,
        receipt_json: str | None = None,
        error: str | None = None,
    ) -> OutboxItem:
        with self.transaction() as conn:
            now_iso = datetime.now(UTC).isoformat()
            conn.execute(
                """
                UPDATE outbox
                SET status = ?, receipt_json = COALESCE(?, receipt_json),
                    last_error = ?, updated_at = ?
                WHERE operation_id = ?
                """,
                (status, receipt_json, error, now_iso, operation_id),
            )
            cur = conn.execute("SELECT * FROM outbox WHERE operation_id = ?", (operation_id,))
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"Outbox item {operation_id} not found.")
            return self._row_to_outbox(row)

    @staticmethod
    def _row_to_outbox(row: sqlite3.Row) -> OutboxItem:
        return OutboxItem(
            outbox_id=row["outbox_id"],
            target_system=row["target_system"],
            operation_id=row["operation_id"],
            content_digest=row["content_digest"],
            preceding_version=row["preceding_version"],
            status=row["status"],
            retry_count=row["retry_count"],
            lease_expires_at=row["lease_expires_at"],
            last_error=row["last_error"],
            receipt_json=row["receipt_json"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # -------------------------------------------------------------------------
    # Projection Bindings
    # -------------------------------------------------------------------------

    def save_projection_binding(self, binding: ProjectionBinding) -> ProjectionBinding:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO projection_bindings (
                    binding_id, scope_type, scope_id, target_type, target_id,
                    remote_digest, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope_type, scope_id, target_type) DO IGNORE
                """,
                (
                    binding.binding_id,
                    binding.scope_type,
                    binding.scope_id,
                    binding.target_type,
                    binding.target_id,
                    binding.remote_digest,
                    binding.updated_at,
                ),
            )
            return binding

    def get_projection_binding(
        self, scope_type: str, scope_id: str, target_type: str
    ) -> ProjectionBinding | None:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT * FROM projection_bindings "
                "WHERE scope_type = ? AND scope_id = ? AND target_type = ?",
                (scope_type, scope_id, target_type),
            )
            row = cur.fetchone()
            if not row:
                return None
            return ProjectionBinding(
                binding_id=row["binding_id"],
                scope_type=row["scope_type"],
                scope_id=row["scope_id"],
                target_type=row["target_type"],
                target_id=row["target_id"],
                remote_digest=row["remote_digest"],
                updated_at=row["updated_at"],
            )

    # -------------------------------------------------------------------------
    # Daily / Weekly Report
    # -------------------------------------------------------------------------

    def get_daily_report(
        self,
        user_id: str,
        date_str: str,
        timezone_name: str = "Asia/Kuala_Lumpur",
    ) -> DailyReport:
        """Aggregate events, rounds, and habits for a given date in specified timezone."""
        tz = get_timezone(timezone_name)

        # Retrieve all events
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM execution_events ORDER BY occurred_at ASC")
            all_events = [self._row_to_event(r) for r in cur.fetchall()]

        # Filter events whose occurred_at lands on date_str in target timezone
        day_events: list[ExecutionEvent] = []
        for ev in all_events:
            dt = datetime.fromisoformat(ev.occurred_at)
            local_dt = dt.astimezone(tz)
            if local_dt.strftime("%Y-%m-%d") == date_str:
                day_events.append(ev)

        # Aggregate done, next, blockers
        done_items: list[dict[str, Any]] = []
        next_items: list[str] = []
        blockers: list[str] = []
        timed_secs = 0
        reported_secs = 0
        estimated_secs = 0
        unlinked_count = 0

        habit_ticks: dict[str, int] = {}

        for ev in day_events:
            if ev.outcome:
                done_items.append(
                    {
                        "event_id": ev.event_id,
                        "task_id": ev.task_id,
                        "outcome": ev.outcome,
                        "occurred_at": ev.occurred_at,
                    }
                )
            if ev.next_step and ev.next_step not in next_items:
                next_items.append(ev.next_step)
            if ev.blocker and ev.blocker not in blockers:
                blockers.append(ev.blocker)

            # Durations
            if ev.actual_duration_seconds:
                if ev.actual_kind == ActualKind.TIMED:
                    timed_secs += ev.actual_duration_seconds
                elif ev.actual_kind == ActualKind.USER_REPORTED:
                    reported_secs += ev.actual_duration_seconds
                elif ev.actual_kind == ActualKind.ESTIMATED:
                    estimated_secs += ev.actual_duration_seconds

            if not ev.task_id and not ev.round_id and not ev.habit_id:
                unlinked_count += 1

            if ev.habit_id:
                habit_ticks[ev.habit_id] = habit_ticks.get(ev.habit_id, 0) + 1

        # Sum durations from round segments belonging to this date
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT rs.duration_seconds, rs.time_source, rs.started_at, r.user_id "
                "FROM round_segments rs JOIN rounds r ON rs.round_id = r.round_id "
                "WHERE r.user_id = ? AND rs.duration_seconds IS NOT NULL",
                (user_id,),
            )
            for row in cur.fetchall():
                s_dt = datetime.fromisoformat(row["started_at"]).astimezone(tz)
                if s_dt.strftime("%Y-%m-%d") == date_str:
                    dur = row["duration_seconds"] or 0
                    ts = row["time_source"]
                    if ts == "timer":
                        timed_secs += dur
                    elif ts == "user_reported":
                        reported_secs += dur
                    elif ts == "estimated":
                        estimated_secs += dur

            # Count rounds created or closed on this date
            cur = conn.execute(
                "SELECT COUNT(*) FROM rounds WHERE user_id = ? AND date(created_at) = ?",
                (user_id, date_str),
            )
            rounds_count = cur.fetchone()[0]

            # Pending outbox items
            cur = conn.execute("SELECT COUNT(*) FROM outbox WHERE status IN ('PENDING', 'FAILED')")
            pending_outbox = cur.fetchone()[0]

        # Habits summary
        all_habits = self.list_habits()
        habits_summary = [
            {
                "habit_id": h.habit_id,
                "name": h.name,
                "target": h.daily_target,
                "count": habit_ticks.get(h.habit_id, 0),
                "completed": habit_ticks.get(h.habit_id, 0) >= h.daily_target,
            }
            for h in all_habits
        ]

        total_active = timed_secs + reported_secs + estimated_secs

        return DailyReport(
            date=date_str,
            user_id=user_id,
            done_items=done_items,
            next_items=next_items,
            blockers=blockers,
            total_active_seconds=total_active,
            timed_seconds=timed_secs,
            reported_seconds=reported_secs,
            estimated_seconds=estimated_secs,
            rounds_count=rounds_count,
            habits_summary=habits_summary,
            pending_outbox_count=pending_outbox,
            unlinked_events_count=unlinked_count,
        )
