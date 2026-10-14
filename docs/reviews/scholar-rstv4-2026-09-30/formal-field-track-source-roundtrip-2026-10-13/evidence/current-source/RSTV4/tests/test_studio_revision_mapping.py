from __future__ import annotations

import csv
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from rstv4.database import transaction
from rstv4.service import RSTV4Error
from rstv4.studio_revision_mapping import extract_layout, tokens, unique_paragraph
from test_writing_studio import complete_document, create_studio, wait_for_job


def layout_fixture(texts):
    stream = []
    for page, line, text in texts:
        stream.extend({"token": value, "page": page, "line": line, "box": [i, line, i + 1, line + 1]}
                      for i, value in enumerate(tokens(text)))
    return {"tokens": stream, "status": "EXTRACTED"}


def test_full_paragraph_uniqueness_never_accepts_prefix_or_duplicate_text():
    actual = "A revised software fixture has two toolbars. No study is conducted."
    layout = layout_fixture([(1, 4, actual)])
    matched, reason = unique_paragraph(layout, actual)
    assert reason == "UNIQUE_FULL_PARAGRAPH" and matched
    assert unique_paragraph(layout, actual + " Unsupported addition.")[1] == "PDF_TEXT_NOT_FOUND"
    duplicate = layout_fixture([(1, 4, actual), (2, 3, actual)])
    assert unique_paragraph(duplicate, actual) == ([], "AMBIGUOUS_PDF_TEXT")


def test_word_boundaries_cannot_be_erased_to_create_a_match():
    layout = layout_fixture([(1, 4, "The rapist example is distinct.")])
    assert unique_paragraph(layout, "Therapist example is distinct.")[1] == "PDF_TEXT_NOT_FOUND"


def test_line_wrap_hyphenation_keeps_actual_end_line_boxes():
    layout = layout_fixture([(1, 4, "Interdisci-"), (1, 5, "plinary fixture.")])
    matched, reason = unique_paragraph(layout, "Interdisciplinary fixture.")
    assert reason == "UNIQUE_FULL_PARAGRAPH"
    assert matched[0]["line"] == 4 and matched[0]["extra_boxes"][-1]["line"] == 5


def generated(service, manuscript_id, revision, output, *, comment_ids=None, sentences=True):
    document = complete_document(service.get_workspace(manuscript_id))
    thought = document["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]
    thought["text"] = ("Install one original toolbar. Record that no study is conducted." if revision == 1
                       else "Install two revised toolbars. Record that no study is conducted.")
    service.save_document(manuscript_id, base_revision=revision - 1, operation_id=f"map-author-{revision}",
                          document=document, comment_ids=comment_ids)
    parts = [item.strip() + "." for item in output[:-1].split(".")]
    response = {"paragraph": output, "sentence_mappings": [{"sentence": i, "thought_ids": [thought["id"]]} for i in range(len(parts))],
                "_contract": {"actual_model": "declared-test-fixture", "task": "paragraph_realization"}}
    if sentences:
        response["sentences"] = parts
    service.gateway.analyze = lambda task, payload: deepcopy(response)
    job = wait_for_job(service, service.create_job(manuscript_id, "GENERATE", input_revision=revision))
    assert job["status"] == "SUCCEEDED", job
    return document, service.get_generated_version(manuscript_id, job["result"]["generated_version_id"])


def package_fixture(tmp_path: Path, *, sentences=True):
    service, _, manuscript_id = create_studio(tmp_path)
    original_document, first = generated(service, manuscript_id, 1, "One original toolbar is present. No study is conducted.")
    round_row = service.create_review_round(manuscript_id, round_number=1, venue="Software fixture")
    opinion = service.import_comments(round_row["review_round_id"], [{"text": "Revise fixture toolbar count", "include": True}], source="FIXTURE")[0]
    target_document, target = generated(service, manuscript_id, 2,
        "Two revised toolbars are present. No study is conducted.", comment_ids=[opinion["comment_id"]], sentences=sentences)
    job = wait_for_job(service, service.create_job(manuscript_id, "SUBMISSION_PACKAGE", input_revision=2,
                                                  request={"review_round_id": round_row["review_round_id"]}))
    assert job["status"] == "SUCCEEDED", job
    directory = Path(job["result"]["directory"])
    report = json.loads((directory / "change-realization-map.json").read_text(encoding="utf-8"))
    return service, manuscript_id, opinion, original_document, target_document, first, target, directory, report


def test_actual_compiled_page_lines_map_multiple_sentences_and_retained_text_separately(tmp_path: Path):
    service, manuscript_id, _, _, target_document, _, target, directory, report = package_fixture(tmp_path)
    assert [row["status"] for row in report["rows"]] == ["GENERATED_TEXT_CHANGED", "EXACT_BASELINE_TEXT_RETAINED"]
    assert report["rows"][0]["thought_id"] == report["rows"][1]["thought_id"]
    assert report["rows"][0]["changed_text"] not in target_document["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]["text"]
    assert not report["automatic_response_approval"] and not report["scientific_acceptance"]
    expected_pdf_sha = hashlib.sha256((directory / "clean-manuscript.pdf").read_bytes()).hexdigest()
    assert report["pdf"]["pdf_sha256"] == expected_pdf_sha
    actual_lines = {(item["page"], item["line"]): item["text"] for item in report["pdf"]["lines"]}
    for row in report["rows"]:
        assert row["generated_version_id"] == target["generated_version_id"]
        assert row["final_pdf_sha256"] == expected_pdf_sha
        assert row["final_page"] == row["final_page_end"] == 1
        assert (row["final_page"], row["final_line"]) in actual_lines
        assert row["boxes"] and row["line_number_kind"] == "visible_text_line_from_top_of_physical_page"
    with (directory / "change-location-map.csv").open(encoding="utf-8-sig", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    assert len(csv_rows) == 2 and csv_rows[0]["final_line"] == str(report["rows"][0]["final_line"])
    assert service.get_workspace(manuscript_id)["document"] == target_document


def test_legacy_missing_sentence_positions_remain_unknown_without_prefix_matching(tmp_path: Path):
    *_, report = package_fixture(tmp_path, sentences=False)
    assert len(report["rows"]) == 1
    assert report["rows"][0]["status"] == "SENTENCE_MAPPING_UNKNOWN"
    assert report["rows"][0]["final_line"] is None and report["rows"][0]["final_page"] is None


def test_superseded_linked_edit_cannot_count_as_completed_final_change(tmp_path: Path):
    service, manuscript_id, opinion, _, target_document, _, _, _, _ = package_fixture(tmp_path)
    current = deepcopy(target_document)
    current["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]["text"] = "A later third author requirement."
    service.save_document(manuscript_id, base_revision=2, operation_id="map-later-author-3", document=current)
    service.gateway.analyze = lambda task, payload: {"paragraph": "A later third author requirement.", "sentences": ["A later third author requirement."],
        "sentence_mappings": [{"sentence": 0, "thought_ids": ["thought_author_1"]}]}
    job = wait_for_job(service, service.create_job(manuscript_id, "GENERATE", input_revision=3))
    assert job["status"] == "SUCCEEDED", job
    package = wait_for_job(service, service.create_job(manuscript_id, "SUBMISSION_PACKAGE", input_revision=3))
    assert package["status"] == "SUCCEEDED", package
    report = json.loads((Path(package["result"]["directory"]) / "change-realization-map.json").read_text(encoding="utf-8"))
    assert report["rows"][0]["comment_id"] == opinion["comment_id"]
    assert report["rows"][0]["status"] == "SUPERSEDED_OR_REVERSED" and report["rows"][0]["final_line"] is None


@pytest.mark.parametrize("tamper", ["model_mapping", "model_contract", "paragraph_id", "original_call_input"])
def test_generated_mapping_is_bound_to_exact_original_model_call_and_author_input(tmp_path: Path, tamper: str):
    service, manuscript_id, _, _, _, _, target, _, _ = package_fixture(tmp_path)
    version_id = target["generated_version_id"]
    with transaction(service.db_path) as conn:
        raw = conn.execute("SELECT inputs_json FROM manuscript_versions WHERE manuscript_version_id=?", (version_id,)).fetchone()[0]
        inputs = json.loads(raw)
        paragraph = inputs["generated"]["sections"][0]["paragraphs"][0]
        if tamper == "model_mapping":
            paragraph["sentence_mappings"][0]["thought_ids"] = ["unknown-thought"]
        elif tamper == "model_contract":
            paragraph["model_contract"] = {"actual_model": "invented"}
        elif tamper == "paragraph_id":
            paragraph["paragraph_id"] = "unavailable-author-paragraph"
        else:
            conn.execute("UPDATE studio_model_calls SET input_json=? WHERE call_id=?", ("{}", paragraph["model_call_id"]))
        if tamper != "original_call_input":
            conn.execute("UPDATE manuscript_versions SET inputs_json=? WHERE manuscript_version_id=?", (json.dumps(inputs), version_id))
    with pytest.raises(RSTV4Error, match="original"):
        service.get_generated_version(manuscript_id, version_id)


def test_missing_layout_tool_reports_unavailable_instead_of_guessing_locations(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "declared-fixture.pdf"
    pdf.write_bytes(b"%PDF-declared-software-fixture")
    monkeypatch.setattr("rstv4.studio_revision_mapping.shutil.which", lambda name: None)
    result = extract_layout(pdf, tmp_path / "unused.xhtml")
    assert result["status"] == "TOOL_UNAVAILABLE" and not result["tokens"]
    assert result["pdf_sha256"] == hashlib.sha256(pdf.read_bytes()).hexdigest()
