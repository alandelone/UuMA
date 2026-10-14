from __future__ import annotations

import copy

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

import dspy
from rstv4.skeleton_contextual_review import ContextualMappedBlockSourceReviewer
from rstv4.skeleton_contract import SourceContractError, with_source_spans
from rstv4.skeleton_dspy import PaperSkeletonProgram, json_text, write_json
from rstv4.skeleton_grounded_review import ReferenceDefect
from rstv4.skeleton_mapped_review import MatchValue, VerdictValue


def source():
    blocks = with_source_spans([
        {"block_id": "a", "text": "Cost is 0.2 USD/kWh."},
        {"block_id": "b", "text": "The study area is defined in Methods."},
    ])
    claims = [{"reference_id": "a:r1", "block_id": "a", "source_span_ids": ["a:s1"],
               "quote": blocks[0]["text"], "qualifications": [],
               "statement": blocks[0]["text"], "intent": "Objective_Finding"}]
    atoms = [{"atom_id": "a:a1", "source_span_ids": ["a:s1"],
              "statement": blocks[0]["text"]}]
    role = {"block_id": "a", "role": "Result_Performance", "confidence": 0.9,
            "rationale": "The source reports measured cost."}
    return blocks, claims, atoms, role


def test_contextual_grading_requires_exact_raw_window_and_document(tmp_path):
    blocks, claims, atoms, role = source()
    reviewer = ContextualMappedBlockSourceReviewer(tmp_path, actual_model="test")
    reviewer.predictor = lambda **kwargs: pytest.fail("Invalid context must fail before model access")
    with pytest.raises(SourceContractError, match="full source window"):
        reviewer.assess("{}", blocks[0], [], claims, role, atoms)
    reviewer.bind_window({"document_context": "other", "source_blocks": json_text(blocks)})
    with pytest.raises(SourceContractError, match="full source window"):
        reviewer.assess("{}", blocks[0], [], claims, role, atoms)
    reviewer.bind_window({"document_context": "{}", "source_blocks": json_text(blocks[1:])})
    with pytest.raises(SourceContractError, match="exactly once"):
        reviewer.assess("{}", blocks[0], [], claims, role, atoms)


def test_full_context_uses_actual_role_contract_and_retains_genuine_defects(tmp_path):
    blocks, claims, atoms, role = source()
    original = copy.deepcopy((blocks, claims, atoms, role))
    reviewer = ContextualMappedBlockSourceReviewer(tmp_path, actual_model="test")
    window = {"document_context": "{}", "source_blocks": json_text(blocks)}
    reviewer.bind_window(window)
    calls = []
    defect = {"kind": "role", "record_id": "a", "evidence_span_ids": ["a:s1"],
              "rationale": "This actual source-specific alternative is deliberately retained."}

    def predict(**values):
        calls.append(values)
        return dspy.Prediction(
            claim_matches={"r0": MatchValue(atom_id="c0", meaning_preserved=True,
                                           qualifications_preserved=True, rationale="Same measured cost.")},
            candidate_verdicts={"c0": VerdictValue(verdict="SUPPORTED", evidence_span_ids=["a:s1"],
                                                   rationale="The exact source reports this cost.")},
            reference_defects=[ReferenceDefect.model_validate(defect)],
            feedback="Preserve the actual role defect for source review.",
        )

    reviewer.predictor = predict
    result = reviewer.assess("{}", blocks[0], [], claims, role, atoms)
    assert calls[0]["source_context_blocks"] == window["source_blocks"]
    assert calls[0]["extraction_role_contract"] == PaperSkeletonProgram().layer4.signature.instructions
    assert result["review"]["reference_defects"] == [defect]
    assert (blocks, claims, atoms, role) == original
    cache = tmp_path / "blocks" / f"{result['input_digest']}.json"
    corrupted = copy.deepcopy(result)
    corrupted["actual_inputs"]["source_context_blocks"] = "[]"
    write_json(cache, corrupted)
    with pytest.raises(SourceContractError, match="inputs changed"):
        reviewer.assess("{}", blocks[0], [], claims, role, atoms)
    assert len(calls) == 1


def test_a_changed_source_window_cannot_reuse_an_earlier_contextual_judgment(tmp_path):
    blocks, _, _, role = source()
    reviewer = ContextualMappedBlockSourceReviewer(tmp_path, actual_model="test")
    reviewer.bind_window({"document_context": "{}", "source_blocks": json_text(blocks)})
    first = reviewer.assess("{}", blocks[0], [], [], role, [])
    blocks[1]["text"] = "The actual context has changed."
    reviewer.bind_window({"document_context": "{}", "source_blocks": json_text(blocks)})
    second = reviewer.assess("{}", blocks[0], [], [], role, [])
    assert first["input_digest"] != second["input_digest"]
    assert len(list((tmp_path / "blocks").glob("*.json"))) == 2
