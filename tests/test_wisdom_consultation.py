from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from uuma.deployment_admission import set_admission
from uuma.models import (
    ResultContract,
    ResultOutcome,
    RunProgress,
    RunRegistration,
    RunStatus,
    TaskContract,
)
from uuma.service import ConflictError, ContractValidationError, ControlPlane, PolicyDeniedError
from uuma.settings import Settings
from uuma.wisdom_consultation import KnowledgeConsultationBroker, KnowledgeConsultationRequest


class WisdomConsultationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.settings = Settings(root, root / "uuma.db", root / "artifacts", root / "spool",
                                 root / "hermes.exe")
        self.control = ControlPlane(self.settings)
        self.control.bootstrap()
        self.parent = self.control.register_direct_run(
            "brainstormer", TaskContract(
                title="Business discussion", objective="Compare business assumptions.",
                source="direct", required_capabilities={"brainstorming"},
                required_tools={"worker_mcp"}, external_project_ref="project-coffee",
            ),
        )
        self.broker = KnowledgeConsultationBroker(self.control)
        self.request = KnowledgeConsultationRequest(
            parent_run_id=self.parent.run_id,
            parent_execution_epoch=self.parent.execution_epoch,
            project_id="project-coffee", topic_id="topic-demand",
            question="What evidence supports local demand?",
            purpose="Distinguish observations from hypothetical sales.",
            source_refs=["conversation:test:message-1"], idempotency_key="question-1",
        )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def register(self, **updates):
        request = self.request.model_copy(update=updates)
        return self.broker.register(request, actor_id="brainstormer")

    def start_child(self, receipt):
        self.control.report_progress(
            RunProgress(run_id=receipt["run_id"], task_id=receipt["task_id"],
                        agent_id="wisdom-oldman", status=RunStatus.RUNNING),
            actor_id="wisdom-oldman",
        )

    def test_registration_retains_provenance_without_knowledge_database(self):
        receipt = self.register()
        self.assertEqual(receipt["run_status"], "PENDING")
        self.assertEqual(receipt["parent_run_id"], self.parent.run_id)
        task = self.control.require_task(receipt["task_id"])
        self.assertEqual(task["assignee"], "wisdom-oldman")
        self.assertIn("conversation:test:message-1", task["contract"]["input_refs"])
        self.assertEqual(task["contract"]["requested_by"], "brainstormer")
        self.assertFalse(receipt["research_if_unknown"])
        self.assertFalse((self.settings.data_dir / "wisdom.db").exists())
        with self.control.events.connect() as conn:
            events = conn.execute(
                "SELECT event_type,actor_id FROM events WHERE aggregate_id=? ORDER BY sequence",
                (receipt["task_id"],),
            ).fetchall()
        self.assertEqual([(r[0], r[1]) for r in events],
                         [("TASK_CREATED", "brainstormer"), ("TASK_ASSIGNED", "brainstormer")])

    def test_identical_request_is_idempotent_and_conflicting_input_is_rejected(self):
        first = self.register()
        second = self.register()
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(len(self.control.list_runs(agent_id="wisdom-oldman")), 1)
        with self.assertRaises(ConflictError):
            self.register(question="A different question")

    def test_concurrent_registration_creates_only_one_child(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts = list(pool.map(lambda _: self.register(), range(4)))
        self.assertEqual(len({r["run_id"] for r in receipts}), 1)
        self.assertEqual(len(self.control.list_runs(agent_id="wisdom-oldman")), 1)

    def test_other_requesters_cannot_register_or_read_consultations(self):
        for actor in ["yonc", "wisdom-oldman", "orchestrator"]:
            with self.assertRaises(PolicyDeniedError):
                self.broker.register(self.request, actor_id=actor)
        receipt = self.register()
        with self.assertRaises(PolicyDeniedError):
            self.broker.status(receipt["run_id"], actor_id="yonc")

    def test_ordinary_brainstormer_run_is_not_a_consultation_status_handle(self):
        with self.assertRaises(PolicyDeniedError):
            self.broker.status(self.parent.run_id, actor_id="brainstormer")

    def test_stale_parent_epoch_and_wrong_project_create_no_child(self):
        with self.assertRaises(PolicyDeniedError):
            self.register(parent_execution_epoch=self.parent.execution_epoch + 1)
        with self.assertRaises(PolicyDeniedError):
            self.register(project_id="project-other")
        self.assertEqual(self.control.list_runs(agent_id="wisdom-oldman"), [])

    def test_paused_parent_cannot_create_or_dispatch_child(self):
        receipt = self.register()
        self.control.report_progress(
            RunProgress(run_id=self.parent.run_id, task_id=self.parent.task_id,
                        agent_id="brainstormer", status=RunStatus.PAUSED),
            actor_id="brainstormer",
        )
        with self.assertRaises(PolicyDeniedError):
            self.register(idempotency_key="another-question")
        with self.assertRaises(PolicyDeniedError):
            self.broker.authorize_dispatch(
                self.control.require_run(receipt["run_id"]),
                self.control.require_task(receipt["task_id"]), actor_id="brainstormer",
            )
        self.assertEqual(self.broker.status(receipt["run_id"], actor_id="brainstormer")["run_status"],
                         "PENDING")

    def test_disabled_wisdom_and_maintenance_pause_block_new_work(self):
        agent = self.control.require_agent("wisdom-oldman")
        self.control.register_agent(agent.model_copy(update={"enabled": False}), actor_id="user")
        with self.assertRaises(PolicyDeniedError):
            self.register()
        self.control.register_agent(agent, actor_id="user")
        set_admission(self.control, ["wisdom-oldman"], "a" * 64, True)
        with self.assertRaises(ConflictError):
            self.register()
        self.assertEqual(self.control.list_runs(agent_id="wisdom-oldman"), [])

    def test_existing_receipt_does_not_bypass_maintenance_on_dispatch(self):
        receipt = self.register()
        set_admission(self.control, ["wisdom-oldman"], "b" * 64, True)
        self.assertEqual(self.register()["run_id"], receipt["run_id"])
        with self.assertRaises(ConflictError):
            self.broker.authorize_dispatch(
                self.control.require_run(receipt["run_id"]),
                self.control.require_task(receipt["task_id"]), actor_id="brainstormer",
            )

    def test_general_worker_pending_registration_is_still_denied(self):
        receipt = self.register()
        with self.assertRaises(PolicyDeniedError):
            self.control.register_run(
                RunRegistration(task_id=receipt["task_id"], agent_id="wisdom-oldman",
                                execution_class="BACKGROUND", source="consultation",
                                initial_status="PENDING"), actor_id="brainstormer",
            )

    def test_uncited_completed_response_is_rejected(self):
        receipt = self.register()
        self.start_child(receipt)
        with self.assertRaises(ContractValidationError):
            self.control.submit_result(ResultContract(
                run_id=receipt["run_id"], task_id=receipt["task_id"], agent_id="wisdom-oldman",
                outcome=ResultOutcome.COMPLETED, summary="Unsupported answer.",
                partial_state={"consultation": {"status": "ANSWERED", "answer": "Trust me."}},
            ), actor_id="wisdom-oldman")

    def test_pending_reply_requires_saved_reference_and_cannot_claim_completed(self):
        receipt = self.register()
        self.start_child(receipt)
        for reference, outcome in [([], ResultOutcome.PARTIAL),
                                   (["question:saved"], ResultOutcome.COMPLETED)]:
            with self.assertRaises(ContractValidationError):
                self.control.submit_result(ResultContract(
                    run_id=receipt["run_id"], task_id=receipt["task_id"], agent_id="wisdom-oldman",
                    outcome=outcome, summary="More information is needed.", partial_state={
                        "consultation": {"status": "PENDING_RESEARCH", "answer": "Not enough data.",
                                         "research_refs": reference}},
                ), actor_id="wisdom-oldman")

    def test_grounded_reply_is_readable_and_remains_pending_review(self):
        receipt = self.register()
        self.start_child(receipt)
        self.control.submit_result(ResultContract(
            run_id=receipt["run_id"], task_id=receipt["task_id"], agent_id="wisdom-oldman",
            outcome=ResultOutcome.COMPLETED, summary="Located evidence returned.", partial_state={
                "consultation": {"status": "ANSWERED", "answer": "A qualified observation.",
                    "citations": [{"source_ref": "evidence:sample", "locator": "report.pdf:p3",
                                   "statement": "Observed demand, within the sampled area."}]}},
        ), actor_id="wisdom-oldman")
        reply = self.broker.status(receipt["run_id"], actor_id="brainstormer")
        self.assertEqual(reply["response"]["status"], "ANSWERED")
        self.assertTrue(reply["result_pending_review"])
        self.assertFalse(reply["canonical_knowledge_approved"])


if __name__ == "__main__":
    unittest.main()
