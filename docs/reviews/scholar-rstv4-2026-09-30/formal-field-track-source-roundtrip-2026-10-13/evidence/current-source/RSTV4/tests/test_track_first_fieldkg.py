from __future__ import annotations

import inspect
import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from rstv4.approval import capture_user_approval
from rstv4.models import (
    DecisionProposalInput,
    FieldInput,
    FieldKGBuildInput,
    FieldKGReviewInput,
    ExperimentPlanInput,
    TrackFirstManuscriptInput,
    TrackFirstProjectInput,
    TrackFirstTopicInput,
    TrackFirstTrackInput,
    TrackMilestoneInput,
    ResearchProjectInput,
)
from rstv4.service import RSTV4Service
from rstv4.track_first import TrackFirstService


def create_hierarchy(service: TrackFirstService) -> tuple[dict, dict, dict, dict]:
    field = service.create_field(FieldInput(name="Rural Electrification"))
    topic = service.create_topic(
        TrackFirstTopicInput(field_id=field["field_id"], name="Energy Trading")
    )
    track = service.create_track(
        TrackFirstTrackInput(
            field_id=field["field_id"],
            primary_topic_id=topic["topic_id"],
            title="Off-grid P2P Trading",
            research_type="engineering_system",
        )
    )
    project = service.create_project(
        TrackFirstProjectInput(
            track_id=track["track_id"],
            slug="sarawak-pilot",
            title="Sarawak Pilot",
            type_payload={
                key: {} for key in ("requirements", "system_design", "implementation", "validation")
            },
        )
    )
    return field, topic, track, project


def make_paperpool(path: Path) -> None:
    semantics = [
        {
            "seq_idx": 1,
            "page_idx": 3,
            "section": "Introduction",
            "raw_text": "Few studies validate peer trading in isolated rural microgrids.",
            "layer1": {
                "coref_resolved": "Few studies validate peer trading in isolated rural microgrids.",
                "atomic_sentences": ["Peer trading has limited rural validation."],
                "triplets": [
                    {"subject": "peer trading", "predicate": "has limited validation in", "object": "rural microgrids"}
                ],
            },
            "layer2": {"discourse_relation": "Contrast", "topic_continuity": "High"},
            "layer3": {"intent": "Research_Gap", "confidence": 0.94, "matched_paradigm": "CARS"},
            "layer4": "Problem_Gap",
        }
    ]
    with sqlite3.connect(path) as conn:
        conn.execute(
            """CREATE TABLE paper(
               id INTEGER PRIMARY KEY,title TEXT,year TEXT,authors TEXT,file TEXT,DOI TEXT,
               ext TEXT,Pp_txt_dict TEXT,Pp_abstract TEXT,Pp_minced_semantics TEXT)"""
        )
        conn.execute(
            "INSERT INTO paper VALUES(1,?,?,?,?,?,?,?,?,?)",
            (
                "Rural peer trading", "2025", json.dumps(["A. Author"]), None,
                "10.1000/rural", None, None, "Abstract", json.dumps(semantics),
            ),
        )


def test_track_first_fieldkg_vertical_slice(tmp_path: Path) -> None:
    service = TrackFirstService(tmp_path)
    field, _, track, project = create_hierarchy(service)
    milestone = service.update_milestone(
        track["track_id"],
        TrackMilestoneInput(milestone="SCOPE", status="ACTIVE", expected_revision=0),
    )
    assert milestone["revision"] == 1
    assert service.get_project(project["project_id"])["track_id"] == track["track_id"]

    pool = tmp_path / "paperpool.db"
    make_paperpool(pool)
    build = service.create_fieldkg_build(
        FieldKGBuildInput(field_id=field["field_id"], retrieval_scope={"seed": "rural"})
    )
    imported = service.import_paperpool(build["build_id"], str(pool), [])
    assert imported["imported"] == 1
    build = service.get_fieldkg_build(build["build_id"])
    assert build["evidence_candidates"]
    for candidate in build["evidence_candidates"]:
        service.review_evidence_candidate(
            candidate["candidate_id"],
            FieldKGReviewInput(decision="ACCEPTED", rationale="Located source statement", expected_revision=1),
        )
    for gap in build["candidate_gaps"]:
        service.review_candidate_gap(
            gap["candidate_gap_id"],
            FieldKGReviewInput(decision="ACCEPTED", rationale="Include as candidate only", expected_revision=1),
        )
    ready = service.finish_fieldkg_build(build["build_id"], build["revision"])
    snapshot = service.seal_snapshot(build["build_id"], ready["revision"])
    adoption = service.adopt_snapshot(track["track_id"], snapshot["snapshot_id"])
    assert adoption["snapshot_digest"] == snapshot["content_digest"]

    with sqlite3.connect(service.db_path) as conn:
        conn.row_factory = sqlite3.Row
        evidence_id = conn.execute("SELECT evidence_id FROM evidence WHERE scope_kind='FIELDKG'").fetchone()[0]
    proposal = service.propose_decision(
        track["track_id"],
        DecisionProposalInput(
            kind="gap",
            statement="Rural peer trading lacks field validation.",
            rationale="The adopted landscape contains located evidence.",
            evidence_ids=[evidence_id],
            track_id=track["track_id"],
        ),
    )
    capture_user_approval(
        tmp_path,
        profile="scholar",
        session_id="session",
        message_id=uuid4().hex,
        user_message=proposal["approval_phrase"],
    )
    approved = service.approve_decision(proposal["proposal_id"], 1)
    manuscript = service.create_manuscript(
        TrackFirstManuscriptInput(
            track_id=track["track_id"], title="Rural validation", project_ids=[project["project_id"]],
            node_ids=[approved["node_id"]], evidence_ids=[evidence_id],
        )
    )
    rendered = service.compile_manuscript(manuscript["manuscript_id"], "Test abstract")
    assert rendered.startswith("# Rural validation")
    assert service.get_field_view(field["field_id"])["tracks"][0]["track_id"] == track["track_id"]


def test_cross_track_project_and_manuscript_bindings_are_rejected(tmp_path: Path) -> None:
    service = TrackFirstService(tmp_path)
    field, topic, track, project = create_hierarchy(service)
    other = service.create_track(
        TrackFirstTrackInput(
            field_id=field["field_id"], primary_topic_id=topic["topic_id"],
            title="Other Track", research_type="engineering_system",
        )
    )
    with pytest.raises(ValueError, match="owned by its track"):
        service.create_manuscript(
            TrackFirstManuscriptInput(
                track_id=other["track_id"], title="Invalid", project_ids=[project["project_id"]]
            )
        )


def test_public_mcp_is_track_first() -> None:
    from rstv4 import mcp_server

    public = [
        mcp_server.propose_scientific_decision,
        mcp_server.get_blueprint,
        mcp_server.create_project,
        mcp_server.get_project,
    ]
    assert all("project_slug" not in inspect.signature(call).parameters for call in public)


def test_track_first_experiment_and_blueprint_snapshot(tmp_path: Path) -> None:
    service = TrackFirstService(tmp_path)
    _, _, track, project = create_hierarchy(service)
    with sqlite3.connect(service.db_path) as conn:
        now = "2026-01-01T00:00:00+00:00"
        conn.execute(
            "INSERT INTO research_nodes VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("method_1", track["track_id"], "method", "APPROVED", "Run a deterministic check",
             "Verification method", "{}", 1, now, now),
        )
    plan = service.propose_experiment_plan(
        track["track_id"],
        ExperimentPlanInput(
            method_node_id="method_1",
            argv=["python", "-c", "print('ok')"],
        ),
        project["project_id"],
    )
    capture_user_approval(
        tmp_path, profile="scholar", session_id="experiment", message_id=uuid4().hex,
        user_message=plan["approval_phrase"],
    )
    service.approve_experiment_plan(plan["plan_id"], 1)
    run = service.run_experiment(plan["plan_id"])
    assert run["exit_code"] == 0
    evidence = service.record_experiment_evidence(run["run_id"], "The check completed.")
    assert evidence["track_id"] == track["track_id"]
    assert service.snapshot_blueprint(track["track_id"])["revision"] == 1


def test_legacy_project_migration_is_idempotent_and_preserves_ids(tmp_path: Path) -> None:
    legacy = RSTV4Service(tmp_path)
    original = legacy.create_project(
        ResearchProjectInput(
            slug="legacy-sarawak", title="Legacy Sarawak", field="Rural Electrification",
            research_type="engineering_system",
            type_payload={
                key: {} for key in ("requirements", "system_design", "implementation", "validation")
            },
        )
    )
    original_track_id = original["tracks"][0]["track_id"]
    migrated = TrackFirstService(tmp_path)
    project = migrated.get_project(original["project_id"])
    assert project["track_id"] == original_track_id
    assert migrated.get_track(original_track_id)["mapping_status"] == "NEEDS_TOPIC_MAPPING"
    TrackFirstService(tmp_path)
    with sqlite3.connect(migrated.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM legacy_migration_sources").fetchone()[0] == 1
    assert (tmp_path / "projects" / "legacy-sarawak" / "research.pre-track-first-v3.bak").exists()
