"""Tests for UuMAControlAdapter."""

import sqlite3
from pathlib import Path

from uuma.librarian_uuma_adapter import UuMAControlAdapter


def test_uuma_control_adapter_extraction(tmp_path: Path) -> None:
    db_file = tmp_path / "test_uuma_control.db"
    conn = sqlite3.connect(str(db_file))
    conn.executescript("""
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
    VALUES ('evt_01', 'stage_gate_passed', 'mission', 'uuma_core', 'user', 'orchestrator', '2026-11-12T10:00:00Z', '{"summary": "Gate 04 verification passed"}', 'hash0101010101010101');
    INSERT INTO events (event_id, event_type, aggregate_type, aggregate_id, actor_type, actor_id, occurred_at, payload_json, event_hash)
    VALUES ('evt_02', 'task_completed', 'task', 'task_publish_catalog', 'agent', 'librarian', '2026-11-12T10:30:00Z', '{"summary": "Published catalog v1.0"}', 'hash0202020202020202');
    """)
    conn.commit()
    conn.close()

    adapter = UuMAControlAdapter()
    assert adapter.source_id == "uuma-control"
    assert adapter.default_category == "Decision"

    records = adapter.extract(db_file)
    assert len(records) == 2

    # Check gate transition (History, confirmed)
    r1 = next(r for r in records if r.record_id == "uuma:event:evt_01")
    assert r1.category == "History"
    assert r1.assertion_status == "confirmed"
    assert r1.evidence[0].locator_value == "events.event_id:evt_01"

    # Check task completion (Work & Artifacts, confirmed)
    r2 = next(r for r in records if r.record_id == "uuma:event:evt_02")
    assert r2.category == "Work & Artifacts"
    assert r2.assertion_status == "confirmed"
    assert "task_completed" in r2.title
