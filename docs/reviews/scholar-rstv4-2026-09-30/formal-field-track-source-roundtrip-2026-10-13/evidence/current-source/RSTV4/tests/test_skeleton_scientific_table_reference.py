import copy

import pytest
from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_scientific_table_reference import (
    table_source_cells,
    validate_scientific_table_output,
)


def source():
    text = "<table><tr><td>Capacity</td><td>5 MW</td></tr><tr></table>"
    return {"block_id": "paper:b1", "text": text, "source_spans": [
        {"span_id": "paper:b1:s1", "start": 0, "end": len(text), "text": text}]}


def output():
    return {"claims": [{"reference_id": "r1", "block_id": "paper:b1",
                        "statement": "Capacity is 5 MW", "quote": "", "source_span_ids": ["paper:b1:s1"],
                        "qualifications": ["The source does not specify a technology."], "intent": "Method_Detail"}],
            "role": {"block_id": "paper:b1", "role": "Core_Methodology", "confidence": 1,
                     "rationale": "Methods parameter table"},
            "cell_coverage": [
                {"cell_id": "row1:cell1", "disposition": "HEADER_OR_STRUCTURE", "reference_ids": [],
                 "rationale": "Capacity is a literal parameter label."},
                {"cell_id": "row1:cell2", "disposition": "SCIENTIFIC_DATA", "reference_ids": ["r1"],
                 "rationale": "The stated capacity and unit are preserved in r1."}],
            "contains_scientific_data": True, "unresolved_fields": []}


def test_raw_cells_and_row_offsets_remain_exact_with_empty_structure_recorded():
    block = source()
    before = copy.deepcopy(block)
    cells, structure = table_source_cells(block)
    assert [cell["raw_value"] for cell in cells] == ["Capacity", "5 MW"]
    assert block["text"][cells[0]["row_char_start"]:cells[0]["row_char_end"]] == "<tr><td>Capacity</td><td>5 MW</td></tr>"
    assert structure[0]["raw_text"] == "<tr>"
    assert block == before


def test_scientific_data_have_located_assertion_without_invented_scope():
    block, raw = source(), output()
    before = copy.deepcopy((block, raw))
    validated = validate_scientific_table_output(block, table_source_cells(block)[0], raw)
    assert validated["scientific_coverage_eligible"] is True
    assert validated["reference"]["claims"][0]["qualifications"] == raw["claims"][0]["qualifications"]
    assert validated["reference"]["claims"][0]["statement"] == "Capacity is 5 MW"
    assert (block, raw) == before


@pytest.mark.parametrize("mutation, message", [
    (lambda raw: raw["cell_coverage"].pop(), "every actual nonempty cell"),
    (lambda raw: raw["cell_coverage"].append(copy.deepcopy(raw["cell_coverage"][0])), "every actual nonempty cell"),
    (lambda raw: raw["cell_coverage"][1].update(reference_ids=[]), "needs actual extracted claim"),
    (lambda raw: raw["cell_coverage"][1].update(reference_ids=["r99"]), "absent or duplicated"),
    (lambda raw: raw["cell_coverage"][0].update(reference_ids=["r1"]), "cannot invent"),
])
def test_missing_duplicate_or_unlocated_scientific_cell_fails(mutation, message):
    raw = output()
    mutation(raw)
    with pytest.raises(SourceContractError, match=message):
        validate_scientific_table_output(source(), table_source_cells(source())[0], raw)


def test_actual_unresolved_geometry_stays_ineligible_without_guessing():
    raw = output()
    raw["cell_coverage"][1].update(disposition="UNRESOLVED", reference_ids=[],
                                  rationale="The parsed geometry cannot establish which technology owns 5 MW.")
    raw["claims"] = []
    raw["unresolved_fields"] = ["Technology association for the literal capacity 5 MW"]
    checked = validate_scientific_table_output(source(), table_source_cells(source())[0], raw)
    assert checked["scientific_coverage_eligible"] is False
    assert checked["reference"]["claims"] == []
    assert checked["unresolved_fields"] == raw["unresolved_fields"]


def test_scientific_data_cannot_be_relabelled_as_all_structure():
    raw = output()
    raw["cell_coverage"][1].update(disposition="HEADER_OR_STRUCTURE", reference_ids=[])
    with pytest.raises(SourceContractError, match="concealed"):
        validate_scientific_table_output(source(), table_source_cells(source())[0], raw)
