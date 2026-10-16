from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from rstv4.service import RSTV4Error
from rstv4.studio import StudioService
from rstv4.studio_api import create_app
from test_writing_studio import complete_document, create_studio, wait_for_job


def database_state(service: StudioService) -> tuple[str, ...]:
    with sqlite3.connect(service.db_path) as conn:
        return tuple(conn.iterdump())


def current_generated(service: StudioService, manuscript_id: str) -> None:
    document = complete_document(service.get_workspace(manuscript_id))
    service.save_document(
        manuscript_id, base_revision=0, operation_id="publication-author-input", document=document
    )
    # Local contract fixture only: no real model or compiler is invoked.
    service.gateway.analyze = lambda task, payload: {
        "paragraph": "The author decides the central scientific claim.",
        "sentence_mappings": [{"sentence": 0, "thought_ids": ["thought_author_1"]}],
    }
    service._compile_artifacts = lambda job, generated: []
    job = wait_for_job(service, service.create_job(manuscript_id, "GENERATE", input_revision=1))
    assert job["status"] == "SUCCEEDED", job


@pytest.mark.parametrize("stage", ["DRAFTING", "FINALIZATION_SUBMISSION", "REVISION", "PUBLICATION"])
def test_publication_event_rejects_zero_versions_without_any_database_change(
    tmp_path: Path, stage: str
) -> None:
    service, _, manuscript_id = create_studio(tmp_path)
    app = create_app(tmp_path)
    try:
        # Legacy stage labels alone are never proof of successful generation.
        with sqlite3.connect(service.db_path) as conn:
            conn.execute(
                "UPDATE manuscripts SET workflow_stage=? WHERE manuscript_id=?", (stage, manuscript_id)
            )
        before = database_state(service)
        with TestClient(app) as client:
            response = client.post(
                f"/api/manuscripts/{manuscript_id}/submission-events",
                json={"venue": "Software fixture", "round_number": 1, "status": "PUBLISHED"},
            )
        assert response.status_code == 422, response.text
        assert database_state(service) == before
    finally:
        service._executor.shutdown(wait=True)


@pytest.mark.parametrize("unready", ["author_changed", "scientific_review", "planning"])
def test_publication_event_cannot_bypass_current_version_science_or_stage_guards(
    tmp_path: Path, unready: str
) -> None:
    service, _, manuscript_id = create_studio(tmp_path)
    try:
        current_generated(service, manuscript_id)
        manuscript = service.get_workspace(manuscript_id)["manuscript"]
        service.set_stage(
            manuscript_id, "FINALIZATION_SUBMISSION", expected_revision=manuscript["revision"],
            reason="Software fixture reviewed output",
        )
        if unready == "author_changed":
            document = service.get_workspace(manuscript_id)["document"]
            document["abstract"] = "New unsent author content"
            service.save_document(
                manuscript_id, base_revision=1, operation_id="publication-stale-input",
                document=document,
            )
        else:
            with sqlite3.connect(service.db_path) as conn:
                if unready == "scientific_review":
                    conn.execute(
                        "UPDATE manuscripts SET needs_scientific_review=1 WHERE manuscript_id=?",
                        (manuscript_id,),
                    )
                else:
                    conn.execute(
                        "UPDATE manuscripts SET workflow_stage='PLANNING' WHERE manuscript_id=?",
                        (manuscript_id,),
                    )
        before = database_state(service)
        app = create_app(tmp_path)
        with TestClient(app) as client:
            response = client.post(
                f"/api/manuscripts/{manuscript_id}/submission-events",
                json={"venue": "Software fixture", "round_number": 1, "status": "PUBLISHED"},
            )
        assert response.status_code == 422, response.text
        assert database_state(service) == before
    finally:
        service._executor.shutdown(wait=True)


def test_publication_event_and_stage_history_commit_together_and_reject_stale_repeat(
    tmp_path: Path,
) -> None:
    service, _, manuscript_id = create_studio(tmp_path)
    try:
        current_generated(service, manuscript_id)
        manuscript = service.get_workspace(manuscript_id)["manuscript"]
        service.set_stage(
            manuscript_id, "FINALIZATION_SUBMISSION", expected_revision=manuscript["revision"],
            reason="Software fixture reviewed output",
        )
        service.record_submission_event(
            manuscript_id, venue="Software fixture", round_number=1, status="ACCEPTED",
            detail="Local fixture acceptance, no external journal action",
        )
        before = service.get_workspace(manuscript_id)
        event = service.record_submission_event(
            manuscript_id, venue="Software fixture", round_number=1, status="PUBLISHED",
            detail="Local software acceptance, no external journal submission",
        )
        after = StudioService(tmp_path).get_workspace(manuscript_id)
        assert event in after["manuscript"]["submissions"]
        assert after["workflow_stage"] == "PUBLICATION"
        assert after["manuscript"]["revision"] == before["manuscript"]["revision"] + 1
        assert len(after["manuscript"]["history"]) == len(before["manuscript"]["history"]) + 1
        assert after["manuscript"]["history"][-1]["reason"] == event["detail"]
        assert after["document"] == before["document"]
        assert after["active_generated_version_id"] == before["active_generated_version_id"]
        again = service.record_submission_event(
            manuscript_id, venue="Software fixture", round_number=1, status="PUBLISHED",
            detail="Second explicitly recorded event",
        )
        repeated = service.get_workspace(manuscript_id)
        assert again in repeated["manuscript"]["submissions"]
        assert repeated["manuscript"]["revision"] == after["manuscript"]["revision"]
        assert repeated["manuscript"]["history"] == after["manuscript"]["history"]
        with sqlite3.connect(service.db_path) as conn:
            conn.execute(
                "UPDATE manuscripts SET needs_scientific_review=1 WHERE manuscript_id=?",
                (manuscript_id,),
            )
        frozen = database_state(service)
        with pytest.raises(RSTV4Error, match="scientific"):
            service.record_submission_event(
                manuscript_id, venue="Software fixture", round_number=1, status="PUBLISHED",
                detail="Must not bypass review just because the stage is already PUBLICATION",
            )
        assert database_state(service) == frozen
    finally:
        service._executor.shutdown(wait=True)


def test_failed_publication_event_insert_rolls_back_stage_and_history(tmp_path: Path) -> None:
    service, _, manuscript_id = create_studio(tmp_path)
    try:
        current_generated(service, manuscript_id)
        manuscript = service.get_workspace(manuscript_id)["manuscript"]
        service.set_stage(
            manuscript_id, "FINALIZATION_SUBMISSION", expected_revision=manuscript["revision"],
            reason="Software fixture reviewed output",
        )
        service.record_submission_event(
            manuscript_id, venue="Software fixture", round_number=1, status="ACCEPTED",
            detail="Local fixture acceptance, no external journal action",
        )
        with sqlite3.connect(service.db_path) as conn:
            conn.execute("""CREATE TRIGGER fixture_fail_submission BEFORE INSERT ON submission_events
                            BEGIN SELECT RAISE(ABORT, 'fixture event insert failure'); END""")
        before = database_state(service)
        with pytest.raises(sqlite3.IntegrityError, match="fixture event insert failure"):
            service.record_submission_event(
                manuscript_id, venue="Software fixture", round_number=1, status="PUBLISHED",
                detail="Must be atomic",
            )
        assert database_state(service) == before
    finally:
        service._executor.shutdown(wait=True)


def test_nonpublication_events_preserve_unready_manuscript_and_remain_append_only(
    tmp_path: Path,
) -> None:
    service, _, manuscript_id = create_studio(tmp_path)
    try:
        before = service.get_workspace(manuscript_id)
        # A new submission must identify a current successful final manuscript.
        # Other editorial metadata can still be recorded for legacy manuscripts.
        frozen = database_state(service)
        with pytest.raises(RSTV4Error, match="successful generated version"):
            service.record_submission_event(
                manuscript_id, venue="Software fixture", round_number=2, status="SUBMITTED",
                detail="Cannot submit an empty draft",
            )
        assert database_state(service) == frozen
        events = [service.record_submission_event(
            manuscript_id, venue="Software fixture", round_number=2, status=status,
            detail="Local event record, no scientific or journal approval",
        ) for status in ("REVISION_REQUESTED", "ACCEPTED", "REJECTED", "WITHDRAWN")]
        after = service.get_workspace(manuscript_id)
        assert after["manuscript"]["submissions"] == before["manuscript"]["submissions"] + events
        assert {k: v for k, v in after["manuscript"].items() if k != "submissions"} == {
            k: v for k, v in before["manuscript"].items() if k != "submissions"}
        assert after["document"] == before["document"]
        assert after["active_generated_version_id"] is None
    finally:
        service._executor.shutdown(wait=True)
