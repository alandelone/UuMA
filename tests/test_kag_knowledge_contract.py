from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from uuma.kag_adapter import (
    KagProjectionWorker,
    KagUnavailableError,
    KnowledgeReasoner,
)
from uuma.knowledge_construction import KnowledgeConstructor
from uuma.knowledge_ingest import KnowledgeIngestor
from uuma.knowledge_models import (
    ClaimEvidenceLink,
    ClaimRecord,
    EntityRecord,
    EvidenceRecord,
    EvidenceStance,
    KnowledgePatch,
    PatchOperation,
    PatchOperationKind,
    ReasoningMode,
    RelationRecord,
    SourceRecord,
)
from uuma.knowledge_service import KnowledgeService


class FakeKagBackend:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.jobs: list[dict[str, Any]] = []
        self.recoveries = 0

    def health(self) -> dict[str, Any]:
        if not self.available:
            raise KagUnavailableError("offline")
        return {"ready": True, "version": "0.8.0"}

    def recover(self) -> dict[str, Any]:
        self.recoveries += 1
        if not self.available:
            raise KagUnavailableError("still offline")
        return {"ready": True}

    def apply(self, job: dict[str, Any]) -> dict[str, Any]:
        self.jobs.append(job)
        return {"applied": True}

    def retrieve(self, query: str, mode: ReasoningMode) -> dict[str, Any]:
        return {
            "answer": f"KAG answer: {query}",
            "satisfaction_level": "SUFFICIENT",
            "result_refs": [],
            "steps": [{"step": 1, "operator": "GRAPH", "query": query}],
        }

    def extract(self, chunks: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "extractor": "fake KAG schema extractor",
            "chunks": [
                {
                    "chunk_id": item["chunk_id"],
                    "entities": [
                        {
                            "source_ref": "wisdom.db",
                            "name": "wisdom.db",
                            "entity_type": "KnowledgeStore",
                            "properties": {},
                        },
                        {
                            "source_ref": "OpenSPG KAG",
                            "name": "OpenSPG KAG",
                            "entity_type": "ProjectionRuntime",
                            "properties": {},
                        },
                    ],
                    "relations": [
                        {
                            "source_ref": "wisdom.db",
                            "predicate": "projectsTo",
                            "target_ref": "OpenSPG KAG",
                            "properties": {},
                        }
                    ],
                }
                for item in chunks
            ],
        }


class KagKnowledgeContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.service = KnowledgeService(self.root / "wisdom.db")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _candidate_claim(self) -> tuple[dict[str, Any], dict[str, Any]]:
        source = self.service.add_source(
            SourceRecord(locator="urn:test:kag-source", title="KAG source"),
            actor_id="wisdom-oldman",
        )
        evidence = self.service.add_evidence(
            EvidenceRecord(
                source_id=source["source_id"],
                excerpt="The governed KAG uses wisdom.db as canonical authority.",
                location="section 1",
            ),
            actor_id="wisdom-oldman",
        )
        claim = self.service.propose_claim(
            ClaimRecord(statement="wisdom.db is the canonical authority for KAG knowledge."),
            actor_id="wisdom-oldman",
        )
        self.service.link_evidence(
            ClaimEvidenceLink(
                claim_id=claim["claim_id"],
                evidence_id=evidence["evidence_id"],
                stance=EvidenceStance.SUPPORTS,
                rationale="The source directly states the authority boundary.",
            ),
            actor_id="wisdom-oldman",
        )
        return claim, evidence

    def _apply(self, kind: PatchOperationKind, target_id: str) -> dict[str, Any]:
        patch = self.service.propose_patch(
            KnowledgePatch(
                operations=[PatchOperation(kind=kind, target_id=target_id)],
                rationale="Reviewed for canonical projection.",
                proposed_by="wisdom-oldman",
            ),
            actor_id="wisdom-oldman",
        )
        return self.service.apply_patch(
            patch["patch_id"], actor_id="orchestrator", review_note="approved"
        )

    def test_candidates_do_not_leak_into_kag_projection(self) -> None:
        claim, _ = self._candidate_claim()
        jobs = self.service.store.pending_projection_jobs()
        types = [job["aggregate_type"] for job in jobs]
        self.assertEqual(types.count("source"), 1)
        self.assertEqual(types.count("evidence"), 1)
        self.assertNotIn("claim", types)
        self.assertNotIn("claim_evidence_link", types)

        patch = self._apply(PatchOperationKind.ACCEPT_CLAIM, claim["claim_id"])
        types = [job["aggregate_type"] for job in self.service.store.pending_projection_jobs()]
        self.assertIn("claim", types)
        self.assertIn("claim_evidence_link", types)

        self.service.reverse_patch(
            patch["patch_id"], actor_id="orchestrator", review_note="reversed for test"
        )
        delete_jobs = [
            job
            for job in self.service.store.pending_projection_jobs()
            if job["operation"] == "DELETE"
        ]
        self.assertEqual(
            {job["aggregate_type"] for job in delete_jobs},
            {"claim", "claim_evidence_link"},
        )

    def test_projection_worker_is_idempotent_at_outbox_boundary(self) -> None:
        self._candidate_claim()
        backend = FakeKagBackend()
        worker = KagProjectionWorker(self.service, backend)
        first = worker.sync()
        second = worker.sync()
        self.assertEqual(first["applied"], 2)
        self.assertEqual(second["processed"], 0)
        self.assertEqual(len(backend.jobs), 2)
        self.assertEqual(self.service.projection_health()["lag"], 0)
        with self.service.store.connect() as conn:
            attempts = [
                row["attempts"]
                for row in conn.execute("SELECT attempts FROM projection_outbox").fetchall()
            ]
        self.assertEqual(attempts, [1, 1])

    def test_accepted_relation_requires_accepted_dependencies(self) -> None:
        left = self.service.propose_entity(
            EntityRecord(canonical_name="wisdom.db", entity_type="KnowledgeStore"),
            actor_id="wisdom-oldman",
        )
        right = self.service.propose_entity(
            EntityRecord(canonical_name="OpenSPG KAG", entity_type="ProjectionRuntime"),
            actor_id="wisdom-oldman",
        )
        relation = self.service.propose_relation(
            RelationRecord(
                subject_entity_id=left["entity_id"],
                predicate="projectsTo",
                object_entity_id=right["entity_id"],
            ),
            actor_id="wisdom-oldman",
        )
        with self.assertRaises(ValueError):
            self._apply(PatchOperationKind.ACCEPT_RELATION, relation["relation_id"])
        self._apply(PatchOperationKind.ACCEPT_ENTITY, left["entity_id"])
        self._apply(PatchOperationKind.ACCEPT_ENTITY, right["entity_id"])
        self._apply(PatchOperationKind.ACCEPT_RELATION, relation["relation_id"])
        neighborhood = self.service.graph_neighborhood(left["entity_id"])
        self.assertEqual(len(neighborhood["entities"]), 2)
        self.assertEqual(neighborhood["relations"][0]["predicate"], "projectsTo")

    def test_degraded_reasoning_is_explicit_and_audited(self) -> None:
        claim, _ = self._candidate_claim()
        self._apply(PatchOperationKind.ACCEPT_CLAIM, claim["claim_id"])
        backend = FakeKagBackend(available=False)
        answer = KnowledgeReasoner(self.service, backend).answer(
            "What is the canonical authority for KAG knowledge?",
            requested_mode=ReasoningMode.AUTO,
            recover=True,
        )
        self.assertEqual(answer["runtime_status"], "DEGRADED_KAG")
        self.assertIn("wisdom.db", answer["answer"])
        self.assertEqual(backend.recoveries, 1)
        trace = self.service.get(answer["reasoning_trace_id"])["record"]
        self.assertTrue(trace["degraded"])
        self.assertEqual(trace["steps"][0]["operator"], "TEXT")

    def test_degraded_reasoning_can_cite_canonical_chunks_before_claim_review(self) -> None:
        ingestor = KnowledgeIngestor(self.service, self.root / "content")
        ingested = ingestor.ingest_text(
            locator="urn:test:chunk-fallback",
            title="Authority note",
            text="wisdom.db is the canonical source of truth; KAG is a disposable projection.",
            actor_id="wisdom-oldman",
        )
        answer = KnowledgeReasoner(self.service, FakeKagBackend(available=False)).answer(
            "wisdom.db canonical source truth disposable projection",
            requested_mode=ReasoningMode.AUTO,
            recover=False,
        )
        self.assertEqual(answer["runtime_status"], "DEGRADED_KAG")
        self.assertIn("wisdom.db", answer["answer"])
        self.assertTrue(
            any(
                citation.get("chunk_id") == ingested["chunks"][0]["chunk_id"]
                for citation in answer["citations"]
            )
        )

    def test_text_ingestion_is_content_addressed_and_versioned(self) -> None:
        ingestor = KnowledgeIngestor(self.service, self.root / "content")
        first = ingestor.ingest_text(
            locator="urn:test:manual",
            title="Manual",
            text="First governed knowledge version.",
            actor_id="wisdom-oldman",
        )
        same = ingestor.ingest_text(
            locator="urn:test:manual",
            title="Manual",
            text="First governed knowledge version.",
            actor_id="wisdom-oldman",
        )
        second = ingestor.ingest_text(
            locator="urn:test:manual",
            title="Manual",
            text="Second governed knowledge version with a preserved predecessor.",
            actor_id="wisdom-oldman",
        )
        self.assertFalse(first["unchanged"])
        self.assertTrue(same["unchanged"])
        self.assertEqual(second["document"]["version"], 2)
        self.assertEqual(
            second["document"]["previous_document_id"], first["document"]["document_id"]
        )
        self.assertTrue(Path(first["document"]["content_ref"]).is_file())

    def test_kag_construction_writes_candidates_before_projection(self) -> None:
        ingestor = KnowledgeIngestor(self.service, self.root / "content")
        ingested = ingestor.ingest_text(
            locator="urn:test:construction",
            title="Construction source",
            text="wisdom.db projects accepted knowledge to OpenSPG KAG.",
            actor_id="wisdom-oldman",
        )
        constructor = KnowledgeConstructor(self.service, FakeKagBackend())
        first = constructor.extract_document(
            ingested["document"]["document_id"], actor_id="wisdom-oldman"
        )
        second = constructor.extract_document(
            ingested["document"]["document_id"], actor_id="wisdom-oldman"
        )
        self.assertEqual(first["canonical_status"], "CANDIDATE")
        self.assertEqual(len(first["created"]["entities"]), 2)
        self.assertEqual(len(first["created"]["claims"]), 1)
        self.assertEqual(len(first["created"]["relations"]), 1)
        self.assertEqual(second["created"]["entities"], [])
        self.assertEqual(second["created"]["claims"], [])
        self.assertEqual(second["created"]["relations"], [])
        self.assertTrue(
            all(
                record["status"] == "CANDIDATE"
                for record in self.service.list_records("entity")["records"]
            )
        )
        pending_types = {
            job["aggregate_type"] for job in self.service.store.pending_projection_jobs()
        }
        self.assertNotIn("entity", pending_types)
        self.assertNotIn("claim", pending_types)
        self.assertNotIn("relation", pending_types)


if __name__ == "__main__":
    unittest.main()
