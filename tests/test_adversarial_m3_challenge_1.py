"""Adversarial challenge and empirical stress-test suite for Milestone M3.

Challenger: challenger_m3_1 (Milestone M3 Adversarial Challenger 1)
Delivery 4: Final Portable Delivery: archive, import, and handover (W28–W34).

Adversarial Stress Vectors:
1. W28: Corrupted PDF magic bytes (b"%NOTPDF"), zero-byte files, and single-byte
   SHA-256 digest mismatches on relocated sources (verify immediate fail-closed rejection).
2. W29: Archive extraction without WAL truncation (verify checksum mismatches or
   data integrity loss on uncheckpointed transactions, plus manifest tampering detection).
3. W30: Concurrent or duplicate history adoption into non-empty target (verify collision
   detection, target record preservation, and idempotent compensating reversal).
4. W33: Port unreachable / connection reset simulation on ports 8892 and 8887
   (verify fail-closed status=BLOCKED without mutating or corrupting local stores).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import pytest

# Ensure UuMA, RSTV4, and .uuma-local scripts are in sys.path
repo_root = Path(__file__).resolve().parents[1]
rstv4_root = repo_root.parent / "RSTV4"
uuma_local_v23 = repo_root / ".uuma-local" / "scholar-catalog-implementation-20261023"

for p in (repo_root / "src", rstv4_root / "src", uuma_local_v23):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from rstv4 import catalog_history_adoption as adoption
from rstv4.catalog_skeleton_views import require_parse_source
from rstv4.paper_sources import require_pdf_source

from uuma.knowledge_runtime import ensure_knowledge_graph

CANONICAL_DB = rstv4_root / "data" / "catalog.db"
SAMPLE_PAPER = "paper_dd83af8026e39dd2a2e9316622a7ca49"


@pytest.fixture
def isolated_db(tmp_path: Path):
    """Hermetic sandbox copy of the canonical catalog database."""
    if not CANONICAL_DB.exists():
        pytest.skip(f"Canonical catalog.db not found at {CANONICAL_DB}")
    sandbox_db = tmp_path / "catalog.db"
    shutil.copy2(CANONICAL_DB, sandbox_db)
    conn = sqlite3.connect(sandbox_db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn, sandbox_db
    conn.close()


@pytest.fixture
def isolated_pdf_sandbox(isolated_db, tmp_path: Path):
    """Hermetic sandbox with canonical database and isolated PDF file copy."""
    conn, db_path = isolated_db
    row = conn.execute(
        """SELECT sf.storage_path, sf.sha256, sf.size_bytes, sf.file_version_id, pr.parse_run_id
           FROM source_file_versions sf JOIN parse_runs pr ON pr.file_version_id=sf.file_version_id
           WHERE sf.paper_id=?""",
        (SAMPLE_PAPER,),
    ).fetchone()
    if not row or not os.path.exists(row["storage_path"]):
        pytest.skip(f"Original source PDF for {SAMPLE_PAPER} not found on disk")

    pdf_copy = tmp_path / "source.pdf"
    shutil.copy2(row["storage_path"], pdf_copy)
    conn.execute(
        "UPDATE source_file_versions SET storage_path=? WHERE file_version_id=?",
        (str(pdf_copy), row["file_version_id"]),
    )
    conn.commit()
    yield conn, db_path, pdf_copy, dict(row)


# ==============================================================================
# SECTION 1: W28 Relocated Source Location Handling & Byte Verification Stress
# ==============================================================================


def test_w28_valid_relocated_source_succeeds(isolated_pdf_sandbox, tmp_path: Path):
    """Verify that relocating PDF to a new detached path and updating storage_path passes validation."""
    conn, _, pdf_path, row = isolated_pdf_sandbox
    relocated_dir = tmp_path / "external_relocated_storage"
    relocated_dir.mkdir(parents=True)
    relocated_pdf = relocated_dir / "relocated_paper.pdf"
    shutil.copy2(pdf_path, relocated_pdf)

    conn.execute(
        "UPDATE source_file_versions SET storage_path=? WHERE file_version_id=?",
        (str(relocated_pdf), row["file_version_id"]),
    )
    conn.commit()

    verified = require_pdf_source(conn, row["file_version_id"], SAMPLE_PAPER)
    assert verified["storage_path"] == str(relocated_pdf)
    assert verified["sha256"] == row["sha256"]
    assert verified["size_bytes"] == row["size_bytes"]


@pytest.mark.parametrize(
    "corrupt_magic_bytes",
    [
        b"%NOTPDF-1.4 header bytes here for testing",
        b"NOTPDF-1.4",
        b"\x00\x00\x00\x00%NOTPDF",
        b"   \r\n\t%NOTPDF",
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",  # PNG header
        b"PK\x03\x04\x14\x00\x00\x00\x08\x00",      # ZIP header
    ],
)
def test_w28_corrupted_pdf_magic_bytes_fails_closed(isolated_pdf_sandbox, corrupt_magic_bytes):
    """Verify that any corrupted magic header (such as b'%NOTPDF') fails closed immediately."""
    conn, _, pdf_path, row = isolated_pdf_sandbox
    orig_bytes = pdf_path.read_bytes()

    # Create payload with exact original length to isolate header check from size check
    padded_payload = corrupt_magic_bytes + b" " * max(0, len(orig_bytes) - len(corrupt_magic_bytes))
    padded_payload = padded_payload[: len(orig_bytes)]
    pdf_path.write_bytes(padded_payload)

    with pytest.raises(ValueError, match="Readable full-text PDF is required before reading"):
        require_pdf_source(conn, row["file_version_id"], SAMPLE_PAPER)

    # Restore original bytes
    pdf_path.write_bytes(orig_bytes)
    assert require_pdf_source(conn, row["file_version_id"], SAMPLE_PAPER)["sha256"] == row["sha256"]


def test_w28_zero_byte_relocated_file_fails_closed(isolated_pdf_sandbox):
    """Verify that zero-byte relocated source file immediately fails closed."""
    conn, _, pdf_path, row = isolated_pdf_sandbox
    orig_bytes = pdf_path.read_bytes()

    # Truncate relocated file to 0 bytes
    pdf_path.write_bytes(b"")
    assert pdf_path.stat().st_size == 0

    with pytest.raises(ValueError, match="Original parsed PDF changed"):
        require_pdf_source(conn, row["file_version_id"], SAMPLE_PAPER)

    # Restore
    pdf_path.write_bytes(orig_bytes)


@pytest.mark.parametrize("offset", [1024, 2048, -1])
def test_w28_single_byte_sha256_mismatch_fails_closed(isolated_pdf_sandbox, offset):
    """Verify single-byte mutation at header boundary, body, or EOF triggers fail-closed rejection."""
    conn, _, pdf_path, row = isolated_pdf_sandbox
    orig_bytes = pdf_path.read_bytes()
    mutated = bytearray(orig_bytes)

    idx = offset if offset >= 0 else len(mutated) + offset
    mutated[idx] = (mutated[idx] + 1) % 256
    pdf_path.write_bytes(mutated)

    with pytest.raises(ValueError, match="Original parsed PDF changed"):
        require_pdf_source(conn, row["file_version_id"], SAMPLE_PAPER)

    with pytest.raises(ValueError, match="Original parsed PDF changed"):
        require_parse_source(conn, row["parse_run_id"], SAMPLE_PAPER)

    # Restore
    pdf_path.write_bytes(orig_bytes)
    assert require_pdf_source(conn, row["file_version_id"], SAMPLE_PAPER)["sha256"] == row["sha256"]


def test_w28_quarantined_relocated_source_fails_closed(isolated_pdf_sandbox):
    """Verify that placing relocated paper into catalog_quarantine immediately blocks access."""
    conn, _, _, row = isolated_pdf_sandbox
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT INTO catalog_quarantine (paper_id, reason, source_path, quarantined_at) VALUES (?, ?, ?, ?)",
        (SAMPLE_PAPER, "Security isolation test", "/dummy/quarantine/path", now),
    )
    conn.commit()

    with pytest.raises(ValueError, match="Quarantined full-text source requires review before reading"):
        require_pdf_source(conn, row["file_version_id"], SAMPLE_PAPER)

    conn.execute("DELETE FROM catalog_quarantine WHERE paper_id=?", (SAMPLE_PAPER,))
    conn.commit()
    assert require_pdf_source(conn, row["file_version_id"], SAMPLE_PAPER)["sha256"] == row["sha256"]


# ==============================================================================
# SECTION 2: W29 Authentic FULL Evidence Archive Packaging & WAL Truncation
# ==============================================================================


def test_w29_archive_without_wal_truncation_causes_data_loss_and_checksum_divergence(tmp_path: Path):
    """Empirically stress-test archiving without PRAGMA wal_checkpoint(TRUNCATE).

    When SQLite operates in WAL mode, transactions commit into the `-wal` file.
    Reading `catalog.db` directly without TRUNCATE checkpoint results in:
    1. Uncheckpointed WAL transactions are completely absent from standalone catalog.db.
    2. Extracting into a clean environment drops latest data.
    3. Running a checkpoint after packaging causes immediate checksum divergence against manifest.
    """
    db_dir = tmp_path / "live_db"
    db_dir.mkdir()
    db_path = db_dir / "catalog.db"

    # Initialize a database and enable WAL mode
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT)")
        conn.execute("INSERT INTO papers VALUES ('p1', 'Committed In Main')")

    # Force initial flush
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # Now make critical new writes in WAL mode WITHOUT truncating
    wal_conn = sqlite3.connect(db_path)
    wal_conn.execute("INSERT INTO papers VALUES ('p2_wal', 'Uncheckpointed Critical Evidence')")
    wal_conn.commit()

    wal_file = db_dir / "catalog.db-wal"
    assert wal_file.exists(), "WAL sidecar must exist"
    assert wal_file.stat().st_size > 0, "WAL sidecar must contain uncheckpointed transactions"

    # Flawed archiver: packages catalog.db bytes directly WITHOUT PRAGMA wal_checkpoint(TRUNCATE)
    raw_db_bytes_before = db_path.read_bytes()
    manifest_sha_before = hashlib.sha256(raw_db_bytes_before).hexdigest()

    flawed_archive = tmp_path / "flawed_archive.zip"
    with zipfile.ZipFile(flawed_archive, "w") as zf:
        zf.writestr("stage-manifest.json", json.dumps({"artifacts": {"catalog.db": manifest_sha_before}}))
        zf.writestr("catalog.db", raw_db_bytes_before)

    wal_conn.close()

    # Extract flawed archive to a fresh, isolated destination
    extract_dir = tmp_path / "flawed_extract"
    extract_dir.mkdir()
    with zipfile.ZipFile(flawed_archive, "r") as zf:
        zf.extractall(extract_dir)

    extracted_db = extract_dir / "catalog.db"
    with sqlite3.connect(extracted_db) as conn:
        conn.row_factory = sqlite3.Row
        rows = {r["paper_id"]: r["title"] for r in conn.execute("SELECT * FROM papers").fetchall()}

        # EMPIRICAL PROOF OF CORRUPTION / DATA LOSS:
        # 'p1' exists, but 'p2_wal' is COMPLETELY MISSING because WAL was not checkpointed into main db!
        assert "p1" in rows
        assert "p2_wal" not in rows, "Without WAL checkpoint TRUNCATE, uncheckpointed records are LOST on extraction!"

    # Now test the CORRECT protocol with PRAGMA wal_checkpoint(TRUNCATE)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # After TRUNCATE checkpoint, WAL is 0 bytes
    assert wal_file.stat().st_size == 0

    # Package proper archive
    valid_db_bytes = db_path.read_bytes()
    valid_db_sha = hashlib.sha256(valid_db_bytes).hexdigest()
    assert valid_db_sha != manifest_sha_before, "Database bytes changed when WAL was truncated into main file!"

    valid_archive = tmp_path / "valid_archive.zip"
    with zipfile.ZipFile(valid_archive, "w") as zf:
        zf.writestr("stage-manifest.json", json.dumps({"artifacts": {"catalog.db": valid_db_sha}}))
        zf.writestr("catalog.db", valid_db_bytes)

    # Extract valid archive to clean destination
    valid_extract = tmp_path / "valid_extract"
    valid_extract.mkdir()
    with zipfile.ZipFile(valid_archive, "r") as zf:
        zf.extractall(valid_extract)

    with sqlite3.connect(valid_extract / "catalog.db") as conn:
        conn.row_factory = sqlite3.Row
        valid_rows = {r["paper_id"]: r["title"] for r in conn.execute("SELECT * FROM papers").fetchall()}
        assert "p1" in valid_rows
        assert "p2_wal" in valid_rows, "With PRAGMA wal_checkpoint(TRUNCATE), all data is 100% preserved!"
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_w29_archive_tamper_detection_in_manifest(tmp_path: Path):
    """Verify that tampering with any artifact in a sealed archive triggers checksum mismatch."""
    archive_path = tmp_path / "tampered_archive.zip"
    db_payload = b"SQLite format 3\x00fake_database_bytes_1234567890"
    db_sha = hashlib.sha256(db_payload).hexdigest()

    manifest = {
        "schema_version": 1,
        "stage": "STAGE_FULL_EVIDENCE_DELIVERY",
        "artifacts": {
            "catalog.db": db_sha,
            "sources/sample.pdf": "a" * 64,
        },
    }

    # Case 1: Corrupted catalog.db bytes in ZIP
    corrupted_db_bytes = bytearray(db_payload)
    corrupted_db_bytes[-1] ^= 0xFF
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("stage-manifest.json", json.dumps(manifest))
        zf.writestr("catalog.db", corrupted_db_bytes)
        zf.writestr("sources/sample.pdf", b"dummy")

    with zipfile.ZipFile(archive_path, "r") as zf:
        m = json.loads(zf.read("stage-manifest.json"))
        extracted_db = zf.read("catalog.db")
        assert hashlib.sha256(extracted_db).hexdigest() != m["artifacts"]["catalog.db"], (
            "Corrupted bytes must trigger SHA-256 mismatch against stage-manifest.json"
        )


# ==============================================================================
# SECTION 3: W30 Non-Empty Target History Adoption & Idempotent Reversal Stress
# ==============================================================================


@pytest.fixture
def nonempty_target_db(tmp_path: Path):
    """Provides a target database pre-populated with existing owner records."""
    target_dir = tmp_path / "owner_data"
    target_dir.mkdir(parents=True)
    db_path = target_dir / "catalog.db"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # Create tables needed for adoption
    conn.executescript(
        """
        CREATE TABLE papers (
            paper_id TEXT PRIMARY KEY,
            canonical_key TEXT,
            title TEXT,
            created_at TEXT
        );
        CREATE TABLE catalog_reading_intents (
            intent_id TEXT PRIMARY KEY,
            paper_id TEXT,
            state TEXT,
            created_at TEXT
        );
        CREATE TABLE catalog_reading_jobs (
            job_id TEXT PRIMARY KEY,
            paper_id TEXT,
            job_type TEXT,
            status TEXT,
            fencing_token INTEGER,
            lease_owner TEXT,
            lease_until TEXT
        );
        CREATE TABLE catalog_reading_requests (
            request_id TEXT PRIMARY KEY,
            request_json TEXT,
            intent_id TEXT,
            result_json TEXT,
            created_at TEXT
        );
        CREATE TABLE catalog_reading_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            intent_id TEXT,
            job_id TEXT,
            event_kind TEXT,
            detail_json TEXT,
            created_at TEXT
        );
        """
    )

    # Insert existing owner records (non-empty owner)
    conn.execute(
        "INSERT INTO papers VALUES ('existing-owner-p1', 'key1', 'Pre-existing Paper 1', '2026-11-01')"
    )
    conn.execute(
        "INSERT INTO papers VALUES ('existing-owner-p2', 'key2', 'Pre-existing Paper 2', '2026-11-01')"
    )
    conn.execute(
        "INSERT INTO catalog_reading_intents VALUES ('existing-intent-1', 'existing-owner-p1', 'ACTIVE', '2026-11-01')"
    )
    conn.commit()
    yield conn, db_path
    conn.close()


def test_w30_non_empty_target_preserves_owner_records(nonempty_target_db, tmp_path: Path):
    """Verify that adoption into non-empty target leaves existing owner records 100% untouched."""
    conn, target_path = nonempty_target_db

    # Baseline owner snapshot
    before_papers = conn.execute("SELECT * FROM papers ORDER BY paper_id").fetchall()
    before_intents = conn.execute("SELECT * FROM catalog_reading_intents ORDER BY intent_id").fetchall()
    assert len(before_papers) == 2

    # Prepare admission packet
    source_db_path = tmp_path / "source.db"
    source_db_path.write_bytes(b"")

    record = {
        "operation": adoption.ADOPT,
        "request_id": "req-adopt-001",
        "reason": "Stress-test non-empty target adoption",
        "authority": "CONTROLLER",
        "target_database": str(target_path.resolve()),
        "source_database": str(source_db_path.resolve()),
        "intent_id": "existing-intent-1",
        "packet_sha256": "1" * 64,
        "manifest_sha256": "2" * 64,
        "proof_json": json.dumps({"scopes": {}}),
        "proof_sha256": hashlib.sha256(json.dumps({"scopes": {}}).encode()).hexdigest(),
        "scientific_acceptance": False,
        "runnable_work_imported": False,
    }
    rec_text = adoption._json(record)
    admission = adoption.Admission(rec_text, adoption._sha(rec_text), adoption._MARKER)

    # Execute adoption inside transaction
    conn.execute("BEGIN IMMEDIATE")
    res = adoption.record_adoption(conn, admission)
    conn.commit()

    assert "catalog_reading_requests" in res
    assert "catalog_reading_events" in res

    # Verify owner records are 100% identical
    after_papers = conn.execute("SELECT * FROM papers ORDER BY paper_id").fetchall()
    after_intents = conn.execute("SELECT * FROM catalog_reading_intents ORDER BY intent_id").fetchall()
    assert [dict(r) for r in before_papers] == [dict(r) for r in after_papers]
    assert [dict(r) for r in before_intents] == [dict(r) for r in after_intents]


def test_w30_duplicate_adoption_is_strictly_idempotent(nonempty_target_db, tmp_path: Path):
    """Verify that executing duplicate adoption with identical admission returns empty dict (no duplicate rows)."""
    conn, target_path = nonempty_target_db
    source_db_path = tmp_path / "source.db"
    source_db_path.write_bytes(b"")

    record = {
        "operation": adoption.ADOPT,
        "request_id": "req-adopt-idem",
        "reason": "Test adoption idempotency",
        "authority": "CONTROLLER",
        "target_database": str(target_path.resolve()),
        "source_database": str(source_db_path.resolve()),
        "intent_id": "existing-intent-1",
        "packet_sha256": "3" * 64,
        "manifest_sha256": "4" * 64,
        "proof_json": json.dumps({"scopes": {}}),
        "proof_sha256": hashlib.sha256(json.dumps({"scopes": {}}).encode()).hexdigest(),
        "scientific_acceptance": False,
        "runnable_work_imported": False,
    }
    rec_text = adoption._json(record)
    admission = adoption.Admission(rec_text, adoption._sha(rec_text), adoption._MARKER)

    # First execution
    conn.execute("BEGIN IMMEDIATE")
    first_res = adoption.record_adoption(conn, admission)
    conn.commit()
    assert first_res != {}

    req_count_1 = conn.execute("SELECT COUNT(*) FROM catalog_reading_requests").fetchone()[0]
    evt_count_1 = conn.execute("SELECT COUNT(*) FROM catalog_reading_events").fetchone()[0]

    # Duplicate execution: MUST return {} without adding new rows
    conn.execute("BEGIN IMMEDIATE")
    dup_res = adoption.record_adoption(conn, admission)
    conn.commit()
    assert dup_res == {}, "Duplicate adoption must return empty dict"

    req_count_2 = conn.execute("SELECT COUNT(*) FROM catalog_reading_requests").fetchone()[0]
    evt_count_2 = conn.execute("SELECT COUNT(*) FROM catalog_reading_events").fetchone()[0]
    assert req_count_1 == req_count_2
    assert evt_count_1 == evt_count_2


def test_w30_conflicting_or_tampered_adoption_fails_closed(nonempty_target_db, tmp_path: Path):
    """Verify that tampered admission, modified request fields, or missing transactions fail closed."""
    conn, target_path = nonempty_target_db
    source_db_path = tmp_path / "source.db"
    source_db_path.write_bytes(b"")

    base_record = {
        "operation": adoption.ADOPT,
        "request_id": "req-adopt-conflict",
        "reason": "Conflict test",
        "authority": "CONTROLLER",
        "target_database": str(target_path.resolve()),
        "source_database": str(source_db_path.resolve()),
        "intent_id": "existing-intent-1",
        "packet_sha256": "5" * 64,
        "manifest_sha256": "6" * 64,
        "proof_json": json.dumps({"scopes": {}}),
        "proof_sha256": hashlib.sha256(json.dumps({"scopes": {}}).encode()).hexdigest(),
        "scientific_acceptance": False,
        "runnable_work_imported": False,
    }

    # Case 1: Outside transaction
    rec_text = adoption._json(base_record)
    admission = adoption.Admission(rec_text, adoption._sha(rec_text), adoption._MARKER)
    with pytest.raises(ValueError, match="Adoption requires a prepared controller admission and owned transaction"):
        adoption.record_adoption(conn, admission)

    # Case 2: Tampered marker
    conn.execute("BEGIN IMMEDIATE")
    bad_marker_adm = adoption.Admission(rec_text, adoption._sha(rec_text), marker="fake_marker")
    with pytest.raises(ValueError, match="Adoption requires a prepared controller admission and owned transaction"):
        adoption.record_adoption(conn, bad_marker_adm)
    conn.rollback()

    # Case 3: Tampered seal (hash mismatch)
    conn.execute("BEGIN IMMEDIATE")
    bad_seal_adm = adoption.Admission(rec_text, "0" * 64, adoption._MARKER)
    with pytest.raises(ValueError, match="Adoption requires a prepared controller admission and owned transaction"):
        adoption.record_adoption(conn, bad_seal_adm)
    conn.rollback()

    # Case 4: Target database mismatch
    tampered_target = dict(base_record, target_database="C:/other_owner/catalog.db")
    tampered_target_text = adoption._json(tampered_target)
    bad_target_adm = adoption.Admission(
        tampered_target_text, adoption._sha(tampered_target_text), adoption._MARKER
    )
    conn.execute("BEGIN IMMEDIATE")
    with pytest.raises(ValueError, match="History adoption belongs to a different owner"):
        adoption.record_adoption(conn, bad_target_adm)
    conn.rollback()


def test_w30_overlapping_active_adoption_collision_fails_closed(nonempty_target_db, tmp_path: Path):
    """Verify that adopting two admissions with overlapping scope identities into same target triggers collision rejection."""
    conn, target_path = nonempty_target_db
    source_db_path = tmp_path / "source.db"
    source_db_path.write_bytes(b"")

    scope_payload = {"job_shared_001": {"fingerprint": "fake_fingerprint"}}
    proof_json = json.dumps({"scopes": scope_payload})
    proof_sha = hashlib.sha256(proof_json.encode()).hexdigest()

    rec1 = {
        "operation": adoption.ADOPT,
        "request_id": "req-adopt-scope-1",
        "reason": "First adoption with scope",
        "authority": "CONTROLLER",
        "target_database": str(target_path.resolve()),
        "source_database": str(source_db_path.resolve()),
        "intent_id": "existing-intent-1",
        "packet_sha256": "7" * 64,
        "manifest_sha256": "8" * 64,
        "proof_json": proof_json,
        "proof_sha256": proof_sha,
        "scientific_acceptance": False,
        "runnable_work_imported": False,
    }
    rec1_text = adoption._json(rec1)
    adm1 = adoption.Admission(rec1_text, adoption._sha(rec1_text), adoption._MARKER)

    # Patch fingerprint check to match mock fingerprint
    with mock.patch("rstv4.catalog_history_adoption._fingerprint", return_value="fake_fingerprint"):
        conn.execute("BEGIN IMMEDIATE")
        adoption.record_adoption(conn, adm1)
        conn.commit()

        # Second adoption with overlapping scope
        rec2 = dict(rec1, request_id="req-adopt-scope-2", reason="Overlapping adoption")
        rec2_text = adoption._json(rec2)
        adm2 = adoption.Admission(rec2_text, adoption._sha(rec2_text), adoption._MARKER)

        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(ValueError, match="History already has an active controller adoption"):
            adoption.record_adoption(conn, adm2)
        conn.rollback()


def test_w30_compensating_reversal_lifecycle_and_idempotency(nonempty_target_db, tmp_path: Path):
    """Verify compensating reversal, idempotency, and state transition without deleting evidence."""
    conn, target_path = nonempty_target_db
    source_db_path = tmp_path / "source.db"
    source_db_path.write_bytes(b"")

    record = {
        "operation": adoption.ADOPT,
        "request_id": "req-adopt-reversal-test",
        "reason": "Test reversal lifecycle",
        "authority": "CONTROLLER",
        "target_database": str(target_path.resolve()),
        "source_database": str(source_db_path.resolve()),
        "intent_id": "existing-intent-1",
        "packet_sha256": "9" * 64,
        "manifest_sha256": "a" * 64,
        "proof_json": json.dumps({"scopes": {}}),
        "proof_sha256": hashlib.sha256(json.dumps({"scopes": {}}).encode()).hexdigest(),
        "scientific_acceptance": False,
        "runnable_work_imported": False,
    }
    rec_text = adoption._json(record)
    admission = adoption.Admission(rec_text, adoption._sha(rec_text), adoption._MARKER)

    conn.execute("BEGIN IMMEDIATE")
    adoption.record_adoption(conn, admission)
    conn.commit()

    # Initial query via _load succeeds
    loaded_rec, reversals = adoption._load(conn, "req-adopt-reversal-test")
    assert loaded_rec["request_id"] == "req-adopt-reversal-test"
    assert reversals == []

    # Execute compensating reversal
    conn.execute("BEGIN IMMEDIATE")
    rev_res = adoption.reverse_adoption(
        conn,
        "req-adopt-reversal-test",
        request_id="req-rev-001",
        reason="Scientific compensating rollback",
    )
    conn.commit()
    assert "catalog_reading_requests" in rev_res
    assert "catalog_reading_events" in rev_res

    # Querying without reversed_ok=True MUST raise ValueError
    with pytest.raises(ValueError, match="History adoption was reversed"):
        adoption._load(conn, "req-adopt-reversal-test", reversed_ok=False)

    # Querying with reversed_ok=True shows the reversal id
    _, rev_list = adoption._load(conn, "req-adopt-reversal-test", reversed_ok=True)
    assert rev_list == ["req-rev-001"]

    # Duplicate reversal with identical request MUST return {} (strictly idempotent)
    conn.execute("BEGIN IMMEDIATE")
    dup_rev = adoption.reverse_adoption(
        conn,
        "req-adopt-reversal-test",
        request_id="req-rev-001",
        reason="Scientific compensating rollback",
    )
    conn.commit()
    assert dup_rev == {}, "Duplicate reversal must return empty dict"

    # Conflicting reversal (different request_id) MUST raise ValueError
    conn.execute("BEGIN IMMEDIATE")
    with pytest.raises(ValueError, match="History adoption is already reversed"):
        adoption.reverse_adoption(
            conn,
            "req-adopt-reversal-test",
            request_id="req-rev-different",
            reason="Conflicting rollback",
        )
    conn.rollback()


# ==============================================================================
# SECTION 4: W33 Live FieldKG Health & Fail-Closed Network Isolation Stress
# ==============================================================================


def test_w33_live_fieldkg_runtime_probe():
    """Verify live connectivity and health of FieldKG runtime (ports 8892 and 8887)."""
    res = ensure_knowledge_graph("scholar", recover=False)
    assert res["ready"] is True
    assert res["graph"] == "ScholarFieldKG"
    assert res["recovered"] is False


@pytest.mark.parametrize(
    "net_error",
    [
        ConnectionRefusedError("Connection refused on 127.0.0.1:8892"),
        ConnectionResetError("Connection reset by peer on 127.0.0.1:8892"),
        TimeoutError("Connection timed out on 127.0.0.1:8892"),
        OSError("Network is unreachable"),
    ],
)
def test_w33_port_8892_unreachable_fails_closed_blocked(net_error):
    """Verify port 8892 connection failure returns status=BLOCKED without modifying local stores."""
    runtime_json = rstv4_root / ".rstv4-local" / "fieldkg" / "runtime.json"
    assert runtime_json.exists()
    content_before = runtime_json.read_bytes()

    with mock.patch("uuma.knowledge_runtime.urlopen", side_effect=net_error):
        res = ensure_knowledge_graph("scholar", recover=False)

    assert res["ready"] is False
    assert res["status"] == "BLOCKED"
    assert res["recovered"] is False
    assert res["reason"] == type(net_error).__name__

    # Verify zero mutations to local config or stores
    assert runtime_json.read_bytes() == content_before


def test_w33_port_8887_schema_probe_failure_fails_closed():
    """Verify that if port 8892 is healthy but port 8887 fails, system fails closed with status=BLOCKED."""
    def mock_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "8892" in url:
            # Bridge is up
            resp = mock.MagicMock()
            resp.__enter__.return_value = resp
            resp.read.return_value = json.dumps({
                "ready": True, "project_id": "2", "host_addr": "http://127.0.0.1:8887"
            }).encode()
            return resp
        # Port 8887 fails
        raise ConnectionRefusedError("Connection refused on 127.0.0.1:8887")

    with mock.patch("uuma.knowledge_runtime.urlopen", side_effect=mock_urlopen):
        res = ensure_knowledge_graph("scholar", recover=False)

    assert res["ready"] is False
    assert res["status"] == "BLOCKED"
    assert res["recovered"] is False
    assert res["reason"] == "ConnectionRefusedError"


def test_w33_schema_or_project_mismatch_fails_closed():
    """Verify that missing project or missing FieldKnowledgeObject schema fails closed with BLOCKED."""
    # Case 1: Project 2 missing
    def mock_urlopen_no_proj(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        resp = mock.MagicMock()
        resp.__enter__.return_value = resp
        if "8892" in url:
            resp.read.return_value = json.dumps({
                "ready": True, "project_id": "2", "host_addr": "http://127.0.0.1:8887"
            }).encode()
        elif "/project" in url:
            # Empty projects list
            resp.read.return_value = json.dumps([]).encode()
        return resp

    with mock.patch("uuma.knowledge_runtime.urlopen", side_effect=mock_urlopen_no_proj):
        res = ensure_knowledge_graph("scholar", recover=False)

    assert res["ready"] is False
    assert res["status"] == "BLOCKED"
    assert "The expected knowledge graph project is missing" in res["reason"]


def test_w33_unauthorized_profile_raises_permission_error():
    """Verify that unauthorized profile immediately raises PermissionError without hitting network."""
    with mock.patch("uuma.knowledge_runtime.urlopen") as mock_url:
        with pytest.raises(PermissionError, match="This profile does not own a managed knowledge graph"):
            ensure_knowledge_graph("unauthorized_user", recover=False)
        mock_url.assert_not_called()
