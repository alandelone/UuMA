"""Explicit software source levels, scoped adoption and append-only compensation."""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy

import pytest
from rstv4.database import initialize_catalog, transaction
from rstv4.fieldkg import digest
from rstv4.models import TrackFirstEvidenceInput
from rstv4.parser_quality import normalize_mineru_result
from rstv4.research_views import skeleton_source
from rstv4.studio_templates import apply_structure, empty_sections
from test_acquisition_deep_read import setup
from test_parser_quality import _result
from test_studio_structure import grouped_fixture


def source_fixture(root, *, levels=(1, 2, 3, 2, 1), prefix=False):
    acquisition, collection_id, db, _ = setup(root)
    blocks = []
    if prefix:
        blocks.append({"text": "SOFTWARE pre-heading abstract", "block_type": "TEXT",
                       "page_number": 1, "section": None, "location": {}})
    for index, level in enumerate(levels):
        title = "Repeated heading" if index in (1, 3) else f"Source heading {index}"
        blocks.extend([
            {"text": title, "block_type": "HEADING", "page_number": index + 1,
             "section": title, "location": {"heading_level": level, "content_index": index * 2,
                                             "bbox": [1, 2, 3, 4]}},
            {"text": f"SOURCE_BODY_{index}_NEVER_AUTHOR_TEXT", "block_type": "TEXT",
             "page_number": index + 1, "section": title, "location": {"content_index": index * 2 + 1}},
        ])
    parsed = acquisition.publish_parse_result(
        collection_id, "existing", "existing-file", parser_name="SOFTWARE_EXPLICIT_LEVELS",
        parser_version="1", config={}, manifest={"software_only": True}, blocks=blocks, references=[],
    )
    with transaction(db) as conn:
        units = [{"block_id": row["block_id"], "page_number": row["page_number"],
                  "section": row["section"], "raw_text": row["text"],
                  "layer1": {"triplets": []}, "layer2": {"discourse_relation": "Context"},
                  "layer3": {"intent": "Software_Intent"}, "layer4": {"role": "Software_Test"}}
                 for row in conn.execute("SELECT * FROM document_blocks WHERE parse_run_id=? ORDER BY sequence",
                                         (parsed["parse_run_id"],)) if row["block_type"] != "HEADING"]
    return acquisition, db, parsed, units


def published_fixture(root, **kwargs):
    acquisition, db, parsed, units = source_fixture(root, **kwargs)
    published = acquisition.publish_skeleton_result(parsed["parse_run_id"], units, model_name="TEST_FIXTURE")
    service, manuscript_id, original = grouped_fixture(root)
    manuscript = service.track_service.get_manuscript(manuscript_id)
    service.track_service.add_evidence(TrackFirstEvidenceInput(
        track_id=manuscript["track_id"], paper_id="existing", statement="Software source fixture",
        excerpt="Synthetic structural test", location="fixture page 1", confidence=0.8,
        relation="SUPPORTS", extractor_model="TEST_FIXTURE", prompt_version="TEST_FIXTURE",
    ))
    preview = service.preview_template(manuscript_id, published["skeleton_id"])
    return service, manuscript_id, original, preview, acquisition, db, parsed, units, published


def rows(db):
    with sqlite3.connect(db) as conn:
        return {r[0]: conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid').fetchall()
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}


def test_normalizer_retains_exact_explicit_heading_levels_and_locations(tmp_path):
    items = [{"type": "text", "text_level": level, "text": f"Heading {level}",
              "page_idx": level - 1, "bbox": [1, 2, 3, 4]} for level in (1, 2, 3)]
    items.append({"type": "text", "text": "Software body for parser quality. " * 5, "page_idx": 2})
    parsed = normalize_mineru_result(_result(tmp_path, items))
    assert [b["location"]["heading_level"] for b in parsed["blocks"][:3]] == [1, 2, 3]
    assert parsed["blocks"][2]["location"]["bbox"] == [1, 2, 3, 4]
    assert "heading_level" not in parsed["blocks"][-1]["location"]


def test_partial_adoption_preserves_ancestors_repeated_titles_and_source_locations(tmp_path):
    service, manuscript_id, original, preview, _, db, _, _, _ = published_fixture(tmp_path)
    before = rows(db)
    assert [s["depth"] for s in preview["sections"]] == [0, 1, 2, 1, 0]
    assert preview["sections"][1]["title"] == preview["sections"][3]["title"]
    assert preview["sections"][1]["source_section_id"] != preview["sections"][3]["source_section_id"]
    selected = preview["sections"][2]["paragraphs"][0]["unit_id"]
    request = {"base_revision": 1, "operation_id": "source-partial", "skeleton_id": preview["skeleton_id"],
               "source_sha256": preview["source_sha256"], "selected_unit_ids": [selected],
               "scope_type": "paper", "scope_id": manuscript_id, "mode": "INSERT",
               "replace_confirmed": False, "comment_ids": []}
    saved = service.apply_template(manuscript_id, request)
    added = saved["document"]["sections"][len(original["sections"]):]
    assert len(added) == 3
    assert [len(s["paragraphs"]) for s in added] == [0, 0, 1]
    assert added[1]["parent_section_id"] == added[0]["id"]
    assert added[2]["parent_section_id"] == added[1]["id"]
    p = added[2]["paragraphs"][0]
    assert p["template_source"]["source_path"] == [s["title"] for s in added]
    assert p["template_source"]["page_number"] == 3
    assert p["template_source"]["heading_location"]["bbox"] == [1, 2, 3, 4]
    assert p["intents"][0]["template_source"] == p["template_source"]
    assert p["intents"][0]["thoughts"] == []
    assert "SOURCE_BODY" not in json.dumps(saved["document"])
    assert saved["document"]["sections"][:len(original["sections"])] == original["sections"]
    service.save_document(manuscript_id, base_revision=2, operation_id="source-undo",
                          operation_kind="UNDO", document=original)
    assert service.get_workspace(manuscript_id)["document"] == original
    assert service.get_document_revision(manuscript_id, 2)["document"] == saved["document"]
    after = rows(db)
    for table in ("skeleton_source_outlines", "skeleton_units", "paper_skeletons", "approval_grants",
                  "acquisition_model_call_events", "studio_model_calls", "studio_jobs"):
        assert after[table] == before[table]
    assert service.apply_template(manuscript_id, request)["idempotent_replay"]


def test_nested_section_target_attaches_only_template_roots(tmp_path):
    _, _, original, preview, *_ = published_fixture(tmp_path)
    original["sections"] = [{"id": "parent", "title": "Author parent", "role": "", "paragraphs": []},
                            {**original["sections"][0], "parent_section_id": "parent"}]
    selected = [p["unit_id"] for s in preview["sections"] for p in s["paragraphs"]]
    sections = empty_sections(preview, selected)
    before = deepcopy(sections)
    for mode in ("INSERT", "REPLACE"):
        saved = apply_structure(original, sections, "section", original["sections"][1]["id"], mode)
        added = [s for s in saved["sections"] if s["id"] in {v["id"] for v in sections}]
        assert added[0]["parent_section_id"] == added[4]["parent_section_id"] == "parent"
        assert added[1]["parent_section_id"] == added[0]["id"]
        assert added[2]["parent_section_id"] == added[1]["id"]
        assert added[3]["parent_section_id"] == added[0]["id"]
        assert sections == before


@pytest.mark.parametrize("levels", [(2,), (1, 3), (1, True), (1, "2"), (1, 6), (1, None)])
def test_ambiguous_or_unsupported_source_levels_reject_atomic_publication(tmp_path, levels):
    acquisition, db, parsed, units = source_fixture(tmp_path, levels=levels)
    before = rows(db)
    with pytest.raises(ValueError, match="heading"):
        acquisition.publish_skeleton_result(parsed["parse_run_id"], units, model_name="TEST_FIXTURE")
    assert rows(db) == before


@pytest.mark.parametrize("defect", ["foreign_block", "duplicate", "reverse", "text", "page", "section"])
def test_foreign_or_changed_unit_rejects_without_partial_writes(tmp_path, defect):
    acquisition, db, parsed, units = source_fixture(tmp_path)
    if defect == "foreign_block":
        units[0]["block_id"] = "foreign"
    elif defect == "duplicate":
        units[1] = deepcopy(units[0])
    elif defect == "reverse":
        units.reverse()
    else:
        units[0][{"text": "raw_text", "page": "page_number", "section": "section"}[defect]] = "changed"
    before = rows(db)
    with pytest.raises(ValueError, match="Outline"):
        acquisition.publish_skeleton_result(parsed["parse_run_id"], units, model_name="TEST_FIXTURE")
    assert rows(db) == before


@pytest.mark.parametrize("defect", ["cycle", "foreign_parse", "digest", "block", "unit_order", "missing_heading_level"])
def test_tampered_outline_or_parse_blocks_new_adoption_and_preserves_author_revision(tmp_path, defect):
    service, manuscript_id, original, preview, _, db, _, _, _ = published_fixture(tmp_path)
    with transaction(db) as conn:
        row = conn.execute("SELECT * FROM skeleton_source_outlines").fetchone()
        outline = json.loads(row["outline_json"])
        if defect == "cycle":
            outline["sections"][0]["parent_source_section_id"] = outline["sections"][2]["source_section_id"]
        elif defect == "foreign_parse":
            outline["parse_run_id"] = "foreign"
        elif defect == "block":
            outline["unit_assignments"][0]["block_id"] = "foreign"
        elif defect == "unit_order":
            outline["unit_assignments"].reverse()
        elif defect == "missing_heading_level":
            conn.execute("UPDATE document_blocks SET location_json='{}' WHERE block_type='HEADING'")
        conn.execute("UPDATE skeleton_source_outlines SET outline_json=?,content_digest=?",
                     (json.dumps(outline), "changed" if defect == "digest" else digest(outline)))
    before = rows(db)
    with pytest.raises(ValueError, match="[Oo]utline"):
        service.preview_template(manuscript_id, preview["skeleton_id"])
    assert rows(db) == before
    assert service.get_workspace(manuscript_id)["document"] == original


def test_unsectioned_prefix_is_explicit_root_and_not_guessed_from_title(tmp_path):
    *_, preview, acquisition, db, parsed, units, published = published_fixture(tmp_path, prefix=True)
    assert preview["sections"][0]["source_path"] == []
    assert preview["sections"][0]["parent_source_section_id"] is None
    assert preview["sections"][1]["parent_source_section_id"] is None
    before = rows(db)
    assert acquisition.publish_skeleton_result(parsed["parse_run_id"], units, model_name="TEST_FIXTURE") == published
    assert rows(db) == before


def test_legacy_source_identity_and_all_rows_survive_additive_migration(tmp_path):
    acquisition, db, parsed, units = source_fixture(tmp_path)
    with transaction(db) as conn:
        conn.execute("UPDATE document_blocks SET location_json='{}' WHERE block_type='HEADING'")
    published = acquisition.publish_skeleton_result(parsed["parse_run_id"], units, model_name="TEST_FIXTURE")
    with transaction(db) as conn:
        old = skeleton_source(conn, published["skeleton_id"])
        assert "source_outline" not in old
        conn.execute("DROP TABLE skeleton_source_outlines")
        conn.execute("UPDATE schema_version SET version=12 WHERE component='catalog'")
    before = rows(db)
    with transaction(db) as conn:
        assert skeleton_source(conn, published["skeleton_id"]) == old
    initialize_catalog(db)
    after = rows(db)
    assert all(after[table] == saved for table, saved in before.items() if table != "schema_version")
    assert after["skeleton_source_outlines"] == []
    assert db.with_suffix(".pre-v14.bak").exists()
    assert next(row for row in after["schema_version"] if row[0] == "catalog")[1] == 14
    assert not after["studio_submission_bindings"]
    with transaction(db) as conn:
        assert skeleton_source(conn, published["skeleton_id"]) == old
