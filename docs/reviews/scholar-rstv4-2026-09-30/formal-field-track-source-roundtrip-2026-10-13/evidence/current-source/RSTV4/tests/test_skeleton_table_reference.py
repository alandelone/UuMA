from __future__ import annotations

import copy

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

from rstv4.skeleton_contract import SourceContractError, source_spans
from rstv4.skeleton_table_reference import table_requirements


def table_case():
    block = {"block_id": "paper:b1", "text": '<table><tr><th>ID</th><th>Method</th></tr>'
             '<tr><td>8</td><td>Quantified (N=1)</td></tr>'
             '<tr><td>9</td><td>Documente d</td></tr></table>'}
    block["source_spans"] = source_spans(block)
    row_span = next(span for span in block["source_spans"] if '<td>8</td>' in span["text"])
    second_span = next(span for span in block["source_spans"] if '<td>9</td>' in span["text"])
    reference = {"claims": [{"reference_id": f"r{index}", "source_span_ids": [span["span_id"]],
                              "statement": "Reported project result", "qualifications": []}
                             for index, span in enumerate((row_span, second_span))], "roles": [], "relations": []}
    return block, reference


def test_literal_table_methods_are_required_without_reassigning_or_guessing():
    block, reference = table_case()
    before = copy.deepcopy(reference)
    updated, ledger = table_requirements(block, reference)
    assert reference == before
    assert [claim["statement"] for claim in updated["claims"]] == [claim["statement"] for claim in reference["claims"]]
    first = updated["claims"][0]["qualifications"]
    second = updated["claims"][1]["qualifications"]
    assert any("Quantified (N=1)" in value for value in first)
    assert not any("Documente d" in value for value in first)
    assert any("Documente d" in value for value in second)
    assert {item["raw_value"] for item in ledger if item["disposition"] == "REFERENCE_REQUIREMENT"} == {
        "8", "9", "Quantified (N=1)", "Documente d",
    }


def test_numeric_table_data_row_cannot_be_dropped_from_reference():
    block, reference = table_case()
    reference["claims"].pop()
    with pytest.raises(SourceContractError, match="no located reference"):
        table_requirements(block, reference)


def test_non_table_reference_remains_identical():
    block, reference = table_case()
    block["text"] = "A non-table source paragraph."
    updated, ledger = table_requirements(block, reference)
    assert updated == reference and not ledger
