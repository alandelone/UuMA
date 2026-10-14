import copy

import pytest
from pydantic import ValidationError
from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_scientific_table_reference_v7 import (
    indexed_original_pdf_lines,
    resolved_table_cell_claims,
    validate_scientific_table_output,
)


def source_and_output():
    block = {"block_id": "paper:b1", "text": "5 MW", "source_spans": [
        {"span_id": "s1", "start": 0, "end": 4}]}
    cells = [{"cell_id": "row1:cell1", "raw_value": "5 MW", "source_span_ids": ["s1"]}]
    pdf = "Parameter    Unit    Technology A\n\nCapacity     MW      5\nCapacity     MW      5\n"
    claim = {"reference_id": "r1", "block_id": "paper:b1", "statement": "Technology A capacity is 5 MW",
             "qualifications": ["Actual Technology A column"], "intent": "Method_Detail",
             "source_cell_ids": ["row1:cell1"], "pdf_evidence_line_ids": ["PDF_LAYOUT:L1", "PDF_LAYOUT:L4"]}
    output = {"claims": [claim], "role": {"block_id": "paper:b1", "role": "Core_Methodology",
              "confidence": 1, "rationale": "Parameter"},
              "cell_coverage": {"row1:cell1": {"disposition": "SCIENTIFIC_DATA", "rationale": "Actual capacity"}},
              "contains_scientific_data": True, "unresolved_fields": []}
    return block, cells, output, {"layout_text": pdf}


def test_original_pdf_line_domain_retains_every_character_and_offset():
    _, _, _, context = source_and_output()
    lines = indexed_original_pdf_lines(context["layout_text"])
    assert "".join(line["text"] for line in lines) == context["layout_text"]
    assert len({line["line_id"] for line in lines}) == len(lines)
    for line in lines:
        assert context["layout_text"][line["start"]:line["end"]] == line["text"]


def test_declared_pdf_line_identity_uses_actual_repeated_line_location_and_preserves_science():
    block, cells, output, context = source_and_output()
    before = copy.deepcopy(output)
    reviewed = validate_scientific_table_output(block, cells, output, context)
    assert output == before
    claim = reviewed["reference"]["claims"][0]
    assert claim["statement"] == output["claims"][0]["statement"]
    assert claim["qualifications"] == output["claims"][0]["qualifications"]
    locations = reviewed["source_cell_locator_resolutions"][0]["pdf_evidence_locations"]
    assert [item["line_id"] for item in locations] == ["PDF_LAYOUT:L1", "PDF_LAYOUT:L4"]
    actual_fourth = indexed_original_pdf_lines(context["layout_text"])[3]
    assert locations[1]["start"] == actual_fourth["start"]
    assert locations[1]["quote"] == actual_fourth["text"]
    assert locations[1]["start"] > context["layout_text"].index(actual_fourth["text"])


@pytest.mark.parametrize("ids", [["foreign"], ["PDF_LAYOUT:L1", "PDF_LAYOUT:L1"], [], ["PDF_LAYOUT:L2"]])
def test_foreign_duplicate_empty_or_blank_pdf_evidence_remains_fatal(ids):
    block, cells, output, context = source_and_output()
    output["claims"][0]["pdf_evidence_line_ids"] = ids
    with pytest.raises((SourceContractError, ValidationError)):
        resolved_table_cell_claims(block, cells, output["claims"], context["layout_text"])
