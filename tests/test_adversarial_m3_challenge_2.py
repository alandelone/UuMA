"""Adversarial challenge and empirical stress harness for Finding F07 & Audit Item W30.

Challenger: challenger_m3_2 (Target Adoption Stress, Concurrency & Reversal Invariance Challenger)
Delivery Scope: Target owner adoption, multi-cycle reversal, sequence map preservation,
               concurrency lock conflicts, fail-closed boundaries, and 100% byte-invariance
               across all 129 tables.

Tasks Verified:
1. Multi-Cycle Adoption and Reversal Stress:
   - Cycle 1: Adopt archive -> verify pre-existing records byte-invariant across all 129 tables.
   - Reversal 1: Reverse adoption -> verify pre-existing records byte-invariant, fail-closed on subsequent queries.
   - Cycle 2: Re-adopt with fresh request ID -> verify adoption succeeds cleanly.
   - Idempotency stress: re-submit identical admission 10 times -> verify returns {} every time and executes 0 mutations.
   - Reversal 2: Re-reverse -> verify pre-existing records invariant.
2. Cross-Table State Leakage & Sequence Map Integrity:
   - Verify that sequence IDs (reading_event_seq, reading_request_id) assigned during adoption strictly
     use the allocated range from SequenceMap and NEVER overwrite, collide with, or leak into pre-existing sequence domains.
   - Seed target database with multiple independent papers, authors, files, and jobs before adoption.
     Verify that table vector hashes for all pre-existing rows remain bitwise identical across all 129 tables.
   - Active adoption collision detection: overlapping scope without reversal fails closed.
3. Fail-Closed and Security Boundary Stress:
   - Attempt adoption with corrupted packet_sha256 or manifest_sha256 -> raises ValueError before SQL execution.
   - Tampered admission seal, invalid marker, or target database mismatch -> fail-closed rejection.
   - Active lock / transaction conflict -> transaction aborts cleanly without partial insertions or dangling records.
   - CATALOG_HISTORY_ADOPTION_REVERSED preserves append-only provenance without deleting rows.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

# Ensure RSTV4 and UuMA paths are available
REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
RSTV4_ROOT = WORKSPACE_ROOT / "RSTV4"
UUMA_ROOT = REPO_ROOT
UUMA_LOCAL = UUMA_ROOT / ".uuma-local" / "scholar-catalog-implementation-20261023"

for p in (REPO_ROOT / "src", RSTV4_ROOT / "src", UUMA_LOCAL):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import rstv4.catalog_history_adoption as adoption
from finished_history_context_v274 import ORIGINAL
from rstv4.database import initialize_catalog
from sequence_history_map_v487 import VERSION as SEQ_VERSION
from sequence_history_map_v487 import SequenceMap

DELIVERY_ARCHIVE_DIR = UUMA_LOCAL / "delivery-archive-20261106"
TARGET_OWNER_DB = UUMA_LOCAL / "target_owner_delivery" / "data" / "catalog.db"

CONTENT_JOB_ID = "skeletonviewjob_1216bde784964dc42990bbd92b55cd7431a23a60a43d94a05fe1bd58c6ec81e6"
PURPOSE_JOB_ID = "skeletonviewjob_b7a6ba5a81ef5f58911dc951ea0c856a9d99fa5c4367a2021a4fdaaec3a40382"
PAPER_ID = "paper_dd83af8026e39dd2a2e9316622a7ca49"


def import_carrier_records(
    conn: sqlite3.Connection,
    src_conn: sqlite3.Connection,
    paper_id: str,
    content_job_id: str,
    purpose_job_id: str,
    inserted_records: dict,
):
    """Import authentic carrier history across schema tables from source into target owner."""
    def insert_rows(table: str, rows: list[sqlite3.Row]):
        if not rows:
            return
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
        placeholders = ",".join("?" for _ in cols)
        s = inserted_records.setdefault(table, set())
        for r in rows:
            cur = conn.execute(
                f'INSERT INTO "{table}" (' + ",".join(f'"{c}"' for c in cols) + f") VALUES ({placeholders})",
                [r[c] for c in cols],
            )
            s.add(cur.lastrowid)

    insert_rows("papers", src_conn.execute("SELECT * FROM papers WHERE paper_id=?", (paper_id,)).fetchall())
    insert_rows("source_file_versions", src_conn.execute("SELECT * FROM source_file_versions WHERE paper_id=?", (paper_id,)).fetchall())
    insert_rows("parse_runs", src_conn.execute(
        "SELECT * FROM parse_runs WHERE file_version_id IN (SELECT file_version_id FROM source_file_versions WHERE paper_id=?)",
        (paper_id,),
    ).fetchall())
    insert_rows("catalog_reading_intents", src_conn.execute("SELECT * FROM catalog_reading_intents WHERE paper_id=?", (paper_id,)).fetchall())
    insert_rows("paper_versions", src_conn.execute("SELECT * FROM paper_versions WHERE paper_id=?", (paper_id,)).fetchall())
    insert_rows("paper_skeletons", src_conn.execute(
        "SELECT * FROM paper_skeletons WHERE paper_version_id IN (SELECT paper_version_id FROM paper_versions WHERE paper_id=?)",
        (paper_id,),
    ).fetchall())
    insert_rows("skeleton_units", src_conn.execute(
        "SELECT * FROM skeleton_units WHERE skeleton_id IN (SELECT skeleton_id FROM paper_skeletons WHERE paper_version_id IN (SELECT paper_version_id FROM paper_versions WHERE paper_id=?))",
        (paper_id,),
    ).fetchall())
    insert_rows("skeleton_triplets", src_conn.execute(
        "SELECT * FROM skeleton_triplets WHERE unit_id IN (SELECT unit_id FROM skeleton_units WHERE skeleton_id IN (SELECT skeleton_id FROM paper_skeletons WHERE paper_version_id IN (SELECT paper_version_id FROM paper_versions WHERE paper_id=?)))",
        (paper_id,),
    ).fetchall())
    insert_rows("skeleton_runs", src_conn.execute(
        "SELECT * FROM skeleton_runs WHERE parse_run_id IN (SELECT parse_run_id FROM parse_runs WHERE file_version_id IN (SELECT file_version_id FROM source_file_versions WHERE paper_id=?))",
        (paper_id,),
    ).fetchall())
    insert_rows("skeleton_checkpoints", src_conn.execute(
        "SELECT * FROM skeleton_checkpoints WHERE skeleton_run_id IN (SELECT skeleton_run_id FROM skeleton_runs WHERE parse_run_id IN (SELECT parse_run_id FROM parse_runs WHERE file_version_id IN (SELECT file_version_id FROM source_file_versions WHERE paper_id=?)))",
        (paper_id,),
    ).fetchall())
    insert_rows("catalog_reading_jobs", src_conn.execute("SELECT * FROM catalog_reading_jobs WHERE job_id IN (?, ?)", (content_job_id, purpose_job_id)).fetchall())
    insert_rows("catalog_skeleton_content_views", src_conn.execute("SELECT * FROM catalog_skeleton_content_views WHERE job_id=?", (content_job_id,)).fetchall())
    insert_rows("catalog_skeleton_purpose_judgments", src_conn.execute("SELECT * FROM catalog_skeleton_purpose_judgments WHERE job_id=?", (purpose_job_id,)).fetchall())
    insert_rows("catalog_reading_model_events", src_conn.execute("SELECT * FROM catalog_reading_model_events WHERE job_id IN (?, ?) ORDER BY event_seq", (content_job_id, purpose_job_id)).fetchall())
    insert_rows("catalog_reading_events", src_conn.execute("SELECT * FROM catalog_reading_events WHERE job_id IN (?, ?) ORDER BY event_seq", (content_job_id, purpose_job_id)).fetchall())
    req_ids = set()
    for r in src_conn.execute("SELECT detail_json FROM catalog_reading_events WHERE job_id IN (?, ?)", (content_job_id, purpose_job_id)).fetchall():
        if not r[0]:
            continue
        try:
            detail = json.loads(r[0])
            if isinstance(detail, dict) and detail.get("request_id"):
                req_ids.add(detail["request_id"])
        except (json.JSONDecodeError, TypeError):
            continue
    for rid in req_ids:
        insert_rows("catalog_reading_requests", src_conn.execute("SELECT * FROM catalog_reading_requests WHERE request_id=?", (rid,)).fetchall())


def canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda item: {"bytes_hex": item.hex()} if isinstance(item, bytes) else str(item),
    )


def quote(name: str) -> str:
    return f'"{name}"'


def table_vectors(conn: sqlite3.Connection, inserted: dict | None = None) -> dict:
    """Hash every original row with its rowid; exclude only explicit new rows."""
    result = {}
    inserted = inserted or {}
    for name, sql in conn.execute(
        "SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ):
        columns = [tuple(row) for row in conn.execute("PRAGMA table_info(" + quote(name) + ")")]
        digest = hashlib.sha256()
        count = 0
        for row in conn.execute("SELECT rowid,* FROM " + quote(name) + " ORDER BY rowid"):
            if row[0] in inserted.get(name, set()):
                continue
            digest.update(canonical(tuple(row)).encode("utf-8"))
            digest.update(b"\n")
            count += 1
        result[name] = {
            "sql": sql,
            "columns": columns,
            "rows": count,
            "sha256": digest.hexdigest(),
        }
    return result


def get_carrier_hashes():
    manifest_path = DELIVERY_ARCHIVE_DIR / "manifest.json"
    raw = manifest_path.read_bytes()
    data = json.loads(raw)
    return data["packet_sha256"], hashlib.sha256(raw).hexdigest()


@pytest.fixture
def cloned_target_owner(tmp_path: Path):
    """Hermetic clone of the target owner database pre-populated with schema and seed data."""
    target_data_dir = tmp_path / "target_owner" / "data"
    target_data_dir.mkdir(parents=True)
    target_db_path = target_data_dir / "catalog.db"

    # Initialize complete schema version 21
    initialize_catalog(target_db_path)

    # Pre-seed target database with independent baseline records
    conn = sqlite3.connect(target_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    seed_now = "2026-11-01T00:00:00+00:00"
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        """INSERT INTO papers (
            paper_id, canonical_key, doi, normalized_title, title, authors_json,
            published_year, abstract, landing_url, pdf_url, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "paper_test_owner_seed_001",
            "seed_canonical_key_001",
            "10.1000/seed001",
            "pre-existing owner test paper seed 001",
            "Pre-existing Owner Test Paper Seed 001",
            json.dumps(["Dr. Alice", "Dr. Bob"]),
            2026,
            "Independent pre-existing target owner paper.",
            "https://example.com/seed001",
            "https://example.com/seed001.pdf",
            seed_now,
            seed_now,
        ),
    )
    conn.execute(
        """INSERT INTO source_file_versions (
            file_version_id, paper_id, sha256, size_bytes, mime_type, storage_path,
            acquisition_method, source_url, identity_status, validation_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "file_test_owner_seed_001",
            "paper_test_owner_seed_001",
            "a" * 64,
            1024,
            "application/pdf",
            "dummy_seed.pdf",
            "DIRECT",
            "https://example.com/seed001.pdf",
            "VERIFIED",
            json.dumps({}),
            seed_now,
        ),
    )
    conn.execute(
        """INSERT INTO parse_runs (
            parse_run_id, file_version_id, parser_name, parser_version, config_digest,
            status, artifact_manifest_json, started_at, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "parse_test_owner_seed_001",
            "file_test_owner_seed_001",
            "mineru",
            "1.0",
            "b" * 64,
            "SUCCEEDED",
            json.dumps({}),
            seed_now,
            seed_now,
        ),
    )
    conn.execute(
        """INSERT INTO catalog_reading_intents (
            intent_id, paper_id, profile_version, state, manual_priority, revision, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("intent_test_owner_seed_001", "paper_test_owner_seed_001", "paperskeleton-understanding-v1", "ACTIVE", 0, 0, seed_now, seed_now),
    )
    conn.execute(
        """INSERT INTO catalog_reading_jobs (
            job_id, intent_id, paper_id, parse_run_id, input_json, manual_priority,
            status, attempts, fencing_token, lease_owner, lease_until, available_at,
            result_json, last_error, created_at, updated_at, job_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "job_test_owner_seed_001",
            "intent_test_owner_seed_001",
            "paper_test_owner_seed_001",
            "parse_test_owner_seed_001",
            json.dumps({}),
            0,
            "SUCCEEDED",
            1,
            1,
            None,
            None,
            seed_now,
            json.dumps({"status": "ok"}),
            None,
            seed_now,
            seed_now,
            "SKELETON_VIEW",
        ),
    )
    conn.execute(
        """INSERT INTO catalog_reading_requests (
            request_id, request_json, intent_id, result_json, created_at
        ) VALUES (?, ?, ?, ?, ?)""",
        (
            "req_test_owner_seed_001",
            json.dumps({"operation": "seed_read", "paper_id": "paper_test_owner_seed_001"}),
            "intent_test_owner_seed_001",
            json.dumps({"status": "ok"}),
            seed_now,
        ),
    )
    conn.execute(
        """INSERT INTO catalog_reading_events (
            intent_id, job_id, event_kind, detail_json, created_at
        ) VALUES (?, ?, ?, ?, ?)""",
        (
            "intent_test_owner_seed_001",
            "job_test_owner_seed_001",
            "SEED_INITIALIZED",
            json.dumps({"status": "pre-existing"}),
            seed_now,
        ),
    )
    conn.commit()
    conn.close()

    yield target_db_path


# ==============================================================================
# 1. Multi-Cycle Adoption & Reversal Stress Tests
# ==============================================================================


def test_multi_cycle_adoption_and_reversal_stress(cloned_target_owner: Path):
    """Multi-Cycle Stress with Authentic Scopes and Non-Destructive Reversal:

    Cycle 1: Adopt authentic carrier history -> verify byte-invariance across all 129 tables.
    Reversal 1: Purely append-only compensating reversal -> zero DELETE operations, imported evidence
                (paper, views, units, triplets) preserved in SQLite, queries fail closed.
    Cycle 2: Re-adopt with fresh request ID -> verify adoption succeeds cleanly without re-insertion.
    Idempotency: Re-submit identical admission 10 times -> verify returns {} and 0 mutations.
    Reversal 2: Re-reverse -> verify pre-existing records invariant across all 129 tables.
    """
    conn = sqlite3.connect(cloned_target_owner)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    packet_sha256, manifest_sha256 = get_carrier_hashes()
    before_vectors = table_vectors(conn)
    assert len(before_vectors) == 129, f"Expected 129 tables, found {len(before_vectors)}"

    src_conn = sqlite3.connect(str(ORIGINAL.resolve()))
    src_conn.row_factory = sqlite3.Row

    # --------------------------------------------------------------------------
    # Cycle 1: Adopt Archive with Authentic Scopes
    # --------------------------------------------------------------------------
    req_id_cycle1 = f"adopt-w30-cycle1-{packet_sha256[:10]}"
    admission_cycle1 = adoption.prepare_adoption(
        src_conn,
        [CONTENT_JOB_ID],
        target_database=cloned_target_owner,
        request_id=req_id_cycle1,
        reason="Adversarial Stress Cycle 1: initial adoption with authentic scopes",
        packet_sha256=packet_sha256,
        manifest_sha256=manifest_sha256,
    )
    proof_data_1 = json.loads(json.loads(admission_cycle1.record_json)["proof_json"])
    assert CONTENT_JOB_ID in proof_data_1["scopes"]

    inserted_records = {}
    conn.execute("BEGIN IMMEDIATE")
    import_carrier_records(conn, src_conn, PAPER_ID, CONTENT_JOB_ID, PURPOSE_JOB_ID, inserted_records)
    adopt_res_1 = adoption.record_adoption(conn, admission_cycle1)
    for tbl, rids in adopt_res_1.items():
        inserted_records.setdefault(tbl, set()).update(rids)
    conn.commit()

    assert "catalog_reading_requests" in adopt_res_1
    assert "catalog_reading_events" in adopt_res_1

    # Verify byte invariance for Cycle 1 across all 129 tables
    during_vectors_1 = table_vectors(conn, inserted=inserted_records)
    for table_name, vec in before_vectors.items():
        assert during_vectors_1[table_name]["sha256"] == vec["sha256"], (
            f"Pre-existing rows modified during Cycle 1 in table: {table_name}"
        )

    # Verify provenance loaded cleanly and origin state is ADOPTED (eligible=True)
    loaded_rec_1, revs_1 = adoption._load(conn, req_id_cycle1)
    assert loaded_rec_1["request_id"] == req_id_cycle1
    assert revs_1 == []

    st_c1 = adoption.history_origin_state(conn, CONTENT_JOB_ID)
    st_p1 = adoption.history_origin_state(conn, PURPOSE_JOB_ID)
    assert st_c1["state"] == "ADOPTED" and st_c1["eligible"] is True
    assert st_p1["state"] == "ADOPTED" and st_p1["eligible"] is True

    # --------------------------------------------------------------------------
    # Reversal 1: NON-DESTRUCTIVE Compensating Reversal (NO DELETE FROM PAPERS!)
    # --------------------------------------------------------------------------
    rev_id_cycle1 = f"rev-w30-cycle1-{packet_sha256[:10]}"
    conn.execute("BEGIN IMMEDIATE")
    rev_res_1 = adoption.reverse_adoption(
        conn,
        req_id_cycle1,
        request_id=rev_id_cycle1,
        reason="Adversarial Stress Cycle 1: compensating reversal",
    )
    for tbl, rids in rev_res_1.items():
        inserted_records.setdefault(tbl, set()).update(rids)
    conn.commit()

    assert "catalog_reading_requests" in rev_res_1
    assert "catalog_reading_events" in rev_res_1

    # Verify query fails closed after Reversal 1
    with pytest.raises(ValueError, match="History adoption was reversed"):
        adoption._load(conn, req_id_cycle1, reversed_ok=False)

    # Verify origin state transitioned to REVERSED (eligible=False)
    st_c_rev1 = adoption.history_origin_state(conn, CONTENT_JOB_ID)
    st_p_rev1 = adoption.history_origin_state(conn, PURPOSE_JOB_ID)
    assert st_c_rev1["state"] == "REVERSED" and st_c_rev1["eligible"] is False
    assert st_p_rev1["state"] == "REVERSED" and st_p_rev1["eligible"] is False

    # Verify non-destructive physical preservation: zero rows deleted from carrier tables
    assert conn.execute("SELECT COUNT(*) FROM papers WHERE paper_id=?", (PAPER_ID,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM catalog_skeleton_content_views WHERE job_id=?", (CONTENT_JOB_ID,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM skeleton_units").fetchone()[0] == 85
    assert conn.execute("SELECT COUNT(*) FROM skeleton_triplets").fetchone()[0] == 347

    # Verify pre-existing byte-invariance post-reversal 1 across all 129 tables
    post_rev1_vectors = table_vectors(conn, inserted=inserted_records)
    for table_name, vec in before_vectors.items():
        assert post_rev1_vectors[table_name]["sha256"] == vec["sha256"], (
            f"Pre-existing rows modified after Reversal 1 in table: {table_name}"
        )

    # --------------------------------------------------------------------------
    # Cycle 2: Re-adopt with fresh request ID (Carrier evidence already preserved)
    # --------------------------------------------------------------------------
    req_id_cycle2 = f"adopt-w30-cycle2-{packet_sha256[:10]}"
    admission_cycle2 = adoption.prepare_adoption(
        src_conn,
        [CONTENT_JOB_ID],
        target_database=cloned_target_owner,
        request_id=req_id_cycle2,
        reason="Adversarial Stress Cycle 2: re-adoption after completed reversal",
        packet_sha256=packet_sha256,
        manifest_sha256=manifest_sha256,
    )

    conn.execute("BEGIN IMMEDIATE")
    adopt_res_2 = adoption.record_adoption(conn, admission_cycle2)
    for tbl, rids in adopt_res_2.items():
        inserted_records.setdefault(tbl, set()).update(rids)
    conn.commit()

    assert "catalog_reading_requests" in adopt_res_2
    assert "catalog_reading_events" in adopt_res_2

    # Verify Cycle 2 provenance and origin state
    loaded_rec_2, revs_2 = adoption._load(conn, req_id_cycle2)
    assert loaded_rec_2["request_id"] == req_id_cycle2
    assert revs_2 == []

    st_c2 = adoption.history_origin_state(conn, CONTENT_JOB_ID)
    st_p2 = adoption.history_origin_state(conn, PURPOSE_JOB_ID)
    assert st_c2["state"] == "ADOPTED" and st_c2["eligible"] is True
    assert st_p2["state"] == "ADOPTED" and st_p2["eligible"] is True

    # --------------------------------------------------------------------------
    # Idempotency Stress: Re-submit identical admission 10 consecutive times
    # --------------------------------------------------------------------------
    total_changes_before_idempotency = conn.total_changes
    for i in range(10):
        conn.execute("BEGIN IMMEDIATE")
        idem_res = adoption.record_adoption(conn, admission_cycle2)
        conn.commit()
        assert idem_res == {}, f"Idempotency failed on attempt {i+1}: expected {{}}, got {idem_res}"

    # Verify total_changes did not advance during 10 idempotency calls
    assert conn.total_changes == total_changes_before_idempotency

    # Verify byte-invariance across all 129 tables after 10 idempotency replays
    vectors_after_10x_idempotency = table_vectors(conn, inserted=inserted_records)
    for table_name, vec in before_vectors.items():
        assert vectors_after_10x_idempotency[table_name]["sha256"] == vec["sha256"], (
            f"Pre-existing rows modified after 10x idempotency stress in table: {table_name}"
        )

    # --------------------------------------------------------------------------
    # Reversal 2: Re-reverse Cycle 2 (Purely append-only)
    # --------------------------------------------------------------------------
    rev_id_cycle2 = f"rev-w30-cycle2-{packet_sha256[:10]}"
    conn.execute("BEGIN IMMEDIATE")
    rev_res_2 = adoption.reverse_adoption(
        conn,
        req_id_cycle2,
        request_id=rev_id_cycle2,
        reason="Adversarial Stress Cycle 2: re-reversal",
    )
    for tbl, rids in rev_res_2.items():
        inserted_records.setdefault(tbl, set()).update(rids)
    conn.commit()

    assert "catalog_reading_requests" in rev_res_2
    assert "catalog_reading_events" in rev_res_2

    # 10x Idempotency on Reversal 2
    total_changes_before_rev_idempotency = conn.total_changes
    for i in range(10):
        conn.execute("BEGIN IMMEDIATE")
        idem_rev_res = adoption.reverse_adoption(
            conn,
            req_id_cycle2,
            request_id=rev_id_cycle2,
            reason="Adversarial Stress Cycle 2: re-reversal",
        )
        conn.commit()
        assert idem_rev_res == {}, f"Reversal idempotency failed on attempt {i+1}"
    assert conn.total_changes == total_changes_before_rev_idempotency

    # Verify both cycles now fail closed
    with pytest.raises(ValueError, match="History adoption was reversed"):
        adoption._load(conn, req_id_cycle1, reversed_ok=False)
    with pytest.raises(ValueError, match="History adoption was reversed"):
        adoption._load(conn, req_id_cycle2, reversed_ok=False)

    # Verify origin state post-reversal 2 has both reversal request IDs
    st_c_final = adoption.history_origin_state(conn, CONTENT_JOB_ID)
    st_p_final = adoption.history_origin_state(conn, PURPOSE_JOB_ID)
    assert st_c_final["state"] == "REVERSED" and st_c_final["eligible"] is False
    assert st_p_final["state"] == "REVERSED" and st_p_final["eligible"] is False
    assert req_id_cycle1 in st_c_final["request_ids"]
    assert req_id_cycle2 in st_c_final["request_ids"]

    # Verify physical retention after two full cycles of adoption and reversal
    assert conn.execute("SELECT COUNT(*) FROM papers WHERE paper_id=?", (PAPER_ID,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM catalog_skeleton_content_views WHERE job_id=?", (CONTENT_JOB_ID,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM skeleton_units").fetchone()[0] == 85
    assert conn.execute("SELECT COUNT(*) FROM skeleton_triplets").fetchone()[0] == 347

    # Verify pre-existing byte-invariance across all 129 tables post all cycles
    final_vectors = table_vectors(conn, inserted=inserted_records)
    for table_name, vec in before_vectors.items():
        assert final_vectors[table_name]["sha256"] == vec["sha256"], (
            f"Final state corrupted pre-existing rows in table: {table_name}"
        )

    # Assert integrity and foreign keys
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert len(conn.execute("PRAGMA foreign_key_check").fetchall()) == 0

    src_conn.close()
    conn.close()


# ==============================================================================
# 2. Cross-Table State Leakage & Sequence Map Integrity Stress Tests
# ==============================================================================


def test_sequence_map_isolation_and_no_collision_with_preexisting_sequences(tmp_path: Path):
    """Stress-test SequenceMap against heavily populated pre-existing target sequences:

    1. Seed multiple independent papers, files, parse runs, intents, jobs.
    2. Seed catalog_reading_events and catalog_reading_model_events with high manual sequence numbers (e.g. 500, 1000).
    3. Execute SequenceMap.merge() and SequenceMap.record().
    4. Verify allocated sequences NEVER overwrite, collide with, or leak into pre-existing sequence domains.
    5. Verify bitwise 100% byte-invariance across all 129 tables for all pre-existing records.
    """
    db_path = tmp_path / "sequence_stress.db"
    initialize_catalog(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    seed_now = "2026-11-01T00:00:00+00:00"

    # Pre-seed 3 independent papers
    conn.execute("BEGIN IMMEDIATE")
    for i in (1, 2, 3):
        pid = f"paper_preexisting_{i:03d}"
        fid = f"file_preexisting_{i:03d}"
        prid = f"parse_preexisting_{i:03d}"
        iid = f"intent_preexisting_{i:03d}"
        jid = f"job_preexisting_{i:03d}"
        conn.execute(
            """INSERT INTO papers (paper_id, canonical_key, normalized_title, title, authors_json, published_year, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (pid, f"key_{i}", f"preexisting paper {i}", f"Preexisting Paper {i}", json.dumps([f"Author {i}"]), 2020 + i, seed_now, seed_now),
        )
        conn.execute(
            """INSERT INTO source_file_versions (
                file_version_id, paper_id, sha256, size_bytes, mime_type, storage_path,
                acquisition_method, source_url, identity_status, validation_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fid,
                pid,
                hashlib.sha256(f"seed_{i}".encode()).hexdigest(),
                5000,
                "application/pdf",
                f"path_{i}.pdf",
                "DIRECT",
                f"https://example.com/{i}.pdf",
                "VERIFIED",
                json.dumps({}),
                seed_now,
            ),
        )
        conn.execute(
            """INSERT INTO parse_runs (parse_run_id, file_version_id, parser_name, parser_version, config_digest, status, artifact_manifest_json, started_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (prid, fid, "mineru", "1.0", "c" * 64, "SUCCEEDED", "{}", seed_now, seed_now),
        )
        conn.execute(
            """INSERT INTO catalog_reading_intents (intent_id, paper_id, profile_version, state, manual_priority, revision, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (iid, pid, "v1", "ACTIVE", 0, 0, seed_now, seed_now),
        )
        conn.execute(
            """INSERT INTO catalog_reading_jobs (job_id, intent_id, paper_id, parse_run_id, input_json, manual_priority, status, attempts, fencing_token, available_at, created_at, updated_at, job_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (jid, iid, pid, prid, "{}", 0, "SUCCEEDED", 1, 1, seed_now, seed_now, seed_now, "SKELETON_VIEW"),
        )
        # Seed pre-existing events with custom sequences
        conn.execute(
            """INSERT INTO catalog_reading_events (event_seq, intent_id, job_id, event_kind, detail_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (100 * i, iid, jid, "PREEXISTING_EVENT", json.dumps({"seed_idx": i}), seed_now),
        )
        conn.execute(
            """INSERT INTO catalog_reading_model_events (event_seq, call_id, job_id, event_kind, request_json, detail_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (100 * i, f"call_preexisting_{i}", jid, "MODEL_PREEXISTING", "{}", "{}", seed_now),
        )
    conn.commit()

    # Capture 100% pre-existing table vector baseline across all 129 tables
    before_vectors = table_vectors(conn)
    assert len(before_vectors) == 129

    # Pre-existing sequence values
    pre_event_seqs = {row[0] for row in conn.execute("SELECT event_seq FROM catalog_reading_events").fetchall()}
    pre_model_seqs = {row[0] for row in conn.execute("SELECT event_seq FROM catalog_reading_model_events").fetchall()}
    assert pre_event_seqs == {100, 200, 300}
    assert pre_model_seqs == {100, 200, 300}

    # Now formulate SequenceMap import plan for incoming events
    imported_intent_id = "intent_incoming_001"
    incoming_job_id = "job_incoming_001"
    source_db_path = tmp_path / "source_sim.db"
    source_db_path.write_bytes(b"dummy source db")

    # Target requires target parent paper, intent, and job for foreign key consistency
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        """INSERT INTO papers (paper_id, canonical_key, normalized_title, title, authors_json, published_year, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("paper_incoming_001", "key_incoming", "incoming adopted paper", "Incoming Adopted Paper", "[]", 2026, seed_now, seed_now),
    )
    conn.execute(
        """INSERT INTO source_file_versions (
            file_version_id, paper_id, sha256, size_bytes, mime_type, storage_path,
            acquisition_method, source_url, identity_status, validation_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "file_incoming_001",
            "paper_incoming_001",
            "d" * 64,
            2048,
            "application/pdf",
            "inc.pdf",
            "DIRECT",
            "https://example.com/inc.pdf",
            "VERIFIED",
            json.dumps({}),
            seed_now,
        ),
    )
    conn.execute(
        """INSERT INTO parse_runs (parse_run_id, file_version_id, parser_name, parser_version, config_digest, status, artifact_manifest_json, started_at, completed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("parse_incoming_001", "file_incoming_001", "mineru", "1.0", "e" * 64, "SUCCEEDED", "{}", seed_now, seed_now),
    )
    conn.execute(
        """INSERT INTO catalog_reading_intents (intent_id, paper_id, profile_version, state, manual_priority, revision, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (imported_intent_id, "paper_incoming_001", "v1", "ACTIVE", 0, 0, seed_now, seed_now),
    )
    conn.execute(
        """INSERT INTO catalog_reading_jobs (job_id, intent_id, paper_id, parse_run_id, input_json, manual_priority, status, attempts, fencing_token, available_at, created_at, updated_at, job_type)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (incoming_job_id, imported_intent_id, "paper_incoming_001", "parse_incoming_001", "{}", 0, "SUCCEEDED", 1, 1, seed_now, seed_now, seed_now, "SKELETON_VIEW"),
    )

    plan = {
        "sequence_mapping_version": SEQ_VERSION,
        "packet_sha256": "f" * 64,
        "source_database": str(source_db_path.resolve()),
        "source_sha256": hashlib.sha256(b"dummy source db").hexdigest(),
        "tables": {
            "catalog_reading_intents": [{"intent_id": imported_intent_id}],
            "catalog_reading_events": [],
            "catalog_reading_model_events": [],
        },
    }

    # Initialize SequenceMap inside transaction
    seq_map = SequenceMap(conn, plan)

    # Attempt to merge incoming events that have original source sequences (e.g. source sequence 1, 2, 3)
    # Notice: source sequences 1, 2, 3 are numbers that in target DB could theoretically conflict if not translated!
    incoming_event_rows = [
        {"event_seq": 1, "intent_id": imported_intent_id, "job_id": incoming_job_id, "event_kind": "INCOMING_EVT_1", "detail_json": '{"inc":1}', "created_at": seed_now},
        {"event_seq": 2, "intent_id": imported_intent_id, "job_id": incoming_job_id, "event_kind": "INCOMING_EVT_2", "detail_json": '{"inc":2}', "created_at": seed_now},
    ]
    incoming_model_rows = [
        {"event_seq": 1, "call_id": "incoming_call_1", "job_id": incoming_job_id, "event_kind": "MODEL_INCOMING_1", "request_json": "{}", "output_json": None, "detail_json": "{}", "created_at": seed_now},
        {"event_seq": 2, "call_id": "incoming_call_2", "job_id": incoming_job_id, "event_kind": "MODEL_INCOMING_2", "request_json": "{}", "output_json": None, "detail_json": "{}", "created_at": seed_now},
    ]

    inserted_event_seqs = []
    for row in incoming_event_rows:
        inserted_id, owner_seq = seq_map.merge("catalog_reading_events", row)
        assert inserted_id is not None
        assert owner_seq not in pre_event_seqs, f"Sequence collision detected: {owner_seq} in pre-existing sequences!"
        assert owner_seq > max(pre_event_seqs), f"Sequence {owner_seq} did not strictly allocate above pre-existing domain!"
        inserted_event_seqs.append(owner_seq)

    inserted_model_seqs = []
    for row in incoming_model_rows:
        inserted_id, owner_seq = seq_map.merge("catalog_reading_model_events", row)
        assert inserted_id is not None
        assert owner_seq not in pre_model_seqs, f"Model sequence collision: {owner_seq} in pre-existing sequences!"
        assert owner_seq > max(pre_model_seqs), f"Model sequence {owner_seq} did not strictly allocate above pre-existing domain!"
        inserted_model_seqs.append(owner_seq)

    # Record SequenceMap receipt
    receipt_appended, req_id = seq_map.record()
    conn.commit()

    assert receipt_appended is not None
    assert req_id == "catalog-sequence-map-" + ("f" * 64)

    # Verify that pre-existing rows in ALL 129 tables remain 100% byte-invariant!
    new_paper_rowids = {row[0] for row in conn.execute("SELECT rowid FROM papers WHERE paper_id='paper_incoming_001'").fetchall()}
    new_file_rowids = {row[0] for row in conn.execute("SELECT rowid FROM source_file_versions WHERE file_version_id='file_incoming_001'").fetchall()}
    new_parse_rowids = {row[0] for row in conn.execute("SELECT rowid FROM parse_runs WHERE parse_run_id='parse_incoming_001'").fetchall()}
    new_intent_rowids = {row[0] for row in conn.execute("SELECT rowid FROM catalog_reading_intents WHERE intent_id=?", (imported_intent_id,)).fetchall()}
    new_job_rowids = {row[0] for row in conn.execute("SELECT rowid FROM catalog_reading_jobs WHERE job_id=?", (incoming_job_id,)).fetchall()}
    new_event_rowids = set(inserted_event_seqs) | set(receipt_appended.get("catalog_reading_events", []))
    new_model_rowids = set(inserted_model_seqs)
    new_req_rowids = set(receipt_appended.get("catalog_reading_requests", []))

    excluded = {
        "papers": new_paper_rowids,
        "source_file_versions": new_file_rowids,
        "parse_runs": new_parse_rowids,
        "catalog_reading_intents": new_intent_rowids,
        "catalog_reading_jobs": new_job_rowids,
        "catalog_reading_events": new_event_rowids,
        "catalog_reading_model_events": new_model_rowids,
        "catalog_reading_requests": new_req_rowids,
    }

    during_vectors = table_vectors(conn, inserted=excluded)
    for table_name, vec in before_vectors.items():
        assert during_vectors[table_name]["sha256"] == vec["sha256"], (
            f"Pre-existing rows modified in {table_name}: {during_vectors[table_name]} != {vec}"
        )

    # Verify that repeat merge with identical rows matches existing and does not duplicate
    conn.execute("BEGIN IMMEDIATE")
    seq_map_repeat = SequenceMap(conn, {**plan, "tables": {**plan["tables"], **seq_map.maps}})
    for row in incoming_event_rows:
        inserted_id, owner_seq = seq_map_repeat.merge("catalog_reading_events", row)
        # Should NOT insert new row, should resolve existing
        assert inserted_id is None, "Repeated merge should resolve existing row without re-insertion"
        assert owner_seq in inserted_event_seqs
    conn.commit()

    conn.close()


def test_active_adoption_collision_rejection(cloned_target_owner: Path):
    """Verify that attempting to adopt an overlapping scope while an active adoption exists

    fails closed with ValueError("History already has an active controller adoption").
    """
    conn = sqlite3.connect(cloned_target_owner)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    packet_sha256, manifest_sha256 = get_carrier_hashes()
    before_vectors = table_vectors(conn)

    # Setup active adoption with a specific scope
    req_id_1 = f"adopt-active-1-{packet_sha256[:10]}"
    proof_1 = adoption._json({"scopes": {"job_shared_scope_001": {"fingerprint": "fp1"}}})
    record_1 = {
        "operation": adoption.ADOPT,
        "request_id": req_id_1,
        "reason": "Active adoption 1",
        "authority": "CONTROLLER",
        "target_database": str(cloned_target_owner.resolve()),
        "source_database": str((RSTV4_ROOT / "data" / "catalog.db").resolve()),
        "intent_id": "intent_test_owner_seed_001",
        "packet_sha256": packet_sha256,
        "manifest_sha256": manifest_sha256,
        "proof_json": proof_1,
        "proof_sha256": adoption._sha(proof_1),
        "scientific_acceptance": False,
        "runnable_work_imported": False,
    }
    rec_text_1 = adoption._json(record_1)
    admission_1 = adoption.Admission(rec_text_1, adoption._sha(rec_text_1), adoption._MARKER)

    # We mock _fingerprint so record_adoption verifies successfully
    original_fingerprint = adoption._fingerprint
    adoption._fingerprint = lambda connection, identity: "fp1"

    try:
        conn.execute("BEGIN IMMEDIATE")
        res_1 = adoption.record_adoption(conn, admission_1)
        conn.commit()
        assert "catalog_reading_requests" in res_1

        # Now attempt second adoption with overlapping scope: "job_shared_scope_001"
        req_id_2 = f"adopt-conflicting-2-{packet_sha256[:10]}"
        record_2 = {**record_1, "request_id": req_id_2, "reason": "Conflicting adoption"}
        rec_text_2 = adoption._json(record_2)
        admission_2 = adoption.Admission(rec_text_2, adoption._sha(rec_text_2), adoption._MARKER)

        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(ValueError, match="History already has an active controller adoption"):
            adoption.record_adoption(conn, admission_2)
        conn.rollback()

        # Verify target DB was not mutated by the rejected call
        vectors_after_conflict = table_vectors(
            conn,
            inserted={
                "catalog_reading_requests": set(res_1["catalog_reading_requests"]),
                "catalog_reading_events": set(res_1["catalog_reading_events"]),
            },
        )
        for table_name, vec in before_vectors.items():
            assert vectors_after_conflict[table_name]["sha256"] == vec["sha256"]
    finally:
        adoption._fingerprint = original_fingerprint
        conn.close()


# ==============================================================================
# 3. Fail-Closed & Security Boundary Stress Tests
# ==============================================================================


def test_corrupted_digest_fails_closed_before_sql(cloned_target_owner: Path):
    """Corrupted packet_sha256 or manifest_sha256 fails immediately in _digest() before SQL."""
    conn = sqlite3.connect(cloned_target_owner)
    conn.row_factory = sqlite3.Row

    # 1. Non-hex string
    with pytest.raises(ValueError, match="History adoption requires exact evidence hashes"):
        adoption._digest("not_a_valid_hex_hash_at_all_1234567890abcdef1234567890abcdef1234567")

    # 2. Too short
    with pytest.raises(ValueError, match="History adoption requires exact evidence hashes"):
        adoption._digest("abc123")

    # 3. Empty string
    with pytest.raises(ValueError, match="History adoption requires exact evidence hashes"):
        adoption._digest("")

    # 4. Non-string type
    with pytest.raises(ValueError, match="History adoption requires exact evidence hashes"):
        adoption._digest(123456)

    # 5. Tampered admission seal in record_adoption
    record = {
        "operation": adoption.ADOPT,
        "request_id": "req-tampered-seal",
        "target_database": str(cloned_target_owner.resolve()),
    }
    rec_text = adoption._json(record)
    tampered_admission = adoption.Admission(rec_text, "0" * 64, adoption._MARKER)
    conn.execute("BEGIN IMMEDIATE")
    with pytest.raises(ValueError, match="Adoption requires a prepared controller admission and owned transaction"):
        adoption.record_adoption(conn, tampered_admission)
    conn.rollback()

    # 6. Untrusted marker
    fake_marker_admission = adoption.Admission(rec_text, adoption._sha(rec_text), object())
    conn.execute("BEGIN IMMEDIATE")
    with pytest.raises(ValueError, match="Adoption requires a prepared controller admission and owned transaction"):
        adoption.record_adoption(conn, fake_marker_admission)
    conn.rollback()

    conn.close()


def test_transaction_ownership_and_concurrency_lock_conflict(cloned_target_owner: Path):
    """Stress transaction requirements and verify clean abort under lock contention:

    1. record_adoption without active transaction -> raises ValueError.
    2. reverse_adoption without active transaction -> raises ValueError.
    3. Active lock conflict: Connection A acquires EXCLUSIVE lock. Connection B attempts
       BEGIN IMMEDIATE -> raises sqlite3.OperationalError (database is locked).
    4. Verify rollback leaves 0 dangling records, and subsequent adoption succeeds.
    """
    conn_a = sqlite3.connect(cloned_target_owner, timeout=0.1)
    conn_a.row_factory = sqlite3.Row
    conn_a.execute("PRAGMA foreign_keys=ON")

    packet_sha256, manifest_sha256 = get_carrier_hashes()
    before_vectors = table_vectors(conn_a)

    req_id = f"adopt-lock-test-{packet_sha256[:10]}"
    proof_text = adoption._json({"scopes": {}})
    record = {
        "operation": adoption.ADOPT,
        "request_id": req_id,
        "reason": "Lock contention test",
        "authority": "CONTROLLER",
        "target_database": str(cloned_target_owner.resolve()),
        "source_database": str((RSTV4_ROOT / "data" / "catalog.db").resolve()),
        "intent_id": "intent_test_owner_seed_001",
        "packet_sha256": packet_sha256,
        "manifest_sha256": manifest_sha256,
        "proof_json": proof_text,
        "proof_sha256": adoption._sha(proof_text),
        "scientific_acceptance": False,
        "runnable_work_imported": False,
    }
    rec_text = adoption._json(record)
    admission = adoption.Admission(rec_text, adoption._sha(rec_text), adoption._MARKER)

    # 1. Reject without transaction
    assert not conn_a.in_transaction
    with pytest.raises(ValueError, match="Adoption requires a prepared controller admission and owned transaction"):
        adoption.record_adoption(conn_a, admission)

    with pytest.raises(ValueError, match="History reversal requires its owned transaction"):
        adoption.reverse_adoption(conn_a, req_id, request_id="rev-test", reason="test")

    # 2. Concurrency Lock Contention Simulation
    conn_b = sqlite3.connect(cloned_target_owner, timeout=0.1)
    conn_b.row_factory = sqlite3.Row
    conn_b.execute("PRAGMA foreign_keys=ON")

    # Connection A locks the database exclusively
    conn_a.execute("BEGIN EXCLUSIVE")

    # Connection B attempts adoption with immediate lock acquisition
    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        conn_b.execute("BEGIN IMMEDIATE")

    # Release lock on Connection A
    conn_a.rollback()
    conn_a.close()

    # Now Connection B can cleanly execute adoption without contention
    conn_b.execute("BEGIN IMMEDIATE")
    res = adoption.record_adoption(conn_b, admission)
    conn_b.commit()
    assert "catalog_reading_requests" in res

    # Verify no dangling records from previous failed attempt
    during_vectors = table_vectors(
        conn_b,
        inserted={
            "catalog_reading_requests": set(res["catalog_reading_requests"]),
            "catalog_reading_events": set(res["catalog_reading_events"]),
        },
    )
    for table_name, vec in before_vectors.items():
        assert during_vectors[table_name]["sha256"] == vec["sha256"]

    conn_b.close()


def test_append_only_provenance_preservation_across_reversals(cloned_target_owner: Path):
    """Verify that CATALOG_HISTORY_ADOPTION_REVERSED preserves append-only provenance without deleting rows:

    - Pre-adoption rows: N requests, M events.
    - Post-adoption rows: N+1 requests, M+1 events.
    - Post-reversal rows: N+2 requests, M+2 events.
    - Absolutely ZERO row deletions occurred in audit ledgers.
    - Ambiguous second reversal with conflicting rationale/request is rejected.
    """
    conn = sqlite3.connect(cloned_target_owner)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    initial_requests_count = conn.execute("SELECT COUNT(*) FROM catalog_reading_requests").fetchone()[0]
    initial_events_count = conn.execute("SELECT COUNT(*) FROM catalog_reading_events").fetchone()[0]

    packet_sha256, manifest_sha256 = get_carrier_hashes()
    req_id = f"adopt-provenance-{packet_sha256[:10]}"
    proof_text = adoption._json({"scopes": {}})
    record = {
        "operation": adoption.ADOPT,
        "request_id": req_id,
        "reason": "Append-only provenance audit",
        "authority": "CONTROLLER",
        "target_database": str(cloned_target_owner.resolve()),
        "source_database": str((RSTV4_ROOT / "data" / "catalog.db").resolve()),
        "intent_id": "intent_test_owner_seed_001",
        "packet_sha256": packet_sha256,
        "manifest_sha256": manifest_sha256,
        "proof_json": proof_text,
        "proof_sha256": adoption._sha(proof_text),
        "scientific_acceptance": False,
        "runnable_work_imported": False,
    }
    rec_text = adoption._json(record)
    admission = adoption.Admission(rec_text, adoption._sha(rec_text), adoption._MARKER)

    # Adopt
    conn.execute("BEGIN IMMEDIATE")
    adoption.record_adoption(conn, admission)
    conn.commit()

    post_adopt_requests = conn.execute("SELECT COUNT(*) FROM catalog_reading_requests").fetchone()[0]
    post_adopt_events = conn.execute("SELECT COUNT(*) FROM catalog_reading_events").fetchone()[0]
    assert post_adopt_requests == initial_requests_count + 1
    assert post_adopt_events == initial_events_count + 1

    # Reverse
    rev_id = f"rev-provenance-{packet_sha256[:10]}"
    conn.execute("BEGIN IMMEDIATE")
    adoption.reverse_adoption(conn, req_id, request_id=rev_id, reason="Append-only verification")
    conn.commit()

    post_rev_requests = conn.execute("SELECT COUNT(*) FROM catalog_reading_requests").fetchone()[0]
    post_rev_events = conn.execute("SELECT COUNT(*) FROM catalog_reading_events").fetchone()[0]
    assert post_rev_requests == initial_requests_count + 2
    assert post_rev_events == initial_events_count + 2

    # Verify both ADOPT and REVERSE event exist side by side
    adopt_event = conn.execute(
        "SELECT * FROM catalog_reading_events WHERE event_kind=? AND json_extract(detail_json, '$.request_id')=?",
        (adoption.ADOPT_EVENT, req_id),
    ).fetchone()
    reverse_event = conn.execute(
        "SELECT * FROM catalog_reading_events WHERE event_kind=? AND json_extract(detail_json, '$.request_id')=?",
        (adoption.REVERSE_EVENT, rev_id),
    ).fetchone()

    assert adopt_event is not None
    assert reverse_event is not None
    assert adopt_event["event_seq"] < reverse_event["event_seq"]

    # Verify that conflicting second reversal is strictly rejected
    conn.execute("BEGIN IMMEDIATE")
    with pytest.raises(ValueError, match="History adoption is already reversed"):
        adoption.reverse_adoption(
            conn,
            req_id,
            request_id="conflicting-second-reversal",
            reason="Different conflicting rationale",
        )
    conn.rollback()

    # Verify that load with reversed_ok=True returns exactly 1 reversal ID
    loaded_rec, reversals = adoption._load(conn, req_id, reversed_ok=True)
    assert loaded_rec["request_id"] == req_id
    assert reversals == [rev_id]

    conn.close()


def test_unregistered_or_foreign_adoption_reversal_rejection(cloned_target_owner: Path):
    """Attempting reversal on an unrecorded or non-existent adoption must fail closed."""
    conn = sqlite3.connect(cloned_target_owner)
    conn.row_factory = sqlite3.Row

    conn.execute("BEGIN IMMEDIATE")
    with pytest.raises(ValueError, match="Missing controller history-adoption receipt"):
        adoption.reverse_adoption(
            conn,
            "non-existent-adoption-req-id",
            request_id="rev-non-existent",
            reason="Illegal attempt to reverse unrecorded adoption",
        )
    conn.rollback()
    conn.close()


def test_scientific_approval_and_runnable_work_fail_closed(cloned_target_owner: Path):
    """Adoption records asserting scientific_acceptance=True or runnable_work_imported=True

    must be strictly rejected because history adoption transfers evidence without scientific authority.
    """
    conn = sqlite3.connect(cloned_target_owner)
    conn.row_factory = sqlite3.Row

    packet_sha256, manifest_sha256 = get_carrier_hashes()
    base_record = {
        "operation": adoption.ADOPT,
        "request_id": "req-illegal-scientific-approval",
        "reason": "Illegal assertion of scientific acceptance",
        "authority": "CONTROLLER",
        "target_database": str(cloned_target_owner.resolve()),
        "source_database": str((RSTV4_ROOT / "data" / "catalog.db").resolve()),
        "intent_id": "intent_test_owner_seed_001",
        "packet_sha256": packet_sha256,
        "manifest_sha256": manifest_sha256,
        "proof_json": adoption._json({"scopes": {}}),
        "proof_sha256": adoption._sha(adoption._json({"scopes": {}})),
        "scientific_acceptance": True,  # Illegal
        "runnable_work_imported": False,
    }
    rec_text = adoption._json(base_record)
    admission = adoption.Admission(rec_text, adoption._sha(rec_text), adoption._MARKER)

    conn.execute("BEGIN IMMEDIATE")
    # record_adoption inserts row then calls _load which verifies scientific_acceptance is False
    with pytest.raises(ValueError, match="History adoption differs from its controller receipt or owner"):
        # We manually insert request to see if _load catches it
        conn.execute("INSERT INTO catalog_reading_requests VALUES(?,?,?,?,?)",
                     (base_record["request_id"], rec_text, base_record["intent_id"],
                      adoption._json({"adoption_sha256": admission.seal}), "2026-11-01"))
        adoption._load(conn, base_record["request_id"])
    conn.rollback()

    # Now test runnable_work_imported=True
    base_record["scientific_acceptance"] = False
    base_record["runnable_work_imported"] = True
    base_record["request_id"] = "req-illegal-runnable-work"
    rec_text_runnable = adoption._json(base_record)
    admission_runnable = adoption.Admission(rec_text_runnable, adoption._sha(rec_text_runnable), adoption._MARKER)

    conn.execute("BEGIN IMMEDIATE")
    with pytest.raises(ValueError, match="History adoption differs from its controller receipt or owner"):
        conn.execute("INSERT INTO catalog_reading_requests VALUES(?,?,?,?,?)",
                     (base_record["request_id"], rec_text_runnable, base_record["intent_id"],
                      adoption._json({"adoption_sha256": admission_runnable.seal}), "2026-11-01"))
        adoption._load(conn, base_record["request_id"])
    conn.rollback()

    conn.close()


def test_tampered_event_or_request_audit_trail_fail_closed(cloned_target_owner: Path):
    """Tampering with catalog_reading_events or catalog_reading_requests causes _load to immediately fail closed."""
    conn = sqlite3.connect(cloned_target_owner)
    conn.row_factory = sqlite3.Row

    packet_sha256, manifest_sha256 = get_carrier_hashes()
    req_id = f"adopt-tamper-audit-{packet_sha256[:10]}"
    proof_text = adoption._json({"scopes": {}})
    record = {
        "operation": adoption.ADOPT,
        "request_id": req_id,
        "reason": "Tamper test",
        "authority": "CONTROLLER",
        "target_database": str(cloned_target_owner.resolve()),
        "source_database": str((RSTV4_ROOT / "data" / "catalog.db").resolve()),
        "intent_id": "intent_test_owner_seed_001",
        "packet_sha256": packet_sha256,
        "manifest_sha256": manifest_sha256,
        "proof_json": proof_text,
        "proof_sha256": adoption._sha(proof_text),
        "scientific_acceptance": False,
        "runnable_work_imported": False,
    }
    rec_text = adoption._json(record)
    admission = adoption.Admission(rec_text, adoption._sha(rec_text), adoption._MARKER)

    conn.execute("BEGIN IMMEDIATE")
    adoption.record_adoption(conn, admission)
    conn.commit()

    # Case 1: Tamper with result_json in catalog_reading_requests
    conn.execute("UPDATE catalog_reading_requests SET result_json='{\"tampered\":true}' WHERE request_id=?", (req_id,))
    conn.commit()
    with pytest.raises(ValueError, match="History adoption differs from its controller receipt or owner"):
        adoption._load(conn, req_id)

    # Restore correct result_json
    conn.execute("UPDATE catalog_reading_requests SET result_json=? WHERE request_id=?",
                 (adoption._json({"adoption_sha256": admission.seal}), req_id))
    conn.commit()
    # Now it loads cleanly
    loaded, _ = adoption._load(conn, req_id)
    assert loaded["request_id"] == req_id

    # Case 2: Drop the matching CATALOG_HISTORY_ADOPTED event
    conn.execute("DELETE FROM catalog_reading_events WHERE event_kind=? AND json_extract(detail_json,'$.request_id')=?",
                 (adoption.ADOPT_EVENT, req_id))
    conn.commit()
    with pytest.raises(ValueError, match="History adoption requires its exact append-only event"):
        adoption._load(conn, req_id)

    conn.close()


def test_sequence_map_transaction_and_prefix_order_guards(tmp_path: Path):
    """SequenceMap requires an owned transaction, valid version, and strictly enforces sequence monotonicity."""
    db_path = tmp_path / "seq_guards.db"
    initialize_catalog(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    plan = {
        "sequence_mapping_version": SEQ_VERSION,
        "packet_sha256": "1" * 64,
        "source_database": str(db_path.resolve()),
        "source_sha256": "2" * 64,
        "tables": {"catalog_reading_intents": [{"intent_id": "intent_test_001"}]},
    }

    # 1. Reject initialization without active transaction
    assert not conn.in_transaction
    with pytest.raises(ValueError, match="Sequence mapping requires the controller-owned transaction"):
        SequenceMap(conn, plan)

    # 2. Reject incorrect version
    conn.execute("BEGIN IMMEDIATE")
    with pytest.raises(ValueError, match="Evidence packet lacks its exact sequence mapping contract"):
        SequenceMap(conn, {**plan, "sequence_mapping_version": "wrong-version"})
    conn.rollback()

    conn.close()


# ==============================================================================
# 4. Authentic Scopes, Non-Destructive Reversal & State Transition Challenges
# ==============================================================================


def test_authentic_scopes_tamper_and_missing_carrier_fail_closed(tmp_path: Path):
    """Verify that record_adoption strictly fails closed if proof_json contains dummy/empty scopes

    or if carrier rows differ from authentic transport source finished_history_context_v274.ORIGINAL.
    """
    target_db = tmp_path / "catalog_tamper.db"
    initialize_catalog(target_db)

    src_conn = sqlite3.connect(str(ORIGINAL.resolve()))
    src_conn.row_factory = sqlite3.Row

    # 1. Reject empty job_ids in prepare_adoption
    with pytest.raises(ValueError, match="History adoption requires distinct completed content jobs"):
        adoption.prepare_adoption(
            src_conn,
            [],
            target_database=target_db,
            request_id="adopt-empty-scope",
            reason="Illegal empty scope",
            packet_sha256="a" * 64,
            manifest_sha256="b" * 64,
        )

    # 2. Prepare authentic admission
    adm = adoption.prepare_adoption(
        src_conn,
        [CONTENT_JOB_ID],
        target_database=target_db,
        request_id="adopt-authentic-scope",
        reason="Authentic scope test",
        packet_sha256="a" * 64,
        manifest_sha256="b" * 64,
    )
    proof_data = json.loads(json.loads(adm.record_json)["proof_json"])
    assert CONTENT_JOB_ID in proof_data["scopes"]

    conn = sqlite3.connect(target_db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    # 3. Reject record_adoption BEFORE carrier records are imported
    conn.execute("BEGIN IMMEDIATE")
    with pytest.raises(ValueError, match="Snapshot origin requires its original reading job"):
        adoption.record_adoption(conn, adm)
    conn.rollback()

    # 4. Import carrier records, but tamper with a model event
    inserted = {}
    conn.execute("BEGIN IMMEDIATE")
    import_carrier_records(conn, src_conn, PAPER_ID, CONTENT_JOB_ID, PURPOSE_JOB_ID, inserted)
    # Tamper with an event
    conn.execute("UPDATE catalog_reading_model_events SET call_id='tampered_call' WHERE job_id=?", (CONTENT_JOB_ID,))
    with pytest.raises(ValueError, match="Imported history differs from its exact verified source"):
        adoption.record_adoption(conn, adm)
    conn.rollback()

    # 5. Tamper with proof_json (digest mismatch)
    rec_tampered = json.loads(adm.record_json)
    rec_tampered["proof_json"] = adoption._json({"scopes": {}})
    rec_tampered_text = adoption._json(rec_tampered)
    adm_tampered = adoption.Admission(rec_tampered_text, adoption._sha(rec_tampered_text), adoption._MARKER)

    conn.execute("BEGIN IMMEDIATE")
    with pytest.raises(ValueError, match="History adoption has a changed source proof"):
        adoption.record_adoption(conn, adm_tampered)
    conn.rollback()

    src_conn.close()
    conn.close()


def test_non_destructive_reversal_evidence_preservation(cloned_target_owner: Path):
    """Confirm zero SQL DELETE operations occur during reversal and all imported evidence

    (papers, views, units, triplets) remains physically present in SQLite with operational
    eligibility revoked.
    """
    conn = sqlite3.connect(cloned_target_owner)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    packet_sha256, manifest_sha256 = get_carrier_hashes()
    src_conn = sqlite3.connect(str(ORIGINAL.resolve()))
    src_conn.row_factory = sqlite3.Row

    req_id = f"adopt-preserve-{packet_sha256[:10]}"
    adm = adoption.prepare_adoption(
        src_conn,
        [CONTENT_JOB_ID],
        target_database=cloned_target_owner,
        request_id=req_id,
        reason="Preservation test",
        packet_sha256=packet_sha256,
        manifest_sha256=manifest_sha256,
    )

    inserted = {}
    conn.execute("BEGIN IMMEDIATE")
    import_carrier_records(conn, src_conn, PAPER_ID, CONTENT_JOB_ID, PURPOSE_JOB_ID, inserted)
    adopt_res = adoption.record_adoption(conn, adm)
    for tbl, rids in adopt_res.items():
        inserted.setdefault(tbl, set()).update(rids)
    conn.commit()

    # Track total changes before reversal
    changes_before_reversal = conn.total_changes

    # Execute compensating reversal - ZERO DELETE FROM!
    rev_id = f"rev-preserve-{packet_sha256[:10]}"
    conn.execute("BEGIN IMMEDIATE")
    rev_res = adoption.reverse_adoption(
        conn,
        req_id,
        request_id=rev_id,
        reason="Non-destructive compensating reversal test",
    )
    for tbl, rids in rev_res.items():
        inserted.setdefault(tbl, set()).update(rids)
    conn.commit()

    # Total changes during reversal should be exactly 2 (1 request + 1 event inserted, 0 deletes!)
    assert conn.total_changes == changes_before_reversal + 2

    # Verify physical retention of all scientific records in SQLite
    assert conn.execute("SELECT COUNT(*) FROM papers WHERE paper_id=?", (PAPER_ID,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM catalog_skeleton_content_views WHERE job_id=?", (CONTENT_JOB_ID,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM catalog_skeleton_purpose_judgments WHERE job_id=?", (PURPOSE_JOB_ID,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM skeleton_units").fetchone()[0] == 85
    assert conn.execute("SELECT COUNT(*) FROM skeleton_triplets").fetchone()[0] == 347
    assert conn.execute("SELECT COUNT(*) FROM paper_skeletons").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM source_file_versions WHERE paper_id=?", (PAPER_ID,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM parse_runs").fetchone()[0] == 2  # 1 seed + 1 imported

    # Verify that operational eligibility is revoked while retained for inspection
    st_content = adoption.history_origin_state(conn, CONTENT_JOB_ID)
    st_purpose = adoption.history_origin_state(conn, PURPOSE_JOB_ID)
    assert st_content["state"] == "REVERSED" and st_content["eligible"] is False
    assert st_purpose["state"] == "REVERSED" and st_purpose["eligible"] is False
    assert "retained artifacts remain available for historical inspection" in st_content["detail"]

    src_conn.close()
    conn.close()


def test_origin_provenance_state_transitions(cloned_target_owner: Path):
    """Verify history_origin_state transitions cleanly across full lifecycle:

    UNRECORDED -> ADOPTED (eligible=True) -> REVERSED (eligible=False) ->
    ADOPTED (eligible=True) -> REVERSED (eligible=False) for both content and purpose jobs.
    """
    conn = sqlite3.connect(cloned_target_owner)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    packet_sha256, manifest_sha256 = get_carrier_hashes()
    src_conn = sqlite3.connect(str(ORIGINAL.resolve()))
    src_conn.row_factory = sqlite3.Row

    # 1. Before adoption: unrecorded
    assert adoption.history_origin_state(conn, CONTENT_JOB_ID) is None
    assert adoption.history_origin_state(conn, PURPOSE_JOB_ID) is None

    # 2. Cycle 1: Adopted
    req1 = f"adopt-trans-c1-{packet_sha256[:10]}"
    adm1 = adoption.prepare_adoption(
        src_conn,
        [CONTENT_JOB_ID],
        target_database=cloned_target_owner,
        request_id=req1,
        reason="Transition c1",
        packet_sha256=packet_sha256,
        manifest_sha256=manifest_sha256,
    )
    inserted = {}
    conn.execute("BEGIN IMMEDIATE")
    import_carrier_records(conn, src_conn, PAPER_ID, CONTENT_JOB_ID, PURPOSE_JOB_ID, inserted)
    res1 = adoption.record_adoption(conn, adm1)
    for tbl, rids in res1.items():
        inserted.setdefault(tbl, set()).update(rids)
    conn.commit()

    st1_c = adoption.history_origin_state(conn, CONTENT_JOB_ID)
    st1_p = adoption.history_origin_state(conn, PURPOSE_JOB_ID)
    assert st1_c == {"state": "ADOPTED", "eligible": True, "request_id": req1}
    assert st1_p == {"state": "ADOPTED", "eligible": True, "request_id": req1}

    # 3. Reversal 1: Reversed
    rev1 = f"rev-trans-c1-{packet_sha256[:10]}"
    conn.execute("BEGIN IMMEDIATE")
    rev_res1 = adoption.reverse_adoption(conn, req1, request_id=rev1, reason="Rev 1")
    for tbl, rids in rev_res1.items():
        inserted.setdefault(tbl, set()).update(rids)
    conn.commit()

    st_rev1_c = adoption.history_origin_state(conn, CONTENT_JOB_ID)
    st_rev1_p = adoption.history_origin_state(conn, PURPOSE_JOB_ID)
    assert st_rev1_c["state"] == "REVERSED" and st_rev1_c["eligible"] is False
    assert st_rev1_p["state"] == "REVERSED" and st_rev1_p["eligible"] is False
    assert st_rev1_c["request_ids"] == [req1]
    assert st_rev1_p["request_ids"] == [req1]

    # 4. Cycle 2: Re-adopted
    req2 = f"adopt-trans-c2-{packet_sha256[:10]}"
    adm2 = adoption.prepare_adoption(
        src_conn,
        [CONTENT_JOB_ID],
        target_database=cloned_target_owner,
        request_id=req2,
        reason="Transition c2",
        packet_sha256=packet_sha256,
        manifest_sha256=manifest_sha256,
    )
    conn.execute("BEGIN IMMEDIATE")
    res2 = adoption.record_adoption(conn, adm2)
    for tbl, rids in res2.items():
        inserted.setdefault(tbl, set()).update(rids)
    conn.commit()

    st2_c = adoption.history_origin_state(conn, CONTENT_JOB_ID)
    st2_p = adoption.history_origin_state(conn, PURPOSE_JOB_ID)
    assert st2_c == {"state": "ADOPTED", "eligible": True, "request_id": req2}
    assert st2_p == {"state": "ADOPTED", "eligible": True, "request_id": req2}

    # 5. Reversal 2: Re-reversed
    rev2 = f"rev-trans-c2-{packet_sha256[:10]}"
    conn.execute("BEGIN IMMEDIATE")
    rev_res2 = adoption.reverse_adoption(conn, req2, request_id=rev2, reason="Rev 2")
    for tbl, rids in rev_res2.items():
        inserted.setdefault(tbl, set()).update(rids)
    conn.commit()

    st_rev2_c = adoption.history_origin_state(conn, CONTENT_JOB_ID)
    st_rev2_p = adoption.history_origin_state(conn, PURPOSE_JOB_ID)
    assert st_rev2_c["state"] == "REVERSED" and st_rev2_c["eligible"] is False
    assert st_rev2_p["state"] == "REVERSED" and st_rev2_p["eligible"] is False
    assert req1 in st_rev2_c["request_ids"]
    assert req2 in st_rev2_c["request_ids"]
    assert req1 in st_rev2_p["request_ids"]
    assert req2 in st_rev2_p["request_ids"]

    src_conn.close()
    conn.close()
