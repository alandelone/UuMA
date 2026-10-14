import copy

import pytest
from pydantic import ValidationError
from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_scientific_table_reference_v5 import (
    complete_cell_schema,
    resolved_table_cell_claims,
    validate_scientific_table_output,
)


def source_and_output():
    block = {"block_id": "paper:b1", "text": "5; separator; MW", "source_spans": [
        {"span_id": "s1", "start": 0, "end": 2}, {"span_id": "s2", "start": 2, "end": 14},
        {"span_id": "s3", "start": 14, "end": 16}]}
    cells = [{"cell_id": "row1:cell1", "raw_value": "5", "source_span_ids": ["s1"]},
             {"cell_id": "row3:cell2", "raw_value": "MW", "source_span_ids": ["s3"]}]
    claim = {"reference_id": "r1", "block_id": "paper:b1", "statement": "Capacity is 5 MW",
             "qualifications": ["Stated capacity and unit"], "intent": "Method_Detail",
             "source_cell_ids": ["row1:cell1", "row3:cell2"]}
    output = {"claims": [claim], "role": {"block_id": "paper:b1", "role": "Core_Methodology",
              "confidence": 1, "rationale": "Actual method parameter"},
              "cell_coverage": {cell["cell_id"]: {"disposition": "SCIENTIFIC_DATA",
                   "rationale": "Actual value or unit belongs to declared scientific claim"} for cell in cells},
              "contains_scientific_data": True, "unresolved_fields": []}
    return block, cells, output


def test_one_actual_cell_declaration_derives_all_raw_spans_and_links_without_changing_science():
    block, cells, output = source_and_output()
    before = copy.deepcopy(output)
    reviewed = validate_scientific_table_output(block, cells, output)
    assert output == before
    claim = reviewed["reference"]["claims"][0]
    assert claim["statement"] == output["claims"][0]["statement"]
    assert claim["qualifications"] == output["claims"][0]["qualifications"]
    assert claim["intent"] == output["claims"][0]["intent"]
    assert claim["source_span_ids"] == ["s1", "s2", "s3"]
    assert claim["quote"] == block["text"]
    assert all(cell["reference_ids"] == ["r1"] for cell in reviewed["cell_coverage"])
    assert reviewed["source_cell_locator_resolutions"] == [{"reference_id": "r1",
        "declared_source_cell_ids": ["row1:cell1", "row3:cell2"],
        "resolved_source_span_ids": ["s1", "s2", "s3"], "source_char_start": 0,
        "source_char_end": 16, "source_block_digest": digest(block), "model_scientific_fields_changed": False}]


@pytest.mark.parametrize("cell_ids", [["foreign"], ["row1:cell1", "row1:cell1"], []])
def test_foreign_duplicate_or_empty_actual_cell_locator_is_rejected(cell_ids):
    block, cells, output = source_and_output()
    output["claims"][0]["source_cell_ids"] = cell_ids
    with pytest.raises((SourceContractError, ValidationError)):
        resolved_table_cell_claims(block, cells, output["claims"])


def test_scientific_cell_not_declared_by_any_claim_remains_fatal():
    block, cells, output = source_and_output()
    output["claims"][0]["source_cell_ids"] = ["row1:cell1"]
    with pytest.raises(SourceContractError, match="row3:cell2"):
        validate_scientific_table_output(block, cells, output)


def test_unresolved_scientific_cell_scope_remains_explicit_and_ineligible():
    block, cells, output = source_and_output()
    output["claims"][0].update(source_cell_ids=["row1:cell1"], statement="Capacity is 5; unit unresolved")
    output["cell_coverage"]["row3:cell2"]["disposition"] = "UNRESOLVED"
    output["unresolved_fields"] = ["Actual unit association unresolved"]
    reviewed = validate_scientific_table_output(block, cells, output)
    assert reviewed["scientific_coverage_eligible"] is False
    assert reviewed["unresolved_fields"] == output["unresolved_fields"]
    output["claims"][0]["source_cell_ids"].append("row3:cell2")
    with pytest.raises(SourceContractError, match="Unresolved scientific cell"):
        validate_scientific_table_output(block, cells, output)


def test_nonassertive_source_context_is_preserved_without_a_standalone_claim():
    block, cells, output = source_and_output()
    output["cell_coverage"]["row3:cell2"]["disposition"] = "HEADER_OR_STRUCTURE"
    reviewed = validate_scientific_table_output(block, cells, output)
    assert reviewed["cell_coverage"][1]["reference_ids"] == []
    assert reviewed["reference"]["claims"][0]["source_span_ids"] == ["s1", "s2", "s3"]
    assert len(reviewed["reference"]["claims"]) == 1


def test_required_cell_schema_rejects_a_second_generated_claim_link_field():
    _, cells, output = source_and_output()
    schema = complete_cell_schema(cells)
    assert schema.model_validate(output["cell_coverage"]).model_dump() == output["cell_coverage"]
    output["cell_coverage"]["row1:cell1"]["reference_ids"] = ["r1"]
    with pytest.raises(ValidationError):
        schema.model_validate(output["cell_coverage"])
