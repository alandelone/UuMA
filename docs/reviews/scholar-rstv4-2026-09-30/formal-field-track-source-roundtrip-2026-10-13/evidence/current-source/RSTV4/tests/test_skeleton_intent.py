from __future__ import annotations

import json
import sqlite3
from contextlib import closing

import pytest
from test_acquisition_deep_read import RecordedGateway, parse, request, setup
from test_fieldkg_workspace import get_field
from test_fieldkg_workspace import setup as field_setup

from rstv4.acquisition_worker import AcquisitionWorker
from rstv4.model_gateway import CONTRACTS
from rstv4.skeleton_intent import INTENT_VERSION, intent_coverage, validate_intent


def output(**values):
    return {"intent": "Objective_Finding", "confidence": .8, "rationale": "Located report",
            "evidence_quote": "Tests report 80% accuracy under cold conditions.",
            "qualifications": ["under cold conditions"], **values}


def test_new_prompt_declares_explicit_schema_and_source_qualifications():
    contract = CONTRACTS["skeleton_layer_3"]
    assert contract.version == INTENT_VERSION
    for value in ["Objective_Finding", "Research_Gap", "UNKNOWN", "evidence_quote", "qualifications", "Formal"]:
        assert value in contract.instruction


@pytest.mark.parametrize("values", [
    {"intent": "free text description"}, {"confidence": 1.5},
    {"evidence_quote": "Invented result"}, {"qualifications": ["hot conditions"]},
    {"unexpected": "extra meaning"}, {"rationale": ""},
    {"evidence_quote": "  Tests report 80% accuracy under cold conditions."},
    {"qualifications": [" under cold conditions "]},
])
def test_missing_unsupported_or_unlocated_classification_is_rejected(values):
    with pytest.raises(ValueError):
        validate_intent(output(**values), "Tests report 80% accuracy under cold conditions.")


def test_old_free_text_is_not_guessed_into_an_intent_or_rewritten():
    layer3 = {"communicative_intent": "To explicitly assert a result", "rationale": "Old output"}
    source = {"skeleton_id": "old", "units": [{"unit_id": "unit", "raw_text": "Old source", "layer3": layer3}]}
    before = json.dumps(source, sort_keys=True)
    result = intent_coverage([source])
    assert not result["complete"] and result["typed_units"] == 0
    assert result["unclassified_units"][0]["layer3"] == layer3
    assert json.dumps(source, sort_keys=True) == before


def test_explicit_unknown_is_distinct_from_missing_and_not_an_evidence_candidate():
    source = {"skeleton_id": "s", "units": [{"unit_id": "u", "raw_text": "Insufficient", "layer3": {"intent": "UNKNOWN"}}]}
    result = intent_coverage([source])
    assert result["complete"] and result["unknown_units"] == 1


class TypedGateway(RecordedGateway):
    def analyze(self, task, payload):
        result = super().analyze(task, payload)
        if task == "skeleton_layer_3":
            result = {**output(), "_contract": {**result["_contract"], "prompt_version": INTENT_VERSION}}
        return result


def test_current_typed_layer_is_saved_with_model_receipt_and_old_generation_kept(tmp_path, monkeypatch):
    from rstv4.acquisition_worker import ROLE_QUEUES
    monkeypatch.setitem(ROLE_QUEUES, "model", ["MODEL_SKELETON"])
    service, cid, db, _ = setup(tmp_path)
    parsed = parse(service, cid, "Tests report 80% accuracy under cold conditions.")
    old = service.publish_skeleton_result(parsed["parse_run_id"], [{"block_id": "old", "raw_text": "Old source", "layer1": {}, "layer2": {}, "layer3": {"communicative_intent": "Old description"}, "layer4": {}}], model_name="old-fixture")
    request(service, cid)
    completed = AcquisitionWorker(tmp_path, "model", model_gateway=TypedGateway(), worker_id="typed-layer-fixture").run_once()
    assert completed["status"] == "SUCCEEDED"
    published = json.loads(completed["result_json"])
    assert published["skeleton_id"] != old["skeleton_id"]
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT prompt_version FROM paper_skeletons WHERE skeleton_id=?", (published["skeleton_id"],)).fetchone()[0] == "paper-skeleton-v2-located-intent"
        rows = conn.execute("SELECT layer3_json FROM skeleton_units ORDER BY rowid").fetchall()
        assert json.loads(rows[0][0]) == {"communicative_intent": "Old description"}
        assert json.loads(rows[-1][0])["intent"] == "Objective_Finding"
        receipt = conn.execute("SELECT output_json,contract_json FROM acquisition_model_call_events WHERE task='skeleton_layer_3' AND event_kind='RETURNED'").fetchone()
        assert json.loads(receipt[0])["intent"] == "Objective_Finding"
        assert json.loads(receipt[1])["prompt_version"] == INTENT_VERSION


def test_invalid_actual_output_retains_receipt_and_publishes_no_skeleton(tmp_path, monkeypatch):
    from rstv4.acquisition_worker import ROLE_QUEUES
    monkeypatch.setitem(ROLE_QUEUES, "model", ["MODEL_SKELETON"])
    service, cid, db, _ = setup(tmp_path)
    parse(service, cid, "Tests report 80% accuracy under cold conditions.")
    request(service, cid)
    class Invalid(TypedGateway):
        def analyze(self, task, payload):
            result = super().analyze(task, payload)
            if task == "skeleton_layer_3":
                result["evidence_quote"] = "Invented scientific conclusion"
            return result
    completed = AcquisitionWorker(tmp_path, "model", model_gateway=Invalid(), worker_id="invalid-layer-fixture").run_once()
    assert completed["status"] != "SUCCEEDED"
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM paper_skeletons").fetchone()[0] == 0
        receipt = conn.execute("SELECT output_json FROM acquisition_model_call_events WHERE task='skeleton_layer_3' AND event_kind='RETURNED'").fetchone()
        assert json.loads(receipt[0])["evidence_quote"] == "Invented scientific conclusion"


def test_unclassified_build_cannot_be_sealed_and_read_preserves_original_source(tmp_path):
    client, db, field, _, _, build = field_setup.__wrapped__(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE skeleton_units SET layer3_json=?", (json.dumps({"communicative_intent": "Old free text"}),))
        conn.execute("UPDATE fieldkg_evidence_candidates SET status='REJECTED'")
        conn.execute("UPDATE fieldkg_candidate_gaps SET status='REJECTED'")
    data = get_field(client, field)
    row = next(b for b in data["builds"] if b["build_id"] == build)
    assert not row["semantic_coverage"]["complete"]
    ready = client.post("/api/catalog/fieldkg-actions", json={"operation": "READY_BUILD", "request_id": "typed-intent-ready", "field_id": field, "confirmed": True, "build_id": build, "expected_context_sha256": row["context_sha256"]})
    assert ready.status_code == 200
    before = db.read_bytes()
    sealed = client.post("/api/catalog/fieldkg-actions", json={"operation": "SEAL_SNAPSHOT", "request_id": "typed-intent-seal", "field_id": field, "confirmed": True, "build_id": build, "expected_context_sha256": ready.json()["build"]["context_sha256"]})
    assert sealed.status_code == 422 and "structured Intent" in sealed.text
    assert db.read_bytes() == before
