from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

import dspy
from rstv4.skeleton_contract import SourceContractError, with_source_spans
from rstv4.skeleton_dspy import json_text
from rstv4.skeleton_grounded_review import ReferenceDefect
from rstv4.skeleton_mapped_review import MatchValue, VerdictValue
from rstv4.skeleton_reference_adjudication import (
    AdjudicatedBlockSourceReviewer,
    validate_source_validity,
)


@pytest.mark.parametrize("status", ["VALID", "DEFECT", "UNRESOLVED"])
def test_actual_source_decision_preserves_comparator_and_controls_fatal_state(tmp_path, monkeypatch, status):
    block = with_source_spans([{"block_id": "a", "text": "Cost is 0.2 USD/kWh."}])[0]
    claims = [{"reference_id": "a:r1", "block_id": "a", "source_span_ids": ["a:s1"],
               "quote": block["text"], "qualifications": [],
               "statement": block["text"], "intent": "Objective_Finding"}]
    atoms = [{"atom_id": "a:a1", "source_span_ids": ["a:s1"], "statement": block["text"]}]
    role = {"block_id": "a", "role": "Result_Performance", "confidence": 0.9,
            "rationale": "The actual source reports cost."}
    comparator_defect = {"kind": "claim", "record_id": "r0", "evidence_span_ids": ["a:s1"],
                         "rationale": "The comparator expressed this concern about the reference."}
    source_defect = {**comparator_defect, "rationale": "The source-only reviewer identified a specific reference disagreement."}
    reviewer = AdjudicatedBlockSourceReviewer(tmp_path, actual_model="test")
    reviewer.bind_window({"document_context": "{}", "source_blocks": json_text([block])})
    reviewer.raw.predictor = lambda **values: dspy.Prediction(
        claim_matches={"r0": MatchValue(atom_id="c0", meaning_preserved=True,
                                        qualifications_preserved=True, rationale="Same cost assertion.")},
        candidate_verdicts={"c0": VerdictValue(verdict="SUPPORTED", evidence_span_ids=["a:s1"],
                                               rationale="Exact original source value.")},
        reference_defects=[ReferenceDefect.model_validate(comparator_defect)], feedback="Retain the source concern.",
    )
    calls = []

    class SourcePredictor:
        def __init__(self, signature):
            self.signature = signature

        def __call__(self, **values):
            calls.append(values)
            return dspy.Prediction(
                source_status=status, checked_reference_ids=["r0"], role_checked=True,
                reference_defects=[ReferenceDefect.model_validate(source_defect)] if status == "DEFECT" else [],
                evidence_span_ids=["a:s1"], rationale="This source-only decision keeps its original uncertainty or actual defect.",
            )

    monkeypatch.setattr(dspy, "Predict", SourcePredictor)
    result = reviewer.assess("{}", block, [], claims, role, atoms)
    raw = json.loads(Path(result["raw_review_path"]).read_text(encoding="utf-8"))
    assert raw["mapped_output"]["reference_defects"] == [comparator_defect]
    assert result["mapped_output"] == raw["mapped_output"]
    assert len(calls) == 2
    for values in calls:
        assert "candidate_atoms" not in values and "score" not in values
        assert "reference_defects" not in values and "comparator_feedback" not in values
        assert values["reference_claims"] == raw["actual_inputs"]["reference_claims"]
    assert "source_annotation" in calls[1]
    if status == "VALID":
        assert result["review"]["reference_defects"] == []
        assert result["review"]["matches"] == raw["review"]["matches"]
    elif status == "DEFECT":
        assert result["review"]["reference_defects"][0]["record_id"] == "a:r1"
        assert result["review"]["reference_defects"][0]["rationale"] == source_defect["rationale"]
    else:
        assert result["status"] == "EVALUATION_CONTRACT_FAILURE"
        assert result["review"]["atom_verdicts"][0]["verdict"] == "UNCERTAIN"
        assert "Unresolved source-only" in result["failed_attempts"][0]


@pytest.mark.parametrize("changed", ["missing_reference", "foreign_span", "invented_defect", "false_valid"])
def test_source_reference_adjudication_cannot_hide_coverage_or_domain_failures(changed):
    block = with_source_spans([{"block_id": "a", "text": "Cost is 0.2 USD/kWh."}])[0]
    values = {"source_block": json_text(block),
              "reference_claims": json_text([{"reference_id": "r0", "source_span_ids": ["a:s1"]}])}
    result = {"source_status": "VALID", "checked_reference_ids": ["r0"], "role_checked": True,
              "reference_defects": [], "evidence_span_ids": ["a:s1"],
              "rationale": "All actual reference assertions and role have been checked."}
    if changed == "missing_reference":
        result["checked_reference_ids"] = []
    elif changed == "foreign_span":
        result["evidence_span_ids"] = ["b:s1"]
    else:
        result["reference_defects"] = [{"kind": "claim", "record_id": "r9" if changed == "invented_defect" else "r0",
                                        "evidence_span_ids": ["a:s1"], "rationale": "This is a source-specific defect with an actual evidence span."}]
        if changed == "invented_defect":
            result["source_status"] = "DEFECT"
    before = copy.deepcopy(result)
    with pytest.raises(SourceContractError):
        validate_source_validity(values, result)
    assert result == before
