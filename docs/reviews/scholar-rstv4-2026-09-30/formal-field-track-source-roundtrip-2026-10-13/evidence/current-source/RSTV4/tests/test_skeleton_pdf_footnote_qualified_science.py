import copy

import pytest
from pydantic import ValidationError
from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_original_pdf_table_science_v2 import (
    indexed_original_pdf_lines,
    source_values,
    validate_pdf_science,
)
from rstv4.skeleton_pdf_footnote_anchors_v1 import (
    normalized_anchor_text,
    verify_footnote_anchor_ledger,
)


def source_case():
    text = "CAPEXa USD/kW Technology A\n5 USD/kW\na\nScale effects expected for large systems.\n"
    context = {"layout_text": text, "indexed_layout_lines": indexed_original_pdf_lines(text),
               "source_pdf": "fake.pdf", "source_pdf_sha256": "fake-pdf-sha",
               "layout_text_path": "fake-layout.txt", "layout_text_sha256": "fake-layout-sha"}
    ids = [line["line_id"] for line in context["indexed_layout_lines"]]
    ledger = {"source_pdf": context["source_pdf"], "source_pdf_sha256": context["source_pdf_sha256"],
              "original_pdf_layout_path": context["layout_text_path"],
              "original_pdf_layout_sha256": context["layout_text_sha256"],
              "table_source_line_ids": list(ids), "scientific_fields_generated_or_changed": False,
              "learner_or_expected_scientific_values_used": False, "actual_pdf_page": 6,
              "source_footnotes": [{"marker": "a", "marker_line_id": ids[2],
                  "definition_lines": [context["indexed_layout_lines"][3]], "anchor_token": "CAPEXa",
                  "anchor_line_id": ids[0], "anchor_line_exact_text": context["indexed_layout_lines"][0]["text"],
                  "original_pdf_page": 6, "anchor_word_body_font_size": 6,
                  "anchor_word_bbox": {"x0": 0, "x1": 6, "top": 1, "bottom": 5},
                  "marker_glyph": {"text": "a", "size": 3, "x0": 4, "x1": 5, "top": 1, "bottom": 4},
                  "footer_marker_glyph": {"text": "a", "size": 3, "x0": 0, "x1": 1, "top": 12, "bottom": 15}}]}
    output = {"claims": [{"reference_id": "r1", "block_id": "paper:b1", "statement": "Technology A CAPEX is 5 USD/kW",
        "qualifications": ["Technology A"], "footnote_qualifications": {"a": {
            "qualification": "Scale effects expected for large systems.", "applicability_rationale": "Original CAPEXa anchor applies to the stated CAPEX value"}},
        "intent": "Method_Detail", "pdf_evidence_line_ids": list(ids)}],
        "line_coverage": {key: {"disposition": "SCIENTIFIC_DATA", "rationale": "Original scientific source support"} for key in ids},
        "contains_scientific_data": True, "unresolved_fields": []}
    return context, ids, ledger, output


def test_footnote_science_preserves_all_model_declared_conditions_and_ordinary_scientific_fields():
    context, ids, ledger, output = source_case()
    original = copy.deepcopy(output)
    result = validate_pdf_science(output, context, ids, "paper:b1", ledger)
    assert output == original and result["claims"] == output["claims"]
    assert result["model_declared_footnote_qualification_links"] == {"a": ["r1"]}
    assert result["parsed_cell_association_complete"] is False
    assert source_values(context, ids, "paper:b1", ledger)["original_pdf_footnote_anchors"]


@pytest.mark.parametrize("fault", ["no_declaration", "foreign_marker", "missing_anchor", "missing_footer", "missing_definition", "empty_condition"])
def test_unqualified_or_unlocated_scientific_footnote_cannot_pass(fault):
    context, ids, ledger, output = source_case()
    claim = output["claims"][0]
    if fault == "no_declaration":
        claim["footnote_qualifications"] = {}
    elif fault == "foreign_marker":
        claim["footnote_qualifications"]["z"] = claim["footnote_qualifications"].pop("a")
    elif fault == "empty_condition":
        claim["footnote_qualifications"]["a"]["qualification"] = ""
    else:
        claim["pdf_evidence_line_ids"].remove(ids[{"missing_anchor": 0, "missing_footer": 2, "missing_definition": 3}[fault]])
    with pytest.raises((SourceContractError, ValidationError)):
        validate_pdf_science(output, context, ids, "paper:b1", ledger)


@pytest.mark.parametrize("fault", ["wrong_anchor", "missing_marker", "missing_definition", "body_font", "changed_source_text"])
def test_source_anchor_ledger_keeps_original_marker_definition_and_glyph_gates(fault):
    context, ids, ledger, _ = source_case()
    footnote = ledger["source_footnotes"][0]
    if fault == "wrong_anchor":
        footnote["anchor_line_id"] = ids[1]
    elif fault == "missing_marker":
        ledger["source_footnotes"] = []
    elif fault == "missing_definition":
        footnote["definition_lines"] = []
    elif fault == "body_font":
        footnote["marker_glyph"]["size"] = 6
    else:
        footnote["anchor_line_exact_text"] = "Changed source"
    with pytest.raises(ValueError):
        verify_footnote_anchor_ledger(context, ids, ledger)


def test_native_glyph_ligature_and_whitespace_alias_is_only_a_locator_and_preserves_source():
    native = "Efficiencyc(System,"
    source = "Efﬁciencyc (System,"
    assert normalized_anchor_text(native) == normalized_anchor_text(source)
    assert source == "Efﬁciencyc (System,"
    assert normalized_anchor_text("Other parameter") != normalized_anchor_text(source)
