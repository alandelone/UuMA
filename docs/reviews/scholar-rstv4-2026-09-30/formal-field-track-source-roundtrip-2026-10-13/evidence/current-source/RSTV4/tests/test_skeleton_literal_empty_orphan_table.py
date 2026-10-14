import copy

import pytest
from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_table_reference import TableRows as OriginalTableRows
from rstv4.skeleton_table_reference import table_requirements as original_requirements
from rstv4.skeleton_table_reference_v2 import TableRows, table_requirements


def block(text):
    return {"block_id": "paper:b1", "text": text,
            "source_spans": [{"span_id": "paper:b1:s1", "start": 0, "end": len(text)}]}


def reference():
    return {"claims": [{"reference_id": "r1", "statement": "Exactly 5 MW",
                        "source_span_ids": ["paper:b1:s1"], "qualifications": []}],
            "roles": [], "relations": []}


def test_exact_empty_orphan_keeps_rows_and_literal_values():
    text = "<table><tr><td>Power</td><td>5 MW</td></tr><tr> \n</table>Footnotes"
    original, current = OriginalTableRows(text), TableRows(text)
    original.feed(text)
    current.feed(text)
    current.close()
    assert original.current is not None
    assert current.current is None
    assert current.rows == original.rows
    recovery = current.structural_recoveries[0]
    assert text[recovery["source_char_start"]:recovery["source_char_end"]] == "<tr> \n"
    assert recovery["raw_text_digest"] == digest("<tr> \n")
    assert recovery["scientific_data_discarded"] is False
    source, claims = block(text), reference()
    before = copy.deepcopy((source, claims))
    updated, ledger = table_requirements(source, claims)
    assert (source, claims) == before
    assert updated["claims"][0]["statement"] == claims["claims"][0]["statement"]
    assert [x["raw_value"] for x in ledger if "raw_value" in x] == ["Power", "5 MW"]
    assert ledger[-1] == recovery


@pytest.mark.parametrize("orphan", ["<tr><td>5 MW</td>", "<tr><td></td>",
                                     "<tr>unparsed data", "<tr class='x'>", "<tr><td>5"])
def test_nonempty_or_attributed_unclosed_rows_remain_fatal(orphan):
    with pytest.raises(SourceContractError, match="Incomplete parsed HTML table"):
        table_requirements(block("<table>" + orphan + "</table>"), reference())


def test_orphan_without_table_close_remains_fatal():
    with pytest.raises(SourceContractError, match="Incomplete parsed HTML table"):
        table_requirements(block("<table><tr>"), reference())


def test_balanced_table_has_exact_original_requirements():
    source = block("<table><tr><td>Power</td><td>5 MW</td></tr></table>")
    assert table_requirements(source, reference()) == original_requirements(source, reference())


def test_numeric_row_without_source_claim_remains_fatal():
    with pytest.raises(SourceContractError, match="has no located reference claim"):
        table_requirements(block("<table><tr><td>5</td></tr><tr></table>"),
                           {"claims": [], "roles": [], "relations": []})
