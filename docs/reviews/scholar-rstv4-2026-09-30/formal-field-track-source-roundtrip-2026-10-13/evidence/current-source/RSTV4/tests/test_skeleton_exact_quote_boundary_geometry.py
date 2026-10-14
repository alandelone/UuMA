import copy

import pytest
from rstv4.skeleton_boundary_reference_v6 import (
    resolve_nonassertive_fragment,
    resolved_boundary_fragment_locations,
    validate_boundary_ledger,
)
from rstv4.skeleton_contract import SourceContractError


def source():
    text = "A stack lasts 5 years (ESMAP &"
    block = {"block_id": "paper:b1", "text": text, "source_spans": [
        {"span_id": "paper:b1:s1", "start": 0, "end": len(text)}]}
    fragment = {"span_id": "paper:b1:s1", "quote": "(ESMAP &", "kind": "BIBLIOGRAPHIC_CITATION"}
    ledger = [{"local_span_ids": ["paper:b1:s1"], "context_span_ids": [],
               "complete_assertion_span_ids": ["paper:b1:s1"],
               "disposition": "COMPLETE_ASSERTION_WITH_NONASSERTIVE_FRAGMENT",
               "nonassertive_fragment": fragment,
               "rationale": "Complete replacement interval, with a separately cut citation"}]
    reference = {"claims": [{"source_span_ids": ["paper:b1:s1"], "statement": "A stack lasts 5 years"}]}
    return block, fragment, ledger, reference


def test_unique_exact_quote_resolves_geometry_without_changing_model_science():
    block, fragment, ledger, reference = source()
    before = copy.deepcopy((block, fragment, ledger, reference))
    validate_boundary_ledger(block, [block], ledger, reference)
    located = resolved_boundary_fragment_locations(block, ledger)[0]
    assert block["text"][located["source_char_start"]:located["source_char_end"]] == fragment["quote"]
    assert located["start_in_span"] == block["text"].index("(ESMAP &")
    assert located["model_output_changed"] is False
    assert (block, fragment, ledger, reference) == before


@pytest.mark.parametrize("quote", ["Missing author", "", "(ESMAP&"])
def test_missing_or_normalized_quote_is_rejected(quote):
    block, fragment, _, _ = source()
    fragment["quote"] = quote
    with pytest.raises(SourceContractError, match="ONE exact occurrence"):
        resolve_nonassertive_fragment(block, fragment)


def test_ambiguous_quote_is_not_resolved_to_arbitrary_first_occurrence():
    block, fragment, _, _ = source()
    block["text"] += " (ESMAP &"
    block["source_spans"][0]["end"] = len(block["text"])
    with pytest.raises(SourceContractError, match="ONE exact occurrence"):
        resolve_nonassertive_fragment(block, fragment)


def test_actual_scientific_continuation_keeps_both_span_gate():
    block, _, ledger, reference = source()
    other = {"block_id": "paper:b2", "source_spans": [{"span_id": "paper:b2:s1"}]}
    ledger[0].update(disposition="FRAGMENT_CONTINUES", nonassertive_fragment=None,
                     context_span_ids=["paper:b2:s1"])
    with pytest.raises(SourceContractError, match="BOTH local and context"):
        validate_boundary_ledger(block, [block, other], ledger, reference)
