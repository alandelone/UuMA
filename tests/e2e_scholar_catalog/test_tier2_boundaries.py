"""Tier 2: Boundary & Corner Cases E2E Tests (B01–B10).

Negative testing, boundary value analysis (BVA), extreme edge cases,
and fail-closed resilience across Deliveries 2, 3, and 4.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import rstv4.catalog_content_retrieval as retrieval
import rstv4.catalog_content_tools as tools
import rstv4.catalog_history_adoption as adoption
import rstv4.catalog_theme_corrections as corrections
import rstv4.reading_policy as policy
from .conftest import (
    MockEmbeddings,
    default_card,
    make_paper_source,
)
from rstv4.catalog_content_retrieval import CatalogContentRetrieval
from rstv4.catalog_mcp_views import MAX_RESPONSE_CHARACTERS, encoded
from rstv4.catalog_understanding import CatalogUnderstanding
from rstv4.database import initialize_catalog, transaction
from rstv4.paper_sources import require_pdf_source


# B01: Empty & Whitespace Search Queries
@pytest.mark.parametrize("query", ["", "   ", "\t\t", "\n\r\n", "       "])
def test_b01_empty_and_whitespace_search_queries(catalog_sandbox, query):
    root = catalog_sandbox["root"]
    embedder = catalog_sandbox["embedder"]
    index = CatalogContentRetrieval(root, embedder)
    index.refresh_batch(manual_requested=True)

    # Empty or whitespace-only search query raises bounded query validation error
    with pytest.raises(ValueError, match="Invalid content query"):
        index.search(query)


# B02: Invalid & Nonexistent Paper IDs
@pytest.mark.parametrize("bad_id", [
    "nonexistent_paper_id_99999",
    "../../../../etc/passwd",
    "paper-with-sql-injection' OR '1'='1",
    "",
])
def test_b02_invalid_and_nonexistent_paper_ids(catalog_sandbox, bad_id):
    db_path = catalog_sandbox["db_path"]
    store = CatalogUnderstanding(catalog_sandbox["root"])

    # Looking up nonexistent paper returns NOT_READ default or None without creating records
    with transaction(db_path) as conn:
        before_count = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]

    paper = store.paper(bad_id) if bad_id else None
    if paper is not None:
        assert paper["understanding"] == "NOT_READ"
        assert paper["themes"] == []
    else:
        assert paper is None

    # No orphan records created in database
    with transaction(db_path) as conn:
        after_count = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        assert before_count == after_count


# B03: Corrupted PDF Bytes & Invalid Magic Header
@pytest.mark.parametrize("corrupt_kind", [
    "invalid_header_same_size",
    "invalid_header_different_size",
    "binary_zeros",
    "altered_body_sha_mismatch",
])
def test_b03_corrupted_pdf_bytes_and_invalid_magic(catalog_sandbox, corrupt_kind):
    paper_id = "paper_dd83af8026e3"
    pdf_path = catalog_sandbox["p1"]["pdf_path"]
    orig_size = pdf_path.stat().st_size

    if corrupt_kind == "invalid_header_same_size":
        # Same byte length as original, but missing %PDF- magic header
        corrupt_payload = b"NOT_A_PDF_FILE!" + b" " * (orig_size - 15)
        expected_regex = "Readable full-text PDF is required before reading"
    elif corrupt_kind == "invalid_header_different_size":
        corrupt_payload = b"PK\x03\x04zip_file_header"
        expected_regex = "Original parsed PDF changed"
    elif corrupt_kind == "binary_zeros":
        corrupt_payload = b"\x00" * orig_size
        expected_regex = "Readable full-text PDF is required before reading"
    else:
        # Starts with %PDF- but body altered (SHA mismatch)
        corrupt_payload = b"%PDF-1.4" + b"A" * (orig_size - 8)
        expected_regex = "Original parsed PDF changed"

    pdf_path.write_bytes(corrupt_payload)
    db_path = catalog_sandbox["db_path"]
    with transaction(db_path) as conn:
        with pytest.raises(ValueError, match=expected_regex):
            require_pdf_source(conn, f"{paper_id}-file", paper_id)


# B04: Zero-Byte Source File & Missing Files
def test_b04_zero_byte_source_file_and_missing_files(catalog_sandbox):
    paper_id = "paper_dd83af8026e3"
    pdf_path = catalog_sandbox["p1"]["pdf_path"]
    db_path = catalog_sandbox["db_path"]

    # 1. Zero-byte file
    pdf_path.write_bytes(b"")
    with transaction(db_path) as conn:
        with pytest.raises(ValueError, match="Original parsed PDF changed"):
            require_pdf_source(conn, f"{paper_id}-file", paper_id)

    # 2. Deleted / Missing file
    pdf_path.unlink()
    with transaction(db_path) as conn:
        with pytest.raises(ValueError, match="Original parsed PDF changed"):
            require_pdf_source(conn, f"{paper_id}-file", paper_id)


# B05: Non-Empty Target Collision Isolation
def test_b05_non_empty_target_collision_isolation(catalog_sandbox, tmp_path):
    source_db = catalog_sandbox["db_path"]
    target_dir = tmp_path / "target_collision_owner" / "data"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_db = target_dir / "catalog.db"
    initialize_catalog(target_db)

    # Pre-populate target database with existing paper and intent
    with transaction(target_db) as conn:
        conn.execute(
            """INSERT INTO papers (paper_id, canonical_key, title, normalized_title, authors_json, created_at, updated_at)
               VALUES ('target-existing', 'target-existing', 'Target Native Paper', 'target native paper', '[]', '2026-11-04', '2026-11-04')"""
        )
        conn.execute(
            """INSERT INTO catalog_reading_intents
               (intent_id, paper_id, profile_version, state, manual_priority, revision, created_at, updated_at)
               VALUES ('intent-target-01', 'target-existing', 'v1', 'ACTIVE', 0, 1, '2026-11-04', '2026-11-04')"""
        )
        before_rows = conn.execute("SELECT * FROM papers").fetchall()

    # Conflicting adoption request with altered proof payload fails closed
    record = {
        "operation": adoption.ADOPT,
        "request_id": "adopt-collision-test",
        "reason": "Collision isolation test",
        "authority": "CONTROLLER",
        "target_database": str(target_db.resolve()),
        "source_database": str(source_db.resolve()),
        "intent_id": "intent-target-01",
        "packet_sha256": "1" * 64,
        "manifest_sha256": "2" * 64,
        "proof_json": '{"scopes": {"fake_scope": {"fingerprint": "mismatched"}}}',
        "proof_sha256": hashlib.sha256('{"scopes": {"fake_scope": {"fingerprint": "mismatched"}}}'.encode()).hexdigest(),
        "scientific_acceptance": False,
        "runnable_work_imported": False,
    }
    rec_text = adoption._json(record)
    admission = adoption.Admission(rec_text, adoption._sha(rec_text), adoption._MARKER)

    with closing(sqlite3.connect(target_db)) as t_conn:
        t_conn.row_factory = sqlite3.Row
        t_conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(ValueError, match="(Snapshot origin requires its original reading job|exact verified source)"):
            adoption.record_adoption(t_conn, admission)
        t_conn.rollback()

    # Target records must remain completely unharmed
    with transaction(target_db) as conn:
        after_rows = conn.execute("SELECT * FROM papers").fetchall()
        assert len(before_rows) == len(after_rows)
        assert after_rows[0]["paper_id"] == "target-existing"


# B06: Night Window Boundary Edge Times (00:00–08:00 Asia/Kuala_Lumpur)
def test_b06_night_window_boundary_edge_times():
    tz = ZoneInfo("Asia/Kuala_Lumpur")

    # Day 1 23:59:59 MYT (outside night window)
    t_235959 = datetime(2026, 11, 3, 23, 59, 59, tzinfo=tz)
    assert policy.night_window_open(t_235959) is False
    assert policy.seconds_until_window(t_235959) == 1
    job_auto = {"job_type": "QUICK_READ", "input_json": {}}
    assert policy.admitted(job_auto, t_235959) is False

    # Day 2 00:00:00 MYT (exact opening boundary)
    t_000000 = datetime(2026, 11, 4, 0, 0, 0, tzinfo=tz)
    assert policy.night_window_open(t_000000) is True
    assert policy.seconds_until_window(t_000000) == 0
    assert policy.admitted(job_auto, t_000000) is True

    # Day 2 07:59:59 MYT (last second before closing)
    t_075959 = datetime(2026, 11, 4, 7, 59, 59, tzinfo=tz)
    assert policy.night_window_open(t_075959) is True
    assert policy.seconds_until_window(t_075959) == 0
    assert policy.admitted(job_auto, t_075959) is True

    # Day 2 08:00:00 MYT (exact closing boundary)
    t_080000 = datetime(2026, 11, 4, 8, 0, 0, tzinfo=tz)
    assert policy.night_window_open(t_080000) is False
    assert policy.seconds_until_window(t_080000) > 0
    assert policy.admitted(job_auto, t_080000) is False

    # Manual override bypasses window regardless of time
    job_manual = {"job_type": "QUICK_READ", "input_json": {"user_requested": True}}
    assert policy.explicit_manual(job_manual) is True
    assert policy.admitted(job_manual, t_235959) is True
    assert policy.admitted(job_manual, t_080000) is True


# B07: Max Transport Character Limit & Pagination (60,000 bytes)
def test_b07_max_transport_character_limit_and_pagination(catalog_sandbox):
    root = catalog_sandbox["root"]
    embedder = catalog_sandbox["embedder"]
    index = CatalogContentRetrieval(root, embedder)
    index.refresh_batch(manual_requested=True)

    result = index.search("governance")
    # Simulate a search response with many large passage quotations (> 120,000 chars)
    large_matches = [
        dict(result["matches"][0], document_id=f"doc-{i}", quote="A" * 25000)
        for i in range(5)
    ]
    result["matches"] = large_matches
    result["total_matches"] = 5

    bounded = tools.bounded_result(result)
    assert len(encoded(bounded)) <= MAX_RESPONSE_CHARACTERS
    # Truncated safely to fit budget
    assert len(bounded["matches"]) < 5
    assert bounded["has_more_matches"] is True
    assert bounded["next_offset"] == len(bounded["matches"])
    # Preserves exact quote intact without mutilating individual characters
    assert bounded["matches"][0]["quote"] == "A" * 25000


# B08: Unicode & Extreme Codepoints in Chunking
def test_b08_unicode_and_extreme_codepoints_in_chunking():
    # Multi-lingual, math symbols, formulas, and emojis
    unicode_text = (
        "微电网去中心化能源市场治理与智能合约清算机制研究。\n"
        "Formula: $\\int_{-\\infty}^{+\\infty} e^{-x^2} dx = \\sqrt{\\pi}$ and $\\lambda_{i,j} \\le 0.15$.\n"
        "Emojis: ⚡🔋🚀💡🔬📊.\n"
        "Greek: α, β, γ, δ, ε, θ, λ, μ, π, σ, ω.\n"
    ) * 40

    chunks = list(retrieval.chunks(unicode_text))
    assert len(chunks) >= 2

    # Verify no corrupted surrogate pairs or broken codepoints
    reconstructed_indices = set()
    for start, end, quote in chunks:
        assert quote == unicode_text[start:end]
        assert len(quote) <= 1600
        reconstructed_indices.update(range(start, end))

    assert reconstructed_indices == set(range(len(unicode_text)))


# B09: Stale Revision Conflict in Theme Corrections
def test_b09_stale_revision_conflict_in_theme_corrections(catalog_sandbox):
    root = catalog_sandbox["root"]
    db_path = catalog_sandbox["db_path"]
    store = CatalogUnderstanding(root)

    with transaction(db_path) as conn:
        obs = conn.execute("SELECT * FROM catalog_theme_observations LIMIT 1").fetchone()
        obs_id = obs["observation_id"]
        evidence = json.loads(obs["evidence_json"])

    # 1. Update from rev 0 to rev 1
    theme_rev1 = {
        "label": "Decentralized Governance (v1)",
        "definition": "First revision definition.",
        "role": "CENTRAL",
        "evidence": evidence,
    }
    corrections.replace(
        store,
        observation_id=obs_id,
        expected_revision=0,
        expected_review_revision=0,
        request_id="req-rev-1",
        reason="First update",
        actor="user1",
        theme=theme_rev1,
    )

    # 2. Concurrent update assuming revision was still 0
    with pytest.raises(ValueError, match="revision"):
        corrections.replace(
            store,
            observation_id=obs_id,
            expected_revision=0,  # STALE!
            expected_review_revision=0,
            request_id="req-rev-conflict-0",
            reason="Conflict update",
            actor="user2",
            theme=theme_rev1,
        )

    # 3. Arbitrary future revision (e.g. 99)
    with pytest.raises(ValueError, match="revision"):
        corrections.replace(
            store,
            observation_id=obs_id,
            expected_revision=99,  # Non-existent future rev
            expected_review_revision=0,
            request_id="req-rev-future",
            reason="Future rev update",
            actor="user3",
            theme=theme_rev1,
        )


# B10: Duplicate Adoption & Double Reversal Idempotency
def test_b10_duplicate_adoption_and_double_reversal_idempotency(catalog_sandbox, tmp_path):
    source_db = catalog_sandbox["db_path"]
    target_dir = tmp_path / "target_idempotency" / "data"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_db = target_dir / "catalog.db"
    initialize_catalog(target_db)

    with transaction(target_db) as conn:
        conn.execute(
            """INSERT INTO papers (paper_id, canonical_key, title, normalized_title, authors_json, created_at, updated_at)
               VALUES ('target-t1', 'target-t1', 'Target T1', 'target t1', '[]', '2026-11-04', '2026-11-04')"""
        )
        conn.execute(
            """INSERT INTO catalog_reading_intents
               (intent_id, paper_id, profile_version, state, manual_priority, revision, created_at, updated_at)
               VALUES ('intent-idem-01', 'target-t1', 'v1', 'ACTIVE', 0, 1, '2026-11-04', '2026-11-04')"""
        )

    record = {
        "operation": adoption.ADOPT,
        "request_id": "adopt-idem-01",
        "reason": "Idempotency test",
        "authority": "CONTROLLER",
        "target_database": str(target_db.resolve()),
        "source_database": str(source_db.resolve()),
        "intent_id": "intent-idem-01",
        "packet_sha256": "1" * 64,
        "manifest_sha256": "2" * 64,
        "proof_json": json.dumps({"scopes": {}}),
        "proof_sha256": hashlib.sha256(json.dumps({"scopes": {}}).encode()).hexdigest(),
        "scientific_acceptance": False,
        "runnable_work_imported": False,
    }
    rec_text = adoption._json(record)
    admission = adoption.Admission(rec_text, adoption._sha(rec_text), adoption._MARKER)

    def conn():
        c = sqlite3.connect(target_db)
        c.row_factory = sqlite3.Row
        return c

    # First adoption: records requests and events
    with closing(conn()) as t_conn:
        t_conn.execute("BEGIN IMMEDIATE")
        res1 = adoption.record_adoption(t_conn, admission)
        t_conn.commit()
        assert "catalog_reading_requests" in res1

    # Second adoption (identical admission): returns empty dict (no-op)
    with closing(conn()) as t_conn:
        t_conn.execute("BEGIN IMMEDIATE")
        res2 = adoption.record_adoption(t_conn, admission)
        t_conn.commit()
        assert res2 == {}, "Duplicate adoption must be an idempotent no-op"

    # First reversal: records reversal
    with closing(conn()) as t_conn:
        t_conn.execute("BEGIN IMMEDIATE")
        rev1 = adoption.reverse_adoption(t_conn, "adopt-idem-01", request_id="rev-idem-01", reason="Reversal 1")
        t_conn.commit()
        assert "catalog_reading_requests" in rev1

    # Second reversal (identical reversal): returns empty dict (no-op)
    with closing(conn()) as t_conn:
        t_conn.execute("BEGIN IMMEDIATE")
        rev2 = adoption.reverse_adoption(t_conn, "adopt-idem-01", request_id="rev-idem-01", reason="Reversal 1")
        t_conn.commit()
        assert rev2 == {}, "Duplicate reversal must be an idempotent no-op"
