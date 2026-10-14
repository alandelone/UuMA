from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_block_review import (
    BLOCK_REVIEW_VERSION,
    alias_block_records,
    unassessed_block_review,
    validate_block_review,
)
from rstv4.skeleton_contract import SourceContractError, digest, with_source_spans
from rstv4.skeleton_dspy import json_text, write_json
from rstv4.skeleton_mapped_review import (
    MappedBlockSourceReviewer,
    MatchValue,
    VerdictValue,
    restore_mapped_review,
    strict_json_object,
)


def fixture() -> tuple[dict, list[dict], list[dict], dict]:
    block = with_source_spans([{"block_id": "a", "text": "Cost is 0.2 USD/kWh. Alice is an author."}])[0]
    claims = [{"reference_id": "a:r1", "block_id": "a", "source_span_ids": ["a:s1"],
               "quote": block["source_spans"][0]["text"], "qualifications": [],
               "statement": "Cost is 0.2 USD/kWh.", "intent": "Objective_Finding"}]
    atoms = [{"atom_id": "a:a1", "source_span_ids": ["a:s1"], "statement": "Cost is 0.2 USD/kWh."},
             {"atom_id": "a:a2", "source_span_ids": ["a:s2"], "statement": "Alice is an author."}]
    mapped = {"claim_matches": {"r0": {"atom_id": "c0", "meaning_preserved": True,
                                       "qualifications_preserved": True, "rationale": "Same measured cost."}},
              "candidate_verdicts": {f"c{i}": {"verdict": "SUPPORTED", "evidence_span_ids": atom["source_span_ids"],
                                             "rationale": "This actual assertion is explicitly stated in its original source."}
                                     for i, atom in enumerate(atoms)},
              "reference_defects": [], "feedback": "Correct metadata remains supported."}
    return block, claims, atoms, mapped


@pytest.mark.parametrize("payload", [
    '{"claim_matches":{"r0":{},"r0":{}},"candidate_verdicts":{}}',
    '{"claim_matches":{},"candidate_verdicts":{"c0":{"verdict":"SUPPORTED","verdict":"UNSUPPORTED"}}}',
])
def test_duplicate_json_keys_are_rejected_before_repair_can_discard_them(payload: str) -> None:
    with pytest.raises(SourceContractError, match="Duplicate JSON"):
        strict_json_object(payload)


def test_mapped_judgment_keeps_source_metadata_without_extra_negative_matches() -> None:
    block, claims, atoms, mapped = fixture()
    _, _, maps = alias_block_records(claims, atoms)
    review = restore_mapped_review(mapped, maps)
    validate_block_review(block, claims, atoms, review)
    assert len(review["matches"]) == 1
    assert [item["atom_id"] for item in review["atom_verdicts"]] == ["a:a1", "a:a2"]
    assert review["atom_verdicts"][1]["verdict"] == "SUPPORTED"
    assert strict_json_object("```json\n" + json.dumps(mapped) + "\n```") == mapped


@pytest.mark.parametrize("kind", ["missing_reference", "extra_reference", "missing_atom", "wrong_anchor"])
def test_missing_items_and_wrong_actual_evidence_cannot_pass(kind: str) -> None:
    block, claims, atoms, mapped = fixture()
    _, _, maps = alias_block_records(claims, atoms)
    if kind == "missing_reference":
        mapped["claim_matches"].clear()
    elif kind == "extra_reference":
        mapped["claim_matches"]["r9"] = copy.deepcopy(mapped["claim_matches"]["r0"])
    elif kind == "missing_atom":
        mapped["candidate_verdicts"].pop("c1")
    else:
        mapped["candidate_verdicts"]["c0"]["evidence_span_ids"] = ["a:s2"]
    with pytest.raises(SourceContractError):
        review = restore_mapped_review(mapped, maps)
        validate_block_review(block, claims, atoms, review)


def test_only_exact_successful_defect_free_legacy_records_are_adopted(tmp_path: Path) -> None:
    block, claims, atoms, mapped = fixture()
    changed_claims, changed_atoms, maps = alias_block_records(claims, atoms)
    role = {"block_id": "a", "role": "Result_Performance", "confidence": 0.9,
            "rationale": "The source states the measured cost."}
    values = {"document_context": "{}", "source_block": json_text(block), "adjacent_source_blocks": "[]",
              "reference_claims": json_text(changed_claims), "reference_role": json_text(role),
              "candidate_atoms": json_text(changed_atoms)}
    key = digest({"version": BLOCK_REVIEW_VERSION, "inputs": values, "maps": maps})
    parent = {"input_digest": key, "identifier_maps": maps, "review": restore_mapped_review(mapped, maps),
              "status": "ASSESSED", "failed_attempts": []}
    legacy = tmp_path / "legacy"
    write_json(legacy / f"{key}.json", parent)
    parent_bytes = (legacy / f"{key}.json").read_bytes()
    reviewer = MappedBlockSourceReviewer(tmp_path / "new", actual_model="test", legacy_root=legacy)
    reviewer.predictor = lambda **kwargs: pytest.fail("An exact valid parent needs no model call")
    result = reviewer.assess("{}", block, [], claims, role, atoms)
    assert result["parent_digest"] == digest(parent)
    assert result["review"] == parent["review"]
    assert (legacy / f"{key}.json").read_bytes() == parent_bytes


@pytest.mark.parametrize("problem", ["failure", "reference_defect"])
def test_failed_or_defective_parent_is_preserved_and_requires_a_new_judgment(tmp_path: Path, problem: str) -> None:
    import dspy

    block, claims, atoms, mapped = fixture()
    changed_claims, changed_atoms, maps = alias_block_records(claims, atoms)
    role = {"block_id": "a", "role": "Result_Performance", "confidence": 0.9,
            "rationale": "The source states the measured cost."}
    values = {"document_context": "{}", "source_block": json_text(block), "adjacent_source_blocks": "[]",
              "reference_claims": json_text(changed_claims), "reference_role": json_text(role),
              "candidate_atoms": json_text(changed_atoms)}
    key = digest({"version": BLOCK_REVIEW_VERSION, "inputs": values, "maps": maps})
    review = restore_mapped_review(mapped, maps)
    if problem == "failure":
        review = unassessed_block_review(claims, atoms, "Previous bounded contract failure")
    else:
        review["reference_defects"] = [{"kind": "role", "record_id": "a", "evidence_span_ids": ["a:s1"],
                                        "rationale": "The previous critic proposed a conflicting source macro role."}]
    parent = {"input_digest": key, "identifier_maps": maps, "review": review,
              "status": "EVALUATION_CONTRACT_FAILURE" if problem == "failure" else "ASSESSED",
              "failed_attempts": ["Previous bounded contract failure"] if problem == "failure" else []}
    legacy = tmp_path / "legacy"
    write_json(legacy / f"{key}.json", parent)
    parent_bytes = (legacy / f"{key}.json").read_bytes()
    calls = []

    def predict(**kwargs: object) -> dspy.Prediction:
        calls.append(kwargs)
        return dspy.Prediction(claim_matches={key: MatchValue.model_validate(value) for key, value in mapped["claim_matches"].items()},
                               candidate_verdicts={key: VerdictValue.model_validate(value) for key, value in mapped["candidate_verdicts"].items()},
                               reference_defects=[], feedback=mapped["feedback"])

    reviewer = MappedBlockSourceReviewer(tmp_path / "new", actual_model="test", legacy_root=legacy)
    reviewer.predictor = predict
    result = reviewer.assess("{}", block, [], claims, role, atoms)
    assert len(calls) == 1
    assert result["origin"] == "UNIQUE_KEY_SOURCE_REVIEW"
    assert (legacy / f"{key}.json").read_bytes() == parent_bytes
