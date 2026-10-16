from __future__ import annotations

import copy
import sqlite3
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from rstv4.approval import capture_user_approval
from rstv4.models import (
    DecisionProposalInput,
    ExperimentPlanInput,
    FieldInput,
    TrackFirstManuscriptInput,
    TrackFirstTopicInput,
    TrackFirstTrackInput,
)
from rstv4.service import RevisionConflictError, RSTV4Error
from rstv4.studio import StudioService
from rstv4.studio_api import create_app
from rstv4.track_first import TrackFirstService


def make_track(service: TrackFirstService, title: str = "Acceptance track") -> str:
    field = service.create_field(FieldInput(name="Acceptance field"))
    topic = service.create_topic(
        TrackFirstTopicInput(field_id=field["field_id"], name="Acceptance topic")
    )
    return service.create_track(
        TrackFirstTrackInput(
            field_id=field["field_id"],
            primary_topic_id=topic["topic_id"],
            title=title,
            research_type="conceptual_framework",
        )
    )["track_id"]


def grant(service: TrackFirstService, proposal: dict) -> None:
    assert (
        capture_user_approval(
            service.root,
            profile="scholar",
            session_id="isolated-acceptance",
            message_id=uuid4().hex,
            user_message=proposal["approval_phrase"],
        )
        is not None
    )


def approve_node(service: TrackFirstService, track_id: str, kind: str, **kwargs) -> dict:
    proposal = service.propose_decision(
        track_id,
        DecisionProposalInput(
            kind=kind,
            statement=f"Isolated {kind}: {uuid4().hex}",
            rationale="Acceptance fixture, not a production scientific approval",
            **kwargs,
        ),
    )
    grant(service, proposal)
    return service.approve_decision(proposal["proposal_id"], 1)


def test_supersession_invalidates_transitive_dependants_once_and_preserves_history(
    tmp_path: Path,
) -> None:
    service = TrackFirstService(tmp_path)
    track_id = make_track(service)
    method = approve_node(service, track_id, "method")
    claim = approve_node(service, track_id, "claim", upstream_node_ids=[method["node_id"]])
    question = approve_node(
        service, track_id, "research_question", upstream_node_ids=[method["node_id"]]
    )
    final = approve_node(
        service, track_id, "claim", upstream_node_ids=[claim["node_id"], question["node_id"]]
    )
    unrelated = approve_node(service, track_id, "method")
    manuscript = service.create_manuscript(
        TrackFirstManuscriptInput(
            track_id=track_id, title="Indirect dependency", node_ids=[final["node_id"]]
        )
    )
    other = service.create_manuscript(
        TrackFirstManuscriptInput(
            track_id=track_id, title="Unrelated", node_ids=[unrelated["node_id"]]
        )
    )
    snapshot = service.snapshot_blueprint(track_id)
    with sqlite3.connect(service.db_path) as conn:
        snapshot_json = conn.execute(
            "SELECT payload_json FROM blueprint_snapshots WHERE blueprint_id=?",
            (snapshot["blueprint_id"],),
        ).fetchone()[0]
    before_provenance = service.trace_provenance(final["node_id"])
    replacement = service.propose_decision(
        track_id,
        DecisionProposalInput(
            kind="method",
            statement="Replacement method",
            rationale="Author chose another method",
            supersedes_node_id=method["node_id"],
        ),
    )
    with pytest.raises(PermissionError):
        service.approve_decision(replacement["proposal_id"], 1)
    assert service.get_manuscript(manuscript["manuscript_id"])["needs_scientific_review"] == 0
    grant(service, replacement)
    approved = service.approve_decision(replacement["proposal_id"], 1)

    impacted = {node["node_id"]: node for node in service.impact_analysis(method["node_id"])}
    assert set(impacted) == {claim["node_id"], question["node_id"], final["node_id"]}
    assert all(node["status"] == "STALE" and node["revision"] == 2 for node in impacted.values())
    assert approved["status"] == "APPROVED"
    assert service.get_decision(method["proposal_id"])["status"] == "APPROVED"
    stale = {node["node_id"]: node for node in service.build_blueprint(track_id)["stale_objects"]}
    assert stale[method["node_id"]]["status"] == "SUPERSEDED"
    assert stale[method["node_id"]]["revision"] == 2
    reviewed = service.get_manuscript(manuscript["manuscript_id"])
    assert reviewed["needs_scientific_review"] == 1
    assert reviewed["revision"] == manuscript["revision"] + 1
    assert reviewed["nodes"] == manuscript["nodes"]
    assert reviewed["history"] == manuscript["history"]
    assert reviewed["writing_status"] == manuscript["writing_status"]
    assert service.get_manuscript(other["manuscript_id"])["needs_scientific_review"] == 0
    assert service.trace_provenance(final["node_id"]) == before_provenance
    with sqlite3.connect(service.db_path) as conn:
        assert (
            conn.execute(
                "SELECT payload_json FROM blueprint_snapshots WHERE blueprint_id=?",
                (snapshot["blueprint_id"],),
            ).fetchone()[0]
            == snapshot_json
        )


def test_pending_decision_cannot_approve_after_its_upstream_was_superseded(tmp_path: Path) -> None:
    service = TrackFirstService(tmp_path)
    track_id = make_track(service)
    method = approve_node(service, track_id, "method")
    pending = service.propose_decision(
        track_id,
        DecisionProposalInput(
            kind="claim",
            statement="Pending claim",
            rationale="Needs a current method",
            upstream_node_ids=[method["node_id"]],
        ),
    )
    grant(service, pending)
    approve_node(service, track_id, "method", supersedes_node_id=method["node_id"])
    with pytest.raises(RevisionConflictError, match="upstream"):
        service.approve_decision(pending["proposal_id"], 1)
    with sqlite3.connect(service.db_path) as conn:
        assert (
            conn.execute(
                "SELECT consumed_at FROM approval_grants WHERE proposal_id=?",
                (pending["proposal_id"],),
            ).fetchone()[0]
            is None
        )
    assert service.get_decision(pending["proposal_id"])["status"] == "PROPOSED"


def test_supersession_cannot_change_another_tracks_node(tmp_path: Path) -> None:
    service = TrackFirstService(tmp_path)
    track_id = make_track(service)
    other_track = make_track(service, "Other track")
    method = approve_node(service, other_track, "method")
    with pytest.raises(ValueError, match="same track"):
        service.propose_decision(
            track_id,
            DecisionProposalInput(
                kind="method",
                statement="Cross-track replacement",
                rationale="Invalid fixture",
                supersedes_node_id=method["node_id"],
            ),
        )
    assert method["node_id"] in {
        node["node_id"] for node in service.build_blueprint(other_track)["approved"]
    }


@pytest.mark.parametrize("status", ["SUPERSEDED", "STALE", "REJECTED"])
def test_invalid_method_refuses_execution_without_a_run(tmp_path: Path, status: str) -> None:
    service = TrackFirstService(tmp_path)
    track_id = make_track(service)
    method = approve_node(service, track_id, "method")
    marker = tmp_path / "must-not-execute.txt"
    plan = service.propose_experiment_plan(
        track_id,
        ExperimentPlanInput(
            method_node_id=method["node_id"],
            argv=[sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"],
        ),
    )
    grant(service, plan)
    service.approve_experiment_plan(plan["plan_id"], 1)
    with sqlite3.connect(service.db_path) as conn:
        conn.execute(
            "UPDATE research_nodes SET status=? WHERE node_id=?", (status, method["node_id"])
        )
    with pytest.raises(RevisionConflictError, match="method"):
        service.run_experiment(plan["plan_id"])
    assert not marker.exists()
    with sqlite3.connect(service.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0] == 0


def test_replacement_method_requires_a_new_plan_grant_and_can_run(tmp_path: Path) -> None:
    service = TrackFirstService(tmp_path)
    track_id = make_track(service)
    method = approve_node(service, track_id, "method")
    replacement = approve_node(service, track_id, "method", supersedes_node_id=method["node_id"])
    plan = service.propose_experiment_plan(
        track_id,
        ExperimentPlanInput(
            method_node_id=replacement["node_id"],
            argv=[sys.executable, "-c", "print('ISOLATED_ACCEPTANCE_ONLY')"],
        ),
    )
    with pytest.raises(PermissionError):
        service.approve_experiment_plan(plan["plan_id"], 1)
    grant(service, plan)
    service.approve_experiment_plan(plan["plan_id"], 1)
    result = service.run_experiment(plan["plan_id"])
    assert result["exit_code"] == 0
    assert "ISOLATED_ACCEPTANCE_ONLY" in result["stdout_preview"]


@pytest.mark.parametrize(
    "current,target",
    [
        ("DRAFTING", "WHOLE_PAPER_REVIEW"),
        ("WHOLE_PAPER_REVIEW", "FINALIZATION_SUBMISSION"),
        ("FINALIZATION_SUBMISSION", "REVISION"),
        ("FINALIZATION_SUBMISSION", "PUBLICATION"),
    ],
)
def test_stage_api_rejects_zero_versions_including_legacy_late_stages(
    tmp_path: Path,
    current: str,
    target: str,
) -> None:
    app = create_app(tmp_path)
    service = app.state.studio
    track_id = make_track(service.track_service)
    manuscript_id = service.create_manuscript(track_id, "Empty manuscript")["manuscript"][
        "manuscript_id"
    ]
    with sqlite3.connect(service.db_path) as conn:
        conn.execute(
            "UPDATE manuscripts SET workflow_stage=? WHERE manuscript_id=?",
            (current, manuscript_id),
        )
    before = service.get_workspace(manuscript_id)
    with TestClient(app) as client:
        response = client.post(
            f"/api/manuscripts/{manuscript_id}/stage",
            json={
                "stage": target,
                "expected_revision": before["manuscript"]["revision"],
                "reason": "Isolated acceptance check",
            },
        )
        assert response.status_code == 422
        assert "successful generated version" in response.json()["detail"]
        restored = client.get(f"/api/manuscripts/{manuscript_id}/workspace")
        assert restored.status_code == 200
        after = restored.json()
        assert after["workflow_stage"] == current
        assert after["manuscript"]["revision"] == before["manuscript"]["revision"]
        assert after["manuscript"]["history"] == before["manuscript"]["history"]


def test_successful_generation_allows_stages_and_return_but_stale_output_cannot_finalize(
    tmp_path: Path,
) -> None:
    service = StudioService(tmp_path)
    track_id = make_track(service.track_service)
    manuscript_id = service.create_manuscript(track_id, "Stage contract")["manuscript"][
        "manuscript_id"
    ]
    document = service.get_workspace(manuscript_id)["document"]
    document["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"] = [
        {
            "id": "thought_contract",
            "text": "Author-approved test thought.",
            "citation_mode": "NONE",
            "citations": [],
        }
    ]
    service.gateway.analyze = lambda task, payload: {
        "paragraph": "Author-approved test thought.",
        "sentence_mappings": [{"sentence": 0, "thought_ids": ["thought_contract"]}],
    }
    # Isolate the stage contract. Real model/LaTeX acceptance is a separate required run.
    service._compile_artifacts = lambda job, generated: []

    def generate(revision: int, expected_status: str = "SUCCEEDED") -> None:
        job = service.create_job(manuscript_id, "GENERATE", input_revision=revision)
        deadline = time.monotonic() + 5
        while job["status"] not in {"SUCCEEDED", "FAILED"} and time.monotonic() < deadline:
            time.sleep(0.02)
            job = service.get_job(job["job_id"])
        assert job["status"] == expected_status, job

    def stage(target: str) -> None:
        current = service.get_workspace(manuscript_id)["manuscript"]
        service.set_stage(
            manuscript_id, target, expected_revision=current["revision"], reason="Fixture action"
        )

    try:
        service.save_document(
            manuscript_id, base_revision=0, operation_id="acceptance-input-1", document=document
        )
        successful_compiler = service._compile_artifacts

        def failed_compiler(job: dict, generated: dict) -> list:
            raise RuntimeError("Isolated compilation failure")

        service._compile_artifacts = failed_compiler
        generate(1, "FAILED")
        failed = service.get_workspace(manuscript_id)
        assert failed["workflow_stage"] == "DRAFTING"
        assert failed["active_generated_version_id"] is None
        with pytest.raises(RSTV4Error, match="successful generated version"):
            stage("WHOLE_PAPER_REVIEW")
        service._compile_artifacts = successful_compiler
        generate(1)
        stage("DRAFTING")
        stage("WHOLE_PAPER_REVIEW")
        prior_version = service.get_workspace(manuscript_id)["active_generated_version_id"]
        revised = copy.deepcopy(document)
        revised["abstract"] = "New author input"
        service.save_document(
            manuscript_id, base_revision=1, operation_id="acceptance-input-2", document=revised
        )
        with pytest.raises(RSTV4Error, match="Regenerate"):
            stage("FINALIZATION_SUBMISSION")
        assert service.get_workspace(manuscript_id)["active_generated_version_id"] == prior_version
        generate(2)
        with sqlite3.connect(service.db_path) as conn:
            conn.execute(
                "UPDATE manuscripts SET needs_scientific_review=1 WHERE manuscript_id=?",
                (manuscript_id,),
            )
        with pytest.raises(RSTV4Error, match="scientific dependencies"):
            stage("FINALIZATION_SUBMISSION")
        # Fixture reset only; a real scientific review/rebinding flow is still required.
        with sqlite3.connect(service.db_path) as conn:
            conn.execute(
                "UPDATE manuscripts SET needs_scientific_review=0 WHERE manuscript_id=?",
                (manuscript_id,),
            )
        stage("FINALIZATION_SUBMISSION")
        stage("REVISION")
        generate(2)
        assert service.get_workspace(manuscript_id)["workflow_stage"] == "REVISION"
        stage("FINALIZATION_SUBMISSION")
        service.record_submission_event(
            manuscript_id, venue="Software fixture", round_number=1, status="ACCEPTED",
            detail="Local fixture acceptance, no external journal action",
        )
        stage("PUBLICATION")
    finally:
        service._executor.shutdown(wait=True)
