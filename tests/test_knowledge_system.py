from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from uuma.knowledge_models import (
    ClaimEvidenceLink,
    ClaimRecord,
    EvidenceRecord,
    EvidenceStance,
    GapRecord,
    GapType,
    KnowledgePatch,
    PatchOperation,
    PatchOperationKind,
    QuestionRecord,
    ResearchRun,
    ResearchRunStatus,
    SourceRecord,
    SourceType,
)
from uuma.knowledge_service import (
    KnowledgeAuthorizationError,
    KnowledgeService,
    StaleKnowledgeError,
)
from uuma.settings import Settings


class KnowledgeSystemTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.knowledge = KnowledgeService(self.root / "wisdom.db")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _claim_with_evidence(
        self, *, locator: str, excerpt: str, statement: str, conditions: dict[str, str]
    ) -> str:
        source = self.knowledge.add_source(
            SourceRecord(
                locator=locator,
                title=f"Battery test at {conditions['temperature']}",
                source_type=SourceType.DATASHEET,
                publisher="Example Cell Maker",
            ),
            actor_id="wisdom-oldman",
        )
        evidence = self.knowledge.add_evidence(
            EvidenceRecord(
                source_id=source["source_id"],
                excerpt=excerpt,
                location="Cycle life table",
                surrounding_context=f"Conditions: {conditions}",
            ),
            actor_id="wisdom-oldman",
        )
        claim = self.knowledge.propose_claim(
            ClaimRecord(statement=statement, qualifiers=conditions),
            actor_id="wisdom-oldman",
        )
        self.knowledge.link_evidence(
            ClaimEvidenceLink(
                claim_id=claim["claim_id"],
                evidence_id=evidence["evidence_id"],
                stance=EvidenceStance.SUPPORTS,
                rationale="The table states the cycle result under the recorded test conditions.",
            ),
            actor_id="wisdom-oldman",
        )
        return claim["claim_id"]

    def test_knowledge_database_is_separate_from_control_plane(self) -> None:
        settings = Settings(
            data_dir=self.root,
            database_path=self.root / "uuma.db",
            artifact_dir=self.root / "artifacts",
            ingest_spool_dir=self.root / "spool",
            hermes_executable=self.root / "hermes.exe",
        )
        self.assertEqual(settings.knowledge_database_path(), self.root / "wisdom.db")
        self.assertNotEqual(settings.knowledge_database_path(), settings.database_path)

    def test_context_dependent_claims_remain_distinct_and_searchable(self) -> None:
        warm_claim = self._claim_with_evidence(
            locator="https://example.test/warm-cell",
            excerpt="The cell retained 80% capacity after 6000 cycles.",
            statement="The test cell retained 80% capacity after 6000 cycles.",
            conditions={"temperature": "25 C", "c_rate": "0.5C", "depth_of_discharge": "80%"},
        )
        cold_claim = self._claim_with_evidence(
            locator="https://example.test/cold-cell",
            excerpt="Under cold fast-charge testing, 80% capacity was reached after 1800 cycles.",
            statement="The test cell retained 80% capacity after 1800 cycles.",
            conditions={"temperature": "-10 C", "c_rate": "2C", "depth_of_discharge": "100%"},
        )

        results = self.knowledge.search("6000 cycles")
        self.assertTrue(any(row["record"].get("claim_id") == warm_claim for row in results["results"]))
        self.assertEqual(self.knowledge.list_records("conflict")["count"], 0)

        gap = self.knowledge.add_gap(
            GapRecord(
                gap_type=GapType.MISSING_CONTEXT,
                reason="A user asking for cycle life without temperature and C-rate is underspecified.",
                why_worthwhile="Those conditions materially change which claim answers the question.",
                related_claim_ids=[warm_claim, cold_claim],
                current_knowledge="Two compatible, context-dependent test results are available.",
            ),
            actor_id="wisdom-oldman",
        )
        self.assertEqual(gap["gap_type"], "MISSING_CONTEXT")

    def test_patch_review_history_and_reversal(self) -> None:
        claim_id = self._claim_with_evidence(
            locator="https://example.test/cell",
            excerpt="The cell retained 80% capacity after 6000 cycles.",
            statement="The test cell retained 80% capacity after 6000 cycles.",
            conditions={"temperature": "25 C", "c_rate": "0.5C"},
        )
        patch = self.knowledge.propose_patch(
            KnowledgePatch(
                operations=[
                    PatchOperation(kind=PatchOperationKind.ACCEPT_CLAIM, target_id=claim_id)
                ],
                rationale="The candidate has directly located manufacturer evidence and conditions.",
                proposed_by="wisdom-oldman",
            ),
            actor_id="wisdom-oldman",
        )
        with self.assertRaises(KnowledgeAuthorizationError):
            self.knowledge.apply_patch(
                patch["patch_id"], actor_id="wisdom-oldman", review_note="self approval"
            )

        applied = self.knowledge.apply_patch(
            patch["patch_id"], actor_id="orchestrator", review_note="Reviewed evidence and scope."
        )
        self.assertEqual(applied["status"], "APPLIED")
        accepted = self.knowledge.get(claim_id)["record"]
        self.assertEqual(accepted["status"], "ACCEPTED")
        self.assertEqual(accepted["revision"], 2)

        history = self.knowledge.history(claim_id)
        self.assertTrue(history["chain_valid"])
        self.assertEqual([event["event_type"] for event in history["events"]], [
            "CLAIM_PROPOSED",
            "ACCEPT_CLAIM",
        ])

        reversed_patch = self.knowledge.reverse_patch(
            patch["patch_id"], actor_id="orchestrator", review_note="New review invalidated acceptance."
        )
        self.assertEqual(reversed_patch["status"], "REVERSED")
        restored = self.knowledge.get(claim_id)["record"]
        self.assertEqual(restored["status"], "CANDIDATE")
        self.assertEqual(restored["revision"], 1)
        self.assertTrue(self.knowledge.history()["chain_valid"])

    def test_event_rows_cannot_be_edited_or_deleted(self) -> None:
        self.knowledge.add_source(
            SourceRecord(locator="urn:test:source", title="Test source"),
            actor_id="wisdom-oldman",
        )
        with self.knowledge.store.connect() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE knowledge_events SET actor_id='changed' WHERE sequence=1")
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM knowledge_events WHERE sequence=1")

    def test_stale_patch_cannot_overwrite_newer_canonical_change(self) -> None:
        claim_id = self._claim_with_evidence(
            locator="https://example.test/stale",
            excerpt="Cycle life was measured at 25 C.",
            statement="Cycle life was measured at 25 C.",
            conditions={"temperature": "25 C"},
        )
        first = self.knowledge.propose_patch(
            KnowledgePatch(
                operations=[PatchOperation(kind=PatchOperationKind.ACCEPT_CLAIM, target_id=claim_id)],
                rationale="Accept the directly supported candidate.",
                proposed_by="wisdom-oldman",
            ),
            actor_id="wisdom-oldman",
        )
        stale = self.knowledge.propose_patch(
            KnowledgePatch(
                operations=[
                    PatchOperation(
                        kind=PatchOperationKind.UPDATE_CLAIM,
                        target_id=claim_id,
                        changes={"statement": "Cycle life was measured under room conditions."},
                    )
                ],
                rationale="Normalize the statement wording.",
                proposed_by="wisdom-oldman",
            ),
            actor_id="wisdom-oldman",
        )
        self.knowledge.apply_patch(
            first["patch_id"], actor_id="orchestrator", review_note="Evidence reviewed."
        )
        with self.assertRaises(StaleKnowledgeError):
            self.knowledge.apply_patch(
                stale["patch_id"], actor_id="orchestrator", review_note="This diff is now stale."
            )

    def test_research_run_persists_satisfaction_and_stop_state(self) -> None:
        question = self.knowledge.add_question(
            QuestionRecord(
                text="What operating conditions determine this cell's useful cycle life?",
                why_worth_knowing="Cycle count without test conditions is not reusable knowledge.",
            ),
            actor_id="wisdom-oldman",
        )
        gap = self.knowledge.add_gap(
            GapRecord(
                gap_type=GapType.MISSING_CONTEXT,
                reason="Temperature and charge rate are missing.",
                why_worthwhile="They materially change cycle-life interpretation.",
                question_id=question["question_id"],
            ),
            actor_id="wisdom-oldman",
        )
        run = self.knowledge.start_research_run(
            ResearchRun(
                objective="Resolve the boundary conditions for useful cycle-life claims.",
                root_question_id=question["question_id"],
                active_gap_ids=[gap["gap_id"]],
                status=ResearchRunStatus.ACTIVE,
                knowledge_satisfaction=0.4,
                satisfaction_rationale="Nominal cycle count is known; test context is not.",
            ),
            actor_id="wisdom-oldman",
        )
        updated = self.knowledge.update_research_run(
            run["research_run_id"],
            {
                "status": "COMPLETED",
                "active_gap_ids": [],
                "knowledge_satisfaction": 0.9,
                "satisfaction_rationale": "The important operating conditions are now evidenced.",
                "stop_reason": "No worthwhile gap remains for the current question.",
            },
            actor_id="wisdom-oldman",
        )
        self.assertEqual(updated["status"], "COMPLETED")
        self.assertEqual(self.knowledge.get(run["research_run_id"])["record"], updated)
        self.assertEqual(self.knowledge.list_records("research_run")["count"], 1)


if __name__ == "__main__":
    unittest.main()
