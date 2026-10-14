import copy

import pytest
from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_original_pdf_table_science_v1 import (
    source_values,
    target_line_domain,
    validate_pdf_science,
)


def actual_pdf_case():
    context = {"layout_text": "Capacity     MW    Technology A\n5            MW    Technology A\nCondition: only at 50 C\n\nNeighbor actual source\n"}
    ids = ["PDF_LAYOUT:L1", "PDF_LAYOUT:L2", "PDF_LAYOUT:L3", "PDF_LAYOUT:L4"]
    claim = {"reference_id": "r1", "block_id": "paper:b1", "statement": "Technology A capacity is 5 MW",
             "qualifications": ["only at 50 C"], "intent": "Method_Detail",
             "pdf_evidence_line_ids": ["PDF_LAYOUT:L1", "PDF_LAYOUT:L2", "PDF_LAYOUT:L3"]}
    output = {"claims": [claim], "contains_scientific_data": True, "unresolved_fields": [],
              "line_coverage": {key: {"disposition": "SCIENTIFIC_DATA", "rationale": "Actual statement context"}
                                for key in ids[:3]}}
    return context, ids, output


def test_pdf_first_has_full_original_pages_and_no_parsed_or_historical_model_inputs():
    context, ids, _ = actual_pdf_case()
    wire = source_values(context, ids, "paper:b1")
    assert "Neighbor actual source" in wire["original_pdf_lines"]
    assert "source_blocks" not in wire and "literal_table_cells" not in wire
    assert "parent_source_reference" not in wire
    assert set(wire) == {"original_pdf_lines", "original_pdf_source_lineage", "target_table_line_ids",
                         "target_block_id", "scientific_interpretation_contract"}


def test_pdf_science_keeps_all_unchanged_science_and_resolves_exact_original_locations():
    context, ids, output = actual_pdf_case()
    original = copy.deepcopy(output)
    reviewed = validate_pdf_science(output, context, ids, "paper:b1")
    assert output == original and reviewed["claims"] == output["claims"]
    assert reviewed["parsed_cell_association_complete"] is False
    assert reviewed["full_source_comparison_complete"] is False
    for location in reviewed["source_line_locator_resolutions"][0]["pdf_evidence_locations"]:
        assert context["layout_text"][location["start"]:location["end"]] == location["quote"]


@pytest.mark.parametrize("fault", ["missing_disposition", "missing_science", "foreign", "blank", "duplicate", "wrong_block"])
def test_original_pdf_coverage_and_evidence_failures_remain_fatal(fault):
    context, ids, output = actual_pdf_case()
    if fault == "missing_disposition":
        del output["line_coverage"]["PDF_LAYOUT:L3"]
    elif fault == "missing_science":
        output["claims"][0]["pdf_evidence_line_ids"].remove("PDF_LAYOUT:L3")
    elif fault == "wrong_block":
        output["claims"][0]["block_id"] = "paper:foreign"
    else:
        output["claims"][0]["pdf_evidence_line_ids"] = {
            "foreign": ["PDF_LAYOUT:L5"], "blank": ["PDF_LAYOUT:L4"],
            "duplicate": ["PDF_LAYOUT:L2", "PDF_LAYOUT:L2"]}[fault]
    with pytest.raises(SourceContractError):
        validate_pdf_science(output, context, ids, "paper:b1")


def test_original_pdf_target_cannot_omit_a_middle_continuation():
    context, _, _ = actual_pdf_case()
    with pytest.raises(SourceContractError):
        target_line_domain(context, ["PDF_LAYOUT:L1", "PDF_LAYOUT:L3"])
