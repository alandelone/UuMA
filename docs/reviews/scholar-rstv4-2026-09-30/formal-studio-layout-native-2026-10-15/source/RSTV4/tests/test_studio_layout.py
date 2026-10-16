from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from copy import deepcopy

import pytest
from test_writing_studio import complete_document, create_studio

from rstv4.service import RevisionConflictError
from rstv4.studio import StudioService
from rstv4.studio_context import generated_view
from rstv4.studio_layout import layout_only_evidence, layout_replay, layout_settings
from rstv4.studio_response_checks import validate_claims
from rstv4.studio_revision_mapping import extract_layout, write_mapping


def fixture():
    author = {"schema_version": 1, "manuscript_id": "layout-fixture", "title": "Layout fixture",
              "abstract": "", "venue": "Software fixture", "sections": [{"id": "s", "title": "Fixture",
              "paragraphs": [{"id": "p", "purpose": "Layout only", "asset_ids": [], "intents": [{
                  "id": "i", "label": "Preserve content", "thoughts": [{"id": "t", "text": "Preserve author wording.",
                      "citation_mode": "NONE", "citations": []}]}]}]}]}
    prose = "Alpha fixture begins. " + " ".join(
        "This software example preserves wording and measured geometry across the unchanged content." for _ in range(18)
    ) + " Alpha fixture ends."
    generated = {"title": author["title"], "abstract": "", "input_revision": 1,
                 "citation_style": "numeric_first_use", "references": [], "sections": [{"section_id": "s",
                 "title": "Fixture", "paragraphs": [{"paragraph_id": "p", "text": prose,
                    "thought_ids": ["t"], "evidence_ids": [], "formulas": []}]}]}
    after = deepcopy(author)
    after["layout"] = {"page_margin": "narrow"}
    return author, after, generated


@pytest.mark.parametrize("value", [None, [], "narrow", {}, {"page_margin": "1in"},
    {"page_margin": True}, {"page_margin": "narrow", "raw_tex": "bad"}, {"font_size": 12}])
def test_layout_rejects_unknown_or_untyped_latex_controls(value):
    with pytest.raises(ValueError):
        layout_settings({"layout": value})


def test_absent_layout_preserves_historical_tex_and_input_does_not_mutate():
    before, after, source = fixture()
    source_bytes = json.dumps(source, sort_keys=True)
    old_tex = StudioService._latex(source, [])
    assert r"\usepackage[margin=1in]{geometry}" in old_tex
    new = layout_replay(before, after, source, 2, "fixed-v5")
    assert json.dumps(source, sort_keys=True) == source_bytes
    assert new["sections"] == source["sections"] and new["references"] == source["references"]
    assert new["layout_replay"]["source_generated_version_id"] == "fixed-v5"
    assert r"\usepackage[margin=0.75in]{geometry}" in StudioService._latex(new, [])
    assert "layout" not in source and "layout" not in before


@pytest.mark.parametrize("mutation", ["text", "citation", "citation_identity", "material", "formula", "condition", "order", "unknown"])
def test_layout_replay_rejects_any_semantic_identity_or_structural_change(mutation):
    before, after, source = fixture()
    paragraph = after["sections"][0]["paragraphs"][0]
    thought = paragraph["intents"][0]["thoughts"][0]
    if mutation == "text":
        thought["text"] += " A changed scientific claim."
    elif mutation == "citation":
        thought["citations"] = [{"evidence_id": "source1", "selected": True}]
    elif mutation == "citation_identity":
        thought["citation_mode"] = "SELECTED"
    elif mutation == "material":
        paragraph["asset_ids"] = ["new-material"]
    elif mutation == "formula":
        paragraph["formulas"] = [{"id": "f", "latex": "a=b"}]
    elif mutation == "condition":
        after["argument_relations"] = [{"condition": "Under different conditions"}]
    elif mutation == "order":
        after["sections"].insert(0, {"id": "new-section", "title": "Changed order", "paragraphs": []})
    else:
        after["future_semantic_field"] = "Never silently strip unknown fields"
    with pytest.raises(ValueError, match="cannot change"):
        layout_replay(before, after, source, 2, "fixed-v5")


def test_replay_requires_real_margin_change_later_revision_and_correct_frozen_source():
    before, after, source = fixture()
    with pytest.raises(ValueError, match="Change a page margin"):
        layout_replay(before, deepcopy(before), source, 2, "fixed-v5")
    with pytest.raises(ValueError, match="later author revision"):
        layout_replay(before, after, source, 1, "fixed-v5")
    source["layout"] = {"page_margin": "narrow"}
    with pytest.raises(ValueError, match="original page margin"):
        layout_replay(before, after, source, 2, "fixed-v5")


@pytest.fixture(scope="module")
def compiled_pair(tmp_path_factory):
    before, after, source = fixture()
    target = layout_replay(before, after, source, 2, "fixed-v5")
    directory = tmp_path_factory.mktemp("layout-compiled")
    layouts, pdfs, views = [], [], []
    for index, generated in enumerate([source, target]):
        folder = directory / str(index)
        folder.mkdir()
        (folder / "manuscript.tex").write_text(StudioService._latex(generated, []), encoding="utf8")
        command = shutil.which("xelatex")
        assert command, "Meaningful layout acceptance requires the actual TeX compiler"
        result = subprocess.run([command, "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", "manuscript.tex"],
            cwd=folder, env={**os.environ, "openin_any": "p", "openout_any": "p"}, capture_output=True, timeout=90, check=False)
        assert result.returncode == 0, result.stdout[-2000:]
        pdf = folder / "manuscript.pdf"
        layout = extract_layout(pdf, folder / "layout.xhtml")
        assert layout["status"] == "EXTRACTED"
        layouts.append(layout)
        pdfs.append(pdf)
        views.append(generated_view({"manuscript_version_id": f"v{index+5}", "manuscript_id": "layout-fixture",
                                    "version": index+5, "content": StudioService._generated_markdown(generated)}, generated, []))
    return before, after, source, target, layouts, pdfs, views, directory


def evidence(pair, **overrides):
    before, after, _, _, layouts, _, views, _ = pair
    arguments = {"baseline_document": before, "target_document": after, "baseline": views[0], "target": views[1],
                 "old_layout": layouts[0], "new_layout": layouts[1]}
    arguments.update(overrides)
    return layout_only_evidence(before, after, **arguments)


def test_actual_compiled_margin_change_moves_final_page_line_geometry_without_new_text(compiled_pair):
    row = evidence(compiled_pair)
    assert row and row["status"] == "LAYOUT_ONLY" and row["change_kind"] == "PRESENTATION"
    assert row["changed_text"] == "" and not row["supports_scientific_text_modification"]
    assert row["baseline_boxes"] != row["boxes"] and row["final_page"] >= 1
    before, after, _, _, _layouts, pdfs, views, directory = compiled_pair
    assert views[0]["content"] == views[1]["content"]
    assert hashlib.sha256(pdfs[0].read_bytes()).hexdigest() == row["baseline_pdf_sha256"]
    changes = [{"comment_id": "opinion", "changes": [{"change_id": "layout-edit", "before_json": json.dumps(before), "after_json": json.dumps(after)}]}]
    summary = write_mapping(directory / "locations.csv", changes, target=views[1], baseline=views[0],
                            target_document=after, baseline_document=before, pdf=pdfs[1], baseline_pdf=pdfs[0])
    assert summary["layout_only_rows"] == 1 and summary["unknown_or_unattributed_rows"] == 0
    report = json.loads((directory / "change-realization-map.json").read_text(encoding="utf8"))
    assert report["rows"][0]["status"] == "LAYOUT_ONLY" and not report["scientific_acceptance"]


@pytest.mark.parametrize("mutation", ["unknown_baseline", "no_geometry_change", "missing_pdf", "changed_source", "changed_material", "changed_text", "changed_realization", "superseded", "unfrozen_layout"])
def test_actual_layout_type_is_not_inferred_from_unchanged_thoughts_or_pdf_hash_alone(compiled_pair, mutation):
    before, _after, _, _, layouts, _, views, _ = compiled_pair
    changed = deepcopy(views[1])
    arguments = {}
    if mutation == "unknown_baseline":
        arguments["baseline_document"] = None
    elif mutation == "no_geometry_change":
        arguments["new_layout"] = layouts[0]
    elif mutation == "missing_pdf":
        arguments["old_layout"] = None
    elif mutation == "changed_source":
        changed["references"] = [{"evidence_id": "different-source", "title": "Same display label"}]
    elif mutation == "changed_material":
        changed["blocks"][-1]["assets"] = [{"asset_id": "different-original", "sha256": "not-original"}]
    elif mutation == "changed_text":
        changed["content"] += "Changed body text."
    elif mutation == "changed_realization":
        changed["realizations"] = [{"model_call_id": "new-model-call"}]
    elif mutation == "superseded":
        arguments["target_document"] = before
    else:
        changed.pop("layout")
    arguments["target"] = changed
    assert evidence(compiled_pair, **arguments) is None


def test_layout_evidence_cannot_prove_scientific_body_modification(compiled_pair):
    row = evidence(compiled_pair)
    assert row
    row["evidence_id"] = "layout-only"
    context = {"state": {"archived_at": None, "response_text": "We changed the science.", "author_decision": "Fixture",
        "generated_version_id": "v6", "current_author_revision": 2, "generated_input_revision": 2},
        "baseline_to_target_diff": "Force a nonempty diff to exercise the evidence-type guard", "evidence": [row]}
    claim = {"start": 0, "end": len("We changed the science.".encode("utf-16-le")) // 2, "text": "We changed the science.", "offset_unit": "utf16", "evidence_ids": ["layout-only"]}
    with pytest.raises(ValueError, match="cannot prove"):
        validate_claims(context, "MODIFIED", [claim], True)


def test_original_save_revision_idempotency_undo_redo_and_invalid_layout_guards(tmp_path):
    service, _, ms = create_studio(tmp_path)
    before = complete_document(service.get_workspace(ms))
    service.save_document(ms, base_revision=0, operation_id="initial-layout-base", document=before)
    after = deepcopy(before)
    after["layout"] = {"page_margin": "narrow"}
    first = service.save_document(ms, base_revision=1, operation_id="layout-only-1", document=after, operation_kind="LAYOUT")
    assert first["document_revision"] == 2
    assert service.save_document(ms, base_revision=1, operation_id="layout-only-1", document=after, operation_kind="LAYOUT")["idempotent_replay"]
    with pytest.raises(RevisionConflictError):
        service.save_document(ms, base_revision=1, operation_id="layout-conflicting", document=before)
    service.save_document(ms, base_revision=2, operation_id="layout-undo-1", document=before, operation_kind="UNDO")
    assert "layout" not in service.get_workspace(ms)["document"]
    service.save_document(ms, base_revision=3, operation_id="layout-redo-1", document=after, operation_kind="REDO")
    assert service.get_workspace(ms)["document"]["layout"] == {"page_margin": "narrow"}
    invalid = deepcopy(after)
    invalid["layout"] = {"page_margin": "arbitrary TeX"}
    with pytest.raises(ValueError):
        service.save_document(ms, base_revision=4, operation_id="layout-invalid-1", document=invalid)
    assert service.get_workspace(ms)["document_revision"] == 4
    assert service.get_workspace(ms)["latest_job"] is None
