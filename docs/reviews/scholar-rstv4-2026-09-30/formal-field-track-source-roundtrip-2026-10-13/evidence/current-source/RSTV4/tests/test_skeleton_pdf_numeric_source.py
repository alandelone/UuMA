"""Fake source contracts for actual numerical omission and column-scope risks."""
import copy

import pytest
from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_pdf_numeric_source_v1 import (
    native_value_projection,
    numeric_tokens,
    validate_literal_scientific_evidence,
    verify_native_value_ledger,
)


def fixture():
    texts = ["Parameter  Unit  AEL  AEMEL  PEMEL\n", "Cost USD 10 20 30\n", "a cold below 50\n"]
    offset, lines = 0, []
    for index, text in enumerate(texts, 1):
        lines.append({"line_id": f"PDF_LAYOUT:L{index}", "text": text,
                      "start": offset, "end": offset + len(text)})
        offset += len(text)
    context = {"source_pdf_sha256": "fake-pdf", "layout_text_sha256": "fake-layout",
               "indexed_layout_lines": lines}
    headers = [{"technology_header_id": f"PDF_COLUMN:{index + 3}",
                "original_header_text": name, "header_line_id": "PDF_LAYOUT:L1",
                "native_header_bbox": {"x0": 40 + 20 * index}}
               for index, name in enumerate(["AEL", "AEMEL", "PEMEL"])]
    word = lambda text, x: {"text": text, "x0": x, "x1": x + 10, "top": 5, "bottom": 10}
    rows = [{"source_line": lines[0], "native_words": [word(text, x) for text, x in
             [("Parameter", 0), ("Unit", 20), ("AEL", 40), ("AEMEL", 60), ("PEMEL", 80)]]},
            {"source_line": lines[1], "native_words": [word(text, x) for text, x in
             [("Cost", 0), ("USD", 20), ("10", 40), ("20", 60), ("30", 80)]]}]
    quantities = [{"quantity_id": f"PDF_LAYOUT:L2:W{index + 3}:N1",
        "source_line_id": "PDF_LAYOUT:L2", "literal_numeric_token": text,
        "native_word_text": text, "native_word_token_start": 0, "native_word_token_end": 2,
        "technology_header_id": f"PDF_COLUMN:{index + 3}",
        "native_word_bbox": {key: rows[1]["native_words"][index + 2][key]
                             for key in ["x0", "x1", "top", "bottom"]}}
        for index, text in enumerate(["10", "20", "30"])]
    ledger = {"source_pdf_sha256": "fake-pdf", "layout_text_sha256": "fake-layout",
        "target_table_line_ids": [line["line_id"] for line in lines], "technology_headers": headers,
        "original_table_body_rows": rows, "original_numeric_tokens_in_scientific_columns": quantities,
        "scientific_fields_generated_or_changed": False, "learner_or_expected_scientific_values_used": False}
    footnotes = {"source_footnotes": [{"marker_line_id": "PDF_LAYOUT:L3"}]}
    claims = [{"reference_id": f"r{index + 1}", "source_technology_header_id": header["technology_header_id"],
        "statement": header["original_header_text"] + " cost " + str((index + 1) * 10),
        "qualifications": ["USD"], "footnote_qualifications": {},
        "pdf_evidence_line_ids": ["PDF_LAYOUT:L1", "PDF_LAYOUT:L2"]}
        for index, header in enumerate(headers)]
    return context, ledger, footnotes, claims


def test_full_literal_source_coverage_keeps_scientific_fields_unchanged():
    context, ledger, _, claims = fixture()
    before = copy.deepcopy(claims)
    result = validate_literal_scientific_evidence(claims, context, ledger)
    assert result["literal_numeric_source_links"] == {
        "PDF_LAYOUT:L2:W3:N1": ["r1"], "PDF_LAYOUT:L2:W4:N1": ["r2"], "PDF_LAYOUT:L2:W5:N1": ["r3"]}
    assert claims == before
    assert result["numeric_coverage_proves_semantic_scope"] is False


def test_selected_other_lines_do_not_prove_a_statement_number():
    context, ledger, _, claims = fixture()
    claims[0]["pdf_evidence_line_ids"] = ["PDF_LAYOUT:L1", "PDF_LAYOUT:L3"]
    with pytest.raises(SourceContractError, match="numbers lack.*r1.*10"):
        validate_literal_scientific_evidence(claims, context, ledger)


def test_coverage_in_another_technology_does_not_prove_original_quantity():
    context, ledger, _, claims = fixture()
    claims[0]["statement"] = "AEL cost 10 and 20"
    with pytest.raises(SourceContractError, match="same-column.*W4"):
        validate_literal_scientific_evidence([claims[0], claims[2]], context, ledger)


def test_missing_native_quantity_is_not_cleared_by_line_coverage():
    context, ledger, _, claims = fixture()
    claims[1]["statement"] = "AEMEL cost unspecified"
    with pytest.raises(SourceContractError, match="same-column.*W4"):
        validate_literal_scientific_evidence(claims, context, ledger)


@pytest.mark.parametrize("mutation, message", [
    (lambda claim: claim.update(source_technology_header_id="FOREIGN"), "foreign original technology"),
    (lambda claim: claim.update(pdf_evidence_line_ids=["PDF_LAYOUT:L2"]), "header evidence"),
    (lambda claim: claim.update(statement="AEL cost10 and AEMEL cost20"), "one actual technology"),
    (lambda claim: claim.update(qualifications=["PEMEL unit USD"]), "one actual technology"),
    (lambda claim: claim.update(statement="alias cost10"), "one actual technology"),
    (lambda claim: claim.update(statement="AEL cost10 in2099"), "numbers lack"),
])
def test_rejects_false_numeric_or_column_proof(mutation, message):
    context, ledger, _, claims = fixture()
    mutation(claims[0])
    with pytest.raises(SourceContractError, match=message):
        validate_literal_scientific_evidence(claims, context, ledger)


def test_footnote_condition_requires_actual_numeric_evidence_but_has_its_own_scope():
    context, ledger, _, claims = fixture()
    claims[0]["footnote_qualifications"] = {"a": {
        "qualification": "Below 50; this source condition specifically describes PEMEL",
        "applicability_rationale": "Fake source condition, unchanged"}}
    with pytest.raises(SourceContractError, match="numbers lack.*50"):
        validate_literal_scientific_evidence(claims, context, ledger)
    claims[0]["pdf_evidence_line_ids"].append("PDF_LAYOUT:L3")
    assert validate_literal_scientific_evidence(claims, context, ledger)[
        "literal_numeric_source_links"]["PDF_LAYOUT:L2:W3:N1"] == ["r1"]


def test_literal_numbers_do_not_convert_punctuation_or_units():
    assert numeric_tokens("1.500–2.200 and55,000–96,000h; formula7M; 2018") == {
        "1.500", "2.200", "55,000", "96,000", "7", "2018"}
    assert numeric_tokens("1,500") != numeric_tokens("1.500")


def test_full_native_ledger_replay_and_projection_preserve_source():
    context, ledger, footnotes, _ = fixture()
    assert verify_native_value_ledger(context, ledger["target_table_line_ids"], footnotes, ledger) == ledger
    projection = native_value_projection(ledger)
    projection["technology_headers"][0]["original_header_text"] = "changed"
    assert ledger["technology_headers"][0]["original_header_text"] == "AEL"


@pytest.mark.parametrize("mutation, message", [
    (lambda ledger: ledger["original_table_body_rows"].pop(), "body line"),
    (lambda ledger: ledger["original_numeric_tokens_in_scientific_columns"].pop(), "incomplete or changed"),
    (lambda ledger: ledger["original_numeric_tokens_in_scientific_columns"][0].update(
        technology_header_id="PDF_COLUMN:4"), "incomplete or changed"),
    (lambda ledger: ledger["original_table_body_rows"][1]["native_words"][2].update(text="11"), "source body"),
    (lambda ledger: ledger.update(source_pdf_sha256="changed"), "lineage"),
])
def test_rejects_native_inventory_or_source_tampering(mutation, message):
    context, ledger, footnotes, _ = fixture()
    mutation(ledger)
    with pytest.raises(SourceContractError, match=message):
        verify_native_value_ledger(context, ledger["target_table_line_ids"], footnotes, ledger)
