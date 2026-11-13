"""Tests for Semantic Pipeline Coordinator and Catalog Exporter."""

import json
import sqlite3
from pathlib import Path

from uuma.librarian_read import LibrarianReader
from uuma.librarian_semantic_db import init_semantic_db, search_records
from uuma.librarian_semantic_pipeline import SemanticPipelineCoordinator


def test_semantic_pipeline_end_to_end(tmp_path: Path) -> None:
    # 1. Init DB
    db_file = tmp_path / "semantic_pipeline.db"
    conn = init_semantic_db(db_file)
    coordinator = SemanticPipelineCoordinator(conn)

    # 2. Fake Yonc DB
    yonc_db = tmp_path / "yonc.db"
    yconn = sqlite3.connect(str(yonc_db))
    yconn.executescript("""
    CREATE TABLE nodes (
        id VARCHAR(36) PRIMARY KEY,
        title TEXT,
        description TEXT,
        status VARCHAR(20),
        node_kind VARCHAR(20),
        stage VARCHAR(20),
        done_when TEXT,
        superseded_by VARCHAR(36)
    );
    INSERT INTO nodes (id, title, description, status, node_kind)
    VALUES ('n_wal', 'Adopt SQLite WAL Mode', 'Concurrency optimization', 'DONE', 'DECISION');
    """)
    yconn.commit()
    yconn.close()

    # 3. Fake Brainstormer state
    bs_state = {
        "project_id": "proj_brainstorm",
        "revision": 2,
        "objects": {
            "dec_01": {
                "id": "dec_01",
                "kind": "decision",
                "title": "Use Gemini Flash for Ingestion",
                "status": "APPROVED",
                "rationale": "High throughput and low cost",
            },
        },
    }

    # 4. Fake UuMA Control DB
    uuma_db = tmp_path / "uuma.db"
    uconn = sqlite3.connect(str(uuma_db))
    uconn.executescript("""
    CREATE TABLE events (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        event_type TEXT NOT NULL,
        aggregate_type TEXT NOT NULL,
        aggregate_id TEXT NOT NULL,
        actor_type TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        event_hash TEXT NOT NULL UNIQUE
    );
    INSERT INTO events (event_id, event_type, aggregate_type, aggregate_id, actor_type, actor_id, occurred_at, payload_json, event_hash)
    VALUES ('e_01', 'stage_gate_passed', 'mission', 'lsip', 'user', 'orchestrator', '2026-11-12T00:00:00Z', '{"summary": "Gate passed"}', '0101010101010101010101010101010101010101010101010101010101010101');
    """)
    uconn.commit()
    uconn.close()

    # Run deterministic ingestion
    results = coordinator.run_deterministic_ingest({
        "yonc-graph": yonc_db,
        "brainstormer-structured-files": bs_state,
        "uuma-control": uuma_db,
    })

    assert results["yonc-graph"] == 1
    assert results["brainstormer-structured-files"] == 1
    assert results["uuma-control"] == 1

    # Check search in DB
    wal_hits = search_records(conn, "WAL")
    assert len(wal_hits) == 1
    assert wal_hits[0]["record_id"] == "yonc:node:n_wal"

    flash_hits = search_records(conn, "Gemini")
    assert len(flash_hits) == 1
    assert flash_hits[0]["record_id"] == "brainstormer:decision:dec_01"

    # Export catalog
    catalog = coordinator.export_catalog(snapshot_id="lsip-pipeline-test")
    assert catalog["schema_version"] == 1
    assert catalog["snapshot_id"] == "lsip-pipeline-test"
    assert len(catalog["records"]) == 3
    assert len(catalog["sources"]) >= 3

    # Test reading exported catalog with LibrarianReader
    archive_root = tmp_path / "published_archive"
    archive_root.mkdir()
    (archive_root / "librarian_semantic_catalog.json").write_text(
        json.dumps(catalog), encoding="utf-8"
    )

    reader = LibrarianReader(archive_root, "librarian")
    assert reader.catalog.snapshot_id == "lsip-pipeline-test"
    assert len(reader.catalog.records) == 3

    # Category search via Reader
    dec_records = reader.search_records(category="Decision")
    assert dec_records["total"] == 2  # yonc decision + brainstormer decision
