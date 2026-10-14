import copy
import json

import pytest
from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_scientific_table_reference_v4 import validate_scientific_table_output


def source_and_output():
    block = {"block_id": "paper:b1", "text": "5; separator; MW", "source_spans": [
        {"span_id": "s1", "start": 0, "end": 2},
        {"span_id": "s2", "start": 2, "end": 14},
        {"span_id": "s3", "start": 14, "end": 16}]}
    cells = [{"cell_id": "row1:cell1", "raw_value": "5", "source_span_ids": ["s1"]},
             {"cell_id": "row3:cell2", "raw_value": "MW", "source_span_ids": ["s3"]}]
    output = {"claims": [{"reference_id": "r1", "block_id": "paper:b1", "statement": "Capacity 5 MW",
                         "qualifications": ["Stated unit MW"], "intent": "Method_Detail",
                         "start_span_id": "s1", "end_span_id": "s3"}],
              "role": {"block_id": "paper:b1", "role": "Core_Methodology", "confidence": 1,
                       "rationale": "Actual parameter"},
              "cell_coverage": {cell["cell_id"]: {"disposition": "SCIENTIFIC_DATA",
                  "reference_ids": ["r1"], "rationale": "Actual parameter value or stated qualifier"} for cell in cells},
              "contains_scientific_data": True, "unresolved_fields": []}
    return block, cells, output


def test_row_feedback_names_actual_cell_claim_and_source_without_repairing_output():
    block, cells, output = source_and_output()
    output["claims"][0]["end_span_id"] = "s1"
    before = copy.deepcopy(output)
    with pytest.raises(SourceContractError) as error:
        validate_scientific_table_output(block, cells, output)
    assert "row3:cell2" in str(error.value)
    actual = json.loads(str(error.value).split(": ", 1)[1].split(". Retain ", 1)[0])
    assert actual == [{"cell_id": "row3:cell2", "claim_id": "r1",
                       "actual_cell_source_spans": ["s3"], "declared_claim_range": ["s1", "s1"]}]
    assert output == before


def test_unit_scientific_cell_requires_actual_claim_link():
    block, cells, output = source_and_output()
    output["cell_coverage"]["row3:cell2"]["reference_ids"] = []
    with pytest.raises(SourceContractError, match="lack extracted claim IDs"):
        validate_scientific_table_output(block, cells, output)


def test_actual_qualifier_links_preserve_science_and_unresolved_scope_stays_ineligible():
    block, cells, output = source_and_output()
    before = copy.deepcopy(output)
    accepted = validate_scientific_table_output(block, cells, output)
    assert accepted["scientific_coverage_eligible"] is True
    assert accepted["reference"]["claims"][0]["statement"] == "Capacity 5 MW"
    assert output == before
    output["cell_coverage"]["row3:cell2"].update(disposition="UNRESOLVED", reference_ids=[])
    output["unresolved_fields"] = ["Raw unit association needs original layout evidence"]
    unresolved = validate_scientific_table_output(block, cells, output)
    assert unresolved["scientific_coverage_eligible"] is False
    assert unresolved["unresolved_fields"] == output["unresolved_fields"]
