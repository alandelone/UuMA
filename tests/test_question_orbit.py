from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from uuma.knowledge_models import BudgetTier, GapRecord, GapType, OrbitStatus, SatisfactionLevel
from uuma.knowledge_service import KnowledgeService
from uuma.question_orbit import QuestionOrbitService, is_investigative


class QuestionOrbitTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.knowledge = KnowledgeService(Path(self.temporary.name) / "wisdom.db")
        self.orbits = QuestionOrbitService(self.knowledge)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _gap(self) -> str:
        gap = self.knowledge.add_gap(
            GapRecord(
                gap_type=GapType.WEAK_EVIDENCE,
                reason="Only one source supports the mechanism.",
                why_worthwhile="Independent evidence could change the answer.",
            ),
            actor_id="wisdom-oldman",
        )
        return gap["gap_id"]

    def test_start_is_atomic_audited_and_reuses_normalized_active_question(self) -> None:
        gap_id = self._gap()
        first = self.orbits.start(
            "How does heat affect battery ageing?",
            "Establish the causal mechanism and operating conditions.",
            SatisfactionLevel.PROVISIONAL,
            "Current evidence is incomplete.",
            actor_id="wisdom-oldman",
            gap_ids=[gap_id],
            uuma_task_id="task-1",
            uuma_run_id="run-1",
            notification_route={"platform": "telegram", "chat_id": "123"},
        )
        second = self.orbits.start(
            "  HOW does heat affect battery ageing?! ",
            "This duplicate should be reused.",
            SatisfactionLevel.INSUFFICIENT,
            "Still incomplete.",
            actor_id="wisdom-oldman",
            gap_ids=[gap_id],
        )

        self.assertTrue(first["created"])
        self.assertTrue(second["reused"])
        self.assertEqual(first["orbit"]["orbit_id"], second["orbit"]["orbit_id"])
        status = self.orbits.get(first["orbit"]["orbit_id"])
        self.assertEqual(status["orbit"]["budget_tier"], "QUICK")
        self.assertEqual(status["research_run"]["orbit_id"], first["orbit"]["orbit_id"])
        self.assertEqual(status["frontier"][0]["gap_id"], gap_id)
        self.assertTrue(self.knowledge.history()["chain_valid"])

    def test_preflight_only_starts_for_investigative_unresolved_question(self) -> None:
        gap_id = self._gap()
        answer = {
            "answer": "Current evidence is partial.",
            "satisfaction_level": "PROVISIONAL",
            "satisfaction_rationale": "One important gap remains.",
            "remaining_gap_ids": [gap_id],
        }
        started = self.orbits.preflight(
            "Why do these sources conflict about battery ageing?",
            answer,
            actor_id="wisdom-oldman",
        )
        not_started = self.orbits.preflight(
            "hello",
            answer,
            actor_id="wisdom-oldman",
        )
        sufficient = self.orbits.preflight(
            "Why do these sources conflict about battery ageing?",
            answer | {"satisfaction_level": "SUFFICIENT"},
            actor_id="wisdom-oldman",
        )

        self.assertTrue(started["orbit_started"])
        self.assertFalse(not_started["orbit_started"])
        self.assertFalse(sufficient["orbit_started"])
        self.assertTrue(is_investigative("比较这两种电池为什么老化速度不同"))

    def test_pause_resume_and_stop_preserve_history(self) -> None:
        started = self.orbits.start(
            "How should conflicting thermal evidence be resolved?",
            "Resolve the evidence conflict.",
            SatisfactionLevel.INSUFFICIENT,
            "The conflict is unresolved.",
            actor_id="wisdom-oldman",
            gap_ids=[self._gap()],
        )
        orbit_id = started["orbit"]["orbit_id"]
        paused = self.orbits.transition(
            orbit_id, OrbitStatus.PAUSED, actor_id="wisdom-oldman", reason="User paused."
        )
        resumed = self.orbits.transition(
            orbit_id, OrbitStatus.QUEUED, actor_id="wisdom-oldman"
        )
        stopped = self.orbits.transition(
            orbit_id, OrbitStatus.STOPPED, actor_id="wisdom-oldman", reason="User stopped."
        )

        self.assertEqual(paused["status"], "PAUSED")
        self.assertEqual(resumed["status"], "QUEUED")
        self.assertEqual(stopped["stop_reason"], "User stopped.")
        events = self.knowledge.history(orbit_id)
        self.assertEqual(events["count"], 4)
        self.assertTrue(events["chain_valid"])

    def test_wisdom_cannot_self_escalate_orbit_budget(self) -> None:
        with self.assertRaises(PermissionError):
            self.orbits.start(
                "Why do these sources disagree about ageing?",
                "Resolve the disagreement.",
                SatisfactionLevel.INSUFFICIENT,
                "Evidence is incomplete.",
                actor_id="wisdom-oldman",
                budget_tier=BudgetTier.DEEP,
            )


if __name__ == "__main__":
    unittest.main()
