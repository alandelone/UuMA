from __future__ import annotations

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_track_first_fieldkg import make_paperpool

from rstv4.catalog_web import create_app
from rstv4.fieldkg import digest
from rstv4.models import (
    FieldInput,
    FieldKGBuildInput,
    TrackFirstTopicInput,
    TrackFirstTrackInput,
)
from rstv4.track_first import TrackFirstService


@pytest.fixture
def setup(tmp_path: Path):
    service = TrackFirstService(tmp_path)
    field = service.create_field(FieldInput(name="Energy"))
    other = service.create_field(FieldInput(name="Other"))
    topic = service.create_topic(TrackFirstTopicInput(field_id=field["field_id"], name="Trading"))
    track = service.create_track(TrackFirstTrackInput(field_id=field["field_id"], primary_topic_id=topic["topic_id"], title="Track", research_type="conceptual_framework"))
    pool = tmp_path / "pool.db"
    make_paperpool(pool)
    build = service.create_fieldkg_build(FieldKGBuildInput(field_id=field["field_id"]))
    service.import_paperpool(build["build_id"], str(pool), [])
    return TestClient(create_app(tmp_path)), service.db_path, field["field_id"], other["field_id"], track["track_id"], build["build_id"]


def get_field(client, field, snapshot=None):
    response = client.get(f"/api/catalog/fields/{field}/workspace", params={"snapshot": snapshot} if snapshot else {})
    assert response.status_code == 200, response.text
    return response.json()


def act(client, field, operation, request_id, **values):
    return client.post("/api/catalog/fieldkg-actions", json={"field_id": field, "operation": operation, "request_id": request_id, "confirmed": True, **values})


def review_all(client, field, build_id):
    data = get_field(client, field)
    candidates = [c for c in data["candidates"] if c["record"]["build_id"] == build_id]
    for candidate in candidates:
        assert act(client, field, "REVIEW_CANDIDATE", f"review-{candidate['record']['candidate_id']}", object_id=candidate["record"]["candidate_id"], expected_context_sha256=candidate["context_sha256"], decision="ACCEPTED", rationale="Exact located source").status_code == 200
    data = get_field(client, field)
    for gap in [g for g in data["candidate_gaps"] if g["record"]["build_id"] == build_id]:
        assert act(client, field, "REVIEW_GAP", f"review-{gap['record']['candidate_gap_id']}", object_id=gap["record"]["candidate_gap_id"], expected_context_sha256=gap["context_sha256"], decision="ACCEPTED", rationale="Keep as a candidate only").status_code == 200


def seal(client, field, build_id):
    build = next(b for b in get_field(client, field)["builds"] if b["build_id"] == build_id)
    response = act(client, field, "READY_BUILD", f"ready-{build_id}", build_id=build_id, expected_context_sha256=build["context_sha256"])
    assert response.status_code == 200, response.text
    result = act(client, field, "SEAL_SNAPSHOT", f"seal-{build_id}", build_id=build_id, expected_context_sha256=response.json()["build"]["context_sha256"])
    assert result.status_code == 200, result.text
    return result.json()


def test_field_read_is_scoped_and_sources_have_exact_original_versions(setup):
    client, db, field, other, _, _ = setup
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    data = get_field(client, field)
    assert data["field"]["field_id"] == field and data["sources"]
    source = data["sources"][0]
    assert source["units"][0]["page_idx"] == 3
    assert source["units"][0]["raw_text"].startswith("Few studies")
    assert source["units"][0]["layer3"]["intent"] == "Research_Gap"
    assert source["file_version_id"] is None and source["parse_run_id"] is None
    assert "source" not in source and "pdf_path" not in source
    empty = get_field(client, other)
    assert not empty["sources"] and not empty["candidates"] and not empty["candidate_gaps"]
    assert data["projection"]["live_service_health"] == "NOT_PROBED"
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_create_build_uses_selected_fixed_skeleton_and_retries_without_duplicate(setup):
    client, db, field, _, _, _ = setup
    source = client.get("/api/catalog/research/skeletons").json()["sources"][0]
    payload = {source["skeleton_id"]: source["context_sha256"]}
    first = act(client, field, "CREATE_BUILD", "new-build", sources=payload)
    assert first.status_code == 200
    assert act(client, field, "CREATE_BUILD", "new-build", sources=payload).json() == first.json()
    built = first.json()["build"]
    assert built["status"] == "EXTRACTING_EVIDENCE"
    assert built["evidence_candidates"][0]["status"] == "PROPOSED"
    assert built["candidate_gaps"][0]["status"] == "PROPOSED"
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM fieldkg_builds").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM research_nodes").fetchone()[0] == 0


def test_source_changed_since_picker_rejects_new_build_atomically(setup):
    client, db, field, _, _, _ = setup
    source = client.get("/api/catalog/research/skeletons").json()["sources"][0]
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE skeleton_units SET raw_text='Changed source'")
    assert act(client, field, "CREATE_BUILD", "stale-source", sources={source["skeleton_id"]: source["context_sha256"]}).status_code == 409
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM fieldkg_builds").fetchone()[0] == 1


def test_review_rejects_wrong_field_and_candidate_source_tampering(setup):
    client, db, field, other, _, _ = setup
    candidate = get_field(client, field)["candidates"][0]
    values = {"object_id": candidate["record"]["candidate_id"], "expected_context_sha256": candidate["context_sha256"], "decision": "ACCEPTED", "rationale": "Located"}
    assert act(client, other, "REVIEW_CANDIDATE", "wrong-field", **values).status_code == 404
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE skeleton_units SET raw_text='Changed source'")
    assert act(client, field, "REVIEW_CANDIDATE", "stale-review", **values).status_code == 409
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT status FROM fieldkg_evidence_candidates").fetchone()[0] == "PROPOSED"
        assert conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 0


def test_gap_cannot_be_accepted_before_its_evidence_is_reviewed(setup):
    client, _, field, _, _, _ = setup
    gap = get_field(client, field)["candidate_gaps"][0]
    response = act(client, field, "REVIEW_GAP", "gap-early", object_id=gap["record"]["candidate_gap_id"], expected_context_sha256=gap["context_sha256"], decision="ACCEPTED", rationale="Not yet grounded")
    assert response.status_code == 422 and "before accepting" in response.json()["detail"]


def test_refreshed_candidate_still_rejects_mismatched_original_source(setup):
    client, db, field, _, _, _ = setup
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE skeleton_units SET raw_text='Later text'")
    candidate = get_field(client, field)["candidates"][0]
    response = act(client, field, "REVIEW_CANDIDATE", "fresh-mismatch", object_id=candidate["record"]["candidate_id"], expected_context_sha256=candidate["context_sha256"], decision="ACCEPTED", rationale="Fresh view cannot repair old excerpt")
    assert response.status_code == 409 and "original source text" in response.json()["detail"]
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT status FROM fieldkg_evidence_candidates").fetchone()[0] == "PROPOSED"


def test_complete_review_seal_and_explicit_adoption_keeps_candidates_non_scientific(setup):
    client, db, field, _, track, build = setup
    review_all(client, field, build)
    sealed = seal(client, field, build)
    snapshot = sealed["snapshot"]
    view = get_field(client, field, snapshot["snapshot_id"])["selected_snapshot"]
    assert view["digest_matches"] and view["source_records_available"]
    assert view["sources"][0]["units"][0]["page_idx"] == 3
    assert view["frozen_evidence"][0]["paper_version_id"] == view["sources"][0]["paper_version_id"]
    track_view = client.get(f"/api/catalog/tracks/{track}/workspace").json()
    values = {"track_id": track, "snapshot_id": snapshot["snapshot_id"], "expected_context_sha256": track_view["context_sha256"], "expected_snapshot_digest": snapshot["content_digest"]}
    saved = act(client, field, "ADOPT_SNAPSHOT", "adopt", **values)
    assert saved.status_code == 200
    assert act(client, field, "ADOPT_SNAPSHOT", "adopt", **values).json() == saved.json()
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM track_snapshot_adoptions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM research_nodes").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM projection_outbox").fetchone()[0] == 3


def test_seal_rejects_pending_candidates_and_missing_accepted_evidence(setup):
    client, db, field, _, _, build_id = setup
    build = get_field(client, field)["builds"][0]
    ready = act(client, field, "READY_BUILD", "ready", build_id=build_id, expected_context_sha256=build["context_sha256"]).json()["build"]
    assert act(client, field, "SEAL_SNAPSHOT", "pending-seal", build_id=build_id, expected_context_sha256=ready["context_sha256"]).status_code == 422
    review_all(client, field, build_id)
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM evidence")
    build = get_field(client, field)["builds"][0]
    assert act(client, field, "SEAL_SNAPSHOT", "missing-evidence-seal", build_id=build_id, expected_context_sha256=build["context_sha256"]).status_code == 422
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM fieldkg_snapshots").fetchone()[0] == 0


def test_snapshot_is_frozen_when_living_source_changes_and_adoption_stays_fixed(setup):
    client, db, field, _, track, build = setup
    review_all(client, field, build)
    snapshot = seal(client, field, build)["snapshot"]
    before = get_field(client, field, snapshot["snapshot_id"])["selected_snapshot"]
    context = client.get(f"/api/catalog/tracks/{track}/workspace").json()["context_sha256"]
    assert act(client, field, "ADOPT_SNAPSHOT", "adopt-frozen", track_id=track, snapshot_id=snapshot["snapshot_id"], expected_context_sha256=context, expected_snapshot_digest=snapshot["content_digest"]).status_code == 200
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE skeleton_units SET raw_text='Later Living text'")
    after = get_field(client, field, snapshot["snapshot_id"])["selected_snapshot"]
    assert before["manifest"] == after["manifest"]
    assert after["sources"][0]["units"][0]["raw_text"] != "Later Living text"
    adopted = client.get(f"/api/catalog/tracks/{track}/workspace").json()["adopted_snapshots"][0]
    assert adopted["content_digest"] == snapshot["content_digest"] and adopted["digest_matches"]


def test_receipt_failure_rolls_back_review_evidence_and_projection(setup):
    client, db, field, _, _, _ = setup
    candidate = get_field(client, field)["candidates"][0]
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON research_workspace_actions BEGIN SELECT RAISE(ABORT,'receipt failed'); END")
    with pytest.raises(sqlite3.IntegrityError, match="receipt failed"):
        act(client, field, "REVIEW_CANDIDATE", "failed", object_id=candidate["record"]["candidate_id"], expected_context_sha256=candidate["context_sha256"], decision="ACCEPTED", rationale="Source checked")
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT status FROM fieldkg_evidence_candidates").fetchone()[0] == "PROPOSED"
        assert conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM projection_outbox").fetchone()[0] == 0


def test_concurrent_accept_and_reject_have_one_winner_and_original_retry_remains(setup):
    client, db, field, _, _, _ = setup
    candidate = get_field(client, field)["candidates"][0]
    values = {"object_id": candidate["record"]["candidate_id"], "expected_context_sha256": candidate["context_sha256"], "rationale": "Checked source"}
    def review(decision):
        return act(client, field, "REVIEW_CANDIDATE", decision, decision=decision, **values)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(review, ["ACCEPTED", "REJECTED"]))
    assert sorted(r.status_code for r in results) == [200, 409]
    winner = next(r.json() for r in results if r.status_code == 200)
    assert review(winner["review"]["record"]["status"]).json() == winner
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM research_workspace_actions").fetchone()[0] == 1


def test_wrong_field_snapshot_and_modified_track_cannot_be_adopted(setup):
    client, db, field, other, track, build = setup
    review_all(client, field, build)
    snapshot = seal(client, field, build)["snapshot"]
    view = client.get(f"/api/catalog/tracks/{track}/workspace").json()
    values = {"track_id": track, "snapshot_id": snapshot["snapshot_id"], "expected_context_sha256": view["context_sha256"], "expected_snapshot_digest": snapshot["content_digest"]}
    assert act(client, other, "ADOPT_SNAPSHOT", "wrong-adopt", **values).status_code == 404
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE research_tracks SET scope='New scope' WHERE track_id=?", (track,))
    assert act(client, field, "ADOPT_SNAPSHOT", "stale-adopt", **values).status_code == 409
    assert client.get(f"/api/catalog/fields/{other}/workspace", params={"snapshot": snapshot["snapshot_id"]}).status_code == 404


def test_tampered_snapshot_digest_and_evidence_cannot_be_silently_used(setup):
    client, db, field, _, track, build = setup
    review_all(client, field, build)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE evidence SET excerpt='Not the source'")
    ready = act(client, field, "READY_BUILD", "ready-tamper", build_id=build, expected_context_sha256=get_field(client, field)["builds"][0]["context_sha256"]).json()["build"]
    assert act(client, field, "SEAL_SNAPSHOT", "seal-tamper", build_id=build, expected_context_sha256=ready["context_sha256"]).status_code == 409
    with sqlite3.connect(db) as conn:
        manifest = {"field_id": field, "test": "original"}
        conn.execute("INSERT INTO fieldkg_snapshots VALUES('tampered',?,1,?,'SEALED',?,?,'MAPPED','now')", (field, build, json.dumps({"changed": True}), digest(manifest)))
    assert not get_field(client, field, "tampered")["selected_snapshot"]["digest_matches"]
    context = client.get(f"/api/catalog/tracks/{track}/workspace").json()["context_sha256"]
    assert act(client, field, "ADOPT_SNAPSHOT", "tampered-adopt", track_id=track, snapshot_id="tampered", expected_context_sha256=context, expected_snapshot_digest=digest(manifest)).status_code == 409


def test_all_actions_require_confirmation_and_forbid_approval_fields(setup):
    client, _, field, _, _, _ = setup
    source = client.get("/api/catalog/research/skeletons").json()["sources"][0]
    values = {"field_id": field, "operation": "CREATE_BUILD", "request_id": "not-confirmed", "sources": {source["skeleton_id"]: source["context_sha256"]}}
    assert client.post("/api/catalog/fieldkg-actions", json=values).status_code == 422
    assert client.post("/api/catalog/fieldkg-actions", json={**values, "confirmed": False}).status_code == 422
    assert client.post("/api/catalog/fieldkg-actions", json={**values, "confirmed": True, "approved": True}).status_code == 422


def test_track_details_keep_independent_milestones_and_owned_projects(setup):
    client, db, field, _, track, _ = setup
    with sqlite3.connect(db) as conn:
        for name, state in [("METHOD", "APPROVED"), ("EXPERIMENT", "BLOCKED")]:
            conn.execute("INSERT INTO track_milestones VALUES(?,?,?,'Located blocker',1,'now')", (track, name, state))
        conn.execute("INSERT INTO projects VALUES('project',?,'owned','Owned project','conceptual_framework',?,'Owned scope','ACTIVE',1,'now','now')", (track, json.dumps({"goal": "Verify", "dataset": "Only fixture", "time": "now"})))
    view = client.get(f"/api/catalog/tracks/{track}/workspace").json()
    assert view["field"]["field_id"] == field and "current_phase" not in view
    assert {m["milestone"]: m["status"] for m in view["milestones"]} == {"METHOD": "APPROVED", "EXPERIMENT": "BLOCKED"}
    assert view["projects"][0]["track_id"] == track and view["projects"][0]["type_payload"]["dataset"] == "Only fixture"


def test_cross_field_gap_reference_is_hidden_and_cannot_be_sealed(setup):
    client, db, field, other, _, build = setup
    review_all(client, field, build)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE evidence SET field_id=?,statement='Private other Field text'", (other,))
        evidence = conn.execute("SELECT evidence_id FROM evidence").fetchone()[0]
        conn.execute("UPDATE fieldkg_candidate_gaps SET evidence_ids_json=?", (json.dumps([evidence]),))
    view = get_field(client, field)
    assert view["candidate_gaps"][0]["references"] == [{"kind": "unavailable", "id": evidence}]
    assert "Private other Field text" not in json.dumps(view)
    ready = act(client, field, "READY_BUILD", "foreign-ready", build_id=build, expected_context_sha256=view["builds"][0]["context_sha256"])
    assert ready.status_code == 200
    rejected = act(client, field, "SEAL_SNAPSHOT", "foreign-seal", build_id=build, expected_context_sha256=ready.json()["build"]["context_sha256"])
    assert rejected.status_code == 422
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM fieldkg_snapshots").fetchone()[0] == 0


def test_snapshot_member_tampering_prevents_adoption(setup):
    client, db, field, _, track, build = setup
    review_all(client, field, build)
    snapshot = seal(client, field, build)["snapshot"]
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE fieldkg_snapshot_members SET member_digest='changed'")
    fixed = get_field(client, field, snapshot["snapshot_id"])["selected_snapshot"]
    assert fixed["digest_matches"] and not fixed["members_match"]
    context = client.get(f"/api/catalog/tracks/{track}/workspace").json()["context_sha256"]
    response = act(client, field, "ADOPT_SNAPSHOT", "tampered-member", track_id=track, snapshot_id=snapshot["snapshot_id"], expected_context_sha256=context, expected_snapshot_digest=snapshot["content_digest"])
    assert response.status_code == 409
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM track_snapshot_adoptions").fetchone()[0] == 0


def test_sealed_gap_references_keep_original_raw_source(setup):
    client, db, field, _, _, build = setup
    review_all(client, field, build)
    snapshot = seal(client, field, build)["snapshot"]
    original = get_field(client, field, snapshot["snapshot_id"])["selected_snapshot"]["manifest"]
    refs = next(iter(original["gap_references"].values()))
    assert refs[0]["record"]["status"] == "ACCEPTED"
    assert refs[0]["source"]["units"][0]["page_idx"] == 3
    assert refs[0]["accepted_evidence"]["content_digest"]
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE skeleton_units SET raw_text='New Living text'")
    assert get_field(client, field, snapshot["snapshot_id"])["selected_snapshot"]["manifest"] == original


def test_track_can_explicitly_adopt_multiple_fixed_versions_without_replacing_first(setup):
    client, _, field, _, track, first_build = setup
    review_all(client, field, first_build)
    first = seal(client, field, first_build)["snapshot"]
    context = client.get(f"/api/catalog/tracks/{track}/workspace").json()
    assert act(client, field, "ADOPT_SNAPSHOT", "adopt-first-version", track_id=track, snapshot_id=first["snapshot_id"], expected_context_sha256=context["context_sha256"], expected_snapshot_digest=first["content_digest"]).status_code == 200
    source = get_field(client, field)["sources"][0]
    second_build = act(client, field, "CREATE_BUILD", "second-version-build", sources={source["skeleton_id"]: source["context_sha256"]}).json()["object_id"]
    review_all(client, field, second_build)
    second = seal(client, field, second_build)["snapshot"]
    context = client.get(f"/api/catalog/tracks/{track}/workspace").json()
    assert act(client, field, "ADOPT_SNAPSHOT", "adopt-second-version", track_id=track, snapshot_id=second["snapshot_id"], expected_context_sha256=context["context_sha256"], expected_snapshot_digest=second["content_digest"]).status_code == 200
    current = client.get(f"/api/catalog/tracks/{track}/workspace").json()
    assert {row["snapshot_id"]: row["snapshot_digest"] for row in current["adoptions"]} == {first["snapshot_id"]: first["content_digest"], second["snapshot_id"]: second["content_digest"]}
    assert all(snapshot["digest_matches"] and snapshot["members_match"] for snapshot in current["adopted_snapshots"])
