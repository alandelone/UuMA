from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from uuma.kag_adapter import KagProjectionWorker, KagUnavailableError, KnowledgeReasoner
from uuma.knowledge_construction import KnowledgeConstructor
from uuma.knowledge_ingest import KnowledgeIngestor
from uuma.knowledge_models import (
    ClaimEvidenceLink,
    ClaimRecord,
    ConflictRecord,
    EntityRecord,
    EvidenceRecord,
    EvidenceStance,
    KnowledgePatch,
    PatchOperation,
    PatchOperationKind,
    RelationRecord,
    ResearchRun,
    SourceRecord,
)
from uuma.knowledge_service import KnowledgeService, StaleKnowledgeError

WISDOM = "wisdom-oldman"
ORCHESTRATOR = "orchestrator"


@pytest.fixture
def service(tmp_path: Path) -> KnowledgeService:
    return KnowledgeService(tmp_path / "wisdom.db")


def propose(
    service: KnowledgeService,
    kind: PatchOperationKind,
    target_id: str,
    changes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return service.propose_patch(
        KnowledgePatch(
            operations=[
                PatchOperation(kind=kind, target_id=target_id, changes=changes or {})
            ],
            rationale="Regression contract",
            proposed_by=WISDOM,
        ),
        actor_id=WISDOM,
    )


def accept(
    service: KnowledgeService, kind: PatchOperationKind, target_id: str
) -> dict[str, Any]:
    patch = propose(service, kind, target_id)
    return service.apply_patch(
        patch["patch_id"], actor_id=ORCHESTRATOR, review_note="Approved in fixture"
    )


class ProjectionBackend:
    def health(self) -> dict[str, Any]:
        return {"ready": True}

    def apply(self, _job: dict[str, Any]) -> dict[str, Any]:
        return {"applied": True}


class OfflineBackend(ProjectionBackend):
    def health(self) -> dict[str, Any]:
        raise KagUnavailableError("Offline fixture")


class RecordingExtractor(ProjectionBackend):
    def __init__(self) -> None:
        self.seen: list[str] = []

    def extract(self, chunks: list[dict[str, Any]]) -> dict[str, Any]:
        self.seen.extend(chunk["chunk_id"] for chunk in chunks)
        return {
            "chunks": [
                {"chunk_id": chunk["chunk_id"], "entities": [], "relations": []}
                for chunk in chunks
            ]
        }


def test_interrupted_projection_is_recovered(service: KnowledgeService) -> None:
    service.add_source(SourceRecord(locator="urn:test:crash", title="Fixture"), actor_id=WISDOM)
    job = service.store.pending_projection_jobs()[0]
    service.store.mark_projection_job(job["projection_job_id"], status="RUNNING")
    active_result = KagProjectionWorker(service, ProjectionBackend()).sync(recover=False)
    assert active_result["processed"] == 0
    assert active_result["lag"] == 1
    with service.store.transaction() as conn:
        conn.execute(
            "UPDATE projection_outbox SET updated_at = ? WHERE projection_job_id = ?",
            ("2000-01-01T00:00:00+00:00", job["projection_job_id"]),
        )

    reopened = KnowledgeService(service.store.path)
    result = KagProjectionWorker(reopened, ProjectionBackend()).sync(recover=False)

    assert result["applied"] == 1
    assert result["lag"] == 0


def test_reversal_refuses_to_break_accepted_relation(service: KnowledgeService) -> None:
    left = service.propose_entity(
        EntityRecord(canonical_name="A", entity_type="Thing"), actor_id=WISDOM
    )
    right = service.propose_entity(
        EntityRecord(canonical_name="B", entity_type="Thing"), actor_id=WISDOM
    )
    left_patch = accept(service, PatchOperationKind.ACCEPT_ENTITY, left["entity_id"])
    accept(service, PatchOperationKind.ACCEPT_ENTITY, right["entity_id"])
    relation = service.propose_relation(
        RelationRecord(
            subject_entity_id=left["entity_id"],
            predicate="dependsOn",
            object_entity_id=right["entity_id"],
        ),
        actor_id=WISDOM,
    )
    accept(service, PatchOperationKind.ACCEPT_RELATION, relation["relation_id"])

    with pytest.raises(StaleKnowledgeError, match="accepted relation"):
        service.reverse_patch(
            left_patch["patch_id"],
            actor_id=ORCHESTRATOR,
            review_note="Withdraw entity approval",
        )


def test_research_budget_is_enforced(service: KnowledgeService) -> None:
    run = service.start_research_run(
        ResearchRun(
            objective="Fixture research",
            satisfaction_rationale="Budget regression",
            budget_tier="QUICK",
            status="ACTIVE",
        ),
        actor_id=WISDOM,
    )
    updated = service.update_research_run(
        run["research_run_id"],
        {"active_seconds": 600, "sources_used": 10, "model_tokens_used": 50_000},
        actor_id=WISDOM,
    )

    assert updated["status"] == "BUDGET_EXHAUSTED"
    assert "active time" in updated["stop_reason"]


def test_fallback_preserves_conditions_conflicts_and_stance(
    service: KnowledgeService,
) -> None:
    source = service.add_source(
        SourceRecord(locator="urn:test:battery", title="Battery fixture"), actor_id=WISDOM
    )
    evidence = service.add_evidence(
        EvidenceRecord(
            source_id=source["source_id"],
            excerpt="Battery lifetime measurements under controlled conditions.",
        ),
        actor_id=WISDOM,
    )
    claims = []
    for cycles in (1_000, 200):
        claim = service.propose_claim(
            ClaimRecord(
                statement=f"Battery lifetime is {cycles} cycles.",
                qualifiers={"temperature": "25 C", "discharge_rate": "0.5 C"},
            ),
            actor_id=WISDOM,
        )
        service.link_evidence(
            ClaimEvidenceLink(
                claim_id=claim["claim_id"],
                evidence_id=evidence["evidence_id"],
                stance=EvidenceStance.SUPPORTS,
                rationale="Direct fixture support",
            ),
            actor_id=WISDOM,
        )
        accept(service, PatchOperationKind.ACCEPT_CLAIM, claim["claim_id"])
        claims.append(claim)
    service.record_conflict(
        ConflictRecord(
            claim_ids=[claim["claim_id"] for claim in claims],
            description="Unresolved battery lifetime disagreement",
        ),
        actor_id=WISDOM,
    )

    answer = KnowledgeReasoner(service, OfflineBackend()).answer(
        "Battery lifetime", recover=False
    )

    assert any("temperature=25 C" in condition for condition in answer["conditions"])
    assert answer["conflicts"]
    assert {citation["stance"] for citation in answer["citations"]} == {"SUPPORTS"}


def test_supersession_freezes_replacement_snapshot(service: KnowledgeService) -> None:
    old = service.propose_claim(ClaimRecord(statement="Old claim."), actor_id=WISDOM)
    replacement = service.propose_claim(
        ClaimRecord(statement="Reviewed replacement."), actor_id=WISDOM
    )
    accept(service, PatchOperationKind.ACCEPT_CLAIM, old["claim_id"])
    supersession = propose(
        service,
        PatchOperationKind.SUPERSEDE_CLAIM,
        old["claim_id"],
        {"replacement_claim_id": replacement["claim_id"]},
    )
    assert {change["target_id"] for change in supersession["diff"]} == {
        old["claim_id"],
        replacement["claim_id"],
    }
    intervening = propose(
        service,
        PatchOperationKind.UPDATE_CLAIM,
        replacement["claim_id"],
        {"statement": "Changed after supersession review."},
    )
    service.apply_patch(
        intervening["patch_id"], actor_id=ORCHESTRATOR, review_note="Independent edit"
    )

    with pytest.raises(StaleKnowledgeError):
        service.apply_patch(
            supersession["patch_id"],
            actor_id=ORCHESTRATOR,
            review_note="Apply stale supersession",
        )


def test_extraction_pages_reach_document_tail(
    service: KnowledgeService, tmp_path: Path
) -> None:
    ingested = KnowledgeIngestor(service, tmp_path / "content").ingest_text(
        locator="urn:test:long",
        title="Long fixture",
        text="alpha beta gamma " * 8_000,
        actor_id=WISDOM,
    )
    backend = RecordingExtractor()
    constructor = KnowledgeConstructor(service, backend)
    offset = 0
    while offset is not None:
        result = constructor.extract_document(
            ingested["document"]["document_id"],
            max_chunks=100,
            offset=offset,
            recover=False,
        )
        offset = result["next_offset"]

    assert len(set(backend.seen)) == len(ingested["chunks"])
    assert result["document_complete"] is True
