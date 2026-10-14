from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_block_review import (
    LocalSourceReviewer,
    aggregate_local_reports,
    alias_block_records,
    restore_block_review,
    unassessed_block_review,
    validate_block_review,
)
from rstv4.skeleton_contract import SourceContractError, with_source_spans


def fixture() -> tuple[dict, list[dict], list[dict], dict]:
    block = with_source_spans([{
        "block_id": "a", "text": "The measured cost is 0.2 USD/kWh in scenario A. Alice is an author.",
    }])[0]
    claims = [{"reference_id": "a:r1", "block_id": "a", "source_span_ids": ["a:s1"],
               "quote": block["source_spans"][0]["text"], "qualifications": ["scenario A"],
               "statement": "The measured cost is 0.2 USD/kWh in scenario A.",
               "intent": "Objective_Finding"}]
    atoms = [
        {"atom_id": "a:a1", "source_span_ids": ["a:s1"],
         "statement": "The measured cost is 0.2 USD/kWh in scenario A.",
         "qualifications": ["scenario A", "0.2 USD/kWh"], "triplets": []},
        {"atom_id": "a:a2", "source_span_ids": ["a:s2"],
         "statement": "Alice is an author.", "qualifications": [], "triplets": []},
    ]
    review = {
        "matches": [{"reference_id": "a:r1", "atom_id": "a:a1", "meaning_preserved": True,
                     "qualifications_preserved": True, "rationale": "Same measured cost and scenario."}],
        "atom_verdicts": [{"atom_id": atom["atom_id"], "verdict": "SUPPORTED",
                           "evidence_span_ids": atom["source_span_ids"],
                           "rationale": "This actual proposition is explicitly stated in the original source."}
                          for atom in atoms],
        "reference_defects": [], "feedback": "Both source-supported atoms checked individually.",
    }
    return block, claims, atoms, review


def test_block_aliases_change_only_ids_and_round_trip_exactly() -> None:
    _, claims, atoms, review = fixture()
    original = copy.deepcopy((claims, atoms))
    changed_claims, changed_atoms, maps = alias_block_records(claims, atoms)
    assert (claims, atoms) == original
    changed_claims[0]["reference_id"] = claims[0]["reference_id"]
    for index, atom in enumerate(changed_atoms):
        atom["atom_id"] = atoms[index]["atom_id"]
    assert (changed_claims, changed_atoms) == original
    aliased = copy.deepcopy(review)
    aliased["matches"][0].update(reference_id="r0", atom_id="c0")
    for index, verdict in enumerate(aliased["atom_verdicts"]):
        verdict["atom_id"] = f"c{index}"
    assert restore_block_review(aliased, maps) == review


@pytest.mark.parametrize("kind", ["reference", "atom"])
def test_invented_alias_is_rejected(kind: str) -> None:
    _, claims, atoms, review = fixture()
    _, _, maps = alias_block_records(claims, atoms)
    review["matches"][0].update(reference_id="r0", atom_id="c0")
    for index, verdict in enumerate(review["atom_verdicts"]):
        verdict["atom_id"] = f"c{index}"
    review["matches"][0]["reference_id" if kind == "reference" else "atom_id"] = "invented"
    with pytest.raises(SourceContractError, match="invented"):
        restore_block_review(review, maps)


def test_match_cannot_use_another_blocks_atom_or_cover_null() -> None:
    block, claims, atoms, review = fixture()
    review["matches"][0]["atom_id"] = "other:a1"
    with pytest.raises(SourceContractError, match="this source block"):
        validate_block_review(block, claims, atoms, review)
    review["matches"][0]["atom_id"] = None
    with pytest.raises(SourceContractError, match="actual atom"):
        validate_block_review(block, claims, atoms, review)


def test_same_block_other_sentence_does_not_ground_an_atom() -> None:
    block, claims, atoms, review = fixture()
    review["atom_verdicts"][0]["evidence_span_ids"] = ["a:s2"]
    with pytest.raises(SourceContractError, match="source anchor"):
        validate_block_review(block, claims, atoms, review)


@pytest.mark.parametrize("record", ["matches", "atom_verdicts"])
def test_block_records_cannot_be_dropped_or_duplicated(record: str) -> None:
    block, claims, atoms, review = fixture()
    review[record].append(copy.deepcopy(review[record][0]))
    with pytest.raises(SourceContractError):
        validate_block_review(block, claims, atoms, review)


def test_correct_metadata_absent_from_reference_remains_supported() -> None:
    block, claims, atoms, review = fixture()
    validate_block_review(block, claims, atoms, review)
    assert review["atom_verdicts"][1]["verdict"] == "SUPPORTED"


def test_relation_defect_cannot_be_invented_in_a_block_only_review() -> None:
    block, claims, atoms, review = fixture()
    review["reference_defects"] = [{"kind": "relation", "record_id": "0",
                                    "evidence_span_ids": ["a:s1"],
                                    "rationale": "This supposed relation is absent from the supplied records."}]
    with pytest.raises(SourceContractError, match="outside this block"):
        validate_block_review(block, claims, atoms, review)


def test_exhausted_evaluator_preserves_all_source_items_as_unknown() -> None:
    block, claims, atoms, _ = fixture()
    review = unassessed_block_review(claims, atoms, "schema mismatch")
    validate_block_review(block, claims, atoms, review)
    assert len(review["matches"]) == len(claims)
    assert {record["atom_id"] for record in review["atom_verdicts"]} == {"a:a1", "a:a2"}
    assert {record["verdict"] for record in review["atom_verdicts"]} == {"UNCERTAIN"}


@pytest.mark.parametrize("failed", [False, True])
def test_complete_window_and_partial_failure_preserve_denominators(tmp_path: Path, failed: bool) -> None:
    block, claims, atoms, review = fixture()
    role = {"block_id": "a", "role": "Result_Performance", "confidence": 0.9,
            "rationale": "The source reports the measured cost."}
    reference = {"claims": claims, "roles": [role], "relations": []}
    candidate = {"block_atoms": [{"block_id": "a", "atoms": atoms}], "relations": [],
                 "intents": [{"atom_id": "a:a1", "primary": "Objective_Finding"},
                             {"atom_id": "a:a2", "primary": "Formal"}], "roles": [role]}

    class StubBlockReviewer:
        def assess(self, *args: object) -> dict:
            return {"input_digest": "stub", "status": "EVALUATION_CONTRACT_FAILURE" if failed else "ASSESSED",
                    "review": unassessed_block_review(claims, atoms, "no valid judgment") if failed else review,
                    "failed_attempts": ["no valid judgment"] if failed else []}

    class NoEdgeReviewer:
        def assess(self, *args: object) -> dict:
            raise AssertionError("There are no candidate edges to judge")

    reviewer = LocalSourceReviewer.__new__(LocalSourceReviewer)
    reviewer.output, reviewer.blocks, reviewer.edges = tmp_path, StubBlockReviewer(), NoEdgeReviewer()
    report = reviewer.assess({"document_context": "{}", "source_blocks": json.dumps([block])},
                             reference, candidate)
    summary = aggregate_local_reports([report])
    assert summary["reference_claims"] == 1
    assert summary["predicted_atoms"] == 2
    assert report["unsupported_claims"] == 0
    assert summary["unassessed_atoms"] == (2 if failed else 0)
    assert report["covered_claims"] == (0 if failed else 1)
    if failed:
        assert not summary["semantic_gate_passed_against_model_reference"]
    else:
        assert report["score"] == 1.0


def test_partial_failure_does_not_hide_a_source_reference_defect() -> None:
    report = {
        "contract_failure": True, "evaluation_contract_failure": True, "candidate_contract_failure": False,
        "score": 0.2, "reference_claims": 1, "predicted_atoms": 2, "covered_claims": 0,
        "qualified_claims": 0, "unsupported_claims": 0, "unassessed_atoms": 1,
        "unassessed_relations": 0, "intent_pairs": [("Objective_Finding", "__MISSING__")],
        "role_pairs": [("Result_Performance", "Result_Performance")], "relation_pairs": [],
        "reference_defects": ["Source number differs from the provisional reference."],
    }
    summary = aggregate_local_reports([report])
    assert summary["reference_defects"] == report["reference_defects"]
    assert not summary["semantic_gate_passed_against_model_reference"]
