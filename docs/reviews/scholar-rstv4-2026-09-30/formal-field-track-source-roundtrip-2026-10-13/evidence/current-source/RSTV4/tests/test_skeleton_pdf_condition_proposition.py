"""Fake source only: condition scope and unique qualified proposition provenance."""
import copy

import pytest
from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_original_pdf_table_science_v5 import validate_condition_qualifications


def fake_source():
    claim = {"reference_id": "r1", "statement": "TX cold startup takes time; warm startup is separate.",
        "source_technology_header_id": "TX", "pdf_evidence_line_ids": ["L1", "L2", "L3"],
        "footnote_qualifications": {"b:F1": {"qualification": "Defined below 50 C.",
            "applicability_rationale": "Fake superscript on cold.",
            "qualified_statement_fragment": "cold startup"}}}
    notes = {"b": {"anchor_line_id": "L1", "marker_line_id": "L2",
        "definition_lines": [{"line_id": "L3", "text": "Defined below 50 C."}]}}
    fragments = {"fragments": [{"fragment_id": "b:F1", "marker": "b", "quote": "Defined below 50 C."}]}
    scope = {"source_scope_protocol_eligible": True, "unresolved_fields": [],
        "condition_scopes": {"b:F1": {"condition_statement": "Defined below 50 C.",
            "anchor_prefix_fragment": "cold", "applicable_technology_header_ids": ["TX", "TY"],
            "resolution": "RESOLVED"}}}
    return claim, notes, fragments, scope


def test_scientific_text_and_selected_proposition_are_preserved():
    values = fake_source()
    original = copy.deepcopy(values)
    result = validate_condition_qualifications(*values)
    assert values == original
    assert result[0]["model_declared_qualified_fragment"] == "cold startup"
    assert result[0]["statement_fragment_start"] == 3
    assert result[0]["statement_fragment_end"] == 15
    assert result[0]["scientific_fields_changed"] is False


@pytest.mark.parametrize("change, message", [
    ("foreign_fragment", "foreign original definition"),
    ("wrong_technology", "resolved original technology"),
    ("changed_condition", "unchanged reviewed source"),
    ("foreign_statement_fragment", "exactly once"),
    ("duplicated_statement_fragment", "exactly once"),
    ("neighboring_proposition", "pre-marker source term"),
    ("incomplete_source", "anchor/complete definition"),
    ("source_ambiguity", "eligible original condition"),
    ("unresolved_condition", "resolved original technology"),
    ("missing_condition_domain", "eligible original condition"),
])
def test_wrong_condition_attachment_is_rejected_without_repair(change, message):
    values = fake_source()
    claim, _, _, scope = values
    qualification = claim["footnote_qualifications"]["b:F1"]
    if change == "foreign_fragment":
        claim["footnote_qualifications"]["foreign"] = claim["footnote_qualifications"].pop("b:F1")
    elif change == "wrong_technology":
        claim["source_technology_header_id"] = "TZ"
    elif change == "changed_condition":
        qualification["qualification"] = "Defined below 51 C."
    elif change == "foreign_statement_fragment":
        qualification["qualified_statement_fragment"] = "unmentioned cold"
    elif change == "duplicated_statement_fragment":
        claim["statement"] += " cold startup"
    elif change == "neighboring_proposition":
        qualification["qualified_statement_fragment"] = "warm startup"
    elif change == "incomplete_source":
        claim["pdf_evidence_line_ids"].remove("L3")
    elif change == "source_ambiguity":
        scope["unresolved_fields"] = ["Fake retained scope ambiguity"]
    elif change == "unresolved_condition":
        scope["condition_scopes"]["b:F1"]["resolution"] = "UNRESOLVED"
    else:
        scope["condition_scopes"].clear()
    before = copy.deepcopy(values)
    with pytest.raises(SourceContractError, match=message):
        validate_condition_qualifications(*values)
    assert values == before
