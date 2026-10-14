"""Real source revisions, SQLite projections and explicit adoption; fixture model only."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from test_studio_context import generated_fixture
from test_studio_suggestions import decision_url, fixture, proposal, request_for

from rstv4.catalog_web import create_app as catalog_app
from rstv4.database import transaction
from rstv4.studio_api import create_app

PREFIX = "/api/research/discussion"


class WritingFixture:
    def __init__(self):
        self.calls = []
        self.suggestions = []
        self.failure = None
        self.entered = threading.Event()
        self.release = threading.Event()
        self.release.set()

    def analyze(self, task, payload):
        self.calls.append((task, deepcopy(payload)))
        self.entered.set()
        assert self.release.wait(5)
        if self.failure:
            raise self.failure
        return {"answer": "Only discussion, no changes applied.", "suggestions": self.suggestions, "evidence_ids": [], "_contract": {"actual_model": "fixture-writing-model", "prompt_version": "fixture-writing-contract", "fixture": True}}


@pytest.fixture
def environment(tmp_path):
    service, manuscript_id, document, evidence = fixture(tmp_path)
    gateway = WritingFixture()
    with TestClient(create_app(tmp_path)) as client:
        client.app.state.discussions.gateway = gateway
        yield client, service, manuscript_id, document, evidence, gateway
    service._executor.shutdown(wait=True)


def target(manuscript_id, kind="thought", object_id="thought_author_1", revision=1, **values):
    return {"module": "STUDIO", "manuscript_id": manuscript_id, "object_kind": kind, "object_id": object_id, "document_revision": revision, **values}


def bound(client, selected):
    result = client.post(f"{PREFIX}/context", json=selected)
    assert result.status_code == 200, result.text
    return result.json()


def payload(fixed_context, request_id="shared-studio-request-001", **values):
    return {"request_id": request_id, "content": "Source", "source": {"target": fixed_context["target"], "expected_context_sha256": fixed_context["context_sha256"]}, **values}


def send(client, fixed_context, **values):
    body = payload(fixed_context, **values)
    result = client.post(f"{PREFIX}/messages", json=body)
    assert result.status_code == 202, result.text
    client.app.state.discussions._futures[body["request_id"]].result(timeout=8)
    receipt = client.get(f"{PREFIX}/requests/{body['request_id']}", params={"scope": fixed_context["scope_key"]})
    assert receipt.status_code == 200, receipt.text
    return body, receipt.json()


@pytest.mark.parametrize("kind", ["paper", "section", "paragraph", "intent", "thought"])
def test_owned_author_objects_and_initial_revision_are_read_only(environment, kind):
    client, service, manuscript_id, document, _, gateway = environment
    objects = {"paper": manuscript_id, "section": document["sections"][0]["id"], "paragraph": document["sections"][0]["paragraphs"][0]["id"], "intent": document["sections"][0]["paragraphs"][0]["intents"][0]["id"], "thought": "thought_author_1"}
    before = service.db_path.read_bytes()
    source = bound(client, target(manuscript_id, kind, objects[kind]))
    assert source["record"]["snapshot"]["document"] == document
    assert source["versions"][0]["author_revision"] == 1
    initial = bound(client, target(manuscript_id, "paper", manuscript_id, revision=0))
    assert initial["record"]["snapshot"]["revision"] == 0
    assert service.db_path.read_bytes() == before and not gateway.calls


def test_shared_writing_reply_projects_exact_original_quote_and_actual_call(environment):
    client, service, manuscript_id, document, _, gateway = environment
    source = bound(client, target(manuscript_id))
    selected = payload(source)["source"]
    selected["quote"] = {"text": "😀", "start": 9, "end": 11, "offset_unit": "utf16", "annotation": "Keep original meaning"}
    _, receipt = send(client, source, source=selected)
    assert receipt["job"]["status"] == "COMPLETE"
    assert [message["message_id"] for message in receipt["messages"]] == [message["message_id"] for message in receipt["studio_messages"]]
    author, agent = receipt["studio_messages"]
    assert author["quoted"]["text"] == "😀" and author["quoted"]["annotation"] == "Keep original meaning"
    assert author["quoted"]["source"]["anchor_revision"] == 1
    assert agent["model_provenance"]["model_contract"]["fixture"]
    assert gateway.calls[0][0] == "writing_chat" and gateway.calls[0][1]["document"] == document
    assert gateway.calls[0][1]["retrieved_evidence"] == service.search_sources(manuscript_id, "Source", limit=8)
    assert service.get_workspace(manuscript_id)["document"] == document
    assert service.list_chat(manuscript_id) == receipt["studio_messages"]
    with transaction(service.db_path) as conn:
        row = conn.execute("SELECT * FROM studio_model_calls").fetchone()
        assert hashlib.sha256(row["input_json"].encode()).hexdigest() == row["input_sha256"]
        assert json.loads(row["input_json"]) == gateway.calls[0][1]
        assert row["message_id"] == author["message_id"] and row["status"] == "RETURNED"


@pytest.mark.parametrize("partial", [False, True])
def test_shared_typed_suggestion_keeps_existing_explicit_adoption_and_retry(environment, partial):
    client, service, manuscript_id, document, _, gateway = environment
    gateway.suggestions = [proposal(document)]
    source = bound(client, target(manuscript_id))
    body, receipt = send(client, source)
    agent = receipt["studio_messages"][-1]
    assert agent["quoted"]["suggestions"][0]["kind"] == "STRUCTURE"
    assert service.get_workspace(manuscript_id)["document"] == document
    decision = request_for(agent)
    if partial:
        decision.update(outcome="ACCEPT_PARTIAL", selected_change_ids=decision["selected_change_ids"][:1])
    result = client.post(decision_url(manuscript_id, agent), json=decision)
    assert result.status_code == 201, result.text
    changed = result.json()["workspace"]["document"]["sections"][0]["paragraphs"][0]
    assert changed["purpose"] == "Clarify the boundary"
    assert changed["intents"][0]["thoughts"] == document["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"]
    assert len(changed["intents"]) == len(document["sections"][0]["paragraphs"][0]["intents"]) + (0 if partial else 1)
    assert client.post(decision_url(manuscript_id, agent), json=decision).status_code == 201
    assert client.post(f"{PREFIX}/messages", json=body).status_code == 202
    assert len(gateway.calls) == 1


def test_followup_survives_deleted_author_object_and_preserves_original_suggestion(environment):
    client, service, manuscript_id, document, _, gateway = environment
    source = bound(client, target(manuscript_id))
    _, first = send(client, source)
    parent = first["messages"][-1]["message_id"]
    changed = deepcopy(document)
    changed["sections"] = []
    service.save_document(manuscript_id, base_revision=1, operation_id="shared-object-deleted", document=changed)
    selected = {**payload(source)["source"], "history_message_id": parent}
    _, second = send(client, source, request_id="shared-followup-deleted", source=selected, parent_message_id=parent)
    assert second["job"]["status"] == "COMPLETE"
    model_input = gateway.calls[-1][1]
    assert len(model_input["conversation"]) == 2
    assert model_input["document"] == document
    assert model_input["conversation"][0]["source"]["context"]["object_text"] == source["object_text"]
    assert service.get_workspace(manuscript_id)["document"] == changed
    original = client.get(f"/api/manuscripts/{manuscript_id}/chat/{parent}/context")
    assert original.status_code == 200 and original.json()["snapshot"]["document"] == document


def test_generated_source_uses_same_verified_version_and_numbered_citations(environment):
    client, service, manuscript_id, _, _, gateway = environment
    manuscript_id = service.create_manuscript(service.get_workspace(manuscript_id)["manuscript"]["track_id"], "Generated source fixture")["manuscript"]["manuscript_id"]
    generated = generated_fixture(service, manuscript_id)
    paragraph = next(item for item in generated["blocks"] if item["kind"] == "paragraph")
    before = service.db_path.read_bytes()
    selected = target(manuscript_id, "generated_paragraph", paragraph["anchor_id"], revision=generated["input_revision"], generated_version_id=generated["generated_version_id"])
    source = bound(client, selected)
    assert source["object_text"] == paragraph["display_text"]
    assert source["record"]["generated"]["references"] == generated["references"]
    assert service.db_path.read_bytes() == before
    _, receipt = send(client, source)
    assert receipt["job"]["status"] == "COMPLETE"
    assert gateway.calls[-1][1]["generated_version"]["generated_version_id"] == generated["generated_version_id"]
    assert receipt["studio_messages"][0]["quoted"]["source"]["generated_version_id"] == generated["generated_version_id"]


def test_other_manuscript_cannot_read_or_use_generated_block(environment):
    client, service, manuscript_id, _, _, gateway = environment
    manuscript_id = service.create_manuscript(service.get_workspace(manuscript_id)["manuscript"]["track_id"], "Generated owner fixture")["manuscript"]["manuscript_id"]
    generated = generated_fixture(service, manuscript_id)
    other = service.create_manuscript(service.get_workspace(manuscript_id)["manuscript"]["track_id"], "Other manuscript")
    block = generated["blocks"][0]
    selected = target(other["manuscript"]["manuscript_id"], "generated_title", block["anchor_id"], revision=generated["input_revision"], generated_version_id=generated["generated_version_id"])
    before = service.db_path.read_bytes()
    assert client.post(f"{PREFIX}/context", json=selected).status_code == 404
    assert service.db_path.read_bytes() == before and not gateway.calls


def test_bad_selection_rolls_back_shared_and_studio_projection_before_model(environment):
    client, service, manuscript_id, _, _, gateway = environment
    source = bound(client, target(manuscript_id))
    selected = payload(source)["source"]
    selected["quote"] = {"text": "Invented", "start": 0, "end": 8, "offset_unit": "utf16"}
    before = service.db_path.read_bytes()
    assert client.post(f"{PREFIX}/messages", json=payload(source, source=selected)).status_code == 422
    assert service.db_path.read_bytes() == before and not service.list_chat(manuscript_id) and not gateway.calls


def test_projection_insert_failure_rolls_back_entire_shared_request(environment):
    client, service, manuscript_id, _, _, gateway = environment
    source = bound(client, target(manuscript_id))
    with transaction(service.db_path) as conn:
        conn.execute("CREATE TRIGGER fail_projection BEFORE INSERT ON studio_chat_messages BEGIN SELECT RAISE(ABORT,'projection failed'); END")
    before = service.db_path.read_bytes()
    with pytest.raises(sqlite3.IntegrityError, match="projection failed"):
        client.post(f"{PREFIX}/messages", json=payload(source))
    assert service.db_path.read_bytes() == before and not gateway.calls


def test_failed_model_retains_both_author_views_actual_call_and_original_retry(environment):
    client, service, manuscript_id, document, _, gateway = environment
    gateway.failure = RuntimeError("Actual fixture model outage")
    source = bound(client, target(manuscript_id))
    body, receipt = send(client, source)
    assert receipt["job"]["status"] == "FAILED" and len(receipt["studio_messages"]) == 1
    assert receipt["studio_messages"][0]["status"] == "AGENT_FAILED"
    calls = service.list_model_calls(manuscript_id)
    assert len(calls) == 1 and calls[0]["status"] == "FAILED" and calls[0]["contract"] is None
    assert client.post(f"{PREFIX}/messages", json=body).status_code == 202
    assert len(gateway.calls) == 1 and service.get_workspace(manuscript_id)["document"] == document


def test_invalid_typed_suggestion_preserves_original_call_but_creates_no_agent_or_edits(environment):
    client, service, manuscript_id, document, _, gateway = environment
    gateway.suggestions = [proposal(document)]
    gateway.suggestions[0]["changes"][0]["target_id"] = "invented-target"
    source = bound(client, target(manuscript_id))
    _, receipt = send(client, source)
    assert receipt["job"]["status"] == "FAILED" and len(receipt["messages"]) == 1
    calls = service.list_model_calls(manuscript_id)
    assert calls[0]["status"] == "REJECTED" and calls[0]["output"]["suggestions"] == gateway.suggestions
    assert service.get_workspace(manuscript_id)["document"] == document


def test_tampered_projected_suggestion_cannot_be_previewed_or_adopted(environment):
    client, service, manuscript_id, document, _, gateway = environment
    gateway.suggestions = [proposal(document)]
    source = bound(client, target(manuscript_id))
    _, receipt = send(client, source)
    agent = receipt["studio_messages"][-1]
    with transaction(service.db_path) as conn:
        quote = json.loads(conn.execute("SELECT quoted_json FROM studio_chat_messages WHERE message_id=?", (agent["message_id"],)).fetchone()[0])
        quote["suggestions"][0]["changes"][0]["value"] = "Altered after model call"
        conn.execute("UPDATE studio_chat_messages SET quoted_json=? WHERE message_id=?", (json.dumps(quote), agent["message_id"]))
    before = service.get_workspace(manuscript_id)["document"]
    result = client.post(decision_url(manuscript_id, agent), json=request_for(agent))
    assert result.status_code == 410
    assert service.get_workspace(manuscript_id)["document"] == before
    assert client.get(f"/api/manuscripts/{manuscript_id}/chat").status_code == 410
    assert client.get(f"/api/manuscripts/{manuscript_id}/chat/{agent['message_id']}/context").status_code == 410
    suggestion_id = agent["quoted"]["suggestions"][0]["suggestion_id"]
    assert client.get(f"/api/manuscripts/{manuscript_id}/chat/{agent['message_id']}/suggestions/{suggestion_id}/preview").status_code == 410


def test_both_apps_expose_the_same_saved_studio_discussion(environment):
    client, service, manuscript_id, _, _, gateway = environment
    source = bound(client, target(manuscript_id))
    body, original = send(client, source)
    with TestClient(catalog_app(service.root)) as catalog:
        before = service.db_path.read_bytes()
        read = catalog.get(f"{PREFIX}/requests/{body['request_id']}", params={"scope": source["scope_key"]})
        assert read.status_code == 200 and read.json()["messages"] == original["messages"]
        assert read.json()["studio_messages"] == original["studio_messages"]
        assert service.db_path.read_bytes() == before and len(gateway.calls) == 1


def test_context_read_does_not_restart_or_seed_unrelated_studio_jobs(environment):
    client, service, manuscript_id, _, _, gateway = environment
    with transaction(service.db_path) as conn:
        conn.execute("INSERT INTO studio_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)", ("existing-running-job", manuscript_id, "GENERATE", "RUNNING", 1, "{}", None, None, "2026-10-05", "2026-10-05", None))
    before = service.db_path.read_bytes()
    bound(client, target(manuscript_id))
    assert service.db_path.read_bytes() == before and not gateway.calls


@pytest.mark.parametrize('deleted', [False, True])
def test_historical_author_source_observes_current_revision_without_rebinding(environment, deleted):
    client, service, manuscript_id, document, _, gateway = environment
    source = bound(client, target(manuscript_id))
    _, receipt = send(client, source)
    changed = deepcopy(document)
    if deleted:
        changed['sections'] = []
    else:
        changed['sections'][0]['paragraphs'][0]['intents'][0]['thoughts'][0]['text'] = 'New author wording'
    service.save_document(manuscript_id, base_revision=1, operation_id='observe-current-author', document=changed)
    before = service.db_path.read_bytes()
    original = client.get(f"{PREFIX}/messages/{receipt['messages'][-1]['message_id']}/context", params={'scope': source['scope_key']})
    assert original.status_code == 200
    assert original.json()['sources'][0]['current_source_state'] == ('SOURCE_UNAVAILABLE' if deleted else 'OLD_VERSION')
    assert original.json()['sources'][0]['context'] == source
    assert service.db_path.read_bytes() == before and len(gateway.calls) == 1


def test_historical_generated_source_is_old_after_author_revision_changes(environment):
    client, service, manuscript_id, _, _, gateway = environment
    manuscript_id = service.create_manuscript(service.get_workspace(manuscript_id)['manuscript']['track_id'], 'Generated history fixture')['manuscript']['manuscript_id']
    generated = generated_fixture(service, manuscript_id)
    block = next(item for item in generated['blocks'] if item['kind'] == 'paragraph')
    source = bound(client, target(manuscript_id, 'generated_paragraph', block['anchor_id'], revision=generated['input_revision'], generated_version_id=generated['generated_version_id']))
    _, receipt = send(client, source)
    workspace = service.get_workspace(manuscript_id)
    changed = deepcopy(workspace['document'])
    changed['title'] = 'New author title'
    service.save_document(manuscript_id, base_revision=workspace['document_revision'], operation_id='observe-current-generated', document=changed)
    before = service.db_path.read_bytes()
    original = client.get(f"{PREFIX}/messages/{receipt['messages'][-1]['message_id']}/context", params={'scope': source['scope_key']})
    assert original.status_code == 200 and original.json()['sources'][0]['current_source_state'] == 'OLD_VERSION'
    assert original.json()['sources'][0]['context'] == source
    assert service.db_path.read_bytes() == before and len(gateway.calls) == 1
