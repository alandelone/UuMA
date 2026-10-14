from __future__ import annotations

import hashlib
import json
import threading
from copy import deepcopy

import pytest
from rstv4.service import NotFoundError
from test_writing_studio import complete_document, create_studio, wait_for_job


def generated_fixture(tmp_path):
    service, track_id, manuscript_id = create_studio(tmp_path)
    document = complete_document(service.get_workspace(manuscript_id))
    service.save_document(manuscript_id, base_revision=0, operation_id="review-input-original", document=document)
    service.gateway.analyze = lambda task, payload: {
        "paragraph": "The author decides the central scientific claim.",
        "sentences": ["The author decides the central scientific claim."],
        "sentence_mappings": [{"sentence": 0, "thought_ids": ["thought_author_1"]}],
        "_contract": {"actual_model": "declared-generation-fixture", "task": "paragraph_realization"},
    }
    service._compile_artifacts = lambda job, generated: []
    generated = wait_for_job(service, service.create_job(manuscript_id, "GENERATE", input_revision=1))
    assert generated["status"] == "SUCCEEDED"
    return service, track_id, manuscript_id, document, generated["result"]["generated_version_id"]


def test_review_fixes_original_author_input_and_records_actual_request_output_and_contract(tmp_path):
    service, _, manuscript_id, document, version_id = generated_fixture(tmp_path)
    later = deepcopy(document)
    later["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]["text"] = "A later unsynchronised realization must not enter the old review."
    service.save_document(manuscript_id, base_revision=1, operation_id="review-later-author", document=later)
    expected = {"findings": [{"kind": "DRIFT", "detail": "Declared fixture possible drift", "anchor": {"thought_id": "thought_author_1"}}],
                "_contract": {"actual_model": "declared-review-fixture", "task": "writing_review", "prompt_version": "fixture-review-v1"}}
    service.gateway.analyze = lambda task, payload: deepcopy(expected)
    job = wait_for_job(service, service.create_job(manuscript_id, "WHOLE_PAPER_REVIEW", input_revision=2))
    assert job["status"] == "SUCCEEDED" and job["request"]["generated_version_id"] == version_id
    assert job["result"]["author_input_revision"] == 1 and job["result"]["semantic_status"] == "AVAILABLE"
    calls = service.list_model_calls(manuscript_id, job_id=job["job_id"])
    assert len(calls) == 1 and calls[0]["status"] == "VALIDATED"
    call = calls[0]
    assert call["input"]["author_structure"] == document and call["input"]["author_input_revision"] == 1
    assert call["input"]["generated_version_id"] == version_id and call["output"] == expected
    assert call["input_sha256"] == hashlib.sha256(json.dumps(call["input"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert job["result"]["model_call_id"] == call["call_id"] and job["result"]["model_contract"] == expected["_contract"]
    current = service.get_workspace(manuscript_id)
    assert current["document"] == later and current["findings"][0]["status"] == "OPEN"
    assert current["findings"][0]["generated_version_id"] == version_id


@pytest.mark.parametrize("response", [
    {}, {"findings": None}, {"findings": "not-an-array"},
    {"findings": [{"detail": "   "}]}, {"findings": [{"detail": "Fixture", "severity": []}]},
    {"findings": [{"detail": "Fixture", "severity": "APPROVED"}]},
    {"findings": [{"detail": "Fixture", "anchor": "unbound"}]},
])
def test_malformed_model_review_is_recorded_rejected_and_never_becomes_model_findings(tmp_path, response):
    service, _, manuscript_id, _, _ = generated_fixture(tmp_path)
    service.gateway.analyze = lambda task, payload: deepcopy(response)
    job = wait_for_job(service, service.create_job(manuscript_id, "WHOLE_PAPER_REVIEW", input_revision=1))
    assert job["status"] == "SUCCEEDED" and job["result"]["semantic_status"].startswith("UNAVAILABLE:")
    call = service.list_model_calls(manuscript_id, job_id=job["job_id"])[0]
    assert call["status"] == "REJECTED" and call["output"] == response and call["error"]
    assert job["result"]["model_call_id"] == call["call_id"]
    assert not any(finding["source"] == "MODEL" for finding in service.get_workspace(manuscript_id)["findings"])


def test_actual_gateway_failure_is_recorded_and_does_not_approve_author_content(tmp_path):
    service, _, manuscript_id, document, _ = generated_fixture(tmp_path)
    def unavailable(task, payload):
        raise RuntimeError("Declared fixture unavailable")
    service.gateway.analyze = unavailable
    job = wait_for_job(service, service.create_job(manuscript_id, "WHOLE_PAPER_REVIEW", input_revision=1))
    call = service.list_model_calls(manuscript_id, job_id=job["job_id"])[0]
    assert call["status"] == "FAILED" and call["contract"] is None and call["output"] is None
    assert job["result"]["semantic_status"].startswith("UNAVAILABLE:")
    assert service.get_workspace(manuscript_id)["document"] == document


def test_new_generated_version_after_review_queues_cannot_change_fixed_review_target(tmp_path):
    service, _, manuscript_id, document, old_version = generated_fixture(tmp_path)
    run_job = service.run_job
    service.run_job = lambda job_id: None
    review = service.create_job(manuscript_id, "WHOLE_PAPER_REVIEW", input_revision=1)
    service.run_job = run_job
    new_document = deepcopy(document)
    new_document["title"] = "Successor fixture title"
    service.save_document(manuscript_id, base_revision=1, operation_id="review-successor-save", document=new_document)
    successor = wait_for_job(service, service.create_job(manuscript_id, "GENERATE", input_revision=2))
    assert successor["status"] == "SUCCEEDED"
    service.gateway.analyze = lambda task, payload: {"findings": [], "_contract": {"actual_model": "declared-review-fixture"}}
    service.run_job(review["job_id"])
    result = wait_for_job(service, review)
    assert result["result"]["generated_version_id"] == old_version
    assert result["result"]["author_input_revision"] == 1 and result["result"]["target_origin"] == "FIXED_AT_JOB_CREATION"
    assert service.get_workspace(manuscript_id)["active_generated_version_id"] == successor["result"]["generated_version_id"]


def test_review_refuses_other_manuscript_generated_version_before_call_or_job_write(tmp_path):
    service, track_id, _manuscript_id, _, version_id = generated_fixture(tmp_path)
    other = service.create_manuscript(track_id, "Other review owner")["manuscript"]["manuscript_id"]
    with pytest.raises(NotFoundError, match="belong"):
        service.create_job(other, "WHOLE_PAPER_REVIEW", input_revision=0, request={"generated_version_id": version_id})
    assert service.list_model_calls(other) == [] and service.get_workspace(other)["latest_job"] is None


def test_cancelled_model_review_retains_call_but_never_publishes_new_findings(tmp_path):
    service, _, manuscript_id, _, _ = generated_fixture(tmp_path)
    entered, release = threading.Event(), threading.Event()
    def waiting(task, payload):
        entered.set()
        assert release.wait(5)
        return {"findings": [{"detail": "Declared cancelled finding"}]}
    service.gateway.analyze = waiting
    job = service.create_job(manuscript_id, "WHOLE_PAPER_REVIEW", input_revision=1)
    assert entered.wait(5)
    service.cancel_job(job["job_id"])
    release.set()
    result = wait_for_job(service, job)
    assert result["status"] == "CANCELLED" and result["result"]["findings"] == []
    assert len(service.list_model_calls(manuscript_id, job_id=job["job_id"])) == 1
    assert service.get_workspace(manuscript_id)["findings"] == []
