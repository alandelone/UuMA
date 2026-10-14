"""Software fixtures only: adoption protects author data and creates no science approval."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_studio_structure import grouped_fixture
from test_track_first_fieldkg import make_paperpool

from rstv4.models import FieldKGBuildInput, TrackFirstEvidenceInput
from rstv4.service import RevisionConflictError
from rstv4.studio import DocumentValidationError
from rstv4.studio_api import create_app


def fixture(root: Path):
    service, manuscript_id, document = grouped_fixture(root)
    manuscript = service.track_service.get_manuscript(manuscript_id)
    with sqlite3.connect(service.db_path) as conn:
        field_id = conn.execute("SELECT field_id FROM research_tracks WHERE track_id=?",
                                (manuscript["track_id"],)).fetchone()[0]
    pool = root / "template-source-fixture.db"
    make_paperpool(pool)
    build = service.track_service.create_fieldkg_build(FieldKGBuildInput(field_id=field_id))
    service.track_service.import_paperpool(build["build_id"], str(pool), [])
    with sqlite3.connect(service.db_path) as conn, conn:
        source = conn.execute("SELECT skeleton_id,paper_version_id FROM paper_skeletons").fetchone()
        paper = conn.execute("SELECT paper_id FROM paper_versions WHERE paper_version_id=?",
                             (source[1],)).fetchone()[0]
        unit = conn.execute("SELECT * FROM skeleton_units WHERE skeleton_id=?", (source[0],)).fetchone()
        columns = [row[1] for row in conn.execute("PRAGMA table_info(skeleton_units)")]
        second = dict(zip(columns, unit, strict=True))
        second.update(unit_id="template-unit-2", seq_idx=2, section="Discussion",
                      raw_text="MODEL SOURCE BODY MUST NEVER BECOME AUTHOR THOUGHT",
                      layer3_json=json.dumps({"rationale": "not a label", "intent": "Claim"}))
        conn.execute(f"INSERT INTO skeleton_units({','.join(columns)}) "
                     f"VALUES({','.join('?' for _ in columns)})", tuple(second.values()))
    service.track_service.add_evidence(TrackFirstEvidenceInput(
        track_id=manuscript["track_id"], paper_id=paper, statement="Template software fixture",
        excerpt="Software source", location="page 1", confidence=0.8, relation="SUPPORTS",
        extractor_model="TEST_FIXTURE", prompt_version="TEST_FIXTURE",
    ))
    preview = service.preview_template(manuscript_id, source[0])
    request = {"base_revision": 1, "operation_id": "template-operation-fixture",
               "skeleton_id": source[0], "source_sha256": preview["source_sha256"],
               "selected_unit_ids": [p["unit_id"] for s in preview["sections"] for p in s["paragraphs"]],
               "scope_type": "paper", "scope_id": manuscript_id, "mode": "INSERT",
               "replace_confirmed": False, "comment_ids": []}
    return service, manuscript_id, document, preview, request


@pytest.mark.parametrize("scope", ["paper", "section", "paragraph", "intent"])
@pytest.mark.parametrize("mode", ["INSERT", "REPLACE"])
def test_template_scope_is_atomic_empty_and_preserves_original_data(tmp_path, scope, mode):
    service, manuscript_id, original, preview, request = fixture(tmp_path)
    first = original["sections"][0]
    paragraph = first["paragraphs"][0]
    request.update(scope_type=scope, mode=mode, replace_confirmed=mode == "REPLACE",
                   scope_id={"paper": manuscript_id, "section": first["id"],
                             "paragraph": paragraph["id"],
                             "intent": paragraph["intents"][0]["id"]}[scope])
    with TestClient(create_app(tmp_path)) as client:
        path = f"/api/manuscripts/{manuscript_id}/template-adoption"
        response = client.post(path, json=request)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["document_revision"] == 2
        assert not result["idempotent_replay"]
        saved = result["document"]
        thoughts = lambda doc: {t["id"]: t for s in doc["sections"] for p in s["paragraphs"]
                                for i in p["intents"] for t in i["thoughts"]}
        assert thoughts(saved) == thoughts(original)
        for old in original["sections"]:
            for p in old["paragraphs"]:
                current = next(x for s in saved["sections"] for x in s["paragraphs"] if x["id"] == p["id"])
                assert current["asset_ids"] == p["asset_ids"]
                assert current.get("formulas") == p.get("formulas")
        assert "MODEL SOURCE BODY" not in json.dumps(saved)
        assert "not a label" not in json.dumps(saved)
        assert any(i["label"] == "Claim" and i["thoughts"] == []
                   for s in saved["sections"] for p in s["paragraphs"] for i in p["intents"])
        assert [s["title"] for s in preview["sections"]] == ["Introduction", "Discussion"]
        if mode == "REPLACE":
            assert any(s.get("placement_status") == "UNPLACED" for s in saved["sections"])
            with pytest.raises(DocumentValidationError) as caught:
                service._check_generate_ready(manuscript_id, saved)
            assert any("unplaced" in i["message"] for i in caught.value.issues)
        else:
            assert not any(s.get("placement_status") for s in saved["sections"])
        digest = hashlib.sha256(service.db_path.read_bytes()).hexdigest()
        replay = client.post(path, json=request)
        assert replay.status_code == 200 and replay.json()["idempotent_replay"]
        assert replay.json()["template_instance"] == result["template_instance"]
        assert hashlib.sha256(service.db_path.read_bytes()).hexdigest() == digest
        assert service.get_document_revision(manuscript_id, 1)["document"] == original
        service.save_document(manuscript_id, base_revision=2, operation_id="template-compensation",
                              operation_kind="UNDO", document=original)
        assert service.get_workspace(manuscript_id)["document"] == original
        assert service.get_document_revision(manuscript_id, 2)["document"] == saved
        after_undo = service.db_path.read_bytes()
        original_retry = client.post(path, json=request).json()
        assert original_retry["idempotent_replay"]
        assert original_retry["document_revision"] == 3
        assert original_retry["operation"]["resulting_revision"] == 2
        assert original_retry["document"] == original
        assert service.db_path.read_bytes() == after_undo


@pytest.mark.parametrize("defect", ["unconfirmed", "foreign_unit", "duplicate_unit", "foreign_scope",
                                  "stale_source", "stale_revision", "withdrawn_source"])
def test_invalid_template_request_changes_no_database_bytes(tmp_path, defect):
    service, manuscript_id, _, _, request = fixture(tmp_path)
    if defect == "unconfirmed":
        request["mode"] = "REPLACE"
    elif defect == "foreign_unit":
        request["selected_unit_ids"] = ["foreign-unit"]
    elif defect == "duplicate_unit":
        request["selected_unit_ids"] *= 2
    elif defect == "foreign_scope":
        request.update(scope_type="section", scope_id="another-ms-section")
    elif defect == "stale_revision":
        request["base_revision"] = 0
    elif defect in {"stale_source", "withdrawn_source"}:
        with sqlite3.connect(service.db_path) as conn, conn:
            if defect == "stale_source":
                conn.execute("UPDATE skeleton_units SET layer4='Changed' WHERE unit_id='template-unit-2'")
            else:
                conn.execute("UPDATE paper_versions SET source_json=?",
                             (json.dumps({"file_version_id": "missing-withdrawn-file"}),))
    with TestClient(create_app(tmp_path)) as client:
        digest = hashlib.sha256(service.db_path.read_bytes()).hexdigest()
        response = client.post(f"/api/manuscripts/{manuscript_id}/template-adoption", json=request)
        assert response.status_code in {409, 422}, response.text
        assert hashlib.sha256(service.db_path.read_bytes()).hexdigest() == digest


def test_partial_template_double_submit_and_changed_retry(tmp_path):
    service, manuscript_id, _, _, request = fixture(tmp_path)
    request["selected_unit_ids"] = ["template-unit-2"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.apply_template(manuscript_id, request), range(2)))
    assert sorted(r["idempotent_replay"] for r in results) == [False, True]
    assert all(r["document_revision"] == 2 for r in results)
    with sqlite3.connect(service.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM studio_template_instances").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM studio_jobs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM studio_model_calls").fetchone()[0] == 0
    altered = deepcopy(request)
    altered["selected_unit_ids"] = ["changed-source-selection"]
    before = service.db_path.read_bytes()
    with pytest.raises(RevisionConflictError):
        service.apply_template(manuscript_id, altered)
    assert service.db_path.read_bytes() == before
    assert service.get_workspace(manuscript_id)["document"]["sections"][-1]["title"] == "Discussion"


def test_adoption_record_failure_rolls_back_document_and_operation(tmp_path, monkeypatch):
    service, manuscript_id, _, _, request = fixture(tmp_path)
    save = service.save_document

    def interrupted(*args, **kwargs):
        saved = save(*args, **kwargs)
        assert saved["document_revision"] == 2
        raise RuntimeError("software fixture failure after document writes")

    monkeypatch.setattr(service, "save_document", interrupted)
    before = service.db_path.read_bytes()
    with pytest.raises(RuntimeError, match="after document writes"):
        service.apply_template(manuscript_id, request)
    assert service.db_path.read_bytes() == before
    assert service.get_workspace(manuscript_id)["document_revision"] == 1


def test_withdrawal_blocks_new_adoption_but_replay_reads_existing_result(tmp_path):
    service, manuscript_id, _, _, request = fixture(tmp_path)
    original = service.apply_template(manuscript_id, request)
    with sqlite3.connect(service.db_path) as conn, conn:
        conn.execute("UPDATE paper_versions SET source_json=?",
                     (json.dumps({"file_version_id": "withdrawn-file"}),))
    before = service.db_path.read_bytes()
    replay = service.apply_template(manuscript_id, request)
    assert replay["idempotent_replay"] and replay["template_instance"] == original["template_instance"]
    assert service.db_path.read_bytes() == before
    next_request = {**request, "operation_id": "template-after-withdrawal", "base_revision": 2}
    with pytest.raises(ValueError, match="unavailable"):
        service.apply_template(manuscript_id, next_request)
    assert service.db_path.read_bytes() == before


def test_original_operation_cannot_be_reused_by_another_manuscript(tmp_path):
    service, manuscript_id, _, _, request = fixture(tmp_path)
    service.apply_template(manuscript_id, request)
    other = service.create_manuscript(
        service.track_service.get_manuscript(manuscript_id)["track_id"], "Other fixture manuscript"
    )["manuscript"]["manuscript_id"]
    before = service.db_path.read_bytes()
    with pytest.raises(RevisionConflictError):
        service.apply_template(other, {**request, "scope_id": other})
    assert service.db_path.read_bytes() == before


def test_preview_is_read_only_and_does_not_copy_source_prose(tmp_path):
    service, manuscript_id, _, preview, _ = fixture(tmp_path)
    before = service.db_path.read_bytes()
    assert service.preview_template(manuscript_id, preview["skeleton_id"]) == preview
    assert service.db_path.read_bytes() == before
    assert "MODEL SOURCE BODY" not in json.dumps(preview)
    assert preview["sections"][1]["paragraphs"][0]["intent"] == "Claim"
