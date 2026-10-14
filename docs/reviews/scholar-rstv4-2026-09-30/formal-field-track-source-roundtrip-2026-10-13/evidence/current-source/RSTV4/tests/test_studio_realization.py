from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from rstv4.service import RSTV4Error
from rstv4.studio_api import create_app
from rstv4.studio_realization import validate
from test_writing_studio import complete_document, create_studio, wait_for_job


def response():
    return {"paragraph": "First fixture sentence. Second fixture sentence.",
            "sentences": ["First fixture sentence.", "Second fixture sentence."],
            "sentence_mappings": [{"sentence": 0, "thought_ids": ["first"]},
                                  {"sentence": 1, "thought_ids": ["first", "second"]}],
            "_contract": {"task": "paragraph_realization", "actual_model": "declared-test-fixture",
                          "prompt_version": "test-only", "usage": {"total_tokens": 17}}}


@pytest.mark.parametrize("defect", ["mapping_string", "mapping_object", "member_string", "ids_string",
                                   "unknown_id", "missing_id", "index_bool", "index_duplicate",
                                   "index_out_of_range", "sentence_mismatch", "sentence_omitted",
                                   "invented_citation"])
def test_invalid_realization_cannot_supply_a_provenance_mapping(defect: str):
    row = response()
    if defect == "mapping_string":
        row["sentence_mappings"] = "first"
    elif defect == "mapping_object":
        row["sentence_mappings"] = {"first": [0]}
    elif defect == "member_string":
        row["sentence_mappings"] = ["first"]
    elif defect == "ids_string":
        row["sentence_mappings"][0]["thought_ids"] = "first"
    elif defect == "unknown_id":
        row["sentence_mappings"][0]["thought_ids"] = ["invented"]
    elif defect == "missing_id":
        row["sentence_mappings"][1]["thought_ids"] = ["first"]
    elif defect == "index_bool":
        row["sentence_mappings"][0]["sentence"] = True
    elif defect == "index_duplicate":
        row["sentence_mappings"][1]["sentence"] = 0
    elif defect == "index_out_of_range":
        row["sentence_mappings"][1]["sentence"] = 2
    elif defect == "sentence_mismatch":
        row["sentences"][1] = "Different content."
    elif defect == "sentence_omitted":
        row["sentences"] = row["sentences"][:1]
    else:
        row["paragraph"] += " [@invented]"
    original = deepcopy(row)
    with pytest.raises(RSTV4Error):
        validate(row, {"first", "second"}, set())
    assert row == original


def test_one_thought_can_map_to_multiple_exact_sentences_without_guessing_positions():
    result = validate(response(), {"first", "second"}, set())
    assert result["sentence_positions_verified"]
    assert result["sentence_mappings"][1]["thought_ids"] == ["first", "second"]
    for sentence in result["sentences"]:
        assert result["text"][sentence["start"]:sentence["end"]] == sentence["text"]
    old = response()
    del old["sentences"]
    legacy = validate(old, {"first", "second"}, set())
    assert not legacy["sentence_positions_verified"] and legacy["sentences"] == []


def prepared(tmp_path: Path):
    service, track_id, manuscript_id = create_studio(tmp_path)
    document = complete_document(service.get_workspace(manuscript_id))
    thoughts = document["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"]
    thoughts[0]["id"] = "first"
    thoughts.append({**deepcopy(thoughts[0]), "id": "second", "text": "Second author fixture."})
    service.save_document(manuscript_id, base_revision=0, operation_id="realization-initial",
                          document=document)
    service._compile_artifacts = lambda job, generated: []
    return service, track_id, manuscript_id, document


def test_rejected_actual_output_is_retained_before_bounded_schema_recovery(tmp_path: Path):
    service, _, manuscript_id, document = prepared(tmp_path)
    payloads = []
    invalid = response()
    invalid["sentence_mappings"] = {"first": [0]}

    def analyze(task, payload):
        payloads.append(deepcopy(payload))
        return deepcopy(invalid if len(payloads) == 1 else response())

    service.gateway.analyze = analyze
    job = wait_for_job(service, service.create_job(manuscript_id, "GENERATE", input_revision=1))
    assert job["status"] == "SUCCEEDED", job
    calls = service.list_model_calls(manuscript_id, job_id=job["job_id"])
    assert [item["status"] for item in calls] == ["REJECTED", "VALIDATED"]
    assert calls[0]["output"] == invalid and "array of objects" in calls[0]["error"]["message"]
    assert calls[1]["input"]["schema_correction"]["attempt"] == 1
    assert calls[1]["contract"]["actual_model"] == "declared-test-fixture"
    for call in calls:
        serialized = json.dumps(call["input"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        assert hashlib.sha256(serialized.encode()).hexdigest() == call["input_sha256"]
    generated = service.get_generated_version(manuscript_id, job["result"]["generated_version_id"])
    paragraph = next(item for item in generated["blocks"] if item["kind"] == "paragraph")
    realization = next(item for item in generated["realizations"] if item["paragraph_id"] == paragraph["object_id"])
    assert "model_call_id" not in paragraph
    assert realization["model_call_id"] == calls[1]["call_id"]
    assert realization["model_contract"] == calls[1]["contract"]
    assert realization["sentence_positions_verified"]
    assert service.get_workspace(manuscript_id)["document"] == document
    with TestClient(create_app(tmp_path)) as client:
        result = client.get(f"/api/manuscripts/{manuscript_id}/model-calls", params={"job_id": job["job_id"]})
        assert result.status_code == 200 and result.json() == calls


def test_three_rejected_attempts_fail_without_promoting_or_editing_author_input(tmp_path: Path):
    service, _, manuscript_id, document = prepared(tmp_path)
    invalid = response()
    invalid["sentence_mappings"] = ["first"]
    service.gateway.analyze = lambda task, payload: deepcopy(invalid)
    job = wait_for_job(service, service.create_job(manuscript_id, "GENERATE", input_revision=1))
    assert job["status"] == "FAILED" and "contain objects" in job["error"]["message"]
    calls = service.list_model_calls(manuscript_id, job_id=job["job_id"])
    assert len(calls) == 3 and all(item["status"] == "REJECTED" for item in calls)
    assert all(item["output"] == invalid for item in calls)
    workspace = service.get_workspace(manuscript_id)
    assert workspace["document"] == document and workspace["active_generated_version_id"] is None
    assert not workspace["artifacts"]


def test_ordinary_chat_retains_actual_contract_without_adoption_and_failure_is_explicit(tmp_path: Path):
    service, _, manuscript_id, document = prepared(tmp_path)
    contract = {"task": "writing_chat", "actual_model": "declared-test-fixture", "usage": {"total_tokens": 11}}
    service.gateway.analyze = lambda task, payload: {"answer": "Discussion only.", "_contract": contract}
    chat = service.discuss(manuscript_id, content="Discuss fixture", anchor_type="thought", anchor_id="first", anchor_revision=1)
    assert chat["agent"]["model_provenance"]["model_contract"] == contract
    assert chat["agent"]["quoted"] == {**chat["author"]["quoted"], "evidence_ids": []}
    assert not chat["agent"]["quoted"].get("suggestions")
    calls = service.list_model_calls(manuscript_id)
    assert len(calls) == 1 and calls[0]["message_id"] == chat["author"]["message_id"]
    assert calls[0]["call_id"] == chat["agent"]["model_provenance"]["model_call_id"]
    assert calls[0]["status"] == "RETURNED"

    def unavailable(task, payload):
        raise RuntimeError("Declared fixture gateway unavailable")

    service.gateway.analyze = unavailable
    with pytest.raises(RSTV4Error, match="unavailable"):
        service.discuss(manuscript_id, content="Discuss again", anchor_type="thought", anchor_id="first", anchor_revision=1)
    failed = service.list_model_calls(manuscript_id)[1]
    assert failed["status"] == "FAILED" and failed["contract"] is None and failed["output"] is None
    assert failed["error"]["type"] == "RuntimeError"
    assert service.get_workspace(manuscript_id)["document"] == document


def test_model_calls_cannot_be_read_as_another_manuscripts_job(tmp_path: Path):
    service, track_id, manuscript_id, _ = prepared(tmp_path)
    service.gateway.analyze = lambda task, payload: response()
    job = wait_for_job(service, service.create_job(manuscript_id, "GENERATE", input_revision=1))
    other = service.create_manuscript(track_id, "Other fixture")["manuscript"]["manuscript_id"]
    with TestClient(create_app(tmp_path)) as client:
        result = client.get(f"/api/manuscripts/{other}/model-calls", params={"job_id": job["job_id"]})
        assert result.status_code == 404
    assert service.list_model_calls(other) == []
