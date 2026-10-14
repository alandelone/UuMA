from __future__ import annotations

import copy

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_contract import SourceContractError, with_source_spans
from rstv4.skeleton_endpoint_review import (
    review_provenance_issues,
    validate_endpoint_verdict,
)


def fixture() -> tuple[list[dict], dict, dict, dict, dict]:
    blocks = with_source_spans([
        {"block_id": "a", "text": "The village is in Dangila. Its elevation is 1800 metres."},
        {"block_id": "b", "text": "The research gap motivated this study."},
    ])
    atoms = [
        {"atom_id": "a:a1", "source_span_ids": ["a:s1"]},
        {"atom_id": "a:a2", "source_span_ids": ["a:s2"]},
    ]
    edge = {"source_id": "a:a1", "target_id": "a:a2", "relation": "Elaboration"}
    candidate = {"block_atoms": [{"block_id": "a", "atoms": atoms}], "relations": [edge]}
    reference = {"claims": [{"reference_id": "r1", "block_id": "a"}]}
    review = {"matches": [{"reference_id": "r1", "atom_id": "a:a1",
                           "meaning_preserved": True}], "edge_verdicts": [{
        "relation_index": 0, "verdict": "SUPPORTED", "evidence_span_ids": ["b:s1"],
    }]}
    verdict = {
        **edge, "verdict": "SUPPORTED", "source_evidence_span_ids": ["a:s1"],
        "target_evidence_span_ids": ["a:s2"],
        "rationale": "The second proposition specifies geographical details of the village.",
    }
    return blocks, reference, candidate, review, verdict


def test_wrong_graph_edge_evidence_is_detected_without_mutating_legacy_report() -> None:
    blocks, reference, candidate, review, _ = fixture()
    before = copy.deepcopy(review)
    issues = review_provenance_issues(blocks, reference, candidate, review)
    assert [issue["endpoint"] for issue in issues] == ["source_id", "target_id"]
    assert all(issue["kind"] == "EDGE_EVIDENCE_MISALIGNED" for issue in issues)
    assert review == before


def test_same_block_wrong_sentence_is_detected() -> None:
    blocks, reference, candidate, review, _ = fixture()
    review["edge_verdicts"][0]["evidence_span_ids"] = ["a:s1"]
    issues = review_provenance_issues(blocks, reference, candidate, review)
    assert len(issues) == 1
    assert issues[0]["atom_id"] == "a:a2"


def test_heading_cannot_gain_source_coverage_from_another_blocks_atom() -> None:
    blocks, reference, candidate, review, _ = fixture()
    reference["claims"][0]["block_id"] = "b"
    review["edge_verdicts"][0]["evidence_span_ids"] = ["a:s1", "a:s2"]
    issues = review_provenance_issues(blocks, reference, candidate, review)
    assert [issue["kind"] for issue in issues] == ["CLAIM_MATCH_DIFFERENT_SOURCE_BLOCK"]


def test_exact_actual_endpoint_evidence_is_accepted() -> None:
    _, _, candidate, _, verdict = fixture()
    source, target = candidate["block_atoms"][0]["atoms"]
    assert validate_endpoint_verdict(candidate["relations"][0], source, target, verdict) == verdict


@pytest.mark.parametrize("field", ["source_id", "target_id", "relation"])
def test_echoed_edge_identity_cannot_be_substituted(field: str) -> None:
    _, _, candidate, _, verdict = fixture()
    verdict[field] = "Cause" if field == "relation" else "b:a1"
    source, target = candidate["block_atoms"][0]["atoms"]
    with pytest.raises(SourceContractError, match="echo"):
        validate_endpoint_verdict(candidate["relations"][0], source, target, verdict)


@pytest.mark.parametrize("ids", [["b:s1"], ["a:s1"], ["a:s2", "a:s2"]])
def test_target_evidence_must_belong_to_actual_target(ids: list[str]) -> None:
    _, _, candidate, _, verdict = fixture()
    verdict["target_evidence_span_ids"] = ids
    source, target = candidate["block_atoms"][0]["atoms"]
    with pytest.raises(SourceContractError, match="target evidence"):
        validate_endpoint_verdict(candidate["relations"][0], source, target, verdict)


def test_unknown_relation_cannot_count_as_established() -> None:
    _, _, candidate, _, verdict = fixture()
    candidate["relations"][0]["relation"] = verdict["relation"] = "UNKNOWN"
    source, target = candidate["block_atoms"][0]["atoms"]
    with pytest.raises(SourceContractError, match="UNKNOWN"):
        validate_endpoint_verdict(candidate["relations"][0], source, target, verdict)


def test_missing_or_out_of_range_edge_is_not_silently_skipped() -> None:
    blocks, reference, candidate, review, _ = fixture()
    review["edge_verdicts"][0]["relation_index"] = 9
    with pytest.raises(SourceContractError, match="out of range"):
        review_provenance_issues(blocks, reference, candidate, review)
