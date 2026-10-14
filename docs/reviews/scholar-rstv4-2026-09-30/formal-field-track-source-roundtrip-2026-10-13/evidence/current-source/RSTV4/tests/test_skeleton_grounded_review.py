from __future__ import annotations

import copy

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_contract import SourceContractError, with_source_spans
from rstv4.skeleton_grounded_review import aggregate_grounded, score_grounded


def fixture() -> tuple[list[dict], dict, dict, dict]:
    blocks = with_source_spans([
        {"block_id": "a", "text": "The authors are Alice and Bob."},
        {"block_id": "b", "text": "The measured cost was 0.2 USD/kWh under scenario A."},
    ])
    reference = {
        "claims": [{"reference_id": "r1", "block_id": "b", "intent": "Objective_Finding"}],
        "relations": [], "roles": [{"block_id": "a", "role": "Front_Matter"},
                                     {"block_id": "b", "role": "Result_Performance"}],
    }
    candidate = {
        "block_atoms": [{"block_id": "a", "atoms": [{"atom_id": "a:a1"}]},
                        {"block_id": "b", "atoms": [{"atom_id": "b:a1"}]}],
        "relations": [],
        "intents": [{"atom_id": "a:a1", "primary": "Formal"},
                    {"atom_id": "b:a1", "primary": "Objective_Finding"}],
        "roles": copy.deepcopy(reference["roles"]),
    }
    review = {
        "matches": [{"reference_id": "r1", "atom_id": "b:a1", "meaning_preserved": True,
                     "qualifications_preserved": True, "rationale": "Same quantity and scenario."}],
        "atom_verdicts": [
            {"atom_id": "a:a1", "verdict": "SUPPORTED", "evidence_span_ids": ["a:s1"],
             "rationale": "The source explicitly names Alice and Bob as the authors."},
            {"atom_id": "b:a1", "verdict": "SUPPORTED", "evidence_span_ids": ["b:s1"],
             "rationale": "The source gives 0.2 USD/kWh and explicitly limits it to scenario A."},
        ],
        "edge_verdicts": [], "reference_defects": [], "feedback": "All items checked against source.",
    }
    return blocks, reference, candidate, review


def test_supported_metadata_absent_from_reference_is_not_hallucination() -> None:
    blocks, reference, candidate, review = fixture()
    report = score_grounded(blocks, reference, candidate, review)
    assert report["predicted_atoms"] == 2
    assert report["reference_claims"] == 1
    assert report["unsupported_claims"] == 0
    assert report["unsupported_claim_rate"] == 0.0
    assert report["score"] == 1.0


def test_uncertainty_is_preserved_and_cannot_pass_quality_gate() -> None:
    blocks, reference, candidate, review = fixture()
    review["atom_verdicts"][1]["verdict"] = "UNCERTAIN"
    report = score_grounded(blocks, reference, candidate, review)
    summary = aggregate_grounded([report])
    assert report["layer1_coverage"] == 0.0
    assert summary["unsupported_claim_rate"] == 0.0
    assert summary["unsupported_claim_rate_upper_bound"] == 0.5
    assert summary["unassessed_atoms"] == 1
    assert not summary["semantic_gate_passed_against_model_reference"]


def test_contradictory_assertion_counts_as_unsupported() -> None:
    blocks, reference, candidate, review = fixture()
    review["atom_verdicts"][1].update(
        verdict="UNSUPPORTED", rationale="The candidate removes scenario A from the reported cost.",
    )
    report = score_grounded(blocks, reference, candidate, review)
    assert report["covered_claims"] == 0
    assert report["unsupported_claims"] == 1
    assert report["unsupported_claim_rate"] == 0.5


@pytest.mark.parametrize("change", ["omit", "duplicate", "unknown"])
def test_every_candidate_atom_requires_one_verdict(change: str) -> None:
    blocks, reference, candidate, review = fixture()
    if change == "omit":
        review["atom_verdicts"].pop()
    elif change == "duplicate":
        review["atom_verdicts"].append(copy.deepcopy(review["atom_verdicts"][0]))
    else:
        review["atom_verdicts"][1]["atom_id"] = "missing"
    with pytest.raises(SourceContractError, match="every candidate atom"):
        score_grounded(blocks, reference, candidate, review)


def test_verdict_evidence_cannot_move_to_another_block() -> None:
    blocks, reference, candidate, review = fixture()
    review["atom_verdicts"][0]["evidence_span_ids"] = ["b:s1"]
    with pytest.raises(SourceContractError, match="own source block"):
        score_grounded(blocks, reference, candidate, review)


def test_unknown_evidence_and_unknown_reference_defects_are_rejected() -> None:
    blocks, reference, candidate, review = fixture()
    review["atom_verdicts"][0]["evidence_span_ids"] = ["invented:s1"]
    with pytest.raises(SourceContractError, match="existing"):
        score_grounded(blocks, reference, candidate, review)
    review = fixture()[3]
    review["reference_defects"] = [{
        "kind": "claim", "record_id": "r99", "evidence_span_ids": ["b:s1"],
        "rationale": "The provisional claim does not reflect the source's scenario restriction.",
    }]
    with pytest.raises(SourceContractError, match="absent reference record"):
        score_grounded(blocks, reference, candidate, review)


def test_relation_alignment_is_derived_from_real_directed_endpoints() -> None:
    blocks, reference, candidate, review = fixture()
    reference["claims"].append({"reference_id": "r2", "block_id": "a", "intent": "Formal"})
    reference["relations"] = [{"source_reference_id": "r1", "target_reference_id": "r2",
                               "relation": "Support"}]
    review["matches"].append({"reference_id": "r2", "atom_id": "a:a1", "meaning_preserved": True,
                              "qualifications_preserved": True, "rationale": "Source-backed metadata."})
    candidate["relations"] = [{"source_id": "a:a1", "target_id": "b:a1", "relation": "Support"}]
    review["edge_verdicts"] = [{
        "relation_index": 0, "verdict": "UNSUPPORTED", "evidence_span_ids": ["a:s1", "b:s1"],
        "rationale": "The author list is not evidence establishing the measured cost.",
    }]
    report = score_grounded(blocks, reference, candidate, review)
    assert report["assessment"]["relation_matches"][0]["predicted_relation_index"] is None
    assert report["unsupported_relations"] == 1
    assert report["layer2_macro_f1"] == 0.0


def test_missing_edge_verdict_cannot_silently_pass() -> None:
    blocks, reference, candidate, review = fixture()
    candidate["relations"] = [{"source_id": "a:a1", "target_id": "b:a1", "relation": "Support"}]
    with pytest.raises(SourceContractError, match="every candidate edge"):
        score_grounded(blocks, reference, candidate, review)
