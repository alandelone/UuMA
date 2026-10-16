"""Frozen author provenance and citation-only attribution; no scientific approval."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest
from test_studio_response_checks import prepared
from test_studio_source_context import generate, source_studio

from rstv4.database import transaction
from rstv4.studio_revision_mapping import compare_sentence, frozen_origins


@pytest.mark.parametrize("before,after,expected", [
    ("A finding [@a].", "A finding [@b].", "CITATION_ONLY"),
    ("A finding [@a].", "A finding.", "CITATION_ONLY"),
    ("A finding.", "A finding [@a] [@b].", "CITATION_ONLY"),
    ("A finding [@a] [@b].", "A finding [@b] [@a].", "CITATION_ONLY"),
    ("A finding [@a].", "A finding [@a].", "EXACT_BASELINE_TEXT_RETAINED"),
    ("A finding [@a].", "A different finding [@b].", "GENERATED_TEXT_CHANGED"),
    ("No study is conducted.", "A study is conducted.", "GENERATED_TEXT_CHANGED"),
    ("A finding?", "A finding.", "GENERATED_TEXT_CHANGED"),
])
def test_citation_identity_cannot_prove_changed_prose(before, after, expected):
    recorded = {"sentence_positions_verified": True, "sentences": [{"text": before}]}
    assert compare_sentence(after, recorded, before) == expected


def test_unrecorded_baseline_sentences_remain_unknown():
    assert compare_sentence("A changed sentence.", None, "Old prose.") == "BASELINE_SENTENCE_COMPARISON_UNKNOWN"


def test_origins_preserve_full_original_bank_intent_and_thought_identity():
    bank = {"id": "bank", "title": "Original section", "placement_status": "UNPLACED",
            "paragraphs": [{"id": "original-paragraph", "purpose": "Original purpose", "intents": [
                {"id": "original-intent", "label": "Original intent", "thoughts": [
                    {"id": "thought-one", "text": "Same opening.\nComplete first qualification."},
                    {"id": "thought-two", "text": "Same opening.\nComplete second qualification."}]}]}]}
    document = {"manuscript_id": "ms", "sections": [bank, {"id": "template", "title": "Placed section",
                "paragraphs": [{"id": "slot", "intents": [{"id": "slot-intent", "label": "Template slot",
                    "author_intent_ids": ["original-intent"], "thoughts": []}]}]}]}
    target = {"manuscript_id": "ms", "generated_version_id": "v-fixed", "version": 4, "input_revision": 8}
    original = deepcopy(document)
    origins = frozen_origins(document, target)
    assert set(origins) == {"thought-one", "thought-two"}
    first, second = origins["thought-one"][0], origins["thought-two"][0]
    assert first["intent_id"] == second["intent_id"] == "original-intent"
    assert first["paragraph_id"] == "original-paragraph" and first["section_id"] == "bank"
    assert first["intent_thoughts"] == second["intent_thoughts"] == [
        {"thought_id": t["id"], "text": t["text"]} for t in bank["paragraphs"][0]["intents"][0]["thoughts"]]
    assert first["thought_text"] != second["thought_text"] and document == original
    with pytest.raises(ValueError, match="another manuscript"):
        frozen_origins(document, {**target, "manuscript_id": "foreign"})


def test_actual_reply_check_keeps_frozen_origins_after_current_author_changes(tmp_path):
    service, ms, comment, context, request, document, _ = prepared(tmp_path)
    row = next(r for r in context["evidence"] if r["status"] == "GENERATED_TEXT_CHANGED")
    origin = row["origins"][0]
    original_intent = document["sections"][0]["paragraphs"][0]["intents"][0]
    assert origin["thought_text"] == original_intent["thoughts"][0]["text"]
    assert origin["input_revision"] == 2 and origin["generated_version_id"] == context["state"]["generated_version_id"]
    check = service.confirm_response_review(ms, comment, request)
    with transaction(service.db_path) as conn:
        raw = conn.execute("SELECT context_json FROM studio_response_checks WHERE check_id=?", (check["check_id"],)).fetchone()[0]
    changed = deepcopy(document)
    changed["sections"][0]["paragraphs"][0]["intents"][0].update(label="Later mutable intent")
    changed["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]["text"] = "Later mutable thought."
    service.save_document(ms, base_revision=2, operation_id="later-origin-edit", document=changed)
    assert service.response_review_history(ms, comment)["history"] == check["history"]
    assert service.confirm_response_review(ms, comment, request)["idempotent_replay"]
    with transaction(service.db_path) as conn:
        assert conn.execute("SELECT context_json FROM studio_response_checks WHERE check_id=?", (check["check_id"],)).fetchone()[0] == raw
    assert json.loads(raw)["evidence"][0]["origins"][0] == origin


def test_actual_citation_only_pdf_rows_cannot_confirm_scientific_prose_change(tmp_path):
    service, ms, evidence, _, _, document = source_studio(tmp_path, compile_pdf=True)
    thought = document["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]

    def response(evidence_id):
        sentence = f"No scientific conclusion is asserted [@{evidence_id}]."
        return {"paragraph": sentence, "sentences": [sentence],
                "sentence_mappings": [{"sentence": 0, "thought_ids": [thought["id"]]}],
                "_contract": {"actual_model": "TEST_FIXTURE", "task": "paragraph_realization"}}

    service.gateway.analyze = lambda task, payload: response(evidence[0]["evidence_id"])
    baseline = generate(service, ms)
    review = service.create_review_round(ms, round_number=1, venue="Software citation-only acceptance")
    comment = service.import_comments(review["review_round_id"], [{"text": "Change only the citation."}], source="FIXTURE")[0]
    thought["citations"] = [{"evidence_id": evidence[1]["evidence_id"], "selected": True}]
    service.save_document(ms, base_revision=1, operation_id="citation-only", document=document, comment_ids=[comment["comment_id"]])
    service.gateway.analyze = lambda task, payload: response(evidence[1]["evidence_id"])
    target = generate(service, ms)
    service.update_comment(comment["comment_id"], {"author_decision": "Software guard test", "response_text": "We modified the prose."})
    context = service.response_review_context(ms, comment["comment_id"])
    assert context["baseline_to_target_diff"] and not context["baseline_to_target_display_diff"]
    assert baseline["references"][0]["evidence_id"] != target["references"][0]["evidence_id"]
    row, = context["evidence"]
    assert row["status"] == "CITATION_ONLY" and row["change_kind"] == "CITATION"
    assert row["boxes"] and row["final_page"] and row["final_line"]
    assert row["supports_scientific_text_modification"] is False
    request = {"request_id": "reject-citation-as-prose", "context_sha256": context["context_sha256"],
               "outcome": "MODIFIED", "acknowledged_all_assertions": True,
               "claims": [{"start": 0, "end": 22, "text": "We modified the prose.", "offset_unit": "utf16", "evidence_ids": [row["evidence_id"]]}]}
    with pytest.raises(ValueError, match="unknown"):
        service.confirm_response_review(ms, comment["comment_id"], request)
    assert service.response_review_history(ms, comment["comment_id"])["history"] == []
