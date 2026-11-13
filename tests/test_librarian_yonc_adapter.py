"""Tests for YoncGraphAdapter."""

import sqlite3
from pathlib import Path

from uuma.librarian_yonc_adapter import YoncGraphAdapter


def test_yonc_graph_adapter_extraction(tmp_path: Path) -> None:
    db_file = tmp_path / "test_graph.db"
    conn = sqlite3.connect(str(db_file))
    conn.executescript("""
    CREATE TABLE nodes (
        id VARCHAR(36) PRIMARY KEY,
        title TEXT,
        description TEXT,
        status VARCHAR(20) DEFAULT 'TODO',
        node_kind VARCHAR(20) DEFAULT 'WORK',
        stage VARCHAR(20) DEFAULT 'PLANNING',
        done_when TEXT,
        superseded_by VARCHAR(36)
    );
    CREATE TABLE projects (
        id VARCHAR(36) PRIMARY KEY,
        title TEXT
    );
    INSERT INTO projects (id, title) VALUES ('p1', 'Alpha Project');
    INSERT INTO nodes (id, title, description, status, node_kind, stage, done_when)
    VALUES ('n1', 'Design LSIP Architecture', 'Design 4-layer knowledge stack', 'DONE', 'WORK', 'EXECUTION', 'Schema verified');
    INSERT INTO nodes (id, title, description, status, node_kind, stage)
    VALUES ('n2', 'Adopt SQLite WAL Mode', 'Architecture choice for concurrency', 'ACTIVE', 'DECISION', 'EXECUTION');
    INSERT INTO nodes (id, title, description, status, node_kind, stage, superseded_by)
    VALUES ('n3', 'Old Backup Script', 'Legacy shell script', 'CANCELLED', 'WORK', 'CLOSED', 'n1');
    """)
    conn.commit()
    conn.close()

    adapter = YoncGraphAdapter()
    assert adapter.source_id == "yonc-graph"
    assert adapter.default_category == "Decision"

    records = adapter.extract(db_file)
    assert len(records) == 3

    # Check n1 (completed work)
    r1 = next(r for r in records if r.record_id == "yonc:node:n1")
    assert r1.category == "Work & Artifacts"
    assert r1.assertion_status == "confirmed"
    assert r1.evidence[0].locator_value == "nodes.id:n1"

    # Check n2 (decision)
    r2 = next(r for r in records if r.record_id == "yonc:node:n2")
    assert r2.category == "Decision"
    assert r2.assertion_status == "proposed"

    # Check n3 (superseded)
    r3 = next(r for r in records if r.record_id == "yonc:node:n3")
    assert r3.assertion_status == "superseded"
    assert r3.superseded_by == "yonc:node:n1"
