from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .artifacts import ArtifactStore
from .event_store import EventStore, task_idempotency_scope, task_request_digest
from .models import (
    AgentDefinition,
    ArtifactRecord,
    GraphOperation,
    OperationKind,
    ResultContract,
    ResultOutcome,
    RiskLevel,
    RouteDecision,
    RunProgress,
    RunRegistration,
    RunStatus,
    TaskContract,
    VerificationDecision,
    VerificationRecord,
)
from .policy import PolicyEngine, default_agents
from .projections import Projector
from .router import CapabilityRouter
from .settings import Settings


class ControlPlaneError(RuntimeError):
    pass


class NotFoundError(ControlPlaneError):
    pass


class PolicyDeniedError(ControlPlaneError):
    pass


class ConflictError(ControlPlaneError):
    pass


class ContractValidationError(ControlPlaneError):
    pass


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ControlPlane:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.settings.ensure_directories()
        self.projector = Projector()
        self.events = EventStore(self.settings.database_path, self.projector.apply)
        self.artifact_store = ArtifactStore(self.settings.artifact_dir)
        self.policy = PolicyEngine()
        self.router = CapabilityRouter(self.policy)

    def bootstrap(self) -> list[AgentDefinition]:
        existing = {agent.agent_id: agent for agent in self.list_agents()}
        registered: list[AgentDefinition] = []
        for definition in default_agents():
            if existing.get(definition.agent_id) == definition:
                continue
            self.register_agent(definition, actor_id="system")
            registered.append(definition)
        return registered

    def register_agent(self, definition: AgentDefinition, *, actor_id: str) -> None:
        self.events.append(
            event_type="AGENT_REGISTERED",
            aggregate_type="agent",
            aggregate_id=definition.agent_id,
            actor_type="system" if actor_id == "system" else "agent",
            actor_id=actor_id,
            payload={"definition": definition.model_dump(mode="json")},
        )

    def create_task(self, contract: TaskContract, *, actor_id: str) -> TaskContract:
        contract_payload = contract.model_dump(mode="json")
        scope = task_idempotency_scope(contract_payload, actor_id)
        digest = task_request_digest(contract_payload)
        with self.events.transaction() as conn:
            if contract.idempotency_key:
                row = conn.execute(
                    """
                    SELECT contract_json, request_digest FROM tasks
                    WHERE idempotency_scope=? AND idempotency_key=?
                    """,
                    (scope, contract.idempotency_key),
                ).fetchone()
                if row is not None:
                    if row["request_digest"] != digest:
                        raise ConflictError(
                            "Idempotency key was already used for a different task request."
                        )
                    return TaskContract.model_validate_json(row["contract_json"])
            if conn.execute(
                "SELECT 1 FROM tasks WHERE task_id=?", (contract.task_id,)
            ).fetchone():
                raise ConflictError(f"Task already exists: {contract.task_id}")
            self.events.append(
                event_type="TASK_CREATED",
                aggregate_type="task",
                aggregate_id=contract.task_id,
                actor_type="agent" if actor_id != "user" else "user",
                actor_id=actor_id,
                payload={
                    "contract": contract_payload,
                    "idempotency_scope": scope if contract.idempotency_key else None,
                    "request_digest": digest,
                },
                correlation_id=contract.task_id,
                conn=conn,
            )
        return contract

    def approve_task(self, task_id: str, *, actor_id: str = "user") -> None:
        with self.events.transaction() as conn:
            task = conn.execute("SELECT status FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if task is None:
                raise NotFoundError(f"Unknown Task: {task_id}")
            if task["status"] != "PROPOSED":
                raise ConflictError(f"Task {task_id} is not awaiting approval.")
            self.events.append(
                event_type="TASK_APPROVED",
                aggregate_type="task",
                aggregate_id=task_id,
                actor_type="user" if actor_id == "user" else "agent",
                actor_id=actor_id,
                payload={},
                correlation_id=task_id,
                conn=conn,
            )

    def route_task(self, task_id: str, *, actor_id: str = "orchestrator") -> RouteDecision:
        task = TaskContract.model_validate(self.require_task(task_id)["contract"])
        decision = self.router.route(task, self.list_agents(), self._workload())
        self.events.append(
            event_type="ROUTE_DECIDED",
            aggregate_type="task",
            aggregate_id=task_id,
            actor_type="agent",
            actor_id=actor_id,
            payload={"decision": decision.model_dump(mode="json")},
            correlation_id=task_id,
        )
        return decision

    def assign_task(
        self,
        task_id: str,
        agent_id: str,
        *,
        actor_id: str = "orchestrator",
        user_approved: bool = False,
    ) -> None:
        del user_approved  # Client booleans are not an approval authority.
        agent = self.require_agent(agent_id)
        with self.events.transaction() as conn:
            task_row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if task_row is None:
                raise NotFoundError(f"Unknown Task: {task_id}")
            if task_row["status"] == "PROPOSED":
                raise PolicyDeniedError("Task must be approved before assignment.")
            if task_row["status"] == "READY" and task_row["assignee"] == agent_id:
                return
            if task_row["status"] != "TODO":
                raise ConflictError(
                    f"Task {task_id} cannot be assigned from status {task_row['status']}."
                )
            task = TaskContract.model_validate_json(task_row["contract_json"])
            approved_by_state = task.risk_level is not RiskLevel.COMMITTING or task_row[
                "status"
            ] != "PROPOSED"
            decision = self.policy.authorize_task(
                agent,
                task,
                user_approved=approved_by_state,
            )
            if not decision.allowed:
                raise PolicyDeniedError(decision.reason)
            self.events.append(
                event_type="TASK_ASSIGNED",
                aggregate_type="task",
                aggregate_id=task_id,
                actor_type="agent",
                actor_id=actor_id,
                payload={
                    "agent_id": agent_id,
                    "approval_recorded": task.risk_level is RiskLevel.COMMITTING,
                },
                correlation_id=task_id,
                conn=conn,
            )

    def register_run(
        self,
        registration: RunRegistration,
        *,
        actor_id: str,
        takeover: bool = False,
    ) -> RunRegistration:
        self.require_agent(registration.agent_id)
        with self.events.transaction() as conn:
            task_row = conn.execute(
                "SELECT * FROM tasks WHERE task_id=?", (registration.task_id,)
            ).fetchone()
            if task_row is None:
                raise NotFoundError(f"Unknown Task: {registration.task_id}")
            if conn.execute(
                "SELECT 1 FROM runs WHERE run_id=?", (registration.run_id,)
            ).fetchone():
                raise ConflictError(f"Run already exists: {registration.run_id}")
            control_takeover = takeover and actor_id == "orchestrator"
            if task_row["assignee"] != registration.agent_id and not control_takeover:
                raise ConflictError("Run Agent does not match the task assignee.")
            if task_row["status"] in {"COMPLETED", "CANCELLED"}:
                raise ConflictError("A completed or cancelled Task cannot start another Run.")

            current_run_id = task_row["current_run_id"]
            if current_run_id:
                current = conn.execute(
                    "SELECT status FROM runs WHERE run_id=?", (current_run_id,)
                ).fetchone()
                if current and current["status"] not in {
                    "COMPLETED",
                    "FAILED",
                    "CANCELLED",
                    "SUPERSEDED",
                }:
                    if not takeover or actor_id != "orchestrator":
                        raise ConflictError(
                            "Task already has an active Run; an Orchestrator takeover is required."
                        )
                    self.events.append(
                        event_type="RUN_SUPERSEDED",
                        aggregate_type="run",
                        aggregate_id=current_run_id,
                        actor_type="agent",
                        actor_id=actor_id,
                        payload={"replacement_run_id": registration.run_id},
                        correlation_id=registration.task_id,
                        conn=conn,
                    )

            registered = registration.model_copy(
                update={"execution_epoch": int(task_row["execution_epoch"]) + 1}
            )
            self.events.append(
                event_type="RUN_REGISTERED",
                aggregate_type="run",
                aggregate_id=registered.run_id,
                actor_type="agent",
                actor_id=actor_id,
                payload={"registration": registered.model_dump(mode="json")},
                correlation_id=registered.task_id,
                conn=conn,
            )
            return registered

    def register_direct_run(
        self,
        agent_id: str,
        contract: TaskContract,
        *,
        external_run_ref: str | None = None,
    ) -> RunRegistration:
        agent = self.require_agent(agent_id)
        decision = self.policy.authorize_direct_run(agent, contract)
        if not decision.allowed:
            raise PolicyDeniedError(decision.reason)
        contract = self.create_task(contract, actor_id=agent_id)
        self.assign_task(contract.task_id, agent_id, actor_id=agent_id)
        registration = RunRegistration(
            task_id=contract.task_id,
            agent_id=agent_id,
            execution_class=contract.execution_class,
            source="direct",
            external_run_ref=external_run_ref,
        )
        return self.register_run(registration, actor_id=agent_id)

    def report_progress(self, progress: RunProgress, *, actor_id: str) -> None:
        if progress.status not in {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.PAUSED}:
            raise ContractValidationError(
                "Heartbeat progress cannot write blocked, review, cancellation, or terminal status."
            )
        event_type = "RUN_HEARTBEAT" if progress.current_step is None else "RUN_PROGRESSED"
        with self.events.transaction() as conn:
            self._assert_current_run(
                conn,
                progress.run_id,
                progress.task_id,
                progress.agent_id,
                actor_id,
            )
            self.events.append(
                event_type=event_type,
                aggregate_type="run",
                aggregate_id=progress.run_id,
                actor_type="agent",
                actor_id=actor_id,
                payload={"progress": progress.model_dump(mode="json")},
                correlation_id=progress.task_id,
                conn=conn,
            )

    def block_run(self, progress: RunProgress, *, actor_id: str) -> None:
        if not progress.blocker:
            raise ContractValidationError("A blocked Run must state its blocker.")
        blocked = progress.model_copy(update={"status": RunStatus.BLOCKED})
        with self.events.transaction() as conn:
            self._assert_current_run(
                conn,
                progress.run_id,
                progress.task_id,
                progress.agent_id,
                actor_id,
            )
            self.events.append(
                event_type="RUN_BLOCKED",
                aggregate_type="run",
                aggregate_id=progress.run_id,
                actor_type="agent",
                actor_id=actor_id,
                payload={"progress": blocked.model_dump(mode="json")},
                correlation_id=progress.task_id,
                conn=conn,
            )

    def submit_result(self, result: ResultContract, *, actor_id: str) -> str:
        task = TaskContract.model_validate(self.require_task(result.task_id)["contract"])
        declared_checks = {check.name: check for check in result.checks}
        missing = [name for name in task.acceptance_checks if name not in declared_checks]
        failed = [name for name in task.acceptance_checks if name in declared_checks and not declared_checks[name].passed]

        if result.outcome is ResultOutcome.COMPLETED and (missing or failed):
            raise ContractValidationError(
                f"Completed result is missing or failing acceptance checks: missing={missing}, failed={failed}"
            )

        if result.outcome in {
            ResultOutcome.COMPLETED,
            ResultOutcome.NEEDS_REVIEW,
            ResultOutcome.PARTIAL,
        }:
            event_type = "RUN_RESULT_SUBMITTED"
        elif result.outcome is ResultOutcome.CANCELLED:
            event_type = "RUN_CANCELLED"
        else:
            event_type = "RUN_FAILED"
        result_payload = result.model_dump(mode="json")
        result_digest = _canonical_digest(result_payload)
        with self.events.transaction() as conn:
            self._assert_current_run(
                conn,
                result.run_id,
                result.task_id,
                result.agent_id,
                actor_id,
            )
            self.events.append(
                event_type=event_type,
                aggregate_type="run",
                aggregate_id=result.run_id,
                actor_type="agent",
                actor_id=actor_id,
                payload={"result": result_payload, "result_digest": result_digest},
                correlation_id=result.task_id,
                conn=conn,
            )
        return event_type

    def verification_context(self, run_id: str) -> dict[str, Any]:
        run = self.require_run(run_id)
        if run["result"] is None or run["result_digest"] is None:
            raise ConflictError("Run has no submitted result to verify.")
        task = TaskContract.model_validate(self.require_task(run["task_id"])["contract"])
        with self.events.connect() as conn:
            verification_rows = conn.execute(
                """
                SELECT record_json FROM verifications
                WHERE run_id=? ORDER BY updated_sequence
                """,
                (run_id,),
            ).fetchall()
        return {
            "run_id": run_id,
            "task_id": run["task_id"],
            "acceptance_checks": task.acceptance_checks,
            "acceptance_digest": _canonical_digest(task.acceptance_checks),
            "result_digest": run["result_digest"],
            "result_version": run["result_version"],
            "artifact_refs": list(run["result"].get("artifact_refs", [])),
            "verifications": [json.loads(row["record_json"]) for row in verification_rows],
        }

    def verify_result(
        self,
        decision: VerificationDecision,
        *,
        actor_id: str,
    ) -> VerificationRecord:
        with self.events.transaction() as conn:
            run = conn.execute(
                "SELECT * FROM runs WHERE run_id=?", (decision.run_id,)
            ).fetchone()
            if run is None:
                raise NotFoundError(f"Unknown Run: {decision.run_id}")
            if run["task_id"] != decision.task_id:
                raise ContractValidationError("Verification Task does not match the Run.")
            if actor_id == run["agent_id"]:
                raise PolicyDeniedError("A Worker cannot independently verify its own result.")
            self._assert_current_run(
                conn,
                decision.run_id,
                decision.task_id,
                run["agent_id"],
                actor_id,
                allow_control=True,
            )
            if run["status"] != "REVIEW" or not run["result_json"]:
                raise ConflictError("Run is not awaiting independent result verification.")

            task_row = conn.execute(
                "SELECT contract_json FROM tasks WHERE task_id=?", (decision.task_id,)
            ).fetchone()
            task = TaskContract.model_validate_json(task_row["contract_json"])
            acceptance_digest = _canonical_digest(task.acceptance_checks)
            if decision.acceptance_digest != acceptance_digest:
                raise ConflictError("Acceptance conditions changed before verification.")
            if decision.result_digest != run["result_digest"]:
                raise ConflictError("Result changed before verification.")

            checked = {check.name: check for check in decision.checks}
            missing = [name for name in task.acceptance_checks if name not in checked]
            failed = [
                name
                for name in task.acceptance_checks
                if name in checked and not checked[name].passed
            ]
            if decision.approved and (missing or failed):
                raise ContractValidationError(
                    "Approved verification is missing or failing acceptance checks: "
                    f"missing={missing}, failed={failed}"
                )

            result_payload = json.loads(run["result_json"])
            record = VerificationRecord(
                run_id=decision.run_id,
                task_id=decision.task_id,
                acceptance_digest=acceptance_digest,
                result_digest=run["result_digest"],
                approved=decision.approved,
                checks=decision.checks,
                artifact_refs=list(result_payload.get("artifact_refs", [])),
                verifier_id=actor_id,
                note=decision.note,
            )
            event_type = (
                "RUN_VERIFIED_COMPLETED" if decision.approved else "RUN_VERIFICATION_REJECTED"
            )
            self.events.append(
                event_type=event_type,
                aggregate_type="run",
                aggregate_id=decision.run_id,
                actor_type="user" if actor_id == "user" else "agent",
                actor_id=actor_id,
                payload={"verification": record.model_dump(mode="json")},
                correlation_id=decision.task_id,
                conn=conn,
            )
            return record

    def request_cancel(self, run_id: str, *, actor_id: str = "orchestrator") -> None:
        with self.events.transaction() as conn:
            run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None:
                raise NotFoundError(f"Unknown Run: {run_id}")
            self._assert_current_run(
                conn,
                run_id,
                run["task_id"],
                run["agent_id"],
                actor_id,
                allow_control=True,
            )
            self.events.append(
                event_type="RUN_CANCEL_REQUESTED",
                aggregate_type="run",
                aggregate_id=run_id,
                actor_type="agent",
                actor_id=actor_id,
                payload={},
                correlation_id=run["task_id"],
                conn=conn,
            )

    def propose_operation(self, operation: GraphOperation, *, actor_id: str | None = None) -> None:
        actor_id = actor_id or operation.requested_by
        if operation.kind in {
            OperationKind.UPSERT_NODE,
            OperationKind.UPSERT_EDGE,
            OperationKind.LINK_DEPENDENCY,
        } and operation.expected_revision is None:
            raise ContractValidationError("Graph writes require an expected_revision.")
        proposed = operation.model_copy(update={"requires_user_approval": True})
        with self.events.transaction() as conn:
            if conn.execute(
                "SELECT 1 FROM operations WHERE operation_id=?", (proposed.operation_id,)
            ).fetchone():
                raise ConflictError(f"Operation already exists: {proposed.operation_id}")
            self._assert_expected_revision(proposed, conn=conn)
            self.events.append(
                event_type="GRAPH_OPERATION_PROPOSED",
                aggregate_type="operation",
                aggregate_id=proposed.operation_id,
                actor_type="agent",
                actor_id=actor_id,
                payload={"operation": proposed.model_dump(mode="json")},
                correlation_id=proposed.target_id,
                conn=conn,
            )

    def approve_operation(self, operation_id: str, *, actor_id: str = "user") -> None:
        with self.events.transaction() as conn:
            operation_row = conn.execute(
                "SELECT * FROM operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if operation_row is None:
                raise NotFoundError(f"Unknown operation: {operation_id}")
            if operation_row["status"] != "PENDING_APPROVAL":
                raise ConflictError(f"Operation {operation_id} is not awaiting approval.")
            operation = GraphOperation.model_validate_json(operation_row["operation_json"])
            self._assert_expected_revision(operation, conn=conn)
            approved = self.events.append(
                event_type="GRAPH_OPERATION_APPROVED",
                aggregate_type="operation",
                aggregate_id=operation_id,
                actor_type="user" if actor_id == "user" else "agent",
                actor_id=actor_id,
                payload={},
                correlation_id=operation.target_id,
                conn=conn,
            )
            self._apply_operation(operation, approved_event_id=approved.event_id, conn=conn)

    def reject_operation(self, operation_id: str, *, reason: str, actor_id: str = "user") -> None:
        with self.events.transaction() as conn:
            operation = conn.execute(
                "SELECT status FROM operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if operation is None:
                raise NotFoundError(f"Unknown operation: {operation_id}")
            if operation["status"] != "PENDING_APPROVAL":
                raise ConflictError(f"Operation {operation_id} is not awaiting approval.")
            self.events.append(
                event_type="GRAPH_OPERATION_REJECTED",
                aggregate_type="operation",
                aggregate_id=operation_id,
                actor_type="user" if actor_id == "user" else "agent",
                actor_id=actor_id,
                payload={"reason": reason},
                conn=conn,
            )

    def register_artifact(
        self,
        source: str | Path,
        *,
        media_type: str,
        logical_name: str,
        created_by: str,
        task_id: str | None = None,
        run_id: str | None = None,
    ) -> ArtifactRecord:
        record = self.artifact_store.add(
            source,
            media_type=media_type,
            logical_name=logical_name,
            created_by=created_by,
            task_id=task_id,
            run_id=run_id,
        )
        self.events.append(
            event_type="ARTIFACT_REGISTERED",
            aggregate_type="artifact",
            aggregate_id=record.artifact_id,
            actor_type="agent",
            actor_id=created_by,
            payload={"artifact": record.model_dump(mode="json")},
            correlation_id=task_id,
        )
        return record

    def ingest_hermes_event(self, event: dict[str, Any], *, profile: str) -> bool:
        supplied_event_id = str(event["uuma_event_id"]) if event.get("uuma_event_id") else None
        if supplied_event_id and self.events.get_event(supplied_event_id) is not None:
            return False
        sanitized = self._redact(event)
        event_type = str(event.get("hook") or event.get("event_type") or "observer_event")
        session_id = str(event.get("session_id") or "unknown")
        self.events.append(
            event_type=f"HERMES_{event_type.upper()}",
            aggregate_type="hermes_session",
            aggregate_id=session_id,
            actor_type="agent",
            actor_id=profile,
            payload={"observer": sanitized},
            correlation_id=str(event.get("task_id") or session_id),
            metadata={"telemetry_schema_version": event.get("telemetry_schema_version")},
            event_id=supplied_event_id,
        )
        return True

    def record_external_snapshot(
        self,
        *,
        source: str,
        external_id: str,
        snapshot: dict[str, Any],
        actor_id: str = "reconciler",
    ) -> bool:
        snapshot_hash = hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        previous = self._external_snapshot(source, external_id)
        if previous and previous["snapshot_hash"] == snapshot_hash:
            return False
        if previous is not None:
            self.events.append(
                event_type="DRIFT_DETECTED",
                aggregate_type="external_state",
                aggregate_id=f"{source}:{external_id}",
                actor_type="system",
                actor_id=actor_id,
                payload={
                    "source": source,
                    "external_id": external_id,
                    "previous_hash": previous["snapshot_hash"],
                    "current_hash": snapshot_hash,
                },
            )
        self.events.append(
            event_type="EXTERNAL_SNAPSHOT_RECORDED",
            aggregate_type="external_state",
            aggregate_id=f"{source}:{external_id}",
            actor_type="system",
            actor_id=actor_id,
            payload={
                "source": source,
                "external_id": external_id,
                "snapshot_hash": snapshot_hash,
                "snapshot": snapshot,
            },
        )
        return True

    def list_agents(self) -> list[AgentDefinition]:
        with self.events.connect() as conn:
            rows = conn.execute("SELECT definition_json FROM agents ORDER BY agent_id").fetchall()
        return [AgentDefinition.model_validate_json(row["definition_json"]) for row in rows]

    def require_agent(self, agent_id: str) -> AgentDefinition:
        with self.events.connect() as conn:
            row = conn.execute(
                "SELECT definition_json FROM agents WHERE agent_id=?", (agent_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Unknown Agent: {agent_id}")
        return AgentDefinition.model_validate_json(row["definition_json"])

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return self._row("tasks", "task_id", task_id, json_columns={"contract_json": "contract"})

    def require_task(self, task_id: str) -> dict[str, Any]:
        row = self.get_task(task_id)
        if row is None:
            raise NotFoundError(f"Unknown Task: {task_id}")
        return row

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self._row(
            "runs",
            "run_id",
            run_id,
            json_columns={"progress_json": "progress", "result_json": "result"},
        )

    def require_run(self, run_id: str) -> dict[str, Any]:
        row = self.get_run(run_id)
        if row is None:
            raise NotFoundError(f"Unknown Run: {run_id}")
        return row

    def list_runs(self, *, status: str | None = None, agent_id: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status=?")
            params.append(status)
        if agent_id:
            clauses.append("agent_id=?")
            params.append(agent_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.events.connect() as conn:
            rows = conn.execute(f"SELECT * FROM runs{where} ORDER BY updated_sequence DESC", params).fetchall()
        return [self._decode_row(row, {"progress_json": "progress", "result_json": "result"}) for row in rows]

    def require_operation(self, operation_id: str) -> dict[str, Any]:
        row = self._row(
            "operations",
            "operation_id",
            operation_id,
            json_columns={"operation_json": "operation"},
        )
        if row is None:
            raise NotFoundError(f"Unknown operation: {operation_id}")
        return row

    def health(self) -> dict[str, Any]:
        valid, sequence, event_id = self.events.verify_chain()
        with self.events.connect() as conn:
            counts = {
                table: conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
                for table in (
                    "events",
                    "agents",
                    "tasks",
                    "runs",
                    "operations",
                    "artifacts",
                    "verifications",
                )
            }
        return {
            "status": "ok" if valid else "degraded",
            "event_chain_valid": valid,
            "first_invalid_sequence": sequence,
            "first_invalid_event_id": event_id,
            "counts": counts,
        }

    def _apply_operation(
        self,
        operation: GraphOperation,
        approved_event_id: str | None,
        *,
        conn: sqlite3.Connection,
    ) -> None:
        if operation.kind is OperationKind.UPSERT_NODE:
            event_type = "GRAPH_NODE_UPSERTED"
            payload = {
                "node_id": operation.target_id,
                "node_type": operation.target_type,
                "data": operation.changes,
                "expected_revision": operation.expected_revision,
            }
        elif operation.kind in {OperationKind.UPSERT_EDGE, OperationKind.LINK_DEPENDENCY}:
            required = {"source_id", "target_id", "edge_type"}
            if not required.issubset(operation.changes):
                raise ContractValidationError(f"Edge operation requires {sorted(required)}")
            event_type = "GRAPH_EDGE_UPSERTED"
            payload = {
                "edge_id": operation.target_id,
                "source_id": operation.changes["source_id"],
                "target_id": operation.changes["target_id"],
                "edge_type": operation.changes["edge_type"],
                "data": operation.changes.get("data", {}),
                "expected_revision": operation.expected_revision,
            }
        else:
            event_type = "GRAPH_CHANGE_RECORDED"
            payload = {"operation": operation.model_dump(mode="json")}
        self.events.append(
            event_type=event_type,
            aggregate_type=operation.target_type,
            aggregate_id=operation.target_id,
            actor_type="system",
            actor_id="graph-runtime",
            payload=payload,
            correlation_id=operation.target_id,
            causation_id=approved_event_id,
            conn=conn,
        )

    def _assert_expected_revision(
        self,
        operation: GraphOperation,
        *,
        conn: sqlite3.Connection,
    ) -> None:
        if operation.expected_revision is None:
            return
        if operation.kind is OperationKind.UPSERT_NODE:
            table = "graph_nodes"
            id_column = "node_id"
        elif operation.kind in {OperationKind.UPSERT_EDGE, OperationKind.LINK_DEPENDENCY}:
            table = "graph_edges"
            id_column = "edge_id"
        else:
            return
        row = conn.execute(
            f"SELECT revision FROM {table} WHERE {id_column}=?", (operation.target_id,)
        ).fetchone()
        actual = int(row["revision"]) if row else 0
        if operation.expected_revision != actual:
            raise ConflictError(
                f"Revision conflict for {operation.target_id}: "
                f"expected {operation.expected_revision}, current {actual}."
            )

    def _assert_current_run(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        task_id: str,
        agent_id: str,
        actor_id: str,
        *,
        allow_control: bool = False,
    ) -> None:
        run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if run is None:
            raise NotFoundError(f"Unknown Run: {run_id}")
        if run["task_id"] != task_id or run["agent_id"] != agent_id:
            raise PolicyDeniedError("Run update identity does not match the registered Run.")
        allowed_actors = {agent_id, "orchestrator"}
        if allow_control:
            allowed_actors.add(actor_id)
        if actor_id not in allowed_actors:
            raise PolicyDeniedError("An Agent may only update its own Run.")
        task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if task is None:
            raise NotFoundError(f"Unknown Task: {task_id}")
        if task["current_run_id"] != run_id or int(task["execution_epoch"]) != int(
            run["execution_epoch"]
        ):
            raise ConflictError("A superseded Run cannot change authoritative Task state.")
        if run["status"] in {"COMPLETED", "FAILED", "CANCELLED", "SUPERSEDED"}:
            raise ConflictError("A terminal Run cannot be updated.")

    def _workload(self) -> dict[str, int]:
        with self.events.connect() as conn:
            rows = conn.execute(
                """
                SELECT agent_id, COUNT(*) AS n FROM runs
                WHERE status IN ('PENDING', 'RUNNING', 'PAUSED', 'BLOCKED', 'REVIEW')
                GROUP BY agent_id
                """
            ).fetchall()
        return {row["agent_id"]: row["n"] for row in rows}

    def _external_snapshot(self, source: str, external_id: str) -> dict[str, Any] | None:
        with self.events.connect() as conn:
            row = conn.execute(
                "SELECT * FROM external_snapshots WHERE source=? AND external_id=?",
                (source, external_id),
            ).fetchone()
        return dict(row) if row else None

    def _row(
        self,
        table: str,
        id_column: str,
        value: str,
        *,
        json_columns: dict[str, str],
    ) -> dict[str, Any] | None:
        allowed = {"tasks", "runs", "operations"}
        if table not in allowed:
            raise ValueError("Unsupported projection table")
        with self.events.connect() as conn:
            row = conn.execute(f"SELECT * FROM {table} WHERE {id_column}=?", (value,)).fetchone()
        return self._decode_row(row, json_columns) if row else None

    @staticmethod
    def _decode_row(row: sqlite3.Row, json_columns: dict[str, str]) -> dict[str, Any]:
        result = dict(row)
        for source, target in json_columns.items():
            value = result.pop(source, None)
            result[target] = json.loads(value) if value else None
        return result

    @classmethod
    def _redact(cls, value: Any) -> Any:
        sensitive = {"authorization", "api_key", "apikey", "token", "password", "secret", "cookie"}
        if isinstance(value, dict):
            return {
                str(key): "[REDACTED]"
                if any(marker in str(key).lower().replace("-", "_") for marker in sensitive)
                else cls._redact(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls._redact(item) for item in value]
        return value
