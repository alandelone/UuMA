"""Shared discussion must receive the exact generated references it may cite."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from test_studio_shared_discussions import PREFIX, bound, send, target
from test_studio_source_context import generate, source_studio

from rstv4.database import transaction
from rstv4.studio_api import create_app


class FixedReferencesGateway:
    def __init__(self, evidence_ids):
        self.evidence_ids = evidence_ids
        self.calls = []

    def analyze(self, task, payload):
        assert task == "writing_chat"
        self.calls.append(deepcopy(payload))
        return {"answer": "Keep the original generated source.",
                "evidence_ids": self.evidence_ids,
                "_contract": {"actual_model": "TEST_FIXTURE_FIXED_DISCUSSION"}}


def generated_target(manuscript_id, generated):
    block = next(item for item in generated["blocks"] if item["kind"] == "paragraph")
    return target(manuscript_id, "generated_paragraph", block["anchor_id"],
                  revision=generated["input_revision"],
                  generated_version_id=generated["generated_version_id"])


@pytest.mark.parametrize("refresh_live", [False, True])
def test_generated_discussion_receives_fixed_references_before_live_search(tmp_path, refresh_live):
    service, ms, evidence, _original, _pdf, document = source_studio(tmp_path)
    first = generate(service, ms)
    ids = [reference["evidence_id"] for reference in first["references"]]
    gateway = FixedReferencesGateway(ids)
    if refresh_live:
        with transaction(service.db_path) as conn:
            conn.execute("UPDATE papers SET title='Refreshed live title' WHERE paper_id='existing'")
            conn.execute("UPDATE evidence SET statement='Refreshed live statement' WHERE evidence_id=?",
                         (evidence[1]["evidence_id"],))
    question = "Refreshed live title" if refresh_live else "zzzNoLiveMatch2026"
    live = service.search_sources(ms, question, limit=8)
    assert bool(live) == refresh_live
    with TestClient(create_app(tmp_path)) as client:
        client.app.state.discussions.gateway = gateway
        source = bound(client, generated_target(ms, first))
        _, receipt = send(client, source, content=question)
        assert receipt["job"]["status"] == "COMPLETE", receipt
        assert receipt["studio_messages"][-1]["quoted"]["evidence_ids"] == ids
        supplied = gateway.calls[0]["retrieved_evidence"]
        assert [item["evidence_id"] for item in supplied] == ids
        assert all(item["title"] == reference["title"]
                   and item["statement"] == reference["statement"]
                   and item["source_context"]["context_sha256"] == reference["source_context"]["context_sha256"]
                   for item, reference in zip(supplied, first["references"], strict=True))
        assert "Original software source body 3." not in json.dumps(gateway.calls[0])
        assert service.get_generated_version(ms, first["generated_version_id"]) == first
        assert service.get_workspace(ms)["document"] == document
    service._executor.shutdown(wait=True)


@pytest.mark.parametrize("unapproved", ["foreign", "unknown_original"])
def test_unsupplied_or_unknown_original_reference_still_rejects(tmp_path, unapproved):
    service, ms, evidence, _source, _pdf, document = source_studio(tmp_path)
    if unapproved == "unknown_original":
        with transaction(service.db_path) as conn:
            conn.execute("UPDATE evidence SET location_json='{}' WHERE evidence_id=?",
                         (evidence[1]["evidence_id"],))
    first = generate(service, ms)
    cited = "foreign-reference" if unapproved == "foreign" else evidence[1]["evidence_id"]
    gateway = FixedReferencesGateway([cited])
    with TestClient(create_app(tmp_path)) as client:
        client.app.state.discussions.gateway = gateway
        source = bound(client, generated_target(ms, first))
        _, receipt = send(client, source, content="zzzNoLiveMatch2026")
        assert receipt["job"]["status"] == "FAILED"
        assert len(receipt["studio_messages"]) == 1
        assert cited not in {item["evidence_id"] for item in gateway.calls[0]["retrieved_evidence"]}
        assert service.list_model_calls(ms)[-1]["status"] == "REJECTED"
        assert service.get_workspace(ms)["document"] == document
    service._executor.shutdown(wait=True)


def test_old_discussion_keeps_original_references_after_regeneration(tmp_path):
    service, ms, _evidence, _source, _pdf, document = source_studio(tmp_path)
    first = generate(service, ms)
    gateway = FixedReferencesGateway([item["evidence_id"] for item in first["references"]])
    with TestClient(create_app(tmp_path)) as client:
        client.app.state.discussions.gateway = gateway
        source = bound(client, generated_target(ms, first))
        _, original = send(client, source, content="zzzNoLiveMatch2026")
        assert original["job"]["status"] == "COMPLETE"
        parent = original["messages"][-1]["message_id"]
        with transaction(service.db_path) as conn:
            conn.execute("UPDATE papers SET title='New catalog version' WHERE paper_id='existing'")
        changed = deepcopy(document)
        changed["title"] = "A new author revision"
        service.save_document(ms, base_revision=1, operation_id="new-fixed-discussion-version",
                              document=changed)
        second = generate(service, ms)
        assert second["references"][0]["title"] == "New catalog version"
        _, followed = send(client, source, request_id="fixed-source-followup-after-regeneration",
                           content="zzzNoLiveMatch2026", parent_message_id=parent,
                           source={"target": source["target"],
                                   "expected_context_sha256": source["context_sha256"],
                                   "history_message_id": parent})
        assert followed["job"]["status"] == "COMPLETE", followed
        assert gateway.calls[-1]["generated_version"]["generated_version_id"] == first["generated_version_id"]
        assert gateway.calls[-1]["retrieved_evidence"] == gateway.calls[0]["retrieved_evidence"]
        context = client.get(f"{PREFIX}/messages/{parent}/context", params={"scope": source["scope_key"]})
        assert context.status_code == 200
        assert context.json()["sources"][0]["context"] == source
        assert context.json()["sources"][0]["current_source_state"] == "OLD_VERSION"
        assert service.get_generated_version(ms, first["generated_version_id"]) == first
        assert service.get_workspace(ms)["document"] == changed
    service._executor.shutdown(wait=True)
