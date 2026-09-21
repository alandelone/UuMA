from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from uuma.models import (
    CheckResult,
    GraphOperation,
    OperationKind,
    ResultContract,
    ResultOutcome,
    RiskLevel,
    RunProgress,
    RunRegistration,
    RunStatus,
    TaskContract,
    VerificationDecision,
)
from uuma.service import ConflictError, ContractValidationError, ControlPlane, PolicyDeniedError
from uuma.settings import Settings


class ControlPlaneTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.settings = Settings(
            data_dir=root,
            database_path=root / "uuma.db",
            artifact_dir=root / "artifacts",
            ingest_spool_dir=root / "spool",
            hermes_executable=root / "hermes.exe",
        )
        self.control = ControlPlane(self.settings)
        self.control.bootstrap()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def task(**changes) -> TaskContract:
        values = {
            "title": "Explore a product boundary",
            "objective": "Produce a decision-ready analysis.",
            "required_capabilities": {"brainstorming"},
            "required_tools": {"worker_mcp"},
            "acceptance_checks": ["scope-defined"],
        }
        values.update(changes)
        return TaskContract(**values)

    @staticmethod
    def create_legacy_database(path: Path, contracts: tuple[TaskContract, ...]) -> None:
        conn = sqlite3.connect(path)
        try:
            conn.executescript(
                """
                CREATE TABLE events (
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
                CREATE TABLE tasks (
                    task_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    assignee TEXT,
                    contract_json TEXT NOT NULL,
                    external_ref TEXT,
                    updated_sequence INTEGER NOT NULL
                );
                CREATE TABLE runs (
                    run_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    execution_class TEXT NOT NULL,
                    external_run_ref TEXT,
                    progress_json TEXT NOT NULL,
                    result_json TEXT,
                    updated_sequence INTEGER NOT NULL
                );
                """
            )
            for sequence, contract in enumerate(contracts, start=1):
                payload = contract.model_dump(mode="json")
                conn.execute(
                    """
                    INSERT INTO events(
                        event_id, event_type, aggregate_type, aggregate_id,
                        actor_type, actor_id, occurred_at, correlation_id,
                        causation_id, payload_json, metadata_json,
                        previous_hash, event_hash
                    ) VALUES (?, 'TASK_CREATED', 'task', ?, 'agent', 'orchestrator',
                              ?, ?, NULL, ?, '{}', ?, ?)
                    """,
                    (
                        f"evt_legacy_{sequence}",
                        contract.task_id,
                        contract.created_at.isoformat(),
                        contract.task_id,
                        json.dumps({"contract": payload}),
                        "0" * 64,
                        f"{sequence:064x}",
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO tasks(
                        task_id, title, status, assignee, contract_json,
                        external_ref, updated_sequence
                    ) VALUES (?, ?, 'TODO', NULL, ?, NULL, ?)
                    """,
                    (
                        contract.task_id,
                        contract.title,
                        contract.model_dump_json(),
                        sequence,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def test_bootstrap_and_hash_chain(self) -> None:
        self.assertEqual(len(self.control.list_agents()), 6)
        health = self.control.health()
        self.assertEqual(health["status"], "ok")
        self.assertTrue(health["event_chain_valid"])

    def test_event_rows_are_immutable(self) -> None:
        with self.control.events.connect() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE events SET actor_id='changed' WHERE sequence=1")
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM events WHERE sequence=1")

    def test_route_unique_specialist(self) -> None:
        task = self.control.create_task(self.task(), actor_id="orchestrator")
        decision = self.control.route_task(task.task_id)
        self.assertEqual(decision.selected_agent, "brainstormer")
        self.assertFalse(decision.requires_orchestrator)

    def test_route_project_graph_work_to_yonc(self) -> None:
        task = self.control.create_task(
            self.task(
                required_capabilities={"project_graph"},
                required_tools={"yonc_project"},
            ),
            actor_id="orchestrator",
        )
        decision = self.control.route_task(task.task_id)
        self.assertEqual(decision.selected_agent, "yonc")

    def test_mixed_orchestrator_tool_contract_requires_split(self) -> None:
        task = self.control.create_task(
            self.task(required_tools={"copycat"}), actor_id="orchestrator"
        )
        decision = self.control.route_task(task.task_id)
        self.assertIsNone(decision.selected_agent)
        self.assertTrue(decision.requires_orchestrator)

    def test_prohibited_capability_is_always_denied(self) -> None:
        task = self.control.create_task(
            self.task(required_capabilities={"delete_files"}), actor_id="orchestrator"
        )
        decision = self.control.route_task(task.task_id)
        self.assertTrue(decision.denied)
        with self.assertRaises(PolicyDeniedError):
            self.control.assign_task(task.task_id, "orchestrator", user_approved=True)

    def test_user_visible_structure_requires_approval(self) -> None:
        task = self.control.create_task(
            self.task(user_visible_structure_change=True), actor_id="orchestrator"
        )
        with self.assertRaises(PolicyDeniedError):
            self.control.assign_task(task.task_id, "brainstormer")
        self.control.approve_task(task.task_id)
        self.control.assign_task(task.task_id, "brainstormer")
        self.assertEqual(self.control.require_task(task.task_id)["status"], "READY")

    def test_direct_run_and_contract_validated_completion(self) -> None:
        task = self.task(source="direct")
        run = self.control.register_direct_run("brainstormer", task)
        result = ResultContract(
            run_id=run.run_id,
            task_id=task.task_id,
            agent_id="brainstormer",
            outcome=ResultOutcome.COMPLETED,
            summary="The product boundary is defined.",
            checks=[CheckResult(name="scope-defined", passed=True)],
        )
        self.assertEqual(
            self.control.submit_result(result, actor_id="brainstormer"),
            "RUN_RESULT_SUBMITTED",
        )
        self.assertEqual(self.control.require_run(run.run_id)["status"], "REVIEW")
        self.assertEqual(self.control.require_task(task.task_id)["status"], "REVIEW")

        context = self.control.verification_context(run.run_id)
        record = self.control.verify_result(
            VerificationDecision(
                run_id=run.run_id,
                task_id=task.task_id,
                acceptance_digest=context["acceptance_digest"],
                result_digest=context["result_digest"],
                approved=True,
                checks=[CheckResult(name="scope-defined", passed=True)],
            ),
            actor_id="orchestrator",
        )
        self.assertTrue(record.approved)
        self.assertEqual(self.control.require_run(run.run_id)["status"], "COMPLETED")
        self.assertEqual(self.control.require_task(task.task_id)["status"], "COMPLETED")
        verified_context = self.control.verification_context(run.run_id)
        self.assertEqual(len(verified_context["verifications"]), 1)
        self.assertEqual(
            verified_context["verifications"][0]["verifier_id"],
            "orchestrator",
        )
        event_count = self.control.health()["counts"]["events"]
        self.assertEqual(self.control.events.rebuild_projections(), event_count)
        self.assertEqual(self.control.require_run(run.run_id)["status"], "COMPLETED")
        with self.control.events.connect() as conn:
            verification_count = conn.execute(
                "SELECT COUNT(*) AS count FROM verifications WHERE run_id=?",
                (run.run_id,),
            ).fetchone()["count"]
        self.assertEqual(verification_count, 1)

    def test_completion_fails_when_acceptance_check_is_missing(self) -> None:
        task = self.task(source="direct")
        run = self.control.register_direct_run("brainstormer", task)
        result = ResultContract(
            run_id=run.run_id,
            task_id=task.task_id,
            agent_id="brainstormer",
            outcome=ResultOutcome.COMPLETED,
            summary="Done without the required evidence.",
        )
        with self.assertRaises(ContractValidationError):
            self.control.submit_result(result, actor_id="brainstormer")

    def test_partial_result_enters_review(self) -> None:
        task = self.task(source="direct")
        run = self.control.register_direct_run("brainstormer", task)
        result = ResultContract(
            run_id=run.run_id,
            task_id=task.task_id,
            agent_id="brainstormer",
            outcome=ResultOutcome.PARTIAL,
            summary="Useful partial output needs review.",
        )
        self.control.submit_result(result, actor_id="brainstormer")
        self.assertEqual(self.control.require_run(run.run_id)["status"], "REVIEW")

    def test_worker_cannot_block_another_workers_run(self) -> None:
        task = self.task(source="direct")
        run = self.control.register_direct_run("brainstormer", task)
        progress = RunProgress(
            run_id=run.run_id,
            task_id=task.task_id,
            agent_id="brainstormer",
            blocker="Waiting for evidence.",
        )
        with self.assertRaises(PolicyDeniedError):
            self.control.block_run(progress, actor_id="scholar")

    def test_committing_action_requires_explicit_approval(self) -> None:
        task = self.control.create_task(
            self.task(
                required_capabilities={"general_assistance"},
                required_tools={"control_mcp"},
                risk_level=RiskLevel.COMMITTING,
            ),
            actor_id="orchestrator",
        )
        with self.assertRaises(PolicyDeniedError):
            self.control.assign_task(task.task_id, "orchestrator")
        with self.assertRaises(PolicyDeniedError):
            self.control.assign_task(task.task_id, "orchestrator", user_approved=True)
        self.control.approve_task(task.task_id)
        self.control.assign_task(task.task_id, "orchestrator")

    def test_graph_revision_conflict_and_rebuild(self) -> None:
        first = GraphOperation(
            kind=OperationKind.UPSERT_NODE,
            target_type="topic",
            target_id="topic-1",
            expected_revision=0,
            changes={"title": "Initial"},
            rationale="Create the topic.",
            requested_by="brainstormer",
            requires_user_approval=False,
        )
        self.control.propose_operation(first)
        self.assertEqual(
            self.control.require_operation(first.operation_id)["status"],
            "PENDING_APPROVAL",
        )
        with self.control.events.connect() as conn:
            self.assertIsNone(
                conn.execute(
                    "SELECT 1 FROM graph_nodes WHERE node_id='topic-1'"
                ).fetchone()
            )
        self.control.approve_operation(first.operation_id)
        stale = GraphOperation(
            kind=OperationKind.UPSERT_NODE,
            target_type="topic",
            target_id="topic-1",
            expected_revision=0,
            changes={"title": "Stale update"},
            rationale="Attempt a stale update.",
            requested_by="brainstormer",
            requires_user_approval=False,
        )
        with self.assertRaises(ConflictError):
            self.control.propose_operation(stale)
        event_count = self.control.health()["counts"]["events"]
        self.assertEqual(self.control.events.rebuild_projections(), event_count)
        self.assertEqual(self.control.health()["counts"]["agents"], 6)

    def test_heartbeat_cannot_write_terminal_or_review_status(self) -> None:
        task = self.task(source="direct")
        run = self.control.register_direct_run("brainstormer", task)
        for status in (
            RunStatus.BLOCKED,
            RunStatus.REVIEW,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        ):
            with self.subTest(status=status), self.assertRaises(ContractValidationError):
                self.control.report_progress(
                    RunProgress(
                        run_id=run.run_id,
                        task_id=task.task_id,
                        agent_id="brainstormer",
                        status=status,
                    ),
                    actor_id="brainstormer",
                )
        self.assertEqual(self.control.require_run(run.run_id)["status"], "RUNNING")

    def test_concurrent_graph_revision_allows_only_one_approval(self) -> None:
        operations = [
            GraphOperation(
                kind=OperationKind.UPSERT_NODE,
                target_type="topic",
                target_id="concurrent-topic",
                expected_revision=0,
                changes={"winner": winner},
                rationale="Exercise compare-and-swap semantics.",
                requested_by="brainstormer",
                requires_user_approval=False,
            )
            for winner in ("one", "two")
        ]
        for operation in operations:
            self.control.propose_operation(operation)

        controls = (ControlPlane(self.settings), ControlPlane(self.settings))

        def approve(index: int) -> str:
            try:
                controls[index].approve_operation(operations[index].operation_id)
            except ConflictError:
                return "conflict"
            return "approved"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(approve, (0, 1)))
        self.assertEqual(sorted(outcomes), ["approved", "conflict"])
        with self.control.events.connect() as conn:
            row = conn.execute(
                "SELECT revision FROM graph_nodes WHERE node_id='concurrent-topic'"
            ).fetchone()
        self.assertEqual(row["revision"], 1)

    def test_takeover_epoch_rejects_stale_run_after_restart(self) -> None:
        task = self.task(source="direct")
        old_run = self.control.register_direct_run("brainstormer", task)
        replacement = self.control.register_run(
            RunRegistration(
                task_id=task.task_id,
                agent_id="brainstormer",
                execution_class=task.execution_class,
                source="orchestrator",
            ),
            actor_id="orchestrator",
            takeover=True,
        )
        self.assertGreater(replacement.execution_epoch, old_run.execution_epoch)
        self.assertEqual(self.control.require_run(old_run.run_id)["status"], "SUPERSEDED")

        replacement_result = ResultContract(
            run_id=replacement.run_id,
            task_id=task.task_id,
            agent_id="brainstormer",
            outcome=ResultOutcome.COMPLETED,
            summary="Replacement Run completed authoritatively.",
            checks=[CheckResult(name="scope-defined", passed=True)],
        )
        self.control.submit_result(replacement_result, actor_id="brainstormer")
        context = self.control.verification_context(replacement.run_id)
        self.control.verify_result(
            VerificationDecision(
                run_id=replacement.run_id,
                task_id=task.task_id,
                acceptance_digest=context["acceptance_digest"],
                result_digest=context["result_digest"],
                approved=True,
                checks=[CheckResult(name="scope-defined", passed=True)],
            ),
            actor_id="orchestrator",
        )

        restarted = ControlPlane(self.settings)
        with self.assertRaises(ConflictError):
            restarted.report_progress(
                RunProgress(
                    run_id=old_run.run_id,
                    task_id=task.task_id,
                    agent_id="brainstormer",
                    current_step="late heartbeat",
                ),
                actor_id="brainstormer",
            )
        with self.assertRaises(ConflictError):
            restarted.block_run(
                RunProgress(
                    run_id=old_run.run_id,
                    task_id=task.task_id,
                    agent_id="brainstormer",
                    blocker="Late stale blocker.",
                ),
                actor_id="brainstormer",
            )
        with self.assertRaises(ConflictError):
            restarted.submit_result(
                ResultContract(
                    run_id=old_run.run_id,
                    task_id=task.task_id,
                    agent_id="brainstormer",
                    outcome=ResultOutcome.COMPLETED,
                    summary="Late stale result.",
                    checks=[CheckResult(name="scope-defined", passed=True)],
                ),
                actor_id="brainstormer",
            )
        self.assertEqual(
            restarted.require_task(task.task_id)["current_run_id"],
            replacement.run_id,
        )
        self.assertEqual(restarted.require_task(task.task_id)["status"], "COMPLETED")

    def test_atomic_idempotency_reuses_same_task_and_rejects_changed_request(self) -> None:
        contracts = (
            self.task(idempotency_key="stable-key"),
            self.task(idempotency_key="stable-key"),
        )
        controls = (ControlPlane(self.settings), ControlPlane(self.settings))

        def create(index: int) -> str:
            return controls[index].create_task(
                contracts[index], actor_id="orchestrator"
            ).task_id

        with ThreadPoolExecutor(max_workers=2) as executor:
            task_ids = list(executor.map(create, (0, 1)))
        self.assertEqual(task_ids[0], task_ids[1])
        with self.control.events.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM tasks WHERE idempotency_key='stable-key'"
            ).fetchone()["count"]
        self.assertEqual(count, 1)

        restarted = ControlPlane(self.settings)
        retry = restarted.create_task(
            self.task(idempotency_key="stable-key"),
            actor_id="orchestrator",
        )
        self.assertEqual(retry.task_id, task_ids[0])
        with self.assertRaises(ConflictError):
            restarted.create_task(
                self.task(
                    idempotency_key="stable-key",
                    objective="A different request must not reuse the key.",
                ),
                actor_id="orchestrator",
            )

    def test_legacy_schema_migration_preserves_task_and_backfills_identity(self) -> None:
        root = Path(self.temporary.name) / "legacy"
        root.mkdir()
        database = root / "uuma.db"
        legacy = self.task(idempotency_key="legacy-key")
        self.create_legacy_database(database, (legacy,))
        settings = Settings(
            data_dir=root,
            database_path=database,
            artifact_dir=root / "artifacts",
            ingest_spool_dir=root / "spool",
            hermes_executable=root / "hermes.exe",
        )

        migrated = ControlPlane(settings)
        task = migrated.require_task(legacy.task_id)
        self.assertEqual(task["idempotency_key"], "legacy-key")
        self.assertEqual(task["idempotency_scope"], "orchestrator:orchestrator")
        retry = migrated.create_task(
            self.task(idempotency_key="legacy-key"),
            actor_id="orchestrator",
        )
        self.assertEqual(retry.task_id, legacy.task_id)
        with migrated.events.connect() as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)")}
        self.assertTrue(
            {"request_digest", "current_run_id", "execution_epoch", "state_version"}
            <= columns
        )

    def test_legacy_migration_fails_closed_on_duplicate_idempotency(self) -> None:
        root = Path(self.temporary.name) / "legacy-duplicate"
        root.mkdir()
        database = root / "uuma.db"
        self.create_legacy_database(
            database,
            (
                self.task(idempotency_key="duplicate-key"),
                self.task(idempotency_key="duplicate-key"),
            ),
        )
        settings = Settings(
            data_dir=root,
            database_path=database,
            artifact_dir=root / "artifacts",
            ingest_spool_dir=root / "spool",
            hermes_executable=root / "hermes.exe",
        )
        with self.assertRaisesRegex(RuntimeError, "Ambiguous task idempotency history"):
            ControlPlane(settings)

    def test_worker_self_checks_cannot_complete_without_independent_verifier(self) -> None:
        task = self.task(source="direct")
        run = self.control.register_direct_run("brainstormer", task)
        result = ResultContract(
            run_id=run.run_id,
            task_id=task.task_id,
            agent_id="brainstormer",
            outcome=ResultOutcome.COMPLETED,
            summary="Worker claims its own work passed.",
            checks=[CheckResult(name="scope-defined", passed=True)],
        )
        self.control.submit_result(result, actor_id="brainstormer")
        context = self.control.verification_context(run.run_id)
        decision = VerificationDecision(
            run_id=run.run_id,
            task_id=task.task_id,
            acceptance_digest=context["acceptance_digest"],
            result_digest=context["result_digest"],
            approved=True,
            checks=[CheckResult(name="scope-defined", passed=True)],
        )
        with self.assertRaises(PolicyDeniedError):
            self.control.verify_result(decision, actor_id="brainstormer")
        self.assertEqual(self.control.require_run(run.run_id)["status"], "REVIEW")

    def test_changed_result_invalidates_prior_verification_context(self) -> None:
        task = self.task(source="direct")
        run = self.control.register_direct_run("brainstormer", task)
        first = ResultContract(
            run_id=run.run_id,
            task_id=task.task_id,
            agent_id="brainstormer",
            outcome=ResultOutcome.COMPLETED,
            summary="First result.",
            checks=[CheckResult(name="scope-defined", passed=True)],
        )
        self.control.submit_result(first, actor_id="brainstormer")
        stale_context = self.control.verification_context(run.run_id)
        second = first.model_copy(update={"summary": "Revised result."})
        self.control.submit_result(second, actor_id="brainstormer")
        with self.assertRaises(ConflictError):
            self.control.verify_result(
                VerificationDecision(
                    run_id=run.run_id,
                    task_id=task.task_id,
                    acceptance_digest=stale_context["acceptance_digest"],
                    result_digest=stale_context["result_digest"],
                    approved=True,
                    checks=[CheckResult(name="scope-defined", passed=True)],
                ),
                actor_id="orchestrator",
            )

    def test_audit_ingest_is_idempotent_and_redacted(self) -> None:
        event = {
            "uuma_event_id": "hermes_fixed",
            "hook": "pre_tool_call",
            "session_id": "session-1",
            "api_key": "do-not-store",
            "nested": {"Authorization": "Bearer secret"},
        }
        self.assertTrue(self.control.ingest_hermes_event(event, profile="scholar"))
        self.assertFalse(self.control.ingest_hermes_event(event, profile="scholar"))
        stored = self.control.events.get_event("hermes_fixed")
        self.assertIsNotNone(stored)
        observer = stored.payload["observer"]
        self.assertEqual(observer["api_key"], "[REDACTED]")
        self.assertEqual(observer["nested"]["Authorization"], "[REDACTED]")


if __name__ == "__main__":
    unittest.main()
