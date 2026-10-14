from __future__ import annotations

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from test_fieldkg_workspace import review_all, seal
from test_fieldkg_workspace import setup as field_setup

from rstv4.approval import capture_user_approval
from rstv4.fieldkg import digest
from rstv4.models import (
    DecisionProposalInput,
    TrackFirstManuscriptInput,
    TrackFirstTrackInput,
)
from rstv4.track_first import TrackFirstService


@pytest.fixture
def setup(tmp_path):
    return field_setup.__wrapped__(tmp_path)


def context(client, track):
    response = client.get(f"/api/catalog/tracks/{track}/scientific-context")
    assert response.status_code == 200, response.text
    return response.json()


def adopt(client, field, track, build):
    review_all(client, field, build)
    snapshot = seal(client, field, build)["snapshot"]
    track_view = client.get(f"/api/catalog/tracks/{track}/workspace").json()
    response = client.post("/api/catalog/fieldkg-actions", json={
        "operation": "ADOPT_SNAPSHOT", "confirmed": True, "request_id": "adopt-science-snapshot",
        "field_id": field, "track_id": track, "snapshot_id": snapshot["snapshot_id"],
        "expected_context_sha256": track_view["context_sha256"],
        "expected_snapshot_digest": snapshot["content_digest"],
    })
    assert response.status_code == 200, response.text
    return snapshot


def propose_body(client, field, track, kind="gap", **values):
    current = context(client, track)
    proposal = {"kind": kind, "statement": "Software fixture scientific candidate",
                "rationale": "Software control flow only; no scientific acceptance", **values}
    if kind == "gap" and "evidence_ids" not in values:
        proposal["evidence_ids"] = [current["evidence"][0]["evidence_id"]]
    return {"operation": "PROPOSE_DECISION", "request_id": "scientific-" + uuid4().hex,
            "confirmed": True, "field_id": field, "track_id": track,
            "expected_context_sha256": current["context_sha256"], "proposal": proposal}


def propose(client, field, track, kind="gap", **values):
    body = propose_body(client, field, track, kind, **values)
    response = client.post("/api/catalog/track-scientific-actions", json=body)
    assert response.status_code == 200, response.text
    return response.json(), body


def apply_body(client, field, track, proposal):
    return {"operation": "APPLY_DECISION", "request_id": "apply-science-" + uuid4().hex,
            "confirmed": True, "field_id": field, "track_id": track,
            "expected_context_sha256": context(client, track)["context_sha256"],
            "proposal_id": proposal["proposal_id"], "expected_revision": proposal["revision"]}


def approve(client, db, field, track, proposal):
    root = db.parent.parent
    grant = capture_user_approval(root, profile="scholar", session_id="software-fixture",
        message_id=uuid4().hex, user_message=proposal["approval_phrase"])
    assert grant
    body = apply_body(client, field, track, proposal)
    response = client.post("/api/catalog/track-scientific-actions", json=body)
    assert response.status_code == 200, response.text
    return response.json(), body


def test_scientific_context_is_read_only_and_unadopted_evidence_is_not_selectable(setup):
    client, db, field, _, track, build = setup
    review_all(client, field, build)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    current = context(client, track)
    assert current["evidence"] and not current["evidence"][0]["selectable"]
    assert current["sources"][0]["units"][0]["page_idx"] == 3
    assert not current["proposals"]
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    denied = client.post("/api/catalog/track-scientific-actions", json=propose_body(client, field, track))
    assert denied.status_code == 409
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_proposal_keeps_located_snapshot_basis_and_requires_real_user_grant(setup):
    client, db, field, _, track, build = setup
    snapshot = adopt(client, field, track, build)
    proposed, _ = propose(client, field, track)
    assert proposed["proposal"]["status"] == "PROPOSED"
    evidence = proposed["dependency_basis"]["evidence"][0]
    assert evidence["adopted_in"][0]["snapshot_id"] == snapshot["snapshot_id"]
    assert evidence["excerpt"].startswith("Few studies")
    current = context(client, track)
    assert current["proposals"][0]["basis_captured"]
    assert not current["proposals"][0]["grant_available"]
    body = apply_body(client, field, track, proposed["proposal"])
    before = db.read_bytes()
    assert client.post("/api/catalog/track-scientific-actions", json=body).status_code == 403
    assert db.read_bytes() == before
    stamp = current["context_sha256"]
    capture_user_approval(db.parent.parent, profile="scholar", session_id="fixture",
        message_id=uuid4().hex, user_message=proposed["proposal"]["approval_phrase"])
    assert context(client, track)["context_sha256"] == stamp
    approved = client.post("/api/catalog/track-scientific-actions", json=body)
    assert approved.status_code == 200, approved.text
    assert approved.json()["proposal"]["status"] == "APPROVED"
    assert not approved.json()["proposal"]["grant_available"]


def test_concurrent_retry_keeps_one_proposal_and_conflicting_key_is_rejected(setup):
    client, db, field, _, track, build = setup
    adopt(client, field, track, build)
    body = propose_body(client, field, track)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post("/api/catalog/track-scientific-actions", json=body), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    assert len(context(client, track)["proposals"]) == 1
    before = db.read_bytes()
    changed = {**body, "proposal": {**body["proposal"], "statement": "different"}}
    assert client.post("/api/catalog/track-scientific-actions", json=changed).status_code == 409
    assert db.read_bytes() == before


def test_completed_apply_retries_original_receipt_without_consuming_twice(setup):
    client, db, field, _, track, build = setup
    adopt(client, field, track, build)
    proposed, _ = propose(client, field, track)
    approved, body = approve(client, db, field, track, proposed["proposal"])
    before = db.read_bytes()
    retried = client.post("/api/catalog/track-scientific-actions", json=body)
    assert retried.status_code == 200 and retried.json() == approved
    assert db.read_bytes() == before
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM approval_grants WHERE consumed_at IS NOT NULL").fetchone()[0] == 1


@pytest.mark.parametrize("kind", ["idea", "research_question", "hypothesis", "method", "claim"])
def test_each_scientific_type_remains_independently_proposed(setup, kind):
    client, db, field, _, track, build = setup
    adopt(client, field, track, build)
    gap, _ = propose(client, field, track)
    approved, _ = approve(client, db, field, track, gap["proposal"])
    proposed, _ = propose(client, field, track, kind, upstream_node_ids=[approved["proposal"]["node_id"]])
    nodes = {n["node_id"]: n for n in context(client, track)["nodes"]}
    assert nodes[gap["proposal"]["node_id"]]["status"] == "APPROVED"
    assert nodes[proposed["proposal"]["node_id"]]["status"] == "PROPOSED"
    assert proposed["proposal"]["kind"] == kind


def test_changed_context_rejected_without_writes_or_grant_consumption(setup):
    client, db, field, _, track, build = setup
    adopt(client, field, track, build)
    proposed, _ = propose(client, field, track)
    stale_body = apply_body(client, field, track, proposed["proposal"])
    propose(client, field, track, "method")
    capture_user_approval(db.parent.parent, profile="scholar", session_id="fixture",
        message_id=uuid4().hex, user_message=proposed["proposal"]["approval_phrase"])
    before = db.read_bytes()
    assert client.post("/api/catalog/track-scientific-actions", json=stale_body).status_code == 409
    assert db.read_bytes() == before


def test_changed_original_evidence_cannot_be_reapproved_with_a_fresh_context(setup):
    client, db, field, _, track, build = setup
    adopt(client, field, track, build)
    proposed, _ = propose(client, field, track)
    capture_user_approval(db.parent.parent, profile="scholar", session_id="fixture",
        message_id=uuid4().hex, user_message=proposed["proposal"]["approval_phrase"])
    eid = proposed["dependency_basis"]["evidence"][0]["evidence_id"]
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT excerpt,location_json FROM evidence WHERE evidence_id=?", (eid,)).fetchone()
        conn.execute("UPDATE evidence SET statement=?,content_digest=? WHERE evidence_id=?",
                     ("Changed source claim", digest(["Changed source claim", row[0], json.loads(row[1])]), eid))
    body = apply_body(client, field, track, proposed["proposal"])
    before = db.read_bytes()
    assert client.post("/api/catalog/track-scientific-actions", json=body).status_code == 409
    assert db.read_bytes() == before


def test_foreign_field_track_dependencies_and_cross_origin_are_rejected(setup):
    client, db, field, other, track, build = setup
    adopt(client, field, track, build)
    body = propose_body(client, field, track)
    before = db.read_bytes()
    assert client.post("/api/catalog/track-scientific-actions", json={**body, "field_id": other}).status_code == 404
    assert client.post("/api/catalog/track-scientific-actions", json=body, headers={"Origin": "https://foreign.example"}).status_code == 403
    bad = {**body, "proposal": {**body["proposal"], "evidence_ids": ["another-field-evidence"]}}
    assert client.post("/api/catalog/track-scientific-actions", json=bad).status_code == 409
    assert db.read_bytes() == before


def test_supersession_invalidates_transitive_nodes_and_manuscript_once(setup):
    client, db, field, _, track, build = setup
    adopt(client, field, track, build)
    approved_nodes = []
    for kind in ["gap", "idea", "research_question", "method", "claim"]:
        values = {"upstream_node_ids": [approved_nodes[-1]]} if approved_nodes else {}
        proposed, _ = propose(client, field, track, kind, **values)
        approved, _ = approve(client, db, field, track, proposed["proposal"])
        approved_nodes.append(approved["proposal"]["node_id"])
    service = TrackFirstService(db.parent.parent)
    manuscript = service.create_manuscript(TrackFirstManuscriptInput(track_id=track,
        title="Software fixture manuscript", node_ids=[approved_nodes[-1], approved_nodes[-2]]))
    original_ms = service.get_manuscript(manuscript["manuscript_id"])
    replacement, _ = propose(client, field, track, supersedes_node_id=approved_nodes[0])
    # Merely proposing never invalidates existing accepted science.
    assert all(n["status"] == "APPROVED" for n in context(client, track)["nodes"] if n["node_id"] in approved_nodes)
    approved, body = approve(client, db, field, track, replacement["proposal"])
    current = context(client, track)
    nodes = {n["node_id"]: n for n in current["nodes"]}
    assert nodes[approved_nodes[0]]["status"] == "SUPERSEDED"
    assert all(nodes[nid]["status"] == "STALE" for nid in approved_nodes[1:])
    changed_ms = service.get_manuscript(manuscript["manuscript_id"])
    assert changed_ms["needs_scientific_review"] == 1
    assert changed_ms["revision"] == original_ms["revision"] + 1
    assert changed_ms["writing_status"] == original_ms["writing_status"]
    assert client.post("/api/catalog/track-scientific-actions", json=body).json() == approved
    assert service.get_manuscript(manuscript["manuscript_id"])["revision"] == changed_ms["revision"]


def test_legacy_uncaptured_proposal_and_foreign_upstream_cannot_be_applied(setup):
    client, db, field, _, track, build = setup
    adopt(client, field, track, build)
    service = TrackFirstService(db.parent.parent)
    legacy = service.propose_decision(track, DecisionProposalInput(kind="method", statement="Old proposal", rationale="Old backend"))
    capture_user_approval(db.parent.parent, profile="scholar", session_id="fixture",
        message_id=uuid4().hex, user_message=legacy["approval_phrase"])
    assert client.post("/api/catalog/track-scientific-actions", json=apply_body(client, field, track, legacy)).status_code == 409
    topic = service.get_track(track)["primary_topic_id"]
    foreign = service.create_track(TrackFirstTrackInput(field_id=field, primary_topic_id=topic,
        title="Another Track", research_type="conceptual_framework"))
    node = service.propose_decision(foreign["track_id"], DecisionProposalInput(kind="method", statement="Foreign method", rationale="Foreign scope"))
    body = propose_body(client, field, track, "method", upstream_node_ids=[node["node_id"]])
    before = db.read_bytes()
    assert client.post("/api/catalog/track-scientific-actions", json=body).status_code == 409
    assert db.read_bytes() == before
