from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from .event_store import task_idempotency_scope, task_request_digest
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
        requires_approval = (
            contract.get("user_visible_structure_change")
            or contract.get("risk_level") == "COMMITTING"
        )
        status = "PROPOSED" if requires_approval else "TODO"
        external_ref = contract.get("external_task_ref") or contract.get("external_project_ref")
        idempotency_scope = event.payload.get("idempotency_scope")
        if contract.get("idempotency_key") and not idempotency_scope:
            idempotency_scope = task_idempotency_scope(contract, event.actor_id)
        request_digest = event.payload.get("request_digest") or task_request_digest(contract)
        conn.execute(
            """
            INSERT INTO tasks(
                task_id, title, status, assignee, contract_json, external_ref,
                idempotency_scope, idempotency_key, request_digest,
                current_run_id, execution_epoch, state_version, updated_sequence
            )
            VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, NULL, 0, 1, ?)
            """,
            (
                contract["task_id"],
                contract["title"],
                status,
                _json(contract),
                external_ref,
                idempotency_scope,
                contract.get("idempotency_key"),
                request_digest,
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
        task = conn.execute(
            "SELECT execution_epoch FROM tasks WHERE task_id=?",
            (registration["task_id"],),
        ).fetchone()
        execution_epoch = int(registration.get("execution_epoch") or 0)
        if execution_epoch == 0:
            execution_epoch = (int(task["execution_epoch"]) if task else 0) + 1
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
            INSERT INTO runs(
                run_id, task_id, agent_id, status, source, execution_class,
                external_run_ref, execution_epoch, progress_json, result_json,
                result_digest, result_version, updated_sequence
            )
            VALUES (?, ?, ?, 'RUNNING', ?, ?, ?, ?, ?, NULL, NULL, 0, ?)
            """,
            (
                registration["run_id"],
                registration["task_id"],
                registration["agent_id"],
                registration["source"],
                registration["execution_class"],
                registration.get("external_run_ref"),
                execution_epoch,
                _json(progress),
                event.sequence,
            ),
        )
        conn.execute(
            """
            UPDATE tasks
            SET status='RUNNING', assignee=?, current_run_id=?, execution_epoch=?,
                state_version=state_version + 1, updated_sequence=?
            WHERE task_id=?
            """,
            (
                registration["agent_id"],
                registration["run_id"],
                execution_epoch,
                event.sequence,
                registration["task_id"],
            ),
        )

    def on_run_progressed(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        progress = event.payload["progress"]
        status = progress.get("status")
        if status not in {"PENDING", "RUNNING", "PAUSED"}:
            status = "RUNNING"
            progress = {**progress, "status": status}
        conn.execute(
            "UPDATE runs SET status=?, progress_json=?, updated_sequence=? WHERE run_id=?",
            (status, _json(progress), event.sequence, progress["run_id"]),
        )

    on_run_heartbeat = on_run_progressed

    def on_run_blocked(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        self._terminalish_run_update(conn, event, "BLOCKED", "BLOCKED")

    def on_run_review_required(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        self._terminalish_run_update(conn, event, "REVIEW", "REVIEW")

    on_run_result_submitted = on_run_review_required

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

    def on_run_superseded(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        conn.execute(
            "UPDATE runs SET status='SUPERSEDED', updated_sequence=? WHERE run_id=?",
            (event.sequence, event.aggregate_id),
        )

    def on_run_verified_completed(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        self._record_verification(conn, event)
        self._terminalish_run_update(conn, event, "COMPLETED", "COMPLETED")

    def on_run_verification_rejected(self, conn: sqlite3.Connection, event: EventEnvelope) -> None:
        self._record_verification(conn, event)

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
        if "expected_revision" in p:
            expected = int(p["expected_revision"])
            if expected == 0:
                conn.execute(
                    """
                    INSERT INTO graph_nodes(
                        node_id, node_type, revision, data_json, updated_sequence
                    ) VALUES (?, ?, 1, ?, ?)
                    """,
                    (p["node_id"], p["node_type"], _json(p.get("data", {})), event.sequence),
                )
                return
            cursor = conn.execute(
                """
                UPDATE graph_nodes
                SET node_type=?, revision=revision + 1, data_json=?, updated_sequence=?
                WHERE node_id=? AND revision=?
                """,
                (
                    p["node_type"],
                    _json(p.get("data", {})),
                    event.sequence,
                    p["node_id"],
                    expected,
                ),
            )
            if cursor.rowcount != 1:
                raise sqlite3.IntegrityError("graph node revision conflict")
            return
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
        if "expected_revision" in p:
            expected = int(p["expected_revision"])
            values = (
                p["source_id"],
                p["target_id"],
                p["edge_type"],
                _json(p.get("data", {})),
                event.sequence,
            )
            if expected == 0:
                conn.execute(
                    """
                    INSERT INTO graph_edges(
                        edge_id, source_id, target_id, edge_type, revision,
                        data_json, updated_sequence
                    ) VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                    (p["edge_id"], *values),
                )
                return
            cursor = conn.execute(
                """
                UPDATE graph_edges
                SET source_id=?, target_id=?, edge_type=?, revision=revision + 1,
                    data_json=?, updated_sequence=?
                WHERE edge_id=? AND revision=?
                """,
                (*values, p["edge_id"], expected),
            )
            if cursor.rowcount != 1:
                raise sqlite3.IntegrityError("graph edge revision conflict")
            return
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
                """
                UPDATE tasks
                SET status=?, state_version=state_version + 1, updated_sequence=?
                WHERE task_id=?
                """,
                (status, event.sequence, event.aggregate_id),
            )
        else:
            conn.execute(
                """
                UPDATE tasks
                SET status=?, assignee=?, state_version=state_version + 1, updated_sequence=?
                WHERE task_id=?
                """,
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
        row = conn.execute(
            """
            SELECT task_id, progress_json, result_json, result_digest,
                   result_version, execution_epoch
            FROM runs WHERE run_id=?
            """,
            (event.aggregate_id,),
        ).fetchone()
        if row is None:
            return
        progress_json = _json(progress) if progress is not None else row["progress_json"]
        result_json = _json(result) if result is not None else row["result_json"]
        result_digest = event.payload.get("result_digest") or row["result_digest"]
        if result is not None and result_digest is None:
            result_digest = hashlib.sha256(result_json.encode("utf-8")).hexdigest()
        result_version = int(row["result_version"]) + int(result is not None)
        conn.execute(
            """
            UPDATE runs
            SET status=?, progress_json=?, result_json=?, result_digest=?,
                result_version=?, updated_sequence=?
            WHERE run_id=?
            """,
            (
                run_status,
                progress_json,
                result_json,
                result_digest,
                result_version,
                event.sequence,
                event.aggregate_id,
            ),
        )
        conn.execute(
            """
            UPDATE tasks
            SET status=?, state_version=state_version + 1, updated_sequence=?
            WHERE task_id=? AND current_run_id=? AND execution_epoch=?
            """,
            (
                task_status,
                event.sequence,
                row["task_id"],
                event.aggregate_id,
                row["execution_epoch"],
            ),
        )

    @staticmethod
    def _record_verification(
        conn: sqlite3.Connection,
        event: EventEnvelope,
    ) -> None:
        record = event.payload["verification"]
        conn.execute(
            """
            INSERT INTO verifications(
                verification_id, run_id, task_id, acceptance_digest,
                result_digest, approved, record_json, updated_sequence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["verification_id"],
                record["run_id"],
                record["task_id"],
                record["acceptance_digest"],
                record["result_digest"],
                int(record["approved"]),
                _json(record),
                event.sequence,
            ),
        )
