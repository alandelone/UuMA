from __future__ import annotations

import copy

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_contract import SourceContractError, with_source_spans
from rstv4.skeleton_source_reference import canonical_block_reference, validate_source_relations


def fixture() -> tuple[dict, list[dict], dict]:
    block = with_source_spans([{
        "block_id": "b", "block_type": "TEXT",
        "text": "The cost is 0.2 USD/kWh in scenario A. Emissions may decline by 5 percent.",
    }])[0]
    claims = [
        {"reference_id": "second", "block_id": "b", "statement": "Emissions may decline by 5 percent.",
         "quote": "", "source_span_ids": ["b:s2"], "qualifications": ["may", "5 percent"],
         "intent": "Implication"},
        {"reference_id": "first", "block_id": "b", "statement": "The cost is 0.2 USD/kWh in scenario A.",
         "quote": "", "source_span_ids": ["b:s1"], "qualifications": ["0.2 USD/kWh", "scenario A"],
         "intent": "Objective_Finding"},
    ]
    role = {"block_id": "b", "role": "Result_Performance", "confidence": 0.9,
            "rationale": "The source reports a cost and a conditional emissions implication."}
    return block, claims, role


def test_source_order_identity_preserves_all_claims_and_qualifications() -> None:
    block, claims, role = fixture()
    before = copy.deepcopy(claims)
    reference = canonical_block_reference(block, claims, role)
    assert claims == before
    assert [claim["reference_id"] for claim in reference["claims"]] == ["b:r1", "b:r2"]
    assert reference["claims"][0]["qualifications"] == ["0.2 USD/kWh", "scenario A"]
    assert reference["claims"][1]["qualifications"] == ["may", "5 percent"]
    assert reference["claims"][1]["quote"] == "Emissions may decline by 5 percent."


def test_plain_heading_can_have_zero_scientific_claims_and_still_has_role() -> None:
    block, _, role = fixture()
    block.update(block_type="HEADING", text="Methodology")
    block = with_source_spans([block])[0]
    role["role"] = "Core_Methodology"
    reference = canonical_block_reference(block, [], role)
    assert reference["claims"] == []
    assert reference["roles"][0]["block_id"] == "b"


def test_long_substantive_source_cannot_be_omitted_to_pass_validation() -> None:
    block, _, role = fixture()
    block["text"] *= 5
    block = with_source_spans([block])[0]
    with pytest.raises(SourceContractError, match="omitted substantive"):
        canonical_block_reference(block, [], role)


def test_reference_cannot_move_claim_to_other_source() -> None:
    block, claims, role = fixture()
    claims[0]["block_id"] = "other"
    with pytest.raises(SourceContractError, match="actual source block"):
        canonical_block_reference(block, claims, role)


@pytest.mark.parametrize("error", ["duplicate", "self", "missing", "unknown"])
def test_source_reference_graph_rejects_invalid_edges(error: str) -> None:
    block, claims, role = fixture()
    reference = canonical_block_reference(block, claims, role)
    edge = {"source_reference_id": "b:r1", "target_reference_id": "b:r2",
            "relation": "Contrast", "rationale": "Different reported quantities are explicitly compared."}
    reference["relations"] = [edge]
    if error == "duplicate":
        reference["relations"].append(copy.deepcopy(edge))
    elif error == "self":
        edge["target_reference_id"] = "b:r1"
    elif error == "missing":
        edge["target_reference_id"] = "missing"
    else:
        edge["relation"] = "UNKNOWN"
    with pytest.raises(SourceContractError):
        validate_source_relations(reference, [block])
