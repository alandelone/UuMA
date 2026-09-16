from __future__ import annotations

import json
import sqlite3
from typing import Any

from .models import EventEnvelope


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Projector:
    """Builds disposable current-state views from immutable UuMA events."""

    def apply(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        handler = getattr(self, f"on_{event.event_type.lower()}", None)
        if handler is not None:
            handler(conn, event)

    def on_agent_registered(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        definition = event.payload["definition"]
        conn.execute(
            """
            INSERT INTO agents(agent_id, display_name, description, definition_json, enabled,
                               updated_sequence)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
                display_name=excluded.display_name,
                description=excluded.description,
                definition_json=excluded.definition_json,
                enabled=excluded.enabled,
                updated_sequence=excluded.updated_sequence
            """,
            (
                definition["agent_id"],
                definition["display_name"],
                definition["description"],
                _json(definition),
                int(definition.get("enabled", True)),
                event.sequence,
            ),
        )

    def on_task_created(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        contract = event.payload["contract"]
        status = "PROPOSED" if contract.get("user_visible_structure_change") else "TODO"
        external_ref = contract.get("external_task_ref") or contract.get("external_project_ref")
        conn.execute(
            """
            INSERT INTO tasks(task_id, title, status, assignee, contract_json, external_ref,
                              updated_sequence)
            VALUES (?, ?, ?, NULL, ?, ?, ?)
            """,
            (
                contract["task_id"],
                contract["title"],
                status,
                _json(contract),
                external_ref,
                event.sequence,
            ),
        )

    def on_task_approved(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        self._update_task(conn, event, status="TODO")

    def on_task_assigned(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        self._update_task(
            conn,
            event,
            status="READY",
            assignee=event.payload["agent_id"],
        )

    def on_run_registered(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        registration = event.payload["registration"]
        progress = {
            "run_id": registration["run_id"],
            "task_id": registration["task_id"],
            "agent_id": registration["agent_id"],
            "status": "RUNNING",
            "completed_steps": 0,
            "total_steps": None,
            "current_step": None,
            "last_heartbeat": registration["started_at"],
            "blocker": None,
            "attempt": 1,
            "elapsed_seconds": 0,
            "artifact_refs": [],
            "eta_seconds": None,
        }
        conn.execute(
            """
            INSERT INTO runs(run_id, task_id, agent_id, status, source, execution_class,
                             external_run_ref, progress_json, result_json, updated_sequence)
            VALUES (?, ?, ?, 'RUNNING', ?, ?, ?, ?, NULL, ?)
            """,
            (
                registration["run_id"],
                registration["task_id"],
                registration["agent_id"],
                registration["source"],
                registration["execution_class"],
                registration.get("external_run_ref"),
                _json(progress),
                event.sequence,
            ),
        )
        conn.execute(
            "UPDATE tasks SET status='RUNNING', assignee=?, updated_sequence=? WHERE task_id=?",
            (registration["agent_id"], event.sequence, registration["task_id"]),
        )

    def on_run_progressed(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        progress = event.payload["progress"]
        conn.execute(
            "UPDATE runs SET status=?, progress_json=?, updated_sequence=? WHERE run_id=?",
            (progress["status"], _json(progress), event.sequence, progress["run_id"]),
        )

    on_run_heartbeat = on_run_progressed

    def on_run_blocked(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        self._terminalish_run_update(conn, event, "BLOCKED", "BLOCKED")

    def on_run_review_required(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        self._terminalish_run_update(conn, event, "REVIEW", "REVIEW")

    def on_run_completed(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        self._terminalish_run_update(conn, event, "COMPLETED", "COMPLETED")

    def on_run_failed(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        self._terminalish_run_update(conn, event, "FAILED", "FAILED")

    def on_run_cancel_requested(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        conn.execute(
            "UPDATE runs SET status='CANCEL_REQUESTED', updated_sequence=? WHERE run_id=?",
            (event.sequence, event.aggregate_id),
        )

    def on_run_cancelled(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        self._terminalish_run_update(conn, event, "CANCELLED", "CANCELLED")

    def on_graph_operation_proposed(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        operation = event.payload["operation"]
        status = "PENDING_APPROVAL" if operation["requires_user_approval"] else "APPROVED"
        conn.execute(
            """
            INSERT INTO operations(operation_id, kind, target_id, status, operation_json,
                                   updated_sequence)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                operation["operation_id"],
                operation["kind"],
                operation["target_id"],
                status,
                _json(operation),
                event.sequence,
            ),
        )

    def on_graph_operation_approved(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        conn.execute(
            "UPDATE operations SET status='APPROVED', updated_sequence=? WHERE operation_id=?",
            (event.sequence, event.aggregate_id),
        )

    on_graph_operation_auto_approved = on_graph_operation_approved

    def on_graph_operation_rejected(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        conn.execute(
            "UPDATE operations SET status='REJECTED', updated_sequence=? WHERE operation_id=?",
            (event.sequence, event.aggregate_id),
        )

    def on_graph_node_upserted(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        p = event.payload
        conn.execute(
            """
            INSERT INTO graph_nodes(node_id, node_type, revision, data_json, updated_sequence)
            VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                node_type=excluded.node_type,
                revision=graph_nodes.revision + 1,
                data_json=excluded.data_json,
                updated_sequence=excluded.updated_sequence
            """,
            (p["node_id"], p["node_type"], _json(p.get("data", {})), event.sequence),
        )

    def on_graph_edge_upserted(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        p = event.payload
        conn.execute(
            """
            INSERT INTO graph_edges(edge_id, source_id, target_id, edge_type, revision, data_json,
                                    updated_sequence)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(edge_id) DO UPDATE SET
                source_id=excluded.source_id,
                target_id=excluded.target_id,
                edge_type=excluded.edge_type,
                revision=graph_edges.revision + 1,
                data_json=excluded.data_json,
                updated_sequence=excluded.updated_sequence
            """,
            (
                p["edge_id"],
                p["source_id"],
                p["target_id"],
                p["edge_type"],
                _json(p.get("data", {})),
                event.sequence,
            ),
        )

    def on_artifact_registered(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        record = event.payload["artifact"]
        conn.execute(
            """
            INSERT INTO artifacts(artifact_id, digest, task_id, run_id, record_json,
                                  updated_sequence)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record["artifact_id"],
                record["digest"],
                record.get("task_id"),
                record.get("run_id"),
                _json(record),
                event.sequence,
            ),
        )

    def on_external_snapshot_recorded(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        p = event.payload
        conn.execute(
            """
            INSERT INTO external_snapshots(source, external_id, snapshot_hash, snapshot_json,
                                           updated_sequence)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source, external_id) DO UPDATE SET
                snapshot_hash=excluded.snapshot_hash,
                snapshot_json=excluded.snapshot_json,
                updated_sequence=excluded.updated_sequence
            """,
            (
                p["source"],
                p["external_id"],
                p["snapshot_hash"],
                _json(p["snapshot"]),
                event.sequence,
            ),
        )

    @staticmethod
    def _update_task(
        conn: sqlite3.Connection,
        event: EventEnvelope,
        *,
        status: str,
        assignee: str | None = None,
    ) -> None:
        if assignee is None:
            conn.execute(
                "UPDATE tasks SET status=?, updated_sequence=? WHERE task_id=?",
                (status, event.sequence, event.aggregate_id),
            )
        else:
            conn.execute(
                "UPDATE tasks SET status=?, assignee=?, updated_sequence=? WHERE task_id=?",
                (status, assignee, event.sequence, event.aggregate_id),
            )

    @staticmethod
    def _terminalish_run_update(
        conn: sqlite3.Connection,
        event: EventEnvelope,
        run_status: str,
        task_status: str,
    ) -> None:
        result = event.payload.get("result")
        progress = event.payload.get("progress")
        row = conn.execute("SELECT task_id, progress_json FROM runs WHERE run_id=?", (event.aggregate_id,)).fetchone()
        if row is None:
            return
        progress_json = _json(progress) if progress is not None else row["progress_json"]
        conn.execute(
            """
            UPDATE runs SET status=?, progress_json=?, result_json=?, updated_sequence=?
            WHERE run_id=?
            """,
            (
                run_status,
                progress_json,
                _json(result) if result is not None else None,
                event.sequence,
                event.aggregate_id,
            ),
        )
        conn.execute(
            "UPDATE tasks SET status=?, updated_sequence=? WHERE task_id=?",
            (task_status, event.sequence, row["task_id"]),
        )
