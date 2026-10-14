import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from rstv4.approval import capture_user_approval
from rstv4.database import initialize_project
from rstv4.models import (
    DecisionProposalInput,
    EvidenceInput,
    FoundationVersionInput,
    ManuscriptInput,
    ManuscriptStatusInput,
    ResearchProjectInput,
    ResearchType,
    SourceCandidate,
    SubmissionEventInput,
    TopicInput,
    TrackInput,
)
from rstv4.service import RSTV4Service


def system_payload() -> dict:
    return {key: {} for key in ("requirements", "system_design", "implementation", "validation")}


def create_project(service: RSTV4Service, slug: str) -> dict:
    return service.create_project(
        ResearchProjectInput(
            slug=slug,
            title=f"Project {slug}",
            field="Rural electrification",
            research_type=ResearchType.ENGINEERING_SYSTEM,
            type_payload=system_payload(),
        )
    )


def test_topics_are_reusable_and_project_scopes_remain_independent(tmp_path: Path) -> None:
    service = RSTV4Service(tmp_path)
    create_project(service, "alpha")
    create_project(service, "beta")
    topic = service.create_topic(TopicInput(name="Energy justice"))

    service.associate_project_topic("alpha", topic["topic_id"], scope="Household access")
    service.associate_project_topic("beta", topic["topic_id"], scope="Tariff fairness")

    assert service.get_project("alpha")["topics"][0]["scope"] == "Household access"
    assert service.get_project("beta")["topics"][0]["scope"] == "Tariff fairness"
    assert service.create_topic(TopicInput(name="  energy JUSTICE "))["topic_id"] == topic["topic_id"]


def test_foundation_versions_are_immutable_and_updates_are_opt_in(tmp_path: Path) -> None:
    service = RSTV4Service(tmp_path)
    project = create_project(service, "alpha")
    track_id = project["tracks"][0]["track_id"]
    topic = service.create_topic(TopicInput(name="Off-grid trading"))
    service.associate_project_topic("alpha", topic["topic_id"])

    v1 = service.publish_foundation(
        FoundationVersionInput(title="Trading landscape", topic_ids=[topic["topic_id"]])
    )
    adopted = service.adopt_foundation("alpha", track_id, v1["foundation_id"], 1)
    v2 = service.publish_foundation(
        FoundationVersionInput(
            title="Trading landscape",
            retrieval_scope={"through": "2026-09"},
            topic_ids=[topic["topic_id"]],
        ),
        v1["foundation_id"],
    )

    assert adopted["snapshot"]["content_digest"] == v1["content_digest"]
    assert service.check_foundation_updates("alpha", track_id)[0]["latest_version"] == 2
    service.adopt_foundation_update("alpha", track_id, v1["foundation_id"], v2["version"])
    assert service.check_foundation_updates("alpha", track_id) == []


def test_tracks_scope_blueprints_and_ideas_require_an_approved_gap(tmp_path: Path) -> None:
    service = RSTV4Service(tmp_path)
    project = create_project(service, "alpha")
    default_track = project["tracks"][0]["track_id"]
    topic = service.create_topic(TopicInput(name="Affordability"))
    service.associate_project_topic("alpha", topic["topic_id"])
    second = service.create_track(
        "alpha", TrackInput(title="Payment models", topic_ids=[topic["topic_id"]])
    )

    with pytest.raises(ValueError, match="track_id is required"):
        service.build_blueprint("alpha")
    with pytest.raises(ValueError, match="approved gap"):
        service.propose_decision(
            "alpha",
            DecisionProposalInput(
                kind="idea",
                statement="Use prepaid credits",
                rationale="Candidate mechanism",
                upstream_node_ids=[
                    service.propose_decision(
                        "alpha",
                        DecisionProposalInput(
                            kind="method",
                            statement="Survey households",
                            rationale="Measure affordability",
                            track_id=default_track,
                        ),
                    )["node_id"]
                ],
                track_id=second["track_id"],
            ),
        )

    assert service.build_blueprint("alpha", second["track_id"])["track"]["track_id"] == second["track_id"]
    path = tmp_path / "projects" / "alpha" / "research.db"
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM blueprint_snapshots").fetchone()[0] == 0
    snapshot = service.snapshot_blueprint("alpha", second["track_id"])
    assert snapshot["revision"] == 1


def test_manuscripts_have_independent_status_versions_and_submission_history(tmp_path: Path) -> None:
    service = RSTV4Service(tmp_path)
    project = create_project(service, "alpha")
    track_id = project["tracks"][0]["track_id"]
    catalog_paper = service.ingest_candidates(
        [SourceCandidate(source_provider="test", external_id="one", title="Energy study")]
    )[0]
    evidence = service.add_evidence(
        "alpha",
        EvidenceInput(
            paper_id=catalog_paper["paper_id"],
            statement="Observed affordability constraint",
            excerpt="Households reported an affordability constraint.",
            location="Results",
            relation="SUPPORTS",
            confidence=0.9,
        ),
    )
    gap = service.propose_decision(
        "alpha",
        DecisionProposalInput(
            kind="gap",
            statement="Payment models remain under-tested.",
            rationale="Evidence shows a constraint.",
            evidence_ids=[evidence["evidence_id"]],
            track_id=track_id,
        ),
    )
    capture_user_approval(
        service.root,
        profile="scholar",
        session_id="test",
        message_id=uuid4().hex,
        user_message=gap["approval_phrase"],
    )
    service.approve_scientific_decision("alpha", gap["proposal_id"], 1)

    paper_a = service.create_manuscript(
        "alpha",
        ManuscriptInput(
            track_id=track_id,
            title="Mechanism paper",
            node_ids=[gap["node_id"]],
            evidence_ids=[evidence["evidence_id"]],
        ),
    )
    paper_b = service.create_manuscript(
        "alpha", ManuscriptInput(track_id=track_id, title="Validation paper")
    )
    paper_a = service.update_manuscript_status(
        "alpha",
        paper_a["manuscript_id"],
        ManuscriptStatusInput(
            status="REVISING",
            blocker="Additional experiment",
            next_step="Run robustness check",
            reason="Reviewer request",
            expected_revision=1,
        ),
    )
    service.record_submission_event(
        "alpha",
        paper_a["manuscript_id"],
        SubmissionEventInput(venue="Journal A", round=1, status="REVISION_REQUESTED"),
    )
    content = service.compile_manuscript(
        "alpha", "Abstract", manuscript_id=paper_a["manuscript_id"]
    )
    replacement = service.propose_decision(
        "alpha",
        DecisionProposalInput(
            kind="gap",
            statement="Payment models need longitudinal validation.",
            rationale="Refined scope.",
            evidence_ids=[evidence["evidence_id"]],
            supersedes_node_id=gap["node_id"],
            track_id=track_id,
        ),
    )
    capture_user_approval(
        service.root,
        profile="scholar",
        session_id="test",
        message_id=uuid4().hex,
        user_message=replacement["approval_phrase"],
    )
    service.approve_scientific_decision("alpha", replacement["proposal_id"], 1)

    assert content.startswith("# Mechanism paper")
    refreshed_a = service.get_manuscript("alpha", paper_a["manuscript_id"])
    refreshed_b = service.get_manuscript("alpha", paper_b["manuscript_id"])
    assert refreshed_a["versions"][0]["version"] == 1
    assert refreshed_a["needs_scientific_review"] == 1
    assert refreshed_a["submissions"][0]["status"] == "REVISION_REQUESTED"
    assert refreshed_b["needs_scientific_review"] == 0
    assert paper_a["writing_status"] == "REVISING"
    assert refreshed_b["writing_status"] == "PLANNING"
    assert service.project_progress("alpha")["manuscripts"][0]["manuscript_id"] == paper_a["manuscript_id"]


def test_migration_is_idempotent_and_preserves_existing_ids(tmp_path: Path) -> None:
    service = RSTV4Service(tmp_path)
    project = create_project(service, "alpha")
    track_id = project["tracks"][0]["track_id"]
    path = tmp_path / "projects" / "alpha" / "research.db"

    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE schema_version")

    initialize_project(path)
    initialize_project(path)

    migrated = service.get_project("alpha")
    assert migrated["project_id"] == project["project_id"]
    assert migrated["tracks"][0]["track_id"] == track_id
    assert path.with_suffix(".pre-v2.bak").exists()
