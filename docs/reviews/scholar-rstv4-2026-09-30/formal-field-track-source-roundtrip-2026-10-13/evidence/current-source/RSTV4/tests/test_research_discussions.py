from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from test_catalog_web import seed_catalog
from test_fieldkg_workspace import review_all, seal
from test_fieldkg_workspace import setup as _fieldkg_setup

from rstv4.catalog_web import create_app
from rstv4.research_context import DiscussionTarget, scope_key
from rstv4.research_discussions import ResearchDiscussionService

fieldkg_setup = _fieldkg_setup


class FakeGateway:
    def __init__(self):
        self.calls = []
        self.failure = None
        self.sources = None
        self.entered = threading.Event()
        self.release = threading.Event()
        self.release.set()

    def analyze(self, task, payload):
        self.calls.append((task, payload))
        self.entered.set()
        assert self.release.wait(5)
        if self.failure:
            raise self.failure
        return {"answer": "Discussion only, no changes applied", "source_ids": self.sources if self.sources is not None else [payload["source"]["context"]["context_sha256"]], "_contract": {"actual_model": "fixture-model", "prompt_version": "fixture-contract", "fixture": True}}


@pytest.fixture
def environment(fieldkg_setup):
    client, db, field, other, track, build = fieldkg_setup
    gateway = FakeGateway()
    client.app.state.discussions.gateway = gateway
    yield client, db, field, other, track, build, gateway
    client.app.state.discussions.shutdown()


def unit_target(client, field):
    data = client.get(f"/api/catalog/fields/{field}/workspace").json()
    source = data["sources"][0]
    return {"module": "FIELDKG", "field_id": field, "object_kind": "unit", "object_id": source["units"][0]["unit_id"]}


def context(client, target):
    response = client.post("/api/catalog/discussion/context", json=target)
    assert response.status_code == 200, response.text
    return response.json()


def payload(bound, request_id="request-test-001", **values):
    return {"request_id": request_id, "content": "Explain this exact original source", "source": {"target": bound["target"], "expected_context_sha256": bound["context_sha256"]}, **values}


def wait(client, request_id, bound):
    service = client.app.state.discussions
    service._futures[request_id].result(timeout=8)
    response = client.get(f"/api/catalog/discussion/requests/{request_id}", params={"scope": bound["scope_key"]})
    assert response.status_code == 200, response.text
    return response.json()


def test_source_context_and_empty_history_are_read_only(environment):
    client, db, field, _, _, _, gateway = environment
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    target = unit_target(client, field)
    bound = context(client, target)
    assert bound["object_text"].startswith("Few studies")
    assert bound["versions"][0]["page_idx"] == 3
    assert bound["versions"][0]["file_version_id"] is None
    result = client.post("/api/catalog/discussion/history", json={"target": target}).json()
    assert not result["messages"] and not result["annotations"]
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert not gateway.calls
    with sqlite3.connect(db) as conn:
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='research_discussion_requests'").fetchone()


def test_discussion_freezes_exact_original_and_actual_fixture_contract(environment):
    client, db, field, _, _, _, gateway = environment
    bound = context(client, unit_target(client, field))
    body = payload(bound)
    body["source"]["quote"] = {"text": "Few studies", "start": 0, "end": 11, "offset_unit": "utf16", "annotation": "My source annotation"}
    assert client.post("/api/catalog/discussion/messages", json=body).status_code == 202
    result = wait(client, body["request_id"], bound)
    assert result["job"]["status"] == "COMPLETE" and len(result["messages"]) == 2
    assert result["messages"][0]["quote"]["text"] == "Few studies"
    assert result["messages"][0]["quote"]["annotation"] == "My source annotation"
    assert result["job"]["model_contract"]["fixture"]
    assert result["job"]["input"]["source"]["context"] == bound
    assert len(gateway.calls) == 1 and gateway.calls[0][0] == "research_chat"
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM research_nodes").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 0
        assert conn.execute("SELECT status FROM fieldkg_evidence_candidates").fetchone()[0] == "PROPOSED"


def test_mismatched_quote_and_stale_source_are_rejected_before_model(environment):
    client, db, field, _, _, _, gateway = environment
    bound = context(client, unit_target(client, field))
    body = payload(bound)
    body["source"]["quote"] = {"text": "Invented original", "start": 0, "end": 17, "offset_unit": "utf16"}
    before = db.read_bytes()
    assert client.post("/api/catalog/discussion/messages", json=body).status_code == 422
    assert db.read_bytes() == before
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE skeleton_units SET raw_text='Source changed'")
    before = db.read_bytes()
    assert client.post("/api/catalog/discussion/messages", json=payload(bound)).status_code == 409
    assert db.read_bytes() == before
    assert not gateway.calls
    with sqlite3.connect(db) as conn:
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='research_discussion_requests'").fetchone()


def test_utf16_quote_cannot_split_a_character(environment):
    client, db, field, _, _, _, gateway = environment
    target = unit_target(client, field)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE skeleton_units SET raw_text='Prefix 🙂 evidence'")
    bound = context(client, target)
    body = payload(bound)
    body["source"]["quote"] = {"text": "🙂", "start": 7, "end": 9, "offset_unit": "utf16"}
    assert client.post("/api/catalog/discussion/messages", json=body).status_code == 202
    assert wait(client, body["request_id"], bound)["job"]["status"] == "COMPLETE"
    body["request_id"] = "split-emoji-quote"
    body["source"]["quote"]["start"] = 8
    assert client.post("/api/catalog/discussion/messages", json=body).status_code == 422
    assert len(gateway.calls) == 1


def test_original_quote_keeps_spaces_line_breaks_and_unicode(environment):
    client, db, field, _, _, _, gateway = environment
    target = unit_target(client, field)
    raw = "\n  Original 🙂 sentence \t\n"
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE skeleton_units SET raw_text=?", (raw,))
    bound = context(client, target)
    body = payload(bound, request_id="exact-whitespace-unicode")
    body["source"]["quote"] = {"text": raw, "start": 0, "end": len(raw.encode("utf-16-le")) // 2, "offset_unit": "utf16"}
    assert client.post("/api/catalog/discussion/messages", json=body).status_code == 202
    receipt = wait(client, body["request_id"], bound)
    assert receipt["messages"][0]["quote"]["text"] == raw
    assert receipt["job"]["input"]["source"]["quote"]["text"] == raw
    assert len(gateway.calls) == 1


def test_changed_or_deleted_sources_keep_original_history(environment):
    client, db, field, _, _, _, _ = environment
    bound = context(client, unit_target(client, field))
    body = payload(bound)
    client.post("/api/catalog/discussion/messages", json=body)
    result = wait(client, body["request_id"], bound)
    message_id = result["messages"][0]["message_id"]
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE skeleton_units SET raw_text='New version text'")
    original = client.get(f"/api/catalog/discussion/messages/{message_id}/context", params={"scope": bound["scope_key"]}).json()
    assert original["sources"][0]["current_source_state"] == "OLD_VERSION"
    assert original["sources"][0]["context"]["object_text"] == bound["object_text"]
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM skeleton_units")
    original = client.get(f"/api/catalog/discussion/messages/{message_id}/context", params={"scope": bound["scope_key"]}).json()
    assert original["sources"][0]["current_source_state"] == "SOURCE_UNAVAILABLE"
    assert original["message"]["context"] == bound


def test_retry_original_request_after_source_change_never_reapplies_or_recalls(environment):
    client, db, field, _, _, _, gateway = environment
    bound = context(client, unit_target(client, field)); body = payload(bound)
    assert client.post("/api/catalog/discussion/messages", json=body).status_code == 202
    original = wait(client, body["request_id"], bound)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE skeleton_units SET raw_text='Later source'")
    replay = client.post("/api/catalog/discussion/messages", json=body)
    assert replay.status_code == 202
    current = wait(client, body["request_id"], bound)
    assert current["messages"] == original["messages"] and len(gateway.calls) == 1
    assert client.post("/api/catalog/discussion/messages", json={**body, "content": "Different request"}).status_code == 409


def test_concurrent_duplicate_requests_call_model_once(environment):
    client, _, field, _, _, _, gateway = environment
    bound = context(client, unit_target(client, field)); body = payload(bound)
    gateway.release.clear()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post("/api/catalog/discussion/messages", json=body), range(2)))
    assert all(result.status_code == 202 for result in results)
    assert gateway.entered.wait(2)
    gateway.release.set()
    assert wait(client, body["request_id"], bound)["job"]["status"] == "COMPLETE"
    assert len(gateway.calls) == 1


def test_annotation_is_immutable_and_retry_does_not_duplicate(environment):
    client, db, field, _, _, _, gateway = environment
    bound = context(client, unit_target(client, field))
    body = {"request_id": "annotation-test-001", "source": payload(bound)["source"], "comment": "Separate discussion annotation"}
    first = client.post("/api/catalog/discussion/annotations", json=body)
    assert first.status_code == 201
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE skeleton_units SET raw_text='Later text'")
    assert client.post("/api/catalog/discussion/annotations", json=body).json() == first.json()
    assert client.post("/api/catalog/discussion/annotations", json={**body, "comment": "Overwrite"}).status_code == 409
    assert not gateway.calls
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM research_discussion_annotations").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM catalog_review_annotations").fetchone()[0] == 0


def test_failed_model_answer_retains_author_and_provenance_without_recall(environment):
    client, _, field, _, _, _, gateway = environment
    gateway.failure = RuntimeError("Model unavailable")
    bound = context(client, unit_target(client, field)); body = payload(bound)
    client.post("/api/catalog/discussion/messages", json=body)
    result = wait(client, body["request_id"], bound)
    assert result["job"]["status"] == "FAILED" and len(result["messages"]) == 1
    assert result["messages"][0]["status"] == "AGENT_FAILED"
    assert result["job"]["model_contract"] is None
    assert result["job"]["requested_contract"]["prompt_version"] == "research-chat-v2-fixed-conversation"
    assert client.post("/api/catalog/discussion/messages", json=body).status_code == 202
    wait(client, body["request_id"], bound)
    assert len(gateway.calls) == 1


def test_model_cannot_cite_an_unsupplied_source(environment):
    client, _, field, _, _, _, gateway = environment
    gateway.sources = ["fabricated-source"]
    bound = context(client, unit_target(client, field)); body = payload(bound)
    client.post("/api/catalog/discussion/messages", json=body)
    result = wait(client, body["request_id"], bound)
    assert result["job"]["status"] == "FAILED" and len(result["messages"]) == 1
    assert result["job"]["response"]["source_ids"] == ["fabricated-source"]


def test_cross_scope_read_and_request_lookup_are_rejected(environment):
    client, _, field, other, _, _, _ = environment
    target = unit_target(client, field)
    assert client.post("/api/catalog/discussion/context", json={**target, "field_id": other}).status_code == 404
    bound = context(client, target); body = payload(bound)
    client.post("/api/catalog/discussion/messages", json=body)
    result = wait(client, body["request_id"], bound)
    wrong_scope = scope_key(DiscussionTarget(module="FIELDKG", field_id=other, object_kind="field", object_id=other))
    assert client.get(f"/api/catalog/discussion/requests/{body['request_id']}", params={"scope": wrong_scope}).status_code == 404
    assert client.get(f"/api/catalog/discussion/messages/{result['messages'][0]['message_id']}/context", params={"scope": wrong_scope}).status_code == 404


def test_explicit_additional_sources_are_all_frozen_and_scope_switch_is_explicit(environment):
    client, db, field, _, track, _, _ = environment
    first = context(client, unit_target(client, field))
    second = context(client, {"module": "TRACK", "track_id": track, "object_kind": "track", "object_id": track})
    body = payload(first, additional_sources=[payload(second)["source"]])
    assert client.post("/api/catalog/discussion/messages", json=body).status_code == 422
    body["allow_cross_scope"] = True
    assert client.post("/api/catalog/discussion/messages", json=body).status_code == 202
    result = wait(client, body["request_id"], first)
    assert result["messages"][0]["additional_sources"][0]["context"] == second
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE research_tracks SET title='Later title' WHERE track_id=?", (track,))
    history = client.get(f"/api/catalog/discussion/messages/{result['messages'][0]['message_id']}/context", params={"scope": first["scope_key"]}).json()
    assert len(history["sources"]) == 2 and history["sources"][1]["current_source_state"] == "OLD_VERSION"


def test_historical_fixed_object_can_be_discussed_after_original_disappears(environment):
    client, db, field, _, _, _, gateway = environment
    bound = context(client, unit_target(client, field)); body = payload(bound)
    client.post("/api/catalog/discussion/messages", json=body)
    original = wait(client, body["request_id"], bound)
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM skeleton_units")
    next_body = payload(bound, request_id="historical-discussion-next")
    next_body["source"]["history_message_id"] = original["messages"][0]["message_id"]
    assert client.post("/api/catalog/discussion/messages", json=next_body).status_code == 202
    next_result = wait(client, next_body["request_id"], bound)
    assert next_result["messages"][0]["context"] == bound and len(gateway.calls) == 2


def test_tampered_saved_context_cannot_be_reused_or_reported_as_original(environment):
    client, db, field, _, _, _, _ = environment
    bound = context(client, unit_target(client, field)); body = payload(bound)
    client.post("/api/catalog/discussion/messages", json=body)
    original = wait(client, body["request_id"], bound)
    altered = {**bound, "object_text": "Fake original"}
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE research_discussion_messages SET context_json=?", (json.dumps(altered),))
    message_id = original["messages"][0]["message_id"]
    assert client.get(f"/api/catalog/discussion/messages/{message_id}/context", params={"scope": bound["scope_key"]}).status_code == 410
    assert client.post("/api/catalog/discussion/history", json={"target": bound["target"]}).status_code == 410
    assert client.get(f"/api/catalog/discussion/requests/{body['request_id']}", params={"scope": bound["scope_key"]}).status_code == 410
    next_body = payload(bound, request_id="tampered-history-next"); next_body["source"]["history_message_id"] = message_id
    assert client.post("/api/catalog/discussion/messages", json=next_body).status_code == 410


def test_snapshot_discussion_uses_frozen_source_even_after_living_change(environment):
    client, db, field, _, _, build, _ = environment
    review_all(client, field, build)
    snapshot = seal(client, field, build)["snapshot"]
    target = {**unit_target(client, field), "snapshot_id": snapshot["snapshot_id"]}
    frozen = context(client, target)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE skeleton_units SET raw_text='New Living text'")
    assert context(client, target) == frozen
    assert frozen["versions"][-1]["snapshot_digest"] == snapshot["content_digest"]


def test_source_history_pagination_keeps_exact_message_ids(environment):
    client, _, field, _, _, _, _ = environment
    bound = context(client, unit_target(client, field))
    for number in range(3):
        body = payload(bound, request_id=f"history-request-{number}")
        client.post("/api/catalog/discussion/messages", json=body); wait(client, body["request_id"], bound)
    first = client.post("/api/catalog/discussion/history", json={"target": bound["target"], "limit": 3}).json()
    second = client.post("/api/catalog/discussion/history", json={"target": bound["target"], "limit": 3, "before": first["next_before"]}).json()
    assert first["has_more"] and not second["has_more"]
    ids = [message["message_id"] for message in first["messages"] + second["messages"]]
    assert len(ids) == len(set(ids)) == 6


def test_restart_observation_does_not_automatically_reinvoke_running_model(environment, monkeypatch):
    client, db, field, _, _, _, gateway = environment
    bound = context(client, unit_target(client, field)); body = payload(bound)
    client.post("/api/catalog/discussion/messages", json=body); wait(client, body["request_id"], bound)
    # Preserve the completed call and model a separate actually unanswered job.
    interrupted = payload(bound, request_id="interrupted-running-request")
    monkeypatch.setattr(client.app.state.discussions, "_schedule", lambda _: None)
    assert client.post("/api/catalog/discussion/messages", json=interrupted).status_code == 202
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE research_discussion_jobs SET status='RUNNING' WHERE request_id=?", (interrupted["request_id"],))
        conn.execute("UPDATE research_discussion_messages SET status='RUNNING' WHERE request_id=?", (interrupted["request_id"],))
    new_gateway = FakeGateway()
    new = ResearchDiscussionService(db.parent.parent, new_gateway)
    try:
        state = new.request(interrupted["request_id"], bound["scope_key"])
        assert state["execution_observation"] == "NOT_OBSERVED_IN_THIS_PROCESS" and not new_gateway.calls
        assert state["job"]["status"] == "RUNNING" and len(state["messages"]) == 1
    finally:
        new.shutdown()
    assert len(gateway.calls) == 1


def test_discussion_receipt_insert_failure_rolls_back_and_never_calls_model(environment):
    client, db, field, _, _, _, gateway = environment
    bound = context(client, unit_target(client, field))
    # Install only the additive schema, then inject an actual transaction failure.
    service = client.app.state.discussions
    with service._write() as conn:
        conn.execute("CREATE TRIGGER fail_discussion BEFORE INSERT ON research_discussion_messages BEGIN SELECT RAISE(ABORT,'failed message'); END")
    with pytest.raises(sqlite3.IntegrityError, match="failed message"):
        client.post("/api/catalog/discussion/messages", json=payload(bound))
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM research_discussion_requests").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM research_discussion_jobs").fetchone()[0] == 0
    assert not gateway.calls


def test_large_context_is_explicitly_rejected_without_truncating_or_calling_model(environment):
    client, db, field, _, _, _, gateway = environment
    target = unit_target(client, field)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE skeleton_units SET raw_text=?", ("Very long original source " * 10000,))
    bound = context(client, target)
    response = client.post("/api/catalog/discussion/messages", json=payload(bound))
    assert response.status_code == 422 and "narrower" in response.json()["detail"]
    assert not gateway.calls


def test_actual_pdf_page_uses_registered_file_sha_and_rejects_changed_file(tmp_path):
    if not shutil.which("pdftotext"):
        pytest.skip("The actual PDF extractor is unavailable")
    seed_catalog(tmp_path)
    pdf = tmp_path / "sample.pdf"
    with sqlite3.connect(tmp_path / "data/catalog.db") as conn:
        conn.execute("UPDATE source_file_versions SET sha256=?", (hashlib.sha256(pdf.read_bytes()).hexdigest(),))
    with TestClient(create_app(tmp_path)) as client:
        target = {"module": "CATALOG", "paper_id": "p2", "object_kind": "pdf_page", "object_id": "f2", "page_number": 1}
        bound = context(client, target)
        assert "Solar Energy B Revised" in bound["object_text"]
        assert bound["versions"][0]["file_sha256"] == hashlib.sha256(pdf.read_bytes()).hexdigest()
        assert bound["record"]["words"] and "storage_path" not in bound["record"]["file"]
        pdf.write_bytes(pdf.read_bytes() + b"\nChanged")
        assert client.post("/api/catalog/discussion/context", json=target).status_code == 410
        assert client.post("/api/catalog/discussion/context", json={**target, "paper_id": "p1"}).status_code == 404
