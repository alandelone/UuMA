from pathlib import Path
from uuid import uuid4

import pytest
from rstv4.approval import capture_user_approval
from rstv4.models import (
    DecisionProposalInput,
    EvidenceInput,
    EvidenceRelation,
    ResearchProjectInput,
    ResearchType,
    SourceCandidate,
)
from rstv4.service import RSTV4Service


def system_payload() -> dict:
    return {key: {} for key in ("requirements", "system_design", "implementation", "validation")}


def make_service(tmp_path: Path) -> RSTV4Service:
    return RSTV4Service(tmp_path)


def create_project(service: RSTV4Service) -> None:
    service.create_project(
        ResearchProjectInput(
            slug="radar-canopy",
            title="Radar canopy sensing",
            field="Agricultural sensing",
            research_type=ResearchType.ENGINEERING_SYSTEM,
            type_payload=system_payload(),
        )
    )


def grant(service: RSTV4Service, proposal: dict) -> None:
    capture_user_approval(
        service.root,
        profile="scholar",
        session_id="test-session",
        message_id=uuid4().hex,
        user_message=proposal["approval_phrase"],
    )


def test_gap_requires_evidence(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    create_project(service)
    with pytest.raises(ValueError, match="evidence"):
        service.propose_decision(
            "radar-canopy",
            DecisionProposalInput(kind="gap", statement="A gap", rationale="No evidence yet"),
        )


def test_approval_is_explicit_and_blueprint_is_grounded(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    create_project(service)
    papers = service.ingest_candidates(
        [
            SourceCandidate(
                source_provider="test",
                external_id="one",
                doi="10.1000/test",
                title="Canopy radar study",
                authors=["A. Researcher"],
                published_year=2025,
            )
        ]
    )
    evidence = service.add_evidence(
        "radar-canopy",
        EvidenceInput(
            paper_id=papers[0]["paper_id"],
            statement="Water content changes radar response.",
            excerpt="Water content significantly affected the radar response.",
            location="Results, p. 6",
            relation=EvidenceRelation.SUPPORTS,
            confidence=0.9,
            extractor_model="test-model",
            prompt_version="v1",
        ),
    )
    proposal = service.propose_decision(
        "radar-canopy",
        DecisionProposalInput(
            kind="gap",
            statement="Robust canopy sensing under moisture variation remains insufficiently validated.",
            rationale="Published response variation requires controlled validation.",
            evidence_ids=[evidence["evidence_id"]],
        ),
    )
    with pytest.raises(PermissionError, match="user-message approval grant"):
        service.approve_scientific_decision("radar-canopy", proposal["proposal_id"], 1)
    grant(service, proposal)
    approved = service.approve_scientific_decision("radar-canopy", proposal["proposal_id"], 1)
    assert approved["status"] == "APPROVED"
    blueprint = service.build_blueprint("radar-canopy")
    assert blueprint["approved"][0]["statement"].startswith("Robust canopy")
    assert blueprint["approved"][0]["provenance"]["evidence"][0]["paper"]["doi"] == "10.1000/test"


def test_superseding_gap_marks_downstream_rq_stale(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    create_project(service)
    papers = service.ingest_candidates(
        [SourceCandidate(source_provider="test", external_id="one", title="A study")]
    )
    evidence = service.add_evidence(
        "radar-canopy",
        EvidenceInput(
            paper_id=papers[0]["paper_id"],
            statement="Observed limitation",
            excerpt="Observed limitation",
            location="p. 1",
            relation=EvidenceRelation.SUPPORTS,
            confidence=0.8,
        ),
    )
    first_gap = service.propose_decision(
        "radar-canopy",
        DecisionProposalInput(
            kind="gap",
            statement="Original gap",
            rationale="Evidence",
            evidence_ids=[evidence["evidence_id"]],
        ),
    )
    grant(service, first_gap)
    service.approve_scientific_decision("radar-canopy", first_gap["proposal_id"], 1)
    rq = service.propose_decision(
        "radar-canopy",
        DecisionProposalInput(
            kind="research_question",
            statement="What conditions affect sensing?",
            rationale="Tests original gap",
            upstream_node_ids=[first_gap["node_id"]],
        ),
    )
    grant(service, rq)
    service.approve_scientific_decision("radar-canopy", rq["proposal_id"], 1)
    replacement = service.propose_decision(
        "radar-canopy",
        DecisionProposalInput(
            kind="gap",
            statement="Replacement gap",
            rationale="New evidence",
            evidence_ids=[evidence["evidence_id"]],
            supersedes_node_id=first_gap["node_id"],
        ),
    )
    grant(service, replacement)
    service.approve_scientific_decision("radar-canopy", replacement["proposal_id"], 1)
    assert service.get_decision("radar-canopy", rq["proposal_id"])["status"] == "APPROVED"
    impacted = service.impact_analysis("radar-canopy", first_gap["node_id"])
    assert impacted[0]["status"] == "STALE"


def test_approval_capture_rejects_non_user_boundary_and_is_single_use(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    create_project(service)
    proposal = service.propose_decision(
        "radar-canopy",
        DecisionProposalInput(kind="method", statement="Fixed method", rationale="Test"),
    )
    assert (
        capture_user_approval(
            service.root,
            profile="wisdom-oldman",
            session_id="session",
            message_id="message-1",
            user_message=proposal["approval_phrase"],
        )
        is None
    )
    with pytest.raises(PermissionError):
        service.approve_scientific_decision("radar-canopy", proposal["proposal_id"], 1)

    grant(service, proposal)
    service.approve_scientific_decision("radar-canopy", proposal["proposal_id"], 1)
    with pytest.raises(Exception, match="pending proposal"):
        service.approve_scientific_decision("radar-canopy", proposal["proposal_id"], 1)
