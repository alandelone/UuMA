"""Local fake evidence for JSON path typing and uncertain source-seed rejection gates."""
from __future__ import annotations

import copy

import pytest
from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_dspy import json_text, write_json
from rstv4.skeleton_independent_source_edge import SOURCE_EDGE_REVISION_VERSION
from rstv4.skeleton_test_cue_reference_v6 import validated_seed_rejections


def fake_evidence(tmp_path):
    common = {"document_context": "fake document", "source_blocks": "[]",
              "reference_claims": "[]", "relation_ontology": "fake ontology"}
    compile_record = {"instructions": {"layer1": "fake instruction"}}
    edge = {"source_id": "source_endpoint", "target_id": "target_endpoint", "relation": "Contrast"}
    verdict = {**edge, "verdict": "UNSUPPORTED", "source_evidence_span_ids": ["fake:s1"],
               "target_evidence_span_ids": ["fake:s2"], "rationale": "The fake two statements do not establish this exact comparison."}
    pair = {"verdict": verdict, "initial_inputs": {"source_atom": json_text({"source_span_ids": ["fake:s1"]}),
              "target_atom": json_text({"source_span_ids": ["fake:s2"]}), "candidate_edge": json_text(edge)}}
    pair_path = tmp_path / "pair.json"
    write_json(pair_path, pair)
    failure = {"accepted_source_reference": False}
    failure_path = tmp_path / "failure.json"
    write_json(failure_path, failure)
    first = {"normalized_pair_path": str(pair_path), "normalized_pair_digest": digest(pair),
             "status": "ASSESSED", "verdict": verdict}
    old = {"source_reference_id": "fake:r1", "target_reference_id": "fake:r2", "relation": "Contrast"}
    frozen = {"version": SOURCE_EDGE_REVISION_VERSION, "selected_prompt_digest": digest(compile_record),
              "candidate_access": False, "learner_score_access": False, "desired_verdict_supplied": False,
              "original_source_or_score_edited": False, "original_source_inputs": common,
              "first_normalized_endpoint_record": first, "actual_failure_path": str(failure_path),
              "actual_failure_digest": digest(failure), "old_constraint": old, "old_constraint_digest": digest(old)}
    report = {"freeze_digest": digest(frozen), "reference_or_score_changed": False, "knowledge_change_applied": False,
              "first_judgment": verdict, "agreement": True, "eligible_for_test_only_rejection_proposal": True,
              "independent_review": verdict, "attempts": [{"model_output": {"verdict": verdict}}]}
    path = tmp_path / "revision" / "report.json"
    write_json(path.parent / "freeze.json", frozen)
    write_json(path, report)
    return path, common, compile_record, report


def test_native_json_path_strings_keep_exact_source_rejection(tmp_path):
    path, common, compile_record, _ = fake_evidence(tmp_path)
    values = validated_seed_rejections([path], common, compile_record)
    assert len(values) == 1
    assert values[0]["old_constraint"]["source_reference_id"] == "fake:r1"
    assert values[0]["scope"] == "TEST_REFERENCE_ELIGIBILITY_ONLY_NO_KNOWLEDGE_CHANGE"


@pytest.mark.parametrize("status", ["SUPPORTED", "UNCERTAIN"])
def test_positive_or_uncertain_independent_review_cannot_reject_old_source_seed(tmp_path, status):
    path, common, compile_record, report = fake_evidence(tmp_path)
    report = copy.deepcopy(report)
    report["independent_review"]["verdict"] = status
    write_json(path, report)
    with pytest.raises(SourceContractError, match="both actual current source reviews"):
        validated_seed_rejections([path], common, compile_record)


def test_seed_rejection_cannot_cross_source_windows(tmp_path):
    path, common, compile_record, _ = fake_evidence(tmp_path)
    assert validated_seed_rejections([path], {**common, "document_context": "another fake source"}, compile_record) == []


def test_missing_json_pair_evidence_is_never_accepted(tmp_path):
    path, common, compile_record, _ = fake_evidence(tmp_path)
    frozen_path = path.parent / "freeze.json"
    import json

    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    frozen["first_normalized_endpoint_record"]["normalized_pair_path"] = str(tmp_path / "never-created.json")
    write_json(frozen_path, frozen)
    report = json.loads(path.read_text(encoding="utf-8"))
    report["freeze_digest"] = digest(frozen)
    write_json(path, report)
    with pytest.raises(FileNotFoundError):
        validated_seed_rejections([path], common, compile_record)
