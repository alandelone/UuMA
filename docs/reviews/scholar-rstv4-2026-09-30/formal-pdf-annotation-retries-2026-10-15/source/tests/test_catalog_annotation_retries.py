from __future__ import annotations

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from test_catalog_web import seed_catalog

from rstv4.catalog_annotations import (
    ReviewAnnotationInput,
    find_review_annotation_replay,
    record_review_annotation,
)
from rstv4.catalog_web import create_app


@pytest.fixture
def catalog(tmp_path: Path) -> Path:
    seed_catalog(tmp_path)
    return tmp_path / "data" / "catalog.db"


def snapshot(path: Path) -> dict[str, list[tuple]]:
    with sqlite3.connect(path) as conn:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {name: conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall()
                for (name,) in tables}


def title_input(**changes: object) -> ReviewAnnotationInput:
    payload = {
        "submission_id": "selection-original", "field_name": "TITLE", "decision": "FOUND",
        "page_number": 1, "word_start": 0, "word_end": 3, "comment": "Original note",
        "expected_annotation_id": "",
    }
    payload.update(changes)
    return ReviewAnnotationInput(**payload)


WORDS = [{"text": text} for text in ["Solar", "Energy", "B", "Revised", "DOI", "10.1234/b"]]


@pytest.mark.parametrize("changes", [
    {"field_name": "DOI"},
    {"field_name": "PDF", "decision": "REOPEN", "page_number": None,
     "word_start": None, "word_end": None},
    {"page_number": 2}, {"word_start": 1}, {"word_end": 2},
    {"comment": "A different note"},
    {"expected_annotation_id": "another-head"},
])
def test_reused_key_rejects_changed_payload_without_mutation(catalog: Path, changes: dict) -> None:
    original = record_review_annotation(catalog, "f2", title_input(), WORDS)
    before = snapshot(catalog)
    with pytest.raises(ValueError, match="Submission ID"):
        record_review_annotation(catalog, "f2", title_input(**changes), WORDS)
    assert snapshot(catalog) == before
    assert record_review_annotation(catalog, "f2", title_input(), None) == original


def test_exact_retry_survives_reversal_and_completed_case(catalog: Path) -> None:
    original = record_review_annotation(catalog, "f2", title_input(), WORDS)
    record_review_annotation(catalog, "f2", ReviewAnnotationInput(
        submission_id="mark-wrong-pdf", field_name="PDF", decision="WRONG_PDF",
        expected_annotation_id="",
    ), None)
    with sqlite3.connect(catalog) as conn:
        conn.execute("UPDATE source_file_versions SET identity_status='MATCHED' WHERE file_version_id='f2'")
    before = snapshot(catalog)
    assert record_review_annotation(catalog, "f2", title_input(), None) == original
    assert snapshot(catalog) == before


def test_replay_lookup_is_read_only_and_detects_key_collision(catalog: Path, tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.db"
    assert find_review_annotation_replay(missing, "f2", title_input()) is None
    assert not missing.exists()
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    assert find_review_annotation_replay(empty, "f2", title_input()) is None
    assert snapshot(empty) == {}
    before = snapshot(catalog)
    assert find_review_annotation_replay(catalog, "f2", title_input()) is None
    assert snapshot(catalog) == before
    original = record_review_annotation(catalog, "f2", title_input(), WORDS)
    before = snapshot(catalog)
    assert find_review_annotation_replay(catalog, "f2", title_input()) == original
    with pytest.raises(ValueError, match="Submission ID"):
        find_review_annotation_replay(catalog, "another-case", title_input())
    assert snapshot(catalog) == before


@pytest.mark.parametrize("expected", ["", "missing-head"])
def test_new_write_rejects_outdated_head_without_mutation(catalog: Path, expected: str) -> None:
    record_review_annotation(catalog, "f2", title_input(), WORDS)
    before = snapshot(catalog)
    with pytest.raises(ValueError, match="changed"):
        record_review_annotation(catalog, "f2", title_input(
            submission_id="selection-newer", expected_annotation_id=expected,
            comment="This must not overwrite the selected passage",
        ), WORDS)
    assert snapshot(catalog) == before


def test_matching_head_appends_and_old_comment_cannot_restore_old_selection(catalog: Path) -> None:
    original = record_review_annotation(catalog, "f2", title_input(), WORDS)
    newer = record_review_annotation(catalog, "f2", title_input(
        submission_id="selection-newer", word_end=2, comment="New passage",
        expected_annotation_id=original["annotation_id"],
    ), WORDS)
    assert newer["supersedes_annotation_id"] == original["annotation_id"]
    before = snapshot(catalog)
    with pytest.raises(ValueError, match="changed"):
        record_review_annotation(catalog, "f2", title_input(
            submission_id="stale-note-save", comment="Late original comment",
            expected_annotation_id=original["annotation_id"],
        ), WORDS)
    assert snapshot(catalog) == before
    assert record_review_annotation(catalog, "f2", title_input(
        submission_id="selection-newer", word_end=2, comment="New passage",
        expected_annotation_id=original["annotation_id"],
    ), None) == newer
    assert snapshot(catalog) == before
    with sqlite3.connect(catalog) as conn:
        assert conn.execute("SELECT title FROM papers WHERE paper_id='p2'").fetchone()[0] == "Solar Energy B"


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_requests_serialize_key_and_head(catalog: Path, same_key: bool) -> None:
    barrier = Barrier(2)

    def write(index: int) -> tuple[str, object]:
        annotation = title_input(submission_id="concurrent-same" if same_key else f"concurrent-{index}")
        barrier.wait(timeout=10)
        try:
            return "saved", record_review_annotation(catalog, "f2", annotation, WORDS)
        except ValueError as exc:
            return "conflict", str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, (1, 2)))
    saved = [row for status, row in results if status == "saved"]
    assert len(saved) == (2 if same_key else 1)
    if same_key:
        assert saved[0] == saved[1]
    else:
        assert [status for status, _ in results].count("conflict") == 1
    with sqlite3.connect(catalog) as conn:
        assert conn.execute("SELECT COUNT(*) FROM catalog_review_annotations").fetchone()[0] == 1


def test_legacy_inputs_and_absent_wrong_reopen_preserve_reversal(catalog: Path) -> None:
    original = record_review_annotation(catalog, "f2", title_input(), WORDS)
    doi = record_review_annotation(catalog, "f2", ReviewAnnotationInput(
        submission_id="legacy-found-doi", field_name="DOI", decision="FOUND",
        page_number=1, word_start=5, word_end=5,
    ), WORDS)
    absent = record_review_annotation(catalog, "f2", ReviewAnnotationInput(
        submission_id="new-absent-doi", field_name="DOI", decision="ABSENT",
        expected_annotation_id=doi["annotation_id"],
    ), None)
    assert absent["value_after"] == "10.1/b"
    wrong = record_review_annotation(catalog, "f2", ReviewAnnotationInput(
        submission_id="new-wrong-pdf", field_name="PDF", decision="WRONG_PDF",
        expected_annotation_id="",
    ), None)
    reopened = record_review_annotation(catalog, "f2", ReviewAnnotationInput(
        submission_id="new-reopen-pdf", field_name="PDF", decision="REOPEN",
        expected_annotation_id=wrong["annotation_id"],
    ), None)
    assert reopened["supersedes_annotation_id"] == wrong["annotation_id"]
    with sqlite3.connect(catalog) as conn:
        assert conn.execute("SELECT title,doi FROM papers WHERE paper_id='p2'").fetchone() == (
            "Solar Energy B", "10.1/b",
        )
        assert conn.execute("SELECT 1 FROM catalog_review_annotations WHERE annotation_id=?",
                            (original["annotation_id"],)).fetchone() is not None
        assert conn.execute("SELECT COUNT(*) FROM catalog_review_annotations").fetchone()[0] == 6


def test_http_conflict_and_stale_head_leave_catalog_unchanged(catalog: Path) -> None:
    with TestClient(create_app(catalog.parent.parent)) as client:
        words = client.get("/api/catalog/files/f2/pages/1/text").json()["words"]
        assert [word["text"] for word in words[:4]] == [word["text"] for word in WORDS[:4]]
        payload = title_input().model_dump()
        first = client.post("/api/catalog/review/cases/f2/annotations", json=payload)
        assert first.status_code == 201
        before = snapshot(catalog)
        for changes in ({"comment": "Changed intent"},
                        {"submission_id": "new-stale-http", "expected_annotation_id": ""}):
            conflict = client.post("/api/catalog/review/cases/f2/annotations", json={**payload, **changes})
            assert conflict.status_code == 409
            assert snapshot(catalog) == before
        replay = client.post("/api/catalog/review/cases/f2/annotations", json=payload)
        assert replay.status_code == 201
        assert replay.json()["annotation_id"] == first.json()["annotation_id"]
        assert snapshot(catalog) == before


def test_http_retry_recognized_before_missing_pdf_or_changed_page(catalog: Path) -> None:
    with TestClient(create_app(catalog.parent.parent)) as client:
        payload = title_input().model_dump()
        original = client.post("/api/catalog/review/cases/f2/annotations", json=payload)
        assert original.status_code == 201
        with sqlite3.connect(catalog) as conn:
            source = Path(conn.execute(
                "SELECT storage_path FROM source_file_versions WHERE file_version_id='f2'",
            ).fetchone()[0])
        source.rename(source.with_suffix(".temporarily-missing"))
        before = snapshot(catalog)
        retry = client.post("/api/catalog/review/cases/f2/annotations", json=payload)
        assert retry.status_code == 201
        assert retry.json() == original.json()
        conflict = client.post("/api/catalog/review/cases/f2/annotations", json={
            **payload, "page_number": 999,
        })
        assert conflict.status_code == 409
        fresh = client.post("/api/catalog/review/cases/f2/annotations", json={
            **payload, "submission_id": "new-source-missing",
            "expected_annotation_id": original.json()["annotation_id"],
        })
        assert fresh.status_code == 410
        assert fresh.json()["detail"] == "PDF file is unavailable"
        assert snapshot(catalog) == before


def test_comment_cannot_restore_value_changed_by_another_file(catalog: Path) -> None:
    first = record_review_annotation(catalog, "f2", title_input(), WORDS)
    original = catalog.parent.parent / "sample.pdf"
    other = catalog.parent.parent / "another-version.pdf"
    other.write_bytes(original.read_bytes() + b"\n% software second file version\n")
    with sqlite3.connect(catalog) as conn:
        conn.execute("""INSERT INTO source_file_versions SELECT 'other-file',paper_id,?,
                     ?,mime_type,?,acquisition_method,source_url,
                     identity_status,validation_json,created_at FROM source_file_versions
                     WHERE file_version_id='f2'""", (
                         hashlib.sha256(other.read_bytes()).hexdigest(),
                         other.stat().st_size, str(other),
                     ))
    record_review_annotation(catalog, "other-file", title_input(
        submission_id="other-file-selection", word_end=2,
    ), WORDS)
    before = snapshot(catalog)
    with pytest.raises(ValueError, match="Catalog changed"):
        record_review_annotation(catalog, "f2", title_input(
            submission_id="old-file-note", expected_annotation_id=first["annotation_id"],
            expected_catalog_value={"value": first["value_after"]}, comment="A late note",
        ), WORDS)
    assert snapshot(catalog) == before


def test_value_guard_retry_is_checked_against_original_receipt(catalog: Path) -> None:
    first = record_review_annotation(catalog, "f2", title_input(), WORDS)
    note = title_input(submission_id="guarded-comment", expected_annotation_id=first["annotation_id"],
                       expected_catalog_value={"value": first["value_after"]}, comment="New note")
    saved = record_review_annotation(catalog, "f2", note, WORDS)
    with sqlite3.connect(catalog) as conn:
        conn.execute("UPDATE papers SET title='Changed elsewhere' WHERE paper_id='p2'")
    before = snapshot(catalog)
    assert record_review_annotation(catalog, "f2", note, None) == saved
    assert find_review_annotation_replay(catalog, "f2", note) == saved
    with pytest.raises(ValueError, match="Submission ID"):
        record_review_annotation(catalog, "f2", title_input(
            **{**note.model_dump(), "expected_catalog_value": {"value": "Different value"}},
        ), None)
    assert snapshot(catalog) == before


def test_explicit_null_value_guard_is_distinct_from_no_guard(catalog: Path) -> None:
    payload = {"submission_id": "null-value-guard", "field_name": "DOI", "decision": "ABSENT",
               "expected_annotation_id": "", "expected_catalog_value": {"value": None}}
    before = snapshot(catalog)
    with pytest.raises(ValueError, match="Catalog changed"):
        record_review_annotation(catalog, "f2", ReviewAnnotationInput(**payload), None)
    assert snapshot(catalog) == before
    with sqlite3.connect(catalog) as conn:
        conn.execute("UPDATE papers SET doi=NULL WHERE paper_id='p2'")
    saved = record_review_annotation(catalog, "f2", ReviewAnnotationInput(**payload), None)
    assert saved["value_before"] is None and saved["value_after"] is None
    before = snapshot(catalog)
    assert record_review_annotation(catalog, "f2", ReviewAnnotationInput(**payload), None) == saved
    assert snapshot(catalog) == before
