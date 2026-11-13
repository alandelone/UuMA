"""Unit test for Librarian LSIP Nightly Pipeline."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from uuma.librarian_nightly_pipeline import run_nightly_pipeline


def test_run_nightly_pipeline_end_to_end(tmp_path: Path):
    db_path = tmp_path / "librarian_semantic.db"
    cat_dir = tmp_path / "catalog"
    cat_dir.mkdir()

    # 1. Create dummy Yonc DB
    yonc_db_path = tmp_path / "yonc.sqlite3"
    with sqlite3.connect(yonc_db_path) as ydb:
        ydb.execute(
            "CREATE TABLE graph_nodes(id TEXT PRIMARY KEY, title TEXT, status TEXT, "
            "description TEXT, created_at TEXT, updated_at TEXT, completed_at TEXT, parent_id TEXT)"
        )
        ydb.execute(
            "INSERT INTO graph_nodes VALUES('n1', 'Initial Setup', 'DONE', "
            "'Project initialized with schema', '2026-11-01', '2026-11-02', '2026-11-02', NULL)"
        )

    # 2. Create dummy UuMA DB
    uuma_db_path = tmp_path / "uuma.db"
    with sqlite3.connect(uuma_db_path) as udb:
        udb.execute(
            "CREATE TABLE events(event_id TEXT PRIMARY KEY, sequence INTEGER, event_type TEXT, "
            "aggregate_type TEXT, aggregate_id TEXT, actor_type TEXT, actor_id TEXT, "
            "payload_json TEXT, occurred_at TEXT, event_hash TEXT)"
        )
        udb.execute(
            "INSERT INTO events VALUES('e1', 1, 'stage_gate_passed', 'gate', 'gate-01', "
            "'agent', 'orchestrator', '{\"summary\": \"Gate passed successfully\"}', "
            "'2026-11-05T10:00:00Z', 'hash1234567890abcdef')"
        )

    config = {
        "yonc_db": str(yonc_db_path),
        "uuma_db": str(uuma_db_path),
    }

    summary = run_nightly_pipeline(db_path, cat_dir, sources_config=config)

    assert summary["status"] == "success"
    assert summary["extracted_counts"]["yonc-graph"] >= 1
    assert summary["extracted_counts"]["uuma-control"] >= 1
    assert summary["total_catalog_records"] >= 2

    # Check publication files
    sem_cat = cat_dir / "librarian_semantic_catalog.json"
    legacy_cat = cat_dir / "catalog.json"
    assert sem_cat.exists()
    assert legacy_cat.exists()

    cat_data = json.loads(sem_cat.read_text(encoding="utf-8"))
    assert cat_data["schema_version"] == 1
    assert cat_data["snapshot_id"].startswith("lsip-")
    assert len(cat_data["records"]) >= 2
