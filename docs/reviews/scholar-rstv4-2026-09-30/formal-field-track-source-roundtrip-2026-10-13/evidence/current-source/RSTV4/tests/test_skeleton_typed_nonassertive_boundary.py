import copy

import pytest
from rstv4.skeleton_boundary_reference_v5 import validate_boundary_ledger
from rstv4.skeleton_contract import SourceContractError


def source():
    text = "The stack is replaced after 5 years (ESMAP &"
    block = {"block_id": "paper:b1", "text": text, "source_spans": [
        {"span_id": "paper:b1:s1", "start": 0, "end": len(text)}]}
    context = {"block_id": "paper:b2", "text": "World Bank, 2020).", "source_spans": [
        {"span_id": "paper:b2:s1", "start": 0, "end": 18}]}
    reference = {"claims": [{"source_span_ids": ["paper:b1:s1"],
                             "statement": "The stack is replaced after 5 years"}]}
    fragment = "(ESMAP &"
    boundary = {"local_span_ids": ["paper:b1:s1"], "context_span_ids": ["paper:b2:s1"],
                "complete_assertion_span_ids": ["paper:b1:s1"],
                "disposition": "COMPLETE_ASSERTION_WITH_NONASSERTIVE_FRAGMENT",
                "rationale": "The local scientific replacement interval is complete; only its citation is cut.",
                "nonassertive_fragment": {"span_id": "paper:b1:s1",
                                         "start_in_span": text.index(fragment), "end_in_span": len(text),
                                         "quote": fragment, "kind": "BIBLIOGRAPHIC_CITATION"}}
    return block, [block, context], reference, boundary


def test_typed_citation_keeps_exact_fragment_and_local_science_unchanged():
    block, window, reference, boundary = source()
    before = copy.deepcopy((block, window, reference, boundary))
    validate_boundary_ledger(block, window, [boundary], reference)
    assert (block, window, reference, boundary) == before


@pytest.mark.parametrize("mutation, message", [
    (lambda item: item.update(nonassertive_fragment=None), "exact substring"),
    (lambda item: item["nonassertive_fragment"].update(quote="Invented author"), "immutable raw source"),
    (lambda item: item["nonassertive_fragment"].update(end_in_span=999), "immutable raw source"),
    (lambda item: item.update(complete_assertion_span_ids=["paper:b2:s1"]), "local scientific spans"),
    (lambda item: item.update(context_span_ids=["paper:b1:s1"]), "OTHER actual blocks"),
])
def test_typed_fragment_requires_raw_offsets_scope_and_other_context(mutation, message):
    block, window, reference, boundary = source()
    mutation(boundary)
    with pytest.raises(SourceContractError, match=message):
        validate_boundary_ledger(block, window, [boundary], reference)


def test_typed_complete_assertion_cannot_be_without_actual_scientific_claim():
    block, window, _, boundary = source()
    with pytest.raises(SourceContractError, match="located scientific claim"):
        validate_boundary_ledger(block, window, [boundary], {"claims": []})


def test_genuine_scientific_continuation_still_requires_both_raw_fragments():
    block, window, reference, boundary = source()
    boundary.pop("nonassertive_fragment")
    boundary["disposition"] = "FRAGMENT_CONTINUES"
    with pytest.raises(SourceContractError, match="BOTH local and context"):
        validate_boundary_ledger(block, window, [boundary], reference)
    boundary["complete_assertion_span_ids"] = ["paper:b1:s1", "paper:b2:s1"]
    validate_boundary_ledger(block, window, [boundary], reference)
