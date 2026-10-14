from __future__ import annotations

import copy

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_boundary_reference import validate_boundary_ledger
from rstv4.skeleton_boundary_reference_v2 import (
    validate_boundary_ledger as validate_directed_boundary,
)
from rstv4.skeleton_contract import SourceContractError


def source_pair():
    first = {"source_spans": [{"span_id": "p:b1:s1"}]}
    second = {"source_spans": [{"span_id": "p:b4:s1"}]}
    ledger = [{"local_span_ids": ["p:b1:s1"], "context_span_ids": ["p:b4:s1"],
               "complete_assertion_span_ids": ["p:b1:s1", "p:b4:s1"],
               "disposition": "FRAGMENT_CONTINUES",
               "rationale": "The sentence resumes after the intervening table."}]
    return first, [first, second], ledger


def test_cross_block_boundary_retains_both_actual_source_positions():
    block, window, ledger = source_pair()
    validate_boundary_ledger(block, window, ledger)


@pytest.mark.parametrize("field", ["local_span_ids", "context_span_ids",
                                  "complete_assertion_span_ids"])
def test_boundary_rejects_source_positions_outside_supplied_context(field):
    block, window, ledger = source_pair()
    changed = copy.deepcopy(ledger)
    changed[0][field] = ["different-paper:b4:s1"]
    with pytest.raises(SourceContractError):
        validate_boundary_ledger(block, window, changed)


def test_continuation_cannot_be_asserted_without_other_block_evidence():
    block, window, ledger = source_pair()
    ledger[0]["context_span_ids"] = ["p:b1:s1"]
    with pytest.raises(SourceContractError):
        validate_boundary_ledger(block, window, ledger)


def test_unresolved_fragment_remains_explicit_without_invented_completion():
    block, window, ledger = source_pair()
    ledger[0].update(disposition="UNRESOLVED_FRAGMENT", context_span_ids=[],
                     complete_assertion_span_ids=[], rationale="No continuation in this source window.")
    validate_boundary_ledger(block, window, ledger)


def test_directed_boundary_retains_both_halves_of_complete_assertion():
    block, window, ledger = source_pair()
    validate_directed_boundary(block, window, ledger)
    ledger[0]["complete_assertion_span_ids"] = ["p:b4:s1"]
    with pytest.raises(SourceContractError, match="BOTH"):
        validate_directed_boundary(block, window, ledger)


def test_unresolved_boundary_cannot_claim_a_complete_assertion():
    block, window, ledger = source_pair()
    ledger[0].update(disposition="UNRESOLVED_FRAGMENT", context_span_ids=[])
    with pytest.raises(SourceContractError, match="no complete assertion"):
        validate_directed_boundary(block, window, ledger)
