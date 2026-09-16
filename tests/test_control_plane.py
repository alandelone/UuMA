from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from uuma.models import (
    CheckResult,
    GraphOperation,
    OperationKind,
    ResultContract,
    ResultOutcome,
    RiskLevel,
    RunProgress,
    TaskContract,
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

    def test_bootstrap_and_hash_chain(self) -> None:
        self.assertEqual(len(self.control.list_agents()), 5)
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
            "RUN_COMPLETED",
        )
        self.assertEqual(self.control.require_run(run.run_id)["status"], "COMPLETED")

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
        self.control.assign_task(task.task_id, "orchestrator", user_approved=True)

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
        self.assertEqual(self.control.health()["counts"]["agents"], 5)

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
