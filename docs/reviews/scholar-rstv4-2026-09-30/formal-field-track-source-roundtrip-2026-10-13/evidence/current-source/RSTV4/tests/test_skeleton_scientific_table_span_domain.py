import copy

import pytest
from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_scientific_table_reference_v2 import (
    table_source_cells,
    validate_scientific_table_output,
)


def source_and_output():
    text = "<table><tr><td>5 MW</td><td>10 MW</td></tr></table>"
    block = {"block_id": "paper:b1", "text": text, "source_spans": [
        {"span_id": "paper:b1:s1", "start": 0, "end": len(text)}]}
    claims = [{"reference_id": f"r{index}", "block_id": "paper:b1", "statement": f"Capacity {value}",
               "quote": "", "source_span_ids": ["paper:b1:s1"], "qualifications": [], "intent": "Method_Detail"}
              for index, value in enumerate(["5 MW", "10 MW"], 1)]
    output = {"claims": claims, "role": {"block_id": "paper:b1", "role": "Core_Methodology",
              "confidence": 1, "rationale": "Methods parameter table"},
              "cell_coverage": [{"cell_id": f"row1:cell{index}", "disposition": "SCIENTIFIC_DATA",
                                 "reference_ids": [f"r{index}"], "rationale": "Exact located capacity"}
                                for index in [1, 2]], "contains_scientific_data": True, "unresolved_fields": []}
    return block, output


def test_different_assertions_can_share_one_raw_span_without_collapsing():
    block, output = source_and_output()
    before = copy.deepcopy(output)
    checked = validate_scientific_table_output(block, table_source_cells(block)[0], output)
    assert len(checked["reference"]["claims"]) == 2
    assert [claim["statement"] for claim in checked["reference"]["claims"]] == ["Capacity 5 MW", "Capacity 10 MW"]
    assert output == before


@pytest.mark.parametrize("span_ids", [["paper:b1:s1", "paper:b1:s1"], ["row1:cell1"], [], ["foreign:s1"]])
def test_actual_bad_claim_and_span_ids_are_reported_without_autocorrection(span_ids):
    block, output = source_and_output()
    output["claims"][1]["source_span_ids"] = span_ids
    before = copy.deepcopy(output)
    with pytest.raises(SourceContractError, match="source span domain violations") as error:
        validate_scientific_table_output(block, table_source_cells(block)[0], output)
    assert "r2" in str(error.value)
    assert "paper:b1:s1" in str(error.value)
    assert output == before


def test_missing_scientific_cells_are_reported_together_with_raw_output_retained():
    block, output = source_and_output()
    for cell in output["cell_coverage"]:
        cell["reference_ids"] = []
    before = copy.deepcopy(output)
    with pytest.raises(SourceContractError, match="cells lack extracted claim IDs") as error:
        validate_scientific_table_output(block, table_source_cells(block)[0], output)
    assert "row1:cell1" in str(error.value) and "row1:cell2" in str(error.value)
    assert output == before
