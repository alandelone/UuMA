"""Readable citations must retain each fixed version's distinct source identity."""
from __future__ import annotations

import difflib

import pytest
from test_studio_source_context import generate, source_studio


@pytest.mark.parametrize("same_printed_text", [False, True])
def test_response_diff_numbers_each_version_without_hiding_source_identity(tmp_path, same_printed_text):
    service, ms, evidence, _source, _pdf, document = source_studio(tmp_path)
    before = generate(service, ms)
    fixed = service.create_review_round(ms, round_number=1, venue="Software display acceptance")
    comment = service.import_comments(fixed["review_round_id"], [{"text":"Keep both exact original citation sources."}], source="PASTED")[0]
    thought = document["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]
    document["sections"][0]["paragraphs"][0]["purpose"] = "Software display comparison"
    service.save_document(ms, base_revision=1, operation_id="citation-display-change", document=document)
    prefix = "First" if same_printed_text else "Revised"
    paragraph = f"{prefix} source [@{evidence[0]['evidence_id']}]. Next [@{evidence[1]['evidence_id']}]. Repeat [@{evidence[0]['evidence_id']}]."
    service.gateway.analyze = lambda task, payload: {
        "paragraph": paragraph, "sentence_mappings":[{"sentence":0,"thought_ids":[thought["id"]]}],
        "_contract":{"actual_model":"TEST_FIXTURE_CITATION_DISPLAY","task":task},
    }
    after = generate(service, ms)
    context = service.response_review_context(ms, comment["comment_id"])
    expected_raw = "\n".join(difflib.unified_diff(before["content"].splitlines(), after["content"].splitlines(), fromfile="reviewed-baseline.md", tofile="final-manuscript.md", lineterm=""))
    assert context["baseline_to_target_diff"] == expected_raw and "[@evidence_" in expected_raw
    display = context["baseline_to_target_display_diff"]
    assert "evidence_" not in display and "[@" not in display
    assert bool(display) is (not same_printed_text)
    assert context["baseline_citation_sources"][0]["page"] == 2
    assert context["target_citation_sources"][0]["page"] == 1
    assert context["baseline_citation_sources"] != context["target_citation_sources"]
    assert not context["scientific_acceptance"] and not context["automatic_response_approval"]
    assert service.get_generated_version(ms, before["generated_version_id"]) == before
