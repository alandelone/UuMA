"""Adversarial stress-test suite for Milestone M3 (W28 Portable Resolution & F06/W29 Archive Tampering).

Challenger: challenger_m3_1
"""
from __future__ import annotations

import gc
import hashlib
import json
import shutil
import sqlite3
import sys
import tarfile
from pathlib import Path

import pytest

# Ensure repos are in sys.path
repo_root = Path(__file__).resolve().parents[1]
rstv4_root = repo_root.parent / "RSTV4"
uuma_local = repo_root / ".uuma-local" / "scholar-catalog-implementation-20261023"

for p in (repo_root / "src", rstv4_root / "src", uuma_local):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from package_scholar_delivery_archive import (
    PDF_BYTES,
    TARGET_ARCHIVE_20261106,
    sha256_file,
    verify_delivery_archive,
)
from rstv4.paper_sources import require_pdf_source, resolve_source_path

SAMPLE_PAPER = "paper_dd83af8026e39dd2a2e9316622a7ca49"


# ==============================================================================
# Helper Fixtures & Builders
# ==============================================================================

@pytest.fixture
def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE source_file_versions (
            file_version_id TEXT PRIMARY KEY,
            paper_id TEXT,
            mime_type TEXT,
            identity_status TEXT,
            storage_path TEXT,
            sha256 TEXT,
            size_bytes INTEGER
        )
    """)
    conn.execute("CREATE TABLE catalog_quarantine (paper_id TEXT)")
    yield conn
    conn.close()


# ==============================================================================
# TASK 1: Adversarial Portable Resolution Stress-Testing (W28)
# ==============================================================================

def test_t1_a_tampered_primary_size_returns_primary_and_raises(tmp_path, memory_db, monkeypatch):
    """1.a: File exists at storage_path but size is tampered (110,015 or 110,017 bytes).

    MUST return primary path and require_pdf_source() MUST raise ValueError("Original parsed PDF changed").
    MUST NEVER fall back to another source (e.g. SCHOLAR_CATALOG_SOURCES) when primary file exists.
    """
    # Create corrupted primary file (110,015 bytes)
    primary_pdf = tmp_path / "primary.pdf"
    corrupt_content = b"%PDF-1.4 " + b"A" * (PDF_BYTES - 10)  # 110,015 bytes
    assert len(corrupt_content) == 110015
    primary_pdf.write_bytes(corrupt_content)

    # Set up authentic fallback in SCHOLAR_CATALOG_SOURCES
    fallback_dir = tmp_path / "fallback_store"
    fallback_dir.mkdir()
    auth_content = b"%PDF-1.4 " + b"A" * (PDF_BYTES - 9)  # 110,016 bytes
    assert len(auth_content) == PDF_BYTES
    auth_sha = hashlib.sha256(auth_content).hexdigest()
    (fallback_dir / "source.pdf").write_bytes(auth_content)
    (fallback_dir / f"{auth_sha}.bin").write_bytes(auth_content)

    monkeypatch.setenv("SCHOLAR_CATALOG_SOURCES", str(fallback_dir))

    # Test resolve_source_path directly: MUST return primary path, NOT fallback
    resolved = resolve_source_path(str(primary_pdf), expected_sha256=auth_sha, expected_size=PDF_BYTES)
    assert resolved == primary_pdf, "resolve_source_path must NOT fall back when primary file exists on disk!"

    # Insert DB record expecting authentic size and sha256
    memory_db.execute(
        "INSERT INTO source_file_versions VALUES ('fv1', ?, 'application/pdf', 'VERIFIED', ?, ?, ?)",
        (SAMPLE_PAPER, str(primary_pdf), auth_sha, PDF_BYTES),
    )
    memory_db.commit()

    # require_pdf_source MUST fail closed with exact error
    with pytest.raises(ValueError, match="Original parsed PDF changed"):
        require_pdf_source(memory_db, "fv1", SAMPLE_PAPER)

    # Also test with 110,017 bytes (1 byte larger)
    primary_pdf.write_bytes(corrupt_content + b"BB")
    assert primary_pdf.stat().st_size == 110017
    with pytest.raises(ValueError, match="Original parsed PDF changed"):
        require_pdf_source(memory_db, "fv1", SAMPLE_PAPER)


def test_t1_b_corrupted_magic_header_rejects(tmp_path, memory_db, monkeypatch):
    """1.b: File exists at storage_path, size matches, but header is corrupted (%BAD-).

    Verify: raises Readable full-text PDF is required before reading.
    Must NOT fall back to SCHOLAR_CATALOG_SOURCES.
    """
    primary_pdf = tmp_path / "bad_magic.pdf"
    corrupt_content = b"%BAD-1.4 " + b"C" * (PDF_BYTES - 9)
    assert len(corrupt_content) == PDF_BYTES
    primary_pdf.write_bytes(corrupt_content)

    fallback_dir = tmp_path / "fallback_store"
    fallback_dir.mkdir()
    auth_content = b"%PDF-1.4 " + b"C" * (PDF_BYTES - 9)
    auth_sha = hashlib.sha256(auth_content).hexdigest()
    (fallback_dir / "source.pdf").write_bytes(auth_content)
    monkeypatch.setenv("SCHOLAR_CATALOG_SOURCES", str(fallback_dir))

    resolved = resolve_source_path(str(primary_pdf), expected_sha256=auth_sha, expected_size=PDF_BYTES)
    assert resolved == primary_pdf, "Must NOT fall back when primary exists"

    memory_db.execute(
        "INSERT INTO source_file_versions VALUES ('fv_magic', ?, 'application/pdf', 'VERIFIED', ?, ?, ?)",
        (SAMPLE_PAPER, str(primary_pdf), auth_sha, PDF_BYTES),
    )
    memory_db.commit()

    with pytest.raises(ValueError, match="Readable full-text PDF is required before reading"):
        require_pdf_source(memory_db, "fv_magic", SAMPLE_PAPER)


def test_t1_c_mutated_sha256_digest_detected_and_rejected(tmp_path, memory_db, monkeypatch):
    """1.c: File exists, size is correct, magic header is correct, but single byte flipped in body.

    Verify: raises Original parsed PDF changed.
    """
    primary_pdf = tmp_path / "tampered_body.pdf"
    content = bytearray(b"%PDF-1.4 " + b"D" * (PDF_BYTES - 9))
    expected_sha = hashlib.sha256(content).hexdigest()
    # Flip a single byte in body
    content[500] = ord(b"Z")
    primary_pdf.write_bytes(content)

    fallback_dir = tmp_path / "fallback_store"
    fallback_dir.mkdir()
    (fallback_dir / "source.pdf").write_bytes(b"%PDF-1.4 " + b"D" * (PDF_BYTES - 9))
    monkeypatch.setenv("SCHOLAR_CATALOG_SOURCES", str(fallback_dir))

    resolved = resolve_source_path(str(primary_pdf), expected_sha256=expected_sha, expected_size=PDF_BYTES)
    assert resolved == primary_pdf

    memory_db.execute(
        "INSERT INTO source_file_versions VALUES ('fv_sha', ?, 'application/pdf', 'VERIFIED', ?, ?, ?)",
        (SAMPLE_PAPER, str(primary_pdf), expected_sha, PDF_BYTES),
    )
    memory_db.commit()

    with pytest.raises(ValueError, match="Original parsed PDF changed"):
        require_pdf_source(memory_db, "fv_sha", SAMPLE_PAPER)


def test_t1_d_primary_missing_fallback_succeeds_without_db_mutation(tmp_path, memory_db, monkeypatch):
    """1.d: Primary storage_path does not exist: test fallback to SCHOLAR_CATALOG_SOURCES.

    Verify: succeeds without database mutation (conn.total_changes == initial_changes, zero updates).
    """
    missing_storage_path = "Z:\\nonexistent_network_share\\missing_paper.pdf"
    auth_content = b"%PDF-1.4 authentic body " + b"E" * (PDF_BYTES - 24)
    auth_sha = hashlib.sha256(auth_content).hexdigest()

    relocated_dir = tmp_path / "relocated_sources"
    relocated_dir.mkdir()
    relocated_file = relocated_dir / f"{auth_sha}.bin"
    relocated_file.write_bytes(auth_content)

    monkeypatch.setenv("SCHOLAR_CATALOG_SOURCES", str(relocated_dir))

    memory_db.execute(
        "INSERT INTO source_file_versions VALUES ('fv_fallback', ?, 'application/pdf', 'VERIFIED', ?, ?, ?)",
        (SAMPLE_PAPER, missing_storage_path, auth_sha, PDF_BYTES),
    )
    memory_db.commit()

    initial_changes = memory_db.total_changes

    traced_statements: list[str] = []
    memory_db.set_trace_callback(traced_statements.append)

    res = require_pdf_source(memory_db, "fv_fallback", SAMPLE_PAPER)
    assert res["file_version_id"] == "fv_fallback"
    assert res["storage_path"] == str(relocated_file.resolve())

    # Verify zero database mutations
    assert memory_db.total_changes == initial_changes
    row = memory_db.execute("SELECT storage_path FROM source_file_versions WHERE file_version_id='fv_fallback'").fetchone()
    assert row["storage_path"] == missing_storage_path, "storage_path in DB must remain immutable!"
    assert not any("UPDATE" in s.upper() for s in traced_statements), "No UPDATE statement may be executed!"


def test_t1_e_primary_missing_and_fallback_corrupted_fails_closed(tmp_path, memory_db, monkeypatch):
    """1.e: Primary does not exist, and SCHOLAR_CATALOG_SOURCES points to corrupted file.

    Verify: fails closed, raises ValueError.
    """
    missing_storage_path = "Z:\\nonexistent\\missing.pdf"
    auth_sha = "a" * 64

    # Corrupted size in fallback
    fallback_dir = tmp_path / "bad_fallback"
    fallback_dir.mkdir()
    (fallback_dir / f"{auth_sha}.bin").write_bytes(b"%PDF-1.4 bad size")
    monkeypatch.setenv("SCHOLAR_CATALOG_SOURCES", str(fallback_dir))

    memory_db.execute(
        "INSERT INTO source_file_versions VALUES ('fv_corrupt_fb', ?, 'application/pdf', 'VERIFIED', ?, ?, ?)",
        (SAMPLE_PAPER, missing_storage_path, auth_sha, PDF_BYTES),
    )
    memory_db.commit()

    with pytest.raises(ValueError, match="Original parsed PDF changed"):
        require_pdf_source(memory_db, "fv_corrupt_fb", SAMPLE_PAPER)


def test_t1_f_database_immutability_strict_assertion(tmp_path, memory_db, monkeypatch):
    """1.f: Strict assertion: assert UPDATE source_file_versions was NEVER executed in any resolution path."""
    primary_pdf = tmp_path / "valid.pdf"
    content = b"%PDF-1.4 " + b"F" * (PDF_BYTES - 9)
    sha = hashlib.sha256(content).hexdigest()
    primary_pdf.write_bytes(content)

    memory_db.execute(
        "INSERT INTO source_file_versions VALUES ('fv_immut', ?, 'application/pdf', 'VERIFIED', ?, ?, ?)",
        (SAMPLE_PAPER, str(primary_pdf), sha, PDF_BYTES),
    )
    memory_db.commit()

    initial_changes = memory_db.total_changes

    traced_sql: list[str] = []
    memory_db.set_trace_callback(traced_sql.append)

    res = require_pdf_source(memory_db, "fv_immut", SAMPLE_PAPER)
    assert res["storage_path"] == str(primary_pdf)

    # Check all traced SQL statements
    for sql in traced_sql:
        normalized = sql.upper().strip()
        assert not normalized.startswith("UPDATE"), f"Forbidden UPDATE executed: {sql}"
        assert "SOURCE_FILE_VERSIONS" not in normalized or normalized.startswith("SELECT"), f"Non-SELECT on source_file_versions: {sql}"

    assert memory_db.total_changes == initial_changes, "total_changes must remain invariant during require_pdf_source"


# ==============================================================================
# TASK 2: Adversarial Delivery Archive Tampering Stress-Testing (F06 & W29)
# ==============================================================================

def test_t2_a_tarball_pdf_single_byte_flip_fails_verifier(tmp_path):
    """2.a: Mutate source.pdf inside packet.tar.gz (flip a single byte), repackage.

    Verify: verifier detects SHA-256 mismatch and fails.
    """
    scratch = tmp_path / "archive_tamper_pdf"
    shutil.copytree(TARGET_ARCHIVE_20261106, scratch)

    tar_path = scratch / "packet.tar.gz"
    assert tar_path.is_file()

    # Extract tarball
    extract_dir = scratch / "_extracted"
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(extract_dir)

    # Flip 1 byte in extracted source.pdf
    pdf_file = extract_dir / "source.pdf"
    pdf_bytes = bytearray(pdf_file.read_bytes())
    pdf_bytes[200] ^= 0x01
    pdf_file.write_bytes(pdf_bytes)

    # Repackage tarball
    tar_path.unlink()
    with tarfile.open(tar_path, "w:gz") as tar:
        for item in sorted(extract_dir.iterdir()):
            tar.add(item, arcname=item.name)

    # If outer manifest is NOT updated, packet_sha256 mismatch
    with pytest.raises(AssertionError, match="Outer manifest packet_sha256 mismatch"):
        verify_delivery_archive(scratch)

    # If outer manifest packet_sha256 IS updated to match tarball, inner content hash mismatch triggers
    manifest = json.loads((scratch / "manifest.json").read_bytes())
    manifest["packet_sha256"] = sha256_file(tar_path)
    manifest["files"]["packet.tar.gz"] = manifest["packet_sha256"]
    (scratch / "manifest.json").write_text(json.dumps(manifest, indent=2))

    with pytest.raises(AssertionError, match="Member source.pdf content differs from outer manifest"):
        verify_delivery_archive(scratch)


def test_t2_b_tarball_catalog_db_corruption_fails_verifier(tmp_path):
    """2.b: Mutate catalog.db inside tarball (corrupt header or delete a table).

    Verify: verifier detects integrity or hash failure.
    """
    scratch = tmp_path / "archive_tamper_db"
    shutil.copytree(TARGET_ARCHIVE_20261106, scratch)

    # Case B1: Corrupt outer catalog.db file
    db_file = scratch / "catalog.db"
    orig_bytes = db_file.read_bytes()
    corrupted_bytes = b"CORRUPTED_SQLITE_HEADER" + orig_bytes[24:]
    db_file.write_bytes(corrupted_bytes)

    with pytest.raises(AssertionError, match="Hash mismatch for catalog.db"):
        verify_delivery_archive(scratch)

    # Case B2: Corrupt SQLite table inside database and recompute outer hash to test integrity check
    db_file.write_bytes(orig_bytes)
    conn = sqlite3.connect(db_file)
    try:
        conn.execute("DROP TABLE catalog_skeleton_theme_observations")
        conn.commit()
    finally:
        conn.close()

    # Force GC to release SQLite lock before running verifier on Windows
    gc.collect()

    # Repackage packet.tar.gz with corrupted catalog.db
    tar_path = scratch / "packet.tar.gz"
    extract_dir = scratch / "_extracted"
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(extract_dir)

    shutil.copy2(db_file, extract_dir / "catalog.db")
    tar_path.unlink()
    with tarfile.open(tar_path, "w:gz") as tar:
        for item in sorted(extract_dir.iterdir()):
            tar.add(item, arcname=item.name)

    # Update manifest hash for catalog.db and packet.tar.gz so hash check passes and integrity check runs
    manifest = json.loads((scratch / "manifest.json").read_bytes())
    manifest["files"]["catalog.db"] = sha256_file(db_file)
    manifest["packet_sha256"] = sha256_file(tar_path)
    manifest["files"]["packet.tar.gz"] = manifest["packet_sha256"]
    (scratch / "manifest.json").write_text(json.dumps(manifest, indent=2))

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        verify_delivery_archive(scratch)


def test_t2_c_altered_metadata_title_fails_verifier(tmp_path):
    """2.c: Alter metadata.json to change title or remove canonical wording.

    Verify: verifier detects canonical title discrepancy.
    """
    scratch = tmp_path / "archive_tamper_meta"
    shutil.copytree(TARGET_ARCHIVE_20261106, scratch)

    meta_file = scratch / "metadata.json"
    meta = json.loads(meta_file.read_bytes())
    meta["title"] = "Tampered Non-Canonical Title"
    meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # If manifest not updated, hash mismatch
    with pytest.raises(AssertionError, match="Hash mismatch for metadata.json"):
        verify_delivery_archive(scratch)

    # Case C2: Update both outer and tarball metadata.json
    tar_path = scratch / "packet.tar.gz"
    extract_dir = scratch / "_extracted"
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(extract_dir)

    (extract_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    tar_path.unlink()
    with tarfile.open(tar_path, "w:gz") as tar:
        for item in sorted(extract_dir.iterdir()):
            tar.add(item, arcname=item.name)

    manifest = json.loads((scratch / "manifest.json").read_bytes())
    manifest["files"]["metadata.json"] = sha256_file(meta_file)
    manifest["packet_sha256"] = sha256_file(tar_path)
    manifest["files"]["packet.tar.gz"] = manifest["packet_sha256"]
    (scratch / "manifest.json").write_text(json.dumps(manifest, indent=2))

    with pytest.raises(AssertionError, match="Title does not match canonical"):
        verify_delivery_archive(scratch)


def test_t2_d_removed_verifier_receipt_fails_verifier(tmp_path):
    """2.d (Part 1): Remove verifier_receipt.json from archive.

    Verify: verifier rejects archive.
    """
    scratch = tmp_path / "archive_missing_receipt"
    shutil.copytree(TARGET_ARCHIVE_20261106, scratch)

    (scratch / "verifier_receipt.json").unlink()

    # Outer check fails if file is missing
    with pytest.raises(AssertionError, match="Missing expected outer file: verifier_receipt.json"):
        verify_delivery_archive(scratch)


def test_t2_d_vulnerability_missing_parse_manifest_not_enforced_by_verifier(tmp_path):
    """2.d (Part 2 - EMPIRICAL VULNERABILITY):
    Remove parse_artifact_manifest.json from tarball and manifest.
    
    EXPECTED SECURE BEHAVIOR: Verifier MUST reject archive due to missing members (must require all 11 files).
    ACTUAL VULNERABLE BEHAVIOR: Verifier permits missing members because it does NOT check len(members) == 11
    or check that all 11 required files are present!
    """
    scratch = tmp_path / "archive_missing_member"
    shutil.copytree(TARGET_ARCHIVE_20261106, scratch)

    # Remove parse_artifact_manifest.json
    (scratch / "parse_artifact_manifest.json").unlink()

    # Repackage packet.tar.gz with remaining 10 files
    tar_path = scratch / "packet.tar.gz"
    tar_path.unlink()
    with tarfile.open(tar_path, "w:gz") as tar:
        for f in sorted(scratch.iterdir()):
            if f.name in ("packet.tar.gz", "manifest.json"):
                continue
            tar.add(f, arcname=f.name)

    # Update outer manifest
    manifest = json.loads((scratch / "manifest.json").read_bytes())
    manifest["packet_sha256"] = sha256_file(tar_path)
    del manifest["files"]["parse_artifact_manifest.json"]
    manifest["files"]["packet.tar.gz"] = manifest["packet_sha256"]
    (scratch / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # Closed-loop security enforcement: Verifier must reject missing member
    with pytest.raises(AssertionError):
        verify_delivery_archive(scratch)


def test_t2_d_vulnerability_tarball_missing_member_divergence(tmp_path):
    """2.d (Part 3 - EMPIRICAL VULNERABILITY):
    Remove parse_artifact_manifest.json ONLY from packet.tar.gz, while outer directory
    and manifest still retain it.
    
    EXPECTED SECURE BEHAVIOR: Verifier MUST detect that packet.tar.gz is missing a member that outer manifest expects.
    """
    scratch = tmp_path / "archive_divergent_tarball"
    shutil.copytree(TARGET_ARCHIVE_20261106, scratch)

    # Repackage packet.tar.gz without parse_artifact_manifest.json, BUT KEEP outer parse_artifact_manifest.json
    tar_path = scratch / "packet.tar.gz"
    tar_path.unlink()
    with tarfile.open(tar_path, "w:gz") as tar:
        for f in sorted(scratch.iterdir()):
            if f.name in ("packet.tar.gz", "manifest.json", "parse_artifact_manifest.json"):
                continue
            tar.add(f, arcname=f.name)

    # Update only packet_sha256 in manifest (manifest['files']['parse_artifact_manifest.json'] is still present!)
    manifest = json.loads((scratch / "manifest.json").read_bytes())
    manifest["packet_sha256"] = sha256_file(tar_path)
    manifest["files"]["packet.tar.gz"] = manifest["packet_sha256"]
    assert "parse_artifact_manifest.json" in manifest["files"]
    (scratch / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # Closed-loop security enforcement: Verifier must reject missing member in packet.tar.gz
    with pytest.raises(AssertionError):
        verify_delivery_archive(scratch)



def test_t2_e_mutated_outer_manifest_packet_sha256_fails_verifier(tmp_path):
    """2.e: Mutate outer manifest.json packet SHA-256.

    Verify: verifier rejects packet hash mismatch.
    """
    scratch = tmp_path / "archive_tamper_packet_sha"
    shutil.copytree(TARGET_ARCHIVE_20261106, scratch)

    manifest = json.loads((scratch / "manifest.json").read_bytes())
    # Tamper packet SHA-256 by flipping last char
    last_char = "0" if manifest["packet_sha256"][-1] != "0" else "1"
    manifest["packet_sha256"] = manifest["packet_sha256"][:-1] + last_char
    (scratch / "manifest.json").write_text(json.dumps(manifest, indent=2))

    with pytest.raises(AssertionError, match="Outer manifest packet_sha256 mismatch"):
        verify_delivery_archive(scratch)
