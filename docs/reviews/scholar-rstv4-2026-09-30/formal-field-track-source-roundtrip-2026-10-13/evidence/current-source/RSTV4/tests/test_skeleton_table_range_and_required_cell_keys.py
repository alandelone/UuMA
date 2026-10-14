import copy

import pytest
from pydantic import ValidationError
from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_scientific_table_reference_v3 import (
    complete_cell_schema,
    resolved_table_range_claims,
    validate_scientific_table_output,
)


def source_and_output():
    block = {"block_id": "paper:b1", "text": "5 MW; separator; 10 MW", "source_spans": [
        {"span_id": "s1", "start": 0, "end": 5}, {"span_id": "s2", "start": 5, "end": 16},
        {"span_id": "s3", "start": 16, "end": 21}]}
    cells = [{"cell_id": "row1:cell1", "raw_value": "5 MW", "source_span_ids": ["s1"]},
             {"cell_id": "row3:cell2", "raw_value": "10 MW", "source_span_ids": ["s3"]}]
    claim = {"reference_id": "r1", "block_id": "paper:b1", "statement": "Capacities 5 MW and 10 MW",
             "qualifications": ["Two stated capacities; no technology association invented"],
             "intent": "Method_Detail", "start_span_id": "s1", "end_span_id": "s3"}
    output = {"claims": [claim], "role": {"block_id": "paper:b1", "role": "Core_Methodology",
              "confidence": 1, "rationale": "Parameters"}, "cell_coverage": {
                  cell["cell_id"]: {"disposition": "SCIENTIFIC_DATA", "reference_ids": ["r1"],
                                     "rationale": "Stated capacity retained"} for cell in cells},
              "contains_scientific_data": True, "unresolved_fields": []}
    return block, cells, output


def test_actual_range_expands_full_source_without_changing_science():
    block, _, output = source_and_output()
    before = copy.deepcopy(output)
    resolved = resolved_table_range_claims(block, output["claims"])
    assert resolved[0]["source_span_ids"] == ["s1", "s2", "s3"]
    assert resolved[0]["statement"] == output["claims"][0]["statement"]
    assert resolved[0]["qualifications"] == output["claims"][0]["qualifications"]
    assert output == before


@pytest.mark.parametrize("start,end", [("s3", "s1"), ("foreign", "s3"), ("s1", "absent")])
def test_foreign_or_reversed_range_remains_invalid(start, end):
    block, _, output = source_and_output()
    output["claims"][0].update(start_span_id=start, end_span_id=end)
    with pytest.raises(SourceContractError, match="actual raw span boundaries"):
        resolved_table_range_claims(block, output["claims"])


def test_dynamic_schema_requires_every_actual_cell_and_rejects_extra_keys():
    _, cells, output = source_and_output()
    schema = complete_cell_schema(cells)
    assert set(schema.model_json_schema()["required"]) == {"row1:cell1", "row3:cell2"}
    assert schema.model_validate(output["cell_coverage"]).model_dump() == output["cell_coverage"]
    missing = copy.deepcopy(output["cell_coverage"])
    missing.pop("row3:cell2")
    with pytest.raises(ValidationError):
        schema.model_validate(missing)
    extra = {**output["cell_coverage"], "invented": output["cell_coverage"]["row1:cell1"]}
    with pytest.raises(ValidationError):
        schema.model_validate(extra)


def test_canonical_science_and_all_cell_decisions_retain_original_model_fields():
    block, cells, output = source_and_output()
    before = copy.deepcopy(output)
    checked = validate_scientific_table_output(block, cells, output)
    assert checked["scientific_coverage_eligible"] is True
    assert {cell["cell_id"] for cell in checked["cell_coverage"]} == set(output["cell_coverage"])
    assert checked["reference"]["claims"][0]["source_span_ids"] == ["s1", "s2", "s3"]
    assert output == before
