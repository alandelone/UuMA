"""Adversarial Empirical Verification Harness for M4 Challenger Replication (challenger_m4_rep_2).

Verifies:
1. Candidate query latency SLA (<500ms mean latency across repeated executions).
2. Target adoption & compensating reversal on isolated database:
   - 100% bitwise invariance across all 129 tables before adoption and after reversal.
   - Zero SQL DELETE statements executed throughout entire lifecycle (strictly append-only).
   - Provenance transitions: ADOPTED -> REVERSED (ineligible).
   - Non-destructive evidence retention in SQLite.
"""
from __future__ import annotations

import gc
import hashlib
import json
import re
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path

import pytest

# Configure workspace roots
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
from rstv4.catalog_content_retrieval import CatalogContentRetrieval
from rstv4.database import initialize_catalog

DELIVERY_ARCHIVE_DIR = UUMA_LOCAL / "delivery-archive-20261106"
CANONICAL_DB_PATH = RSTV4_ROOT / "data" / "catalog.db"
CONTENT_JOB_ID = "skeletonviewjob_1216bde784964dc42990bbd92b55cd7431a23a60a43d94a05fe1bd58c6ec81e6"
PURPOSE_JOB_ID = "skeletonviewjob_b7a6ba5a81ef5f58911dc951ea0c856a9d99fa5c4367a2021a4fdaaec3a40382"
PAPER_ID = "paper_dd83af8026e39dd2a2e9316622a7ca49"


def canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda item: {"bytes_hex": item.hex()} if isinstance(item, bytes) else str(item),
    )


def compute_table_vectors(conn: sqlite3.Connection, inserted: dict | None = None) -> dict[str, dict]:
    """Compute sha256 hash of each table excluding explicitly inserted rowids."""
    result = {}
    inserted = inserted or {}
    for name, sql in conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ):
        cols = [tuple(row) for row in conn.execute(f'PRAGMA table_info("{name}")')]
        digest = hashlib.sha256()
        count = 0
        for row in conn.execute(f'SELECT rowid, * FROM "{name}" ORDER BY rowid'):
            if row[0] in inserted.get(name, set()):
                continue
            digest.update(canonical_json(tuple(row)).encode("utf-8"))
            digest.update(b"\n")
            count += 1
        result[name] = {
            "sql": sql,
            "columns": cols,
            "rows": count,
            "sha256": digest.hexdigest(),
        }
    return result


# =====================================================================
# EMPIRICAL TEST 1: Candidate Query Latency SLA Benchmark
# =====================================================================

def test_candidate_query_latency_sla_repeated_executions():
    """Empirically measure candidate query latency over 25 consecutive executions against <500ms SLA."""
    print("\n" + "=" * 75)
    print("EMPIRICAL TEST 1: Candidate Query Latency SLA Benchmark (25 Executions)")
    print("=" * 75)

    if not CANONICAL_DB_PATH.exists():
        pytest.skip(f"Canonical catalog.db not found at {CANONICAL_DB_PATH}")

    retriever = CatalogContentRetrieval(RSTV4_ROOT)

    # Warmup query
    t_start_warm = time.perf_counter()
    warmup_res = retriever.candidate_relations(limit=20, evidence_limit=4, min_similarity=0.75)
    warmup_duration_ms = (time.perf_counter() - t_start_warm) * 1000.0
    print(f"  Warmup Execution: {warmup_duration_ms:.2f} ms | Items: {len(warmup_res['items'])}")

    iterations = 25
    latencies_ms: list[float] = []

    for i in range(iterations):
        t0 = time.perf_counter()
        res = retriever.candidate_relations(limit=20, evidence_limit=4, min_similarity=0.75)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(dt_ms)

        # Integrity assertions
        assert "items" in res
        assert len(res["items"]) > 0
        assert res["applied_merges"] == 0
        assert "source_fingerprint" in res
        item0 = res["items"][0]
        assert "theme_ids" in item0
        assert "similarity" in item0
        assert item0["similarity"] >= 0.75

        print(f"  Execution {i+1:2d}/{iterations}: {dt_ms:6.2f} ms | Items: {len(res['items']):2d} | Top Sim: {item0['similarity']:.4f}")

    retriever.close()

    # Statistical computation
    mean_lat = statistics.mean(latencies_ms)
    median_lat = statistics.median(latencies_ms)
    sorted_lats = sorted(latencies_ms)
    p95_lat = sorted_lats[int(len(sorted_lats) * 0.95)]
    min_lat = min(latencies_ms)
    max_lat = max(latencies_ms)
    std_lat = statistics.stdev(latencies_ms)

    print("-" * 75)
    print("BENCHMARK SUMMARY:")
    print(f"  Mean Latency       : {mean_lat:6.2f} ms (Strict SLA: < 500.00 ms)")
    print(f"  Median (p50)       : {median_lat:6.2f} ms")
    print(f"  p95 Latency        : {p95_lat:6.2f} ms")
    print(f"  Min Latency        : {min_lat:6.2f} ms")
    print(f"  Max Latency        : {max_lat:6.2f} ms")
    print(f"  Std Deviation      : {std_lat:6.2f} ms")
    print("-" * 75)

    # SLA Assertions
    assert mean_lat < 500.0, f"SLA Violation: Mean latency {mean_lat:.2f} ms exceeds 500 ms SLA!"
    assert p95_lat < 500.0, f"SLA Violation: p95 latency {p95_lat:.2f} ms exceeds 500 ms SLA!"
    assert max_lat < 500.0, f"SLA Violation: Max latency {max_lat:.2f} ms exceeds 500 ms SLA!"
    print(f"  [PASS] Candidate query latency SLA STRICTLY SATISFIED: Mean {mean_lat:.2f} ms < 500 ms SLA threshold.")


# =====================================================================
# EMPIRICAL TEST 2: Target Adoption Bitwise Invariance & Zero-DELETE
# =====================================================================

def test_target_adoption_bitwise_invariance_and_zero_delete(tmp_path: Path):
    """Execute target adoption and compensating reversal on an isolated database.
    Assert 100% bitwise invariance across all 129 tables and verify zero SQL DELETE statements.
    """
    print("\n" + "=" * 75)
    print("EMPIRICAL TEST 2: Target Adoption Bitwise Invariance & Zero-DELETE Stress")
    print("=" * 75)

    isolated_db_dir = tmp_path / "isolated_target" / "data"
    isolated_db_dir.mkdir(parents=True, exist_ok=True)
    isolated_db = isolated_db_dir / "catalog.db"

    print(f"Initializing isolated test database at: {isolated_db}")
    initialize_catalog(isolated_db)

    # Trace callback to record EVERY SQL statement executed across connections
    executed_statements: list[str] = []

    def make_traced_connection(path: Path) -> sqlite3.Connection:
        c = sqlite3.connect(str(path.resolve()))
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        c.set_trace_callback(lambda stmt: executed_statements.append(stmt))
        return c

    # Step A: Seed target owner with pre-existing independent records (non-empty owner)
    seed_now = "2026-11-01T00:00:00+00:00"
    conn = make_traced_connection(isolated_db)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO papers (
                paper_id, canonical_key, doi, normalized_title, title, authors_json,
                published_year, abstract, landing_url, pdf_url, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "paper_isolated_seed_001",
                "seed_canonical_key_iso_001",
                "10.1000/iso001",
                "pre-existing isolated owner paper 001",
                "Pre-existing Isolated Owner Paper 001",
                json.dumps(["Author One", "Author Two"]),
                2026,
                "Pre-existing independent paper in isolated test database.",
                "https://example.com/iso001",
                "https://example.com/iso001.pdf",
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
                "file_isolated_seed_001",
                "paper_isolated_seed_001",
                "c" * 64,
                2048,
                "application/pdf",
                "dummy_isolated.pdf",
                "DIRECT",
                "https://example.com/iso001.pdf",
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
                "parse_isolated_seed_001",
                "file_isolated_seed_001",
                "mineru",
                "1.0",
                "d" * 64,
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
            ("intent_isolated_seed_001", "paper_isolated_seed_001", "paperskeleton-understanding-v1", "ACTIVE", 0, 0, seed_now, seed_now),
        )
        conn.execute(
            """INSERT INTO catalog_reading_jobs (
                job_id, intent_id, paper_id, parse_run_id, input_json, manual_priority,
                status, attempts, fencing_token, lease_owner, lease_until, available_at,
                result_json, last_error, created_at, updated_at, job_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "job_isolated_seed_001",
                "intent_isolated_seed_001",
                "paper_isolated_seed_001",
                "parse_isolated_seed_001",
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
                "req_isolated_seed_001",
                json.dumps({"op": "seed"}),
                "intent_isolated_seed_001",
                json.dumps({"status": "ok"}),
                seed_now,
            ),
        )
        conn.execute(
            """INSERT INTO catalog_reading_events (
                intent_id, job_id, event_kind, detail_json, created_at
            ) VALUES (?, ?, ?, ?, ?)""",
            (
                "intent_isolated_seed_001",
                "job_isolated_seed_001",
                "SEED_INITIALIZED",
                json.dumps({"status": "isolated"}),
                seed_now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # Step B: Capture baseline pre-adoption table vectors across all 129 tables
    conn = make_traced_connection(isolated_db)
    before_vectors = compute_table_vectors(conn)
    total_tables = len(before_vectors)
    print(f"Captured pre-adoption baseline across {total_tables} tables.")
    assert total_tables == 129, f"Expected exactly 129 tables in catalog schema, found {total_tables}"

    # Step C: Prepare carrier hashes and admission
    manifest_path = DELIVERY_ARCHIVE_DIR / "manifest.json"
    assert manifest_path.exists(), f"Delivery archive manifest missing at {manifest_path}"
    manifest_raw = manifest_path.read_bytes()
    manifest_data = json.loads(manifest_raw)
    packet_sha256 = manifest_data["packet_sha256"]
    manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()

    src_conn = make_traced_connection(ORIGINAL)
    adopt_request_id = f"adopt-empirical-rep2-{packet_sha256[:12]}"

    admission = adoption.prepare_adoption(
        src_conn,
        [CONTENT_JOB_ID],
        target_database=isolated_db,
        request_id=adopt_request_id,
        reason="Empirical replication challenger adoption test",
        packet_sha256=packet_sha256,
        manifest_sha256=manifest_sha256,
    )

    # Step D: Execute Adoption Transaction
    inserted_adoption: dict[str, set[int]] = {}

    def insert_rows(table: str, rows: list[sqlite3.Row]):
        if not rows:
            return
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
        placeholders = ",".join("?" for _ in cols)
        s = inserted_adoption.setdefault(table, set())
        for r in rows:
            cur = conn.execute(
                f'INSERT INTO "{table}" (' + ",".join(f'"{c}"' for c in cols) + f") VALUES ({placeholders})",
                [r[c] for c in cols],
            )
            s.add(cur.lastrowid)

    conn.execute("BEGIN IMMEDIATE")
    insert_rows("papers", src_conn.execute("SELECT * FROM papers WHERE paper_id=?", (PAPER_ID,)).fetchall())
    insert_rows("source_file_versions", src_conn.execute("SELECT * FROM source_file_versions WHERE paper_id=?", (PAPER_ID,)).fetchall())
    insert_rows("parse_runs", src_conn.execute(
        "SELECT * FROM parse_runs WHERE file_version_id IN (SELECT file_version_id FROM source_file_versions WHERE paper_id=?)",
        (PAPER_ID,),
    ).fetchall())
    insert_rows("catalog_reading_intents", src_conn.execute("SELECT * FROM catalog_reading_intents WHERE paper_id=?", (PAPER_ID,)).fetchall())
    insert_rows("paper_versions", src_conn.execute("SELECT * FROM paper_versions WHERE paper_id=?", (PAPER_ID,)).fetchall())
    insert_rows("paper_skeletons", src_conn.execute(
        "SELECT * FROM paper_skeletons WHERE paper_version_id IN (SELECT paper_version_id FROM paper_versions WHERE paper_id=?)",
        (PAPER_ID,),
    ).fetchall())
    insert_rows("skeleton_units", src_conn.execute(
        "SELECT * FROM skeleton_units WHERE skeleton_id IN (SELECT skeleton_id FROM paper_skeletons WHERE paper_version_id IN (SELECT paper_version_id FROM paper_versions WHERE paper_id=?))",
        (PAPER_ID,),
    ).fetchall())
    insert_rows("skeleton_triplets", src_conn.execute(
        "SELECT * FROM skeleton_triplets WHERE unit_id IN (SELECT unit_id FROM skeleton_units WHERE skeleton_id IN (SELECT skeleton_id FROM paper_skeletons WHERE paper_version_id IN (SELECT paper_version_id FROM paper_versions WHERE paper_id=?)))",
        (PAPER_ID,),
    ).fetchall())
    insert_rows("skeleton_runs", src_conn.execute(
        "SELECT * FROM skeleton_runs WHERE parse_run_id IN (SELECT parse_run_id FROM parse_runs WHERE file_version_id IN (SELECT file_version_id FROM source_file_versions WHERE paper_id=?))",
        (PAPER_ID,),
    ).fetchall())
    insert_rows("skeleton_checkpoints", src_conn.execute(
        "SELECT * FROM skeleton_checkpoints WHERE skeleton_run_id IN (SELECT skeleton_run_id FROM skeleton_runs WHERE parse_run_id IN (SELECT parse_run_id FROM parse_runs WHERE file_version_id IN (SELECT file_version_id FROM source_file_versions WHERE paper_id=?)))",
        (PAPER_ID,),
    ).fetchall())
    insert_rows("catalog_reading_jobs", src_conn.execute("SELECT * FROM catalog_reading_jobs WHERE job_id IN (?, ?)", (CONTENT_JOB_ID, PURPOSE_JOB_ID)).fetchall())
    insert_rows("catalog_skeleton_content_views", src_conn.execute("SELECT * FROM catalog_skeleton_content_views WHERE job_id=?", (CONTENT_JOB_ID,)).fetchall())
    insert_rows("catalog_skeleton_purpose_judgments", src_conn.execute("SELECT * FROM catalog_skeleton_purpose_judgments WHERE job_id=?", (PURPOSE_JOB_ID,)).fetchall())
    insert_rows("catalog_reading_model_events", src_conn.execute("SELECT * FROM catalog_reading_model_events WHERE job_id IN (?, ?) ORDER BY event_seq", (CONTENT_JOB_ID, PURPOSE_JOB_ID)).fetchall())
    insert_rows("catalog_reading_events", src_conn.execute("SELECT * FROM catalog_reading_events WHERE job_id IN (?, ?) ORDER BY event_seq", (CONTENT_JOB_ID, PURPOSE_JOB_ID)).fetchall())

    req_ids = set()
    for r in src_conn.execute("SELECT detail_json FROM catalog_reading_events WHERE job_id IN (?, ?)", (CONTENT_JOB_ID, PURPOSE_JOB_ID)).fetchall():
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

    adopt_res = adoption.record_adoption(conn, admission)
    for tbl, rids in adopt_res.items():
        inserted_adoption.setdefault(tbl, set()).update(rids)
    conn.commit()

    # Verify origin state is ADOPTED and eligible
    st_content = adoption.history_origin_state(conn, CONTENT_JOB_ID)
    st_purpose = adoption.history_origin_state(conn, PURPOSE_JOB_ID)
    assert st_content["state"] == "ADOPTED" and st_content["eligible"] is True
    assert st_purpose["state"] == "ADOPTED" and st_purpose["eligible"] is True

    # Verify 100% byte invariance during adoption across all 129 tables
    during_vectors = compute_table_vectors(conn, inserted=inserted_adoption)
    for tbl, vec in before_vectors.items():
        assert during_vectors[tbl]["sha256"] == vec["sha256"], f"Pre-existing rows modified during adoption in table {tbl}"
    print("Pre-existing records 100% byte-invariant verified during ADOPTED state across all 129 tables.")

    # Step E: Execute Compensating Reversal (Reverse Adoption)
    rev_request_id = f"rev-empirical-rep2-{packet_sha256[:12]}"
    conn.execute("BEGIN IMMEDIATE")
    rev_res = adoption.reverse_adoption(
        conn,
        adopt_request_id,
        request_id=rev_request_id,
        reason="Empirical replication challenger compensating reversal test",
    )
    for tbl, rids in rev_res.items():
        inserted_adoption.setdefault(tbl, set()).update(rids)
    conn.commit()

    # Verify origin state is REVERSED and ineligible
    st_rev_content = adoption.history_origin_state(conn, CONTENT_JOB_ID)
    st_rev_purpose = adoption.history_origin_state(conn, PURPOSE_JOB_ID)
    assert st_rev_content["state"] == "REVERSED" and st_rev_content["eligible"] is False
    assert st_rev_purpose["state"] == "REVERSED" and st_rev_purpose["eligible"] is False

    # Verify 100% bitwise invariance across ALL 129 tables post-reversal
    post_reversal_vectors = compute_table_vectors(conn, inserted=inserted_adoption)
    invariant_tables_count = 0
    for tbl, vec in before_vectors.items():
        assert post_reversal_vectors[tbl]["sha256"] == vec["sha256"], (
            f"Bitwise invariance violation in table {tbl}: before={vec['sha256']} post={post_reversal_vectors[tbl]['sha256']}"
        )
        assert post_reversal_vectors[tbl]["rows"] == vec["rows"], (
            f"Row count violation in table {tbl}: before={vec['rows']} post={post_reversal_vectors[tbl]['rows']}"
        )
        invariant_tables_count += 1

    print(f"Post-reversal bitwise invariance: {invariant_tables_count}/{total_tables} tables 100% BITWISE INVARIANT!")
    assert invariant_tables_count == 129

    # Step F: Verify ZERO SQL DELETE Statements Executed Throughout Lifecycle
    delete_pattern = re.compile(r"\bDELETE\b", re.IGNORECASE)
    delete_statements = [stmt for stmt in executed_statements if delete_pattern.search(stmt)]
    print(f"Total SQL statements executed during test: {len(executed_statements)}")
    print(f"Total SQL DELETE statements executed: {len(delete_statements)}")
    if delete_statements:
        print("DETECTED FORBIDDEN SQL DELETE STATEMENTS:")
        for s in delete_statements:
            print(f"  -> {s}")

    assert len(delete_statements) == 0, f"VIOLATION: Executed {len(delete_statements)} forbidden SQL DELETE statements!"

    # Step G: Verify Non-Destructive Preservation of Imported Evidence in SQLite
    paper_count = conn.execute("SELECT COUNT(*) FROM papers WHERE paper_id=?", (PAPER_ID,)).fetchone()[0]
    view_count = conn.execute("SELECT COUNT(*) FROM catalog_skeleton_content_views WHERE job_id=?", (CONTENT_JOB_ID,)).fetchone()[0]
    unit_count = conn.execute("SELECT COUNT(*) FROM skeleton_units").fetchone()[0]
    assert paper_count == 1, "Imported paper row must be retained in SQLite"
    assert view_count == 1, "Imported view row must be retained in SQLite"
    assert unit_count == 85, "Imported skeleton units must be retained in SQLite"
    print("Non-destructive evidence preservation confirmed: rows retained with operational eligibility revoked.")

    # Step H: DB Foreign Key and Integrity checks
    assert len(conn.execute("PRAGMA foreign_key_check").fetchall()) == 0
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    src_conn.close()
    conn.close()
    print("  [PASS] Isolated adoption, compensating reversal, 100% bitwise invariance across 129 tables, and zero SQL DELETE verified!")
