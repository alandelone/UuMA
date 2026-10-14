"""Fake source provenance checks for repeated actual block/blank-line failures."""
import copy
import json

import pytest
from pydantic import ValidationError
from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_original_pdf_table_science_v4 import (
    indexed_original_pdf_lines,
    source_values,
    validate_pdf_science,
)
from test_skeleton_pdf_numeric_source import fixture


def source_case():
    context, native, _, claims = fixture()
    text = "Parameter  Unit  AEL  AEMEL  PEMEL\nCosta USD 10 20 30\na\nCold below 50.\n\n"
    lines = indexed_original_pdf_lines(text)
    context.update(layout_text=text, indexed_layout_lines=lines,
                   source_pdf="fake.pdf", layout_text_path="fake-layout.txt")
    ids = [line["line_id"] for line in lines]
    native["target_table_line_ids"] = list(ids)
    for index, row in enumerate(native["original_table_body_rows"]):
        row["source_line"] = lines[index]
    native["original_table_body_rows"][1]["native_words"][0]["text"] = "Costa"
    footnote = {"marker": "a", "marker_line_id": ids[2], "definition_lines": [lines[3]],
        "anchor_token": "Costa", "anchor_line_id": ids[1], "anchor_line_exact_text": lines[1]["text"],
        "original_pdf_page": 6, "anchor_word_body_font_size": 6,
        "anchor_word_bbox": {"x0": 0, "x1": 10, "top": 5, "bottom": 10},
        "marker_glyph": {"text": "a", "size": 3, "x0": 6, "x1": 7, "top": 5, "bottom": 8},
        "footer_marker_glyph": {"text": "a", "size": 3, "x0": 0, "x1": 1, "top": 12, "bottom": 15}}
    ledger = {"source_pdf": context["source_pdf"], "source_pdf_sha256": context["source_pdf_sha256"],
        "original_pdf_layout_path": context["layout_text_path"],
        "original_pdf_layout_sha256": context["layout_text_sha256"], "table_source_line_ids": list(ids),
        "scientific_fields_generated_or_changed": False, "learner_or_expected_scientific_values_used": False,
        "actual_pdf_page": 6, "source_footnotes": [footnote]}
    for claim in claims:
        claim["intent"] = "Method_Detail"
    claims[0]["footnote_qualifications"] = {"a": {
        "qualification": "Cold below 50.", "applicability_rationale": "Fake original Costa scope."}}
    claims[0]["pdf_evidence_line_ids"].extend(ids[2:4])
    output = {"claims": claims, "line_coverage": {key: {
        "disposition": "SCIENTIFIC_DATA" if index in [1, 3] else "HEADER_OR_STRUCTURE",
        "rationale": "Fake source disposition."} for index, key in enumerate(ids[:4])},
        "contains_scientific_data": True, "unresolved_fields": []}
    return context, ids, ledger, native, output


def test_source_identity_binding_preserves_every_raw_scientific_field():
    context, ids, ledger, native, output = source_case()
    original = copy.deepcopy(output)
    result = validate_pdf_science(output, context, ids, "fakepaper:b1", ledger, native)
    assert output == original
    assert [{key: value for key, value in claim.items() if key != "block_id"}
            for claim in result["claims"]] == output["claims"]
    assert [claim["block_id"] for claim in result["claims"]] == ["fakepaper:b1"] * 3
    assert result["source_block_identity_resolutions"] == [{
        "reference_id": f"r{index}", "actual_target_block_id": "fakepaper:b1",
        "source_identity_generated_by_model": False, "scientific_fields_changed": False}
        for index in range(1, 4)]


def test_foreign_predicted_block_id_stays_a_fatal_extra_field():
    context, ids, ledger, native, output = source_case()
    output["claims"][0]["block_id"] = "foreignpaper:b9"
    with pytest.raises(ValidationError, match="block_id.*|Extra inputs"):
        validate_pdf_science(output, context, ids, "fakepaper:b1", ledger, native)


def test_duplicate_claim_id_is_named_and_never_repaired():
    context, ids, ledger, native, output = source_case()
    output["claims"][1]["reference_id"] = "r1"
    with pytest.raises(SourceContractError, match="duplicated: r1"):
        validate_pdf_science(output, context, ids, "fakepaper:b1", ledger, native)


def test_blank_source_lines_are_preserved_but_not_coverage_keys():
    context, ids, ledger, native, output = source_case()
    values = source_values(context, ids, "fakepaper:b1", ledger, native)
    assert json.loads(values["required_nonblank_line_coverage_ids"]) == ids[:4]
    assert json.loads(values["target_table_line_ids"]) == ids
    assert json.loads(values["original_pdf_lines"])[-1] == {"line_id": ids[4], "text": "\n"}
    output["line_coverage"][ids[4]] = {"disposition": "HEADER_OR_STRUCTURE", "rationale": "Blank"}
    with pytest.raises(SourceContractError, match="exactly one disposition"):
        validate_pdf_science(output, context, ids, "fakepaper:b1", ledger, native)


def test_footnote_error_names_exact_claim_required_and_missing_source_ids():
    context, ids, ledger, native, output = source_case()
    output["claims"][0]["pdf_evidence_line_ids"].remove(ids[3])
    with pytest.raises(SourceContractError) as failure:
        validate_pdf_science(output, context, ids, "fakepaper:b1", ledger, native)
    assert json.loads(str(failure.value).partition(": ")[2]) == {
        "reference_id": "r1", "marker": "a", "selected_pdf_line_ids": ids[:3],
        "required_source_line_ids": ids[1:4], "missing_source_line_ids": [ids[3]]}
