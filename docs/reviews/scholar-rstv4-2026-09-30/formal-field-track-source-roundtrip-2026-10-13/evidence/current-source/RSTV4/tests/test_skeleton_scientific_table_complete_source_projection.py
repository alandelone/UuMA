import copy
import json

import pytest
from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_scientific_table_reference_v8 import (
    source_wire_values,
    validate_scientific_table_output,
)
from test_skeleton_scientific_table_pdf_line_locators import source_and_output


def test_compact_wire_preserves_complete_original_window_cells_pdf_unicode_and_blank_lines():
    block, cells, _, context = source_and_output()
    cells[0]["header_tag"] = False
    context["layout_text"] += "Condition    ≤50 °C    ≪20 min\n"
    context["indexed_layout_lines"] = [{"retained_only_in_freeze": True}]
    context["source_pdf_sha256"] = "unchanged-original-hash"
    neighbor = {"block_id": "paper:b2", "text": "Actual complete adjacent scientific condition."}
    inputs = {"document_context": "Original context", "source_blocks": json.dumps([neighbor, block])}
    parent = {"claims": [{"statement": "Historical incorrect interpretation is not authority"}]}
    originals = copy.deepcopy((inputs, block, cells, parent, context))
    wire = source_wire_values(inputs, block, cells, parent, context)
    assert (inputs, block, cells, parent, context) == originals
    assert wire["source_window"] == inputs["source_blocks"]
    assert json.loads(wire["source_block"])["source_window_index"] == 1
    lines = json.loads(wire["original_pdf_layout"])
    assert "".join(line["text"] for line in lines) == context["layout_text"]
    assert [line["line_id"] for line in lines] == [f"PDF_LAYOUT:L{i}" for i in range(1, len(lines) + 1)]
    assert json.loads(wire["literal_table_cells"])[0]["raw_value"] == "5 MW"
    assert json.loads(wire["original_pdf_source_lineage"]) == {"source_pdf_sha256": "unchanged-original-hash"}
    assert parent["claims"][0]["statement"] not in wire["parent_source_reference"]


@pytest.mark.parametrize("copies", [0, 2])
def test_projection_rejects_missing_or_duplicate_actual_target(copies):
    block, cells, _, context = source_and_output()
    inputs = {"document_context": "context", "source_blocks": json.dumps([block] * copies)}
    with pytest.raises(SourceContractError):
        source_wire_values(inputs, block, cells, {}, context)


def test_compact_wire_does_not_change_scientific_or_pdf_locator_validation():
    block, cells, output, context = source_and_output()
    reviewed = validate_scientific_table_output(block, cells, output, context)
    assert reviewed["reference"]["claims"][0]["statement"] == output["claims"][0]["statement"]
    assert reviewed["reference"]["claims"][0]["qualifications"] == output["claims"][0]["qualifications"]
    for foreign in ["PDF_LAYOUT:L999", "PDF_LAYOUT:L2"]:
        invalid = copy.deepcopy(output)
        invalid["claims"][0]["pdf_evidence_line_ids"] = [foreign]
        with pytest.raises(SourceContractError):
            validate_scientific_table_output(block, cells, invalid, context)
    omitted = copy.deepcopy(output)
    omitted["claims"] = []
    with pytest.raises(SourceContractError):
        validate_scientific_table_output(block, cells, omitted, context)
