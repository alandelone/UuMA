import copy

import pytest
from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_scientific_table_reference_v6 import (
    resolved_table_cell_claims,
    validate_scientific_table_output,
)


def source_and_output():
    block = {"block_id": "paper:b1", "text": "5 MW", "source_spans": [
        {"span_id": "s1", "start": 0, "end": 4}]}
    cells = [{"cell_id": "row1:cell1", "raw_value": "5 MW", "source_span_ids": ["s1"]}]
    pdf = "Parameter    Unit    Technology A\nCapacity     MW      5\n"
    quote = "Capacity     MW      5"
    claim = {"reference_id": "r1", "block_id": "paper:b1", "statement": "Technology A capacity is 5 MW",
             "qualifications": ["Original PDF column Technology A"], "intent": "Method_Detail",
             "source_cell_ids": ["row1:cell1"], "pdf_evidence_quotes": [quote]}
    output = {"claims": [claim], "role": {"block_id": "paper:b1", "role": "Core_Methodology",
              "confidence": 1, "rationale": "Parameter"},
              "cell_coverage": {"row1:cell1": {"disposition": "SCIENTIFIC_DATA",
                                              "rationale": "Actual stated capacity"}},
              "contains_scientific_data": True, "unresolved_fields": []}
    return block, cells, output, {"layout_text": pdf}


def test_actual_pdf_evidence_geometry_and_parsed_source_are_retained_separately():
    block, cells, output, context = source_and_output()
    before = copy.deepcopy(output)
    checked = validate_scientific_table_output(block, cells, output, context)
    assert output == before
    claim = checked["reference"]["claims"][0]
    assert claim["statement"] == output["claims"][0]["statement"]
    assert claim["qualifications"] == output["claims"][0]["qualifications"]
    assert claim["quote"] == block["text"]
    location = checked["source_cell_locator_resolutions"][0]["pdf_evidence_locations"][0]
    assert context["layout_text"][location["start"]:location["end"]] == output["claims"][0]["pdf_evidence_quotes"][0]
    assert location["original_pdf_layout_digest"] == digest(context["layout_text"])
    assert location["model_quote_changed"] is False


@pytest.mark.parametrize("quote", ["Capacity MW 5", "Not in original PDF", ""])
def test_normalized_missing_or_empty_pdf_evidence_is_rejected(quote):
    block, cells, output, context = source_and_output()
    output["claims"][0]["pdf_evidence_quotes"] = [quote]
    with pytest.raises(SourceContractError, match="uniquely and verbatim"):
        resolved_table_cell_claims(block, cells, output["claims"], context["layout_text"])


def test_ambiguous_pdf_quote_is_not_located_by_arbitrary_first_occurrence():
    block, cells, output, context = source_and_output()
    context["layout_text"] += context["layout_text"]
    with pytest.raises(SourceContractError, match="uniquely and verbatim"):
        validate_scientific_table_output(block, cells, output, context)
