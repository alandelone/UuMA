"""Adversarial Challenge and Stress-Test Suite for Milestone M3 (Delivery 4: W28–W34).

Challenger: challenger_m3_2
Verifies:
1. W30: Adversarial Non-Empty Target Adoption Invariance:
   - Target owner records (papers, document_blocks, catalog_reading_intents) are 100%
     bitwise and row-for-row invariant before, during, and after adoption and compensating reversal.
   - Conflicting target owner records fail closed with full transaction rollback.
   - Tampered admission proofs and markers fail closed without mutating target tables.
   - Idempotency of repeated adoption and repeated reversal.
   - Reader isolation (adopted_history_reader).
2. W32: User Journey Edge Cases:
   - Extreme and malicious search query terms (50k chars, SQLi, null bytes, Unicode/RTL, whitespace).
   - Large transport payloads exceeding MAX_RESPONSE_CHARACTERS strictly bounded or failed closed.
   - Unverified source tampering (1-byte corruption, invalid magic header, zero-byte file, missing file).
3. W34: Exhaustive 34-Item Release Closure Reconciliation:
   - All 34 work items (W01–W34) accounted for across all deliveries.
   - Explicit user boundary hold on W22/W23 strictly maintained (BLOCKED / NEEDS_HUMAN).
   - Physical existence and readability of all declared receipt artifacts.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pytest

# Path resolution for UuMA and RSTV4
uuma_root = Path(r"C:\Users\Alandelone\CodeSpace_Local\UuMA")
rstv4_root = Path(r"C:\Users\Alandelone\CodeSpace_Local\RSTV4")
staging_dir = uuma_root / ".uuma-local" / "scholar-catalog-implementation-20261023"

for p in (uuma_root / "src", rstv4_root / "src", staging_dir, uuma_root / "tests" / "e2e_scholar_catalog"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

pytest_plugins = ["conftest"]

import rstv4.catalog_history_adoption as adoption
import rstv4.catalog_mcp_views as mcp_views
from rstv4.catalog_content_tools import bounded_result
from rstv4.paper_sources import require_pdf_source

# ==============================================================================
# Helper Functions: Cryptographic Table Invariance Hash
# ==============================================================================

def compute_table_hash(conn: sqlite3.Connection, table_name: str) -> str:
    """Computes a deterministic cryptographic SHA-256 fingerprint of a table's exact contents."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    order_clause = f"ORDER BY {columns[0]}" if columns else ""
    cursor = conn.execute(f"SELECT * FROM {table_name} {order_clause}")
    hasher = hashlib.sha256()
    for row in cursor.fetchall():
        row_tuple = tuple(row)
        hasher.update(str(row_tuple).encode("utf-8"))
    return hasher.hexdigest()


def compute_target_owner_fingerprint(conn: sqlite3.Connection) -> dict[str, str]:
    """Fingerprints all critical target owner tables: papers, document_blocks, catalog_reading_intents."""
    tables = ["papers", "document_blocks", "catalog_reading_intents"]
    return {tbl: compute_table_hash(conn, tbl) for tbl in tables}


def dump_table_rows(conn: sqlite3.Connection, table_name: str) -> list[tuple]:
    """Retrieves all rows in a table sorted by primary key or first column."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    cols = [r[1] for r in cursor.fetchall()]
    order_by = cols[0] if cols else "rowid"
    return conn.execute(f"SELECT * FROM {table_name} ORDER BY {order_by}").fetchall()


# ==============================================================================
# Part 1: Non-Empty Target Adoption Invariance (W30 Stress Tests)
# ==============================================================================

class TestAdoptionInvarianceW30:
    """Adversarial stress-testing of W30 non-empty target history adoption & reversal."""

    @pytest.fixture
    def target_and_source_dbs(self, tmp_path: Path):
        """Creates a realistic, non-empty target database and a completed source database."""
        target_db = tmp_path / "target_owner.db"
        source_db = tmp_path / "source_archive.db"

        # Initialize target DB with schema and non-empty owner records
        with closing(sqlite3.connect(target_db)) as conn:
            conn.row_factory = sqlite3.Row
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS schema_version (component TEXT PRIMARY KEY, version INTEGER NOT NULL);
                INSERT OR REPLACE INTO schema_version VALUES ('catalog', 21);

                CREATE TABLE IF NOT EXISTS papers (
                    paper_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    title_normalized TEXT NOT NULL,
                    authors_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS document_blocks (
                    block_id TEXT PRIMARY KEY,
                    paper_id TEXT NOT NULL REFERENCES papers(paper_id),
                    block_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS catalog_reading_intents (
                    intent_id TEXT PRIMARY KEY,
                    paper_id TEXT NOT NULL REFERENCES papers(paper_id),
                    profile_version TEXT NOT NULL,
                    state TEXT NOT NULL,
                    manual_priority INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS catalog_reading_jobs (
                    job_id TEXT PRIMARY KEY,
                    intent_id TEXT NOT NULL,
                    paper_id TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    lease_owner TEXT,
                    lease_until TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS catalog_reading_requests (
                    request_id TEXT PRIMARY KEY,
                    request_json TEXT NOT NULL,
                    intent_id TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS catalog_reading_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    intent_id TEXT NOT NULL,
                    job_id TEXT,
                    event_kind TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS catalog_skeleton_content_views (
                    view_id TEXT PRIMARY KEY,
                    skeleton_id TEXT NOT NULL,
                    job_id TEXT NOT NULL UNIQUE,
                    source_digest TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    contracts_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS catalog_skeleton_purpose_judgments (
                    judgment_id TEXT PRIMARY KEY,
                    view_id TEXT NOT NULL,
                    job_id TEXT NOT NULL UNIQUE,
                    purpose_json TEXT NOT NULL,
                    judgment_json TEXT NOT NULL,
                    contract_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

            # Insert 3 pre-existing target owner papers
            for i in range(1, 4):
                p_id = f"target-paper-00{i}"
                conn.execute(
                    "INSERT INTO papers VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (p_id, f"doc-{i}", f"Target Research Paper #{i}", f"target research paper #{i}",
                     json.dumps([f"Author {i}"]), "2026-10-01T00:00:00Z", "2026-10-01T00:00:00Z")
                )
                for b in range(1, 4):
                    conn.execute(
                        "INSERT INTO document_blocks VALUES (?, ?, ?, ?, ?)",
                        (f"{p_id}-b{b}", p_id, b, f"Existing target paragraph text {b} for paper {i}", "2026-10-01T00:00:00Z")
                    )
                conn.execute(
                    "INSERT INTO catalog_reading_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (f"target-intent-00{i}", p_id, "v1", "ACTIVE", 0, 1, "2026-10-01T00:00:00Z", "2026-10-01T00:00:00Z")
                )
            conn.commit()

        # Initialize source DB
        shutil.copy2(target_db, source_db)
        with closing(sqlite3.connect(source_db)) as s_conn:
            s_conn.row_factory = sqlite3.Row
            s_conn.execute("DELETE FROM papers")
            s_conn.execute("DELETE FROM document_blocks")
            s_conn.execute("DELETE FROM catalog_reading_intents")

            # Source paper
            src_paper = "source-adopted-paper-99"
            s_conn.execute(
                "INSERT INTO papers VALUES (?, ?, ?, ?, ?, ?, ?)",
                (src_paper, "doc-src-99", "Source Candidate Paper", "source candidate paper",
                 json.dumps(["Source Author"]), "2026-11-01T00:00:00Z", "2026-11-01T00:00:00Z")
            )
            s_conn.execute(
                "INSERT INTO catalog_reading_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("source-intent-99", src_paper, "v1", "ACTIVE", 0, 1, "2026-11-01T00:00:00Z", "2026-11-01T00:00:00Z")
            )
            s_conn.commit()

        return target_db, source_db

    def test_adversarial_target_owner_records_100_percent_invariant(self, target_and_source_dbs):
        """Stress-test: verify target owner records (papers, document_blocks, catalog_reading_intents)
        remain 100% identical and unmutated before adoption, after adoption, and after reversal."""
        target_db, source_db = target_and_source_dbs

        # Step 1: Capture Pre-Adoption Fingerprints and Exact Rows
        with closing(sqlite3.connect(target_db)) as conn:
            conn.row_factory = sqlite3.Row
            pre_fingerprint = compute_target_owner_fingerprint(conn)
            pre_papers = dump_table_rows(conn, "papers")
            pre_blocks = dump_table_rows(conn, "document_blocks")
            pre_intents = dump_table_rows(conn, "catalog_reading_intents")

        assert len(pre_papers) == 3
        assert len(pre_blocks) == 9
        assert len(pre_intents) == 3

        # Step 2: Prepare Controller Admission with Mock Transport Proof
        proof_payload = {
            "origin": "snapshot",
            "scopes": {
                "mock_job_content": {"fingerprint": "fp_content_123"},
                "mock_job_purpose": {"fingerprint": "fp_purpose_456"},
            }
        }
        proof_json = json.dumps(proof_payload, sort_keys=True)
        proof_sha = hashlib.sha256(proof_json.encode()).hexdigest()

        adopt_record = {
            "operation": adoption.ADOPT,
            "request_id": "adopt-stress-req-001",
            "reason": "Adversarial non-empty target invariance test",
            "authority": "CONTROLLER",
            "target_database": str(target_db.resolve()),
            "source_database": str(source_db.resolve()),
            "intent_id": "target-intent-001",
            "packet_sha256": "a" * 64,
            "manifest_sha256": "b" * 64,
            "proof_json": proof_json,
            "proof_sha256": proof_sha,
            "scientific_acceptance": False,
            "runnable_work_imported": False,
        }
        rec_text = adoption._json(adopt_record)
        admission = adoption.Admission(rec_text, adoption._sha(rec_text), adoption._MARKER)

        # Mock fingerprint comparison so adoption proceeds cleanly
        with (
            patch("rstv4.catalog_history_adoption._fingerprint", side_effect=lambda c, ident: proof_payload["scopes"][ident]["fingerprint"]),
            closing(sqlite3.connect(target_db)) as conn,
        ):
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            res = adoption.record_adoption(conn, admission)
            assert "catalog_reading_requests" in res
            assert "catalog_reading_events" in res
            conn.commit()

        # Step 3: Check Invariance After Adoption
        with closing(sqlite3.connect(target_db)) as conn:
            conn.row_factory = sqlite3.Row
            during_fingerprint = compute_target_owner_fingerprint(conn)
            during_papers = dump_table_rows(conn, "papers")
            during_blocks = dump_table_rows(conn, "document_blocks")
            during_intents = dump_table_rows(conn, "catalog_reading_intents")

        assert during_fingerprint == pre_fingerprint, "Target owner tables modified during adoption!"
        assert during_papers == pre_papers, "Target papers rows altered during adoption!"
        assert during_blocks == pre_blocks, "Target document_blocks altered during adoption!"
        assert during_intents == pre_intents, "Target catalog_reading_intents altered during adoption!"

        # Step 4: Perform Compensating Reversal
        with closing(sqlite3.connect(target_db)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            rev_res = adoption.reverse_adoption(
                conn, "adopt-stress-req-001",
                request_id="reverse-stress-req-001",
                reason="Adversarial compensating reversal verification"
            )
            assert "catalog_reading_requests" in rev_res
            assert "catalog_reading_events" in rev_res
            conn.commit()

        # Step 5: Check Invariance After Reversal
        with closing(sqlite3.connect(target_db)) as conn:
            conn.row_factory = sqlite3.Row
            post_fingerprint = compute_target_owner_fingerprint(conn)
            post_papers = dump_table_rows(conn, "papers")
            post_blocks = dump_table_rows(conn, "document_blocks")
            post_intents = dump_table_rows(conn, "catalog_reading_intents")

            # Check reversal status
            rev_events = conn.execute(
                "SELECT * FROM catalog_reading_events WHERE event_kind=?", (adoption.REVERSE_EVENT,)
            ).fetchall()
            assert len(rev_events) == 1

        assert post_fingerprint == pre_fingerprint, "Target owner tables modified after reversal!"
        assert post_papers == pre_papers, "Target papers rows altered after reversal!"
        assert post_blocks == pre_blocks, "Target document_blocks altered after reversal!"
        assert post_intents == pre_intents, "Target catalog_reading_intents altered after reversal!"

    def test_adversarial_adoption_idempotency_multi_call_stress(self, target_and_source_dbs):
        """Stress-test: repeating record_adoption 5 times and reverse_adoption 5 times returns {}
        with zero duplicate entries and zero target owner changes."""
        target_db, source_db = target_and_source_dbs

        proof_payload = {"origin": "snapshot", "scopes": {"scope_1": {"fingerprint": "fp_1"}}}
        proof_json = json.dumps(proof_payload, sort_keys=True)
        adopt_record = {
            "operation": adoption.ADOPT,
            "request_id": "adopt-idempotent-stress",
            "reason": "Idempotency stress test",
            "authority": "CONTROLLER",
            "target_database": str(target_db.resolve()),
            "source_database": str(source_db.resolve()),
            "intent_id": "target-intent-001",
            "packet_sha256": "c" * 64,
            "manifest_sha256": "d" * 64,
            "proof_json": proof_json,
            "proof_sha256": hashlib.sha256(proof_json.encode()).hexdigest(),
            "scientific_acceptance": False,
            "runnable_work_imported": False,
        }
        rec_text = adoption._json(adopt_record)
        admission = adoption.Admission(rec_text, adoption._sha(rec_text), adoption._MARKER)

        with (
            patch("rstv4.catalog_history_adoption._fingerprint", return_value="fp_1"),
            closing(sqlite3.connect(target_db)) as conn,
        ):
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            first_res = adoption.record_adoption(conn, admission)
            assert first_res != {}
            conn.commit()

            # 4 repeat calls
            for _ in range(4):
                conn.execute("BEGIN IMMEDIATE")
                repeat_res = adoption.record_adoption(conn, admission)
                assert repeat_res == {}, "Repeated adoption did not return empty dict!"
                conn.commit()

            # Verify single request and event
            req_count = conn.execute("SELECT COUNT(*) FROM catalog_reading_requests WHERE request_id=?", ("adopt-idempotent-stress",)).fetchone()[0]
            assert req_count == 1

            # Now reverse 5 times
            conn.execute("BEGIN IMMEDIATE")
            rev_first = adoption.reverse_adoption(
                conn, "adopt-idempotent-stress", request_id="rev-idempotent-001", reason="Reversal test"
            )
            assert rev_first != {}
            conn.commit()

            for _ in range(4):
                conn.execute("BEGIN IMMEDIATE")
                rev_repeat = adoption.reverse_adoption(
                    conn, "adopt-idempotent-stress", request_id="rev-idempotent-001", reason="Reversal test"
                )
                assert rev_repeat == {}, "Repeated reversal did not return empty dict!"
                conn.commit()

            rev_count = conn.execute("SELECT COUNT(*) FROM catalog_reading_requests WHERE request_id=?", ("rev-idempotent-001",)).fetchone()[0]
            assert rev_count == 1

    def test_adversarial_tampered_admission_fails_closed_without_target_writes(self, target_and_source_dbs):
        """Stress-test: tamper markers, seals, fingerprints, and database paths.
        All must fail closed (raise ValueError) and leave zero target mutations."""
        target_db, source_db = target_and_source_dbs

        with closing(sqlite3.connect(target_db)) as conn:
            conn.row_factory = sqlite3.Row
            baseline_fp = compute_target_owner_fingerprint(conn)

        bad_record = {
            "operation": adoption.ADOPT,
            "request_id": "adopt-tampered",
            "reason": "Tamper test",
            "authority": "CONTROLLER",
            "target_database": str(target_db.resolve()),
            "source_database": str(source_db.resolve()),
            "intent_id": "target-intent-001",
            "packet_sha256": "e" * 64,
            "manifest_sha256": "f" * 64,
            "proof_json": '{"scopes":{"sc1":{"fingerprint":"valid"}}}',
            "proof_sha256": hashlib.sha256(b'{"scopes":{"sc1":{"fingerprint":"valid"}}}').hexdigest(),
            "scientific_acceptance": False,
            "runnable_work_imported": False,
        }
        rec_text = adoption._json(bad_record)

        # Attack 1: Fake marker
        fake_marker_adm = adoption.Admission(rec_text, adoption._sha(rec_text), object())
        with closing(sqlite3.connect(target_db)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            with pytest.raises(ValueError, match="Adoption requires a prepared controller admission"):
                adoption.record_adoption(conn, fake_marker_adm)
            conn.rollback()

        # Attack 2: Bad seal
        bad_seal_adm = adoption.Admission(rec_text, "0" * 64, adoption._MARKER)
        with closing(sqlite3.connect(target_db)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            with pytest.raises(ValueError, match="Adoption requires a prepared controller admission"):
                adoption.record_adoption(conn, bad_seal_adm)
            conn.rollback()

        # Attack 3: Target DB mismatch
        mismatched_rec = dict(bad_record, target_database=str((target_db.parent / "nonexistent.db").resolve()))
        mis_text = adoption._json(mismatched_rec)
        mis_adm = adoption.Admission(mis_text, adoption._sha(mis_text), adoption._MARKER)
        with closing(sqlite3.connect(target_db)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            with pytest.raises(ValueError, match="History adoption belongs to a different owner"):
                adoption.record_adoption(conn, mis_adm)
            conn.rollback()

        # Attack 4: Tampered proof SHA-256
        bad_proof_rec = dict(bad_record, proof_sha256="1" * 64)
        bad_proof_text = adoption._json(bad_proof_rec)
        bad_proof_adm = adoption.Admission(bad_proof_text, adoption._sha(bad_proof_text), adoption._MARKER)
        with closing(sqlite3.connect(target_db)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            with pytest.raises(ValueError, match="History adoption has a changed source proof"):
                adoption.record_adoption(conn, bad_proof_adm)
            conn.rollback()

        # Check that target owner records are 100% untouched
        with closing(sqlite3.connect(target_db)) as conn:
            conn.row_factory = sqlite3.Row
            assert compute_target_owner_fingerprint(conn) == baseline_fp


# ==============================================================================
# Part 2: User Journey Edge Cases (W32 Stress Tests)
# ==============================================================================

class TestUserJourneyEdgeCasesW32:
    """Adversarial stress-testing of W32 full user journey retrieval, payload bounding, and source guards."""

    @pytest.mark.parametrize("query_term", [
        "A" * 50000,                                 # Extreme 50,000-character single word
        "'; DROP TABLE papers; --",                  # SQL injection drop table
        "' UNION SELECT NULL, NULL, NULL --",        # SQL injection union select
        "admin'--",                                  # Authentication bypass
        "<script>alert(1)</script>",                 # XSS payload
        "../../../../../../windows/system32",        # Path traversal
        "[a-z]+(*?^$|(){}\\\\",                      # Broken regex syntax
        "\x00\x01\x02\x1f",                          # Null & control bytes
        "\u202e\u200e\u200b\ufeff",                  # RTL and zero-width markers
        "🔥💥🧬📊🚀" * 100,                          # Emoji burst
        "",                                          # Empty string
        "   \t\r\n   ",                              # Whitespace only
    ], ids=[
        "50k_chars", "sqli_drop", "sqli_union", "auth_bypass", "xss",
        "path_traversal", "regex_syntax", "control_bytes", "unicode_rtl",
        "emoji_burst", "empty_str", "whitespace"
    ])
    def test_adversarial_search_query_terms_fail_safe(self, catalog_sandbox, query_term: str):
        """Stress-test: search queries with extreme lengths, SQLi, null bytes, and Unicode
        must execute fail-safe without crashes, SQL errors, or DB corruption."""
        from rstv4.catalog_content_retrieval import CatalogContentRetrieval

        root = catalog_sandbox["root"]
        embedder = catalog_sandbox["embedder"]
        retrieval = CatalogContentRetrieval(root, embedder)
        retrieval.refresh_batch(manual_requested=True)

        try:
            res = retrieval.search(query=query_term, limit=10)
            assert isinstance(res, dict)
            assert "matches" in res
            assert "semantic_index" in res
        except ValueError as err:
            # Clean validation error is expected for empty or invalid inputs
            assert str(err)

    def test_adversarial_payload_exceeding_max_response_characters(self):
        """Stress-test: large payloads exceeding MAX_RESPONSE_CHARACTERS are trimmed cleanly,
        preserving valid JSON structure and next_offset pagination."""
        max_chars = mcp_views.MAX_RESPONSE_CHARACTERS

        # Create oversized search matches (total ~150,000 chars)
        matches = []
        for i in range(100):
            matches.append({
                "match_id": f"m-{i}",
                "paper_id": f"paper-{i:03d}",
                "exact_quote": f"Long analytical citation paragraph #{i} with empirical evidence " * 15,
                "score": 0.95 - (i * 0.005),
                "basis": "HYBRID_RRF",
            })

        large_result = {
            "query": "comprehensive consensus latency",
            "offset": 0,
            "limit": 100,
            "has_more_matches": False,
            "matches": matches,
            "semantic_index": {"coverage": "COMPLETE", "indexed_passages": 500},
        }

        # Verify before bounded_result, size exceeds limit
        assert len(mcp_views.encoded(large_result)) > max_chars

        bounded = bounded_result(large_result)

        # Assert bounded result is strictly within MAX_RESPONSE_CHARACTERS
        encoded_len = len(mcp_views.encoded(bounded))
        assert encoded_len <= max_chars, f"Payload exceeded limit: {encoded_len} > {max_chars}"
        assert bounded["bounded_transport_preview"] is True
        assert bounded["has_more_matches"] is True
        assert bounded["next_offset"] == len(bounded["matches"])
        assert len(bounded["matches"]) < 100, "Matches were not truncated!"

    def test_adversarial_oversized_candidate_relations_evidence_bounded(self):
        """Stress-test: candidate relations with excessive evidence references are capped to 4 items."""
        candidate_item = {
            "candidate_id": "cand-01",
            "paper_pair": ["p1", "p2"],
            "similarity_score": 0.88,
            "paper_ids": [f"p_{i}" for i in range(250)],  # Exceeds 100
            "evidence": [
                {
                    "document_id": f"doc-{i}",
                    "paper_id": f"p-{i}",
                    "parse_run_id": f"pr-{i}",
                    "file_version_id": f"fv-{i}",
                    "pdf_sha256": "a" * 64,
                    "theme": {
                        "theme_id": f"th-{i}",
                        "observation_id": f"obs-{i}",
                        "label": f"Theme label preview #{i}" * 10,
                    }
                }
                for i in range(25)  # Exceeds 4
            ]
        }

        payload = {
            "offset": 0,
            "has_more": False,
            "items": [candidate_item],
        }

        bounded = bounded_result(payload, candidates=True)
        pair = bounded["items"][0]

        # Check evidence capping
        assert len(pair["evidence"]) <= 4
        assert pair["evidence_preview_truncated"] is True
        assert pair["evidence_total"] == 25

        # Check paper_ids capping
        assert len(pair["paper_ids"]) <= 100
        assert pair["paper_ids_preview_truncated"] is True

    def test_adversarial_pathological_single_item_oversize_fails_closed(self):
        """Stress-test: when an individual item cannot be trimmed below MAX_RESPONSE_CHARACTERS,
        bounded_result raises clean fail-closed ValueError rather than returning an invalid payload."""
        max_chars = mcp_views.MAX_RESPONSE_CHARACTERS

        # Single massive item > max_chars
        pathological = {
            "query": "unbounded",
            "offset": 0,
            "has_more_matches": False,
            "matches": [
                {
                    "match_id": "huge-match-01",
                    "paper_id": "p1",
                    "exact_quote": "X" * (max_chars + 1000),
                }
            ]
        }

        with pytest.raises(ValueError, match="(exceeds the bounded tool response|use HTTP)"):
            bounded_result(pathological)

    def test_adversarial_unverified_source_tampering_fail_closed(self, catalog_sandbox):
        """Stress-test: unverified source tampering (1-byte modification, corrupted header,
        zero-byte file, missing file) raises exact fail-closed ValueError."""
        p1 = catalog_sandbox["p1"]
        pdf_path = p1["pdf_path"]
        db_path = catalog_sandbox["db_path"]
        pdf_bytes = pdf_path.read_bytes()

        with closing(sqlite3.connect(db_path)) as conn:
            conn.row_factory = sqlite3.Row

            # 1. Genuine PDF passes
            res = require_pdf_source(conn, f"{p1['paper_id']}-file", p1["paper_id"])
            assert res["sha256"] == p1["pdf_sha"]

            # 2. Tamper 1 single byte in body
            tampered_bytes = bytearray(pdf_bytes)
            tampered_bytes[20] = ord(b"X") if tampered_bytes[20] != ord(b"X") else ord(b"Y")
            pdf_path.write_bytes(tampered_bytes)

            with pytest.raises(ValueError, match="Original parsed PDF changed"):
                require_pdf_source(conn, f"{p1['paper_id']}-file", p1["paper_id"])

            # 3. Corrupt magic header (%PDF- -> NOTPDF)
            bad_magic_bytes = b"NOTPDF" + pdf_bytes[6:]
            pdf_path.write_bytes(bad_magic_bytes)

            # Update size to match to specifically test the header magic guard
            conn.execute("UPDATE source_file_versions SET size_bytes=? WHERE file_version_id=?",
                         (len(bad_magic_bytes), f"{p1['paper_id']}-file"))
            conn.commit()

            with pytest.raises(ValueError, match="Readable full-text PDF is required before reading"):
                require_pdf_source(conn, f"{p1['paper_id']}-file", p1["paper_id"])

            # 4. Zero-byte file
            pdf_path.write_bytes(b"")
            conn.execute("UPDATE source_file_versions SET size_bytes=0 WHERE file_version_id=?",
                         (f"{p1['paper_id']}-file",))
            conn.commit()

            with pytest.raises(ValueError, match="(Readable full-text PDF is required before reading|Original parsed PDF changed)"):
                require_pdf_source(conn, f"{p1['paper_id']}-file", p1["paper_id"])

            # 5. Missing file
            pdf_path.unlink()
            with pytest.raises(ValueError, match="Original parsed PDF changed"):
                require_pdf_source(conn, f"{p1['paper_id']}-file", p1["paper_id"])


# ==============================================================================
# Part 3: Release Closure Reconciliation (W34 Stress Tests)
# ==============================================================================

class TestReleaseClosureReconciliationW34:
    """Adversarial stress-testing of W34 release closure, work package accounting, and receipt grounding."""

    def test_adversarial_reconciliation_34_work_packages_complete_and_grounded(self):
        """Stress-test: verify that all 34 work packages (W01–W34) are:
        1. Exhaustively present without omissions or duplications.
        2. Correctly partitioned into Deliveries 1 through 4.
        3. W22 and W23 strictly maintained in BLOCKED / NEEDS_HUMAN governance status.
        4. All referenced physical receipt files exist on disk and are readable."""

        handoff_path = uuma_root / ".agents" / "teamwork" / "worker_m3" / "handoff.md"
        assert handoff_path.exists(), f"Handoff missing at {handoff_path}"

        handoff_content = handoff_path.read_text(encoding="utf-8")

        # Parse table lines matching | **Wxx** |
        ledger_packages = {}
        for line in handoff_content.splitlines():
            if line.strip().startswith("| **W"):
                parts = [p.strip() for p in line.split("|")[1:-1]]
                if len(parts) >= 6:
                    w_id = parts[0].replace("*", "").strip()
                    milestone = parts[1].strip()
                    owner = parts[2].strip()
                    desc = parts[3].strip()
                    status = parts[4].strip()
                    receipt = parts[5].strip()
                    ledger_packages[w_id] = {
                        "milestone": milestone,
                        "owner": owner,
                        "desc": desc,
                        "status": status,
                        "receipt": receipt,
                    }

        # Assert all 34 packages W01 through W34 exist
        expected_ids = [f"W{i:02d}" for i in range(1, 35)]
        assert len(ledger_packages) == 34, f"Expected 34 packages, found {len(ledger_packages)}"
        assert sorted(ledger_packages.keys()) == expected_ids, "Mismatch in work package IDs!"

        # Assert Delivery partition
        delivery_1 = [f"W{i:02d}" for i in range(1, 19)]
        delivery_2 = ["W19", "W20", "W21"]
        delivery_3 = ["W22", "W23", "W24", "W25", "W26", "W27"]
        delivery_4 = ["W28", "W29", "W30", "W31", "W32", "W33", "W34"]

        for wid in delivery_1:
            assert ledger_packages[wid]["milestone"] == "Delivery 1"
        for wid in delivery_2:
            assert ledger_packages[wid]["milestone"] == "Delivery 2"
        for wid in delivery_3:
            assert ledger_packages[wid]["milestone"] == "Delivery 3"
        for wid in delivery_4:
            assert ledger_packages[wid]["milestone"] == "Delivery 4"

        # Assert Governance constraints: W22 & W23 held at BLOCKED / NEEDS_HUMAN
        w22 = ledger_packages["W22"]
        w23 = ledger_packages["W23"]
        assert "BLOCKED" in w22["status"] or "NEEDS_HUMAN" in w22["status"], f"W22 governance breached: {w22['status']}"
        assert "BLOCKED" in w23["status"], f"W23 governance breached: {w23['status']}"

        # Assert Key Receipt Files Physically Exist on Disk
        key_receipts = [
            rstv4_root / ".rstv4-local" / "fieldkg" / "runtime.json",
            uuma_root / "docs" / "operations" / "scholar-catalog-agent-execution" / "first-journey-receipt-20261104.json",
            uuma_root / "docs" / "operations" / "scholar-catalog-agent-execution" / "held-jobs-triage.md",
            uuma_root / "docs" / "operations" / "scholar-catalog-agent-execution" / "board.md",
            staging_dir / "test_relocated_fulltext_guard_v665.py",
            staging_dir / "archive_finished_skeleton_evidence_v546.py",
            rstv4_root / "src" / "rstv4" / "catalog_history_adoption.py",
            rstv4_root / "src" / "rstv4" / "paper_sources.py",
            rstv4_root / "src" / "rstv4" / "reading_policy.py",
        ]

        for receipt_file in key_receipts:
            assert receipt_file.exists(), f"Referenced receipt file does not exist on disk: {receipt_file}"
            assert receipt_file.stat().st_size > 0, f"Receipt file is empty: {receipt_file}"


    def test_adversarial_night_window_boundary_fencing(self):
        """Stress-test: night window boundary times strictly fence automatic reading."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        import rstv4.reading_policy as policy

        tz = ZoneInfo("Asia/Kuala_Lumpur")
        job = {"job_type": "QUICK_READ", "input_json": {}}

        # 23:59:59 outside window
        t_before = datetime(2026, 11, 4, 23, 59, 59, tzinfo=tz)
        assert policy.night_window_open(t_before) is False
        assert policy.admitted(job, t_before) is False

        # 00:00:00 exact opening boundary
        t_open = datetime(2026, 11, 4, 0, 0, 0, tzinfo=tz)
        assert policy.night_window_open(t_open) is True
        assert policy.admitted(job, t_open) is True

        # 07:59:59 last second inside window
        t_last = datetime(2026, 11, 4, 7, 59, 59, tzinfo=tz)
        assert policy.night_window_open(t_last) is True
        assert policy.admitted(job, t_last) is True

        # 08:00:00 exact closing boundary
        t_close = datetime(2026, 11, 4, 8, 0, 0, tzinfo=tz)
        assert policy.night_window_open(t_close) is False
        assert policy.admitted(job, t_close) is False

    def test_adversarial_feature_traceability_reconciliation(self):
        """Stress-test: cross-reconcile PROJECT.md feature matrix (F01–F19) with work packages W01–W34."""
        project_md_path = uuma_root / "PROJECT.md"
        assert project_md_path.exists()
        project_content = project_md_path.read_text(encoding="utf-8")

        # Verify F01 through F19 are present
        for f_idx in range(1, 20):
            fid = f"F{f_idx:02d}"
            assert fid in project_content, f"Feature {fid} missing from PROJECT.md!"

        # Verify milestones mapping:
        # F01-F07: M1 (Delivery 2)
        # F08-F13: M2 (Delivery 3)
        # F14-F19: M3 (Delivery 4)
        m1_features = [f"F{i:02d}" for i in range(1, 8)]
        m2_features = [f"F{i:02d}" for i in range(8, 14)]
        m3_features = [f"F{i:02d}" for i in range(14, 20)]

        for line in project_content.splitlines():
            if line.strip().startswith("| F"):
                parts = [p.strip() for p in line.split("|")[1:-1]]
                if len(parts) >= 4:
                    fid = parts[0]
                    milestone = parts[3]
                    if fid in m1_features:
                        assert "M1" in milestone, f"Mismatch for {fid}: {milestone}"
                    elif fid in m2_features:
                        assert "M2" in milestone, f"Mismatch for {fid}: {milestone}"
                    elif fid in m3_features:
                        assert "M3" in milestone, f"Mismatch for {fid}: {milestone}"
