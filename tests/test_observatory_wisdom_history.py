"""Wisdom history remains visible independently of active research and local copies."""
import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

from uuma.observatory.adapters.registry import AdapterRegistry
from uuma.observatory.adapters.wisdom import WisdomAdapter
from uuma.observatory.adapters.wisdom_remote import (
    RemoteWisdomReader,
    read_wisdom_snapshot,
    snapshot_items,
)
from uuma.observatory.models import ObservatoryItem, SourceFreshness


@pytest.fixture
def history_db(tmp_path):
    path = tmp_path / "wisdom.db"
    with sqlite3.connect(path) as db:
        for table, columns in {
            "knowledge_topics": "topic_id TEXT, record_json TEXT, updated_sequence INTEGER",
            "question_orbits": "orbit_id TEXT, record_json TEXT, updated_sequence INTEGER",
            "questions": "question_id TEXT, record_json TEXT, updated_sequence INTEGER",
            "topic_document_versions": "topic_id TEXT",
            "topic_knowledge_links": "topic_id TEXT",
            "orbit_cycles": "orbit_id TEXT, status TEXT, record_json TEXT, updated_sequence INTEGER",
            "orbit_frontier": "frontier_item_id TEXT, orbit_id TEXT, priority TEXT, status TEXT, "
                              "record_json TEXT, updated_sequence INTEGER",
            "research_runs": "record_json TEXT, updated_sequence INTEGER",
            "knowledge_events": "occurred_at TEXT",
        }.items():
            db.execute(f"CREATE TABLE {table} ({columns})")
        db.execute("INSERT INTO knowledge_topics VALUES (?,?,?)", (
            "topic_old", json.dumps({"topic_id": "topic_old", "title": "Past research", "status": "ARCHIVED"}), 1,
        ))
        for number, topic in [(1, "topic_old"), (2, "topic_old"), (3, None)]:
            orbit = {"orbit_id": f"orbit_{number}", "topic_id": topic, "status": "STOPPED"}
            db.execute("INSERT INTO question_orbits VALUES (?,?,?)", (
                orbit["orbit_id"], json.dumps(orbit), number,
            ))
            for status in ("FILLED", "OPEN"):
                frontier = {"question_id": "q_1", "rationale": "Recorded evidence gap"}
                db.execute("INSERT INTO orbit_frontier VALUES (?,?,?,?,?,?)", (
                    f"f_{number}_{status}", orbit["orbit_id"], "HIGH", status,
                    json.dumps(frontier), number,
                ))
        db.execute("INSERT INTO questions VALUES (?,?,?)", (
            "q_1", json.dumps({"question_id": "q_1", "text": "Original research question"}), 1,
        ))
        db.execute("INSERT INTO knowledge_events VALUES ('2026-10-20T10:00:00Z')")
    return path


def test_archived_topic_and_all_orbits_preserve_completed_and_unfinished_history(history_db):
    before = hashlib.sha256(history_db.read_bytes()).hexdigest()
    snapshot = read_wisdom_snapshot(str(history_db))
    items = snapshot_items(snapshot, "http://view.test", "fixture-view-token")
    topic, orphan = items
    assert topic["status"] == "ARCHIVED"
    assert len(topic["payload"]["investigations"]) == 2
    assert orphan["kind"] == "knowledge_orbit"
    all_frontier = [f for orbit in snapshot["orbits"] for f in orbit["pipeline_items"]]
    assert len(all_frontier) == 6
    assert sum(f["stage"].startswith("PASSED") for f in all_frontier) == 3
    assert sum(f["stage"] == "PAUSED" for f in all_frontier) == 3
    assert all(not orbit["runner_live"] for orbit in snapshot["orbits"])
    assert {f["question_text"] for f in all_frontier} == {"Original research question"}
    assert hashlib.sha256(history_db.read_bytes()).hexdigest() == before


def test_missing_source_is_not_initialized(tmp_path):
    path = tmp_path / "missing.db"
    with pytest.raises(sqlite3.OperationalError):
        read_wisdom_snapshot(str(path))
    assert not path.exists()


def test_remote_transport_executes_standalone_reader_and_caches(history_db, monkeypatch):
    marker = history_db.with_name("owner.json")
    marker.write_text(json.dumps({
        "agent": "wisdom-oldman", "owner_node": "alandelone-server-001",
        "server_database": "/owned/wisdom.db",
    }), encoding="utf-8")
    calls = []
    run = subprocess.run

    def execute_remote(command, **kwargs):
        calls.append(command)
        assert command[-3:] == ["python3", "-B", "-"]
        code = kwargs["input"].replace(repr("/owned/wisdom.db"), repr(str(history_db)))
        # Match SSH's explicit UTF-8 contract, including on Windows hosts using GBK.
        result = run([sys.executable, "-B", "-"], input=code, text=True,
                     encoding="utf-8", capture_output=True, check=False)
        assert result.returncode == 0, result.stderr
        return result

    monkeypatch.setattr(subprocess, "run", execute_remote)
    reader = RemoteWisdomReader(marker)
    assert len(reader.read()["orbits"]) == 3
    assert reader.read() == reader.snapshot
    assert len(calls) == 1
    assert reader.error is None

    def unavailable(*args, **kwargs):
        raise subprocess.TimeoutExpired("ssh", 10)

    monkeypatch.setattr(subprocess, "run", unavailable)
    reader._checked = float("-inf")
    assert len(reader.read()["orbits"]) == 3
    assert reader.error is not None


def test_remote_owner_never_falls_back_to_local_old_state(tmp_path, monkeypatch):
    db = tmp_path / "wisdom.db"
    marker = db.with_name("wisdom.db.remote-owner.json")
    marker.write_text(json.dumps({
        "agent": "wisdom-oldman", "owner_node": "alandelone-server-001",
        "server_database": "/owned/wisdom.db",
    }), encoding="utf-8")
    monkeypatch.setattr(WisdomAdapter, "_resolve_wisdom_db", lambda *args: db)
    monkeypatch.setattr(RemoteWisdomReader, "read", lambda self: None)
    adapter = WisdomAdapter(tmp_path)
    assert adapter.list_items() == []
    assert adapter.probe_health().is_available is False
    assert not db.exists()


def test_explicit_source_paths_are_authoritative_even_when_absent(tmp_path):
    wisdom = tmp_path / "configured-wisdom.db"
    control = tmp_path / "configured-uuma.db"
    adapter = WisdomAdapter(tmp_path, knowledge_path=wisdom, uuma_db_path=control)
    assert adapter.db_path == wisdom.resolve()
    assert adapter.uuma_db_path == control.resolve()
    assert not wisdom.exists()
    assert not control.exists()


@pytest.mark.parametrize("live", [False, True])
def test_running_requires_current_cycle_and_unexpired_lease(history_db, live):
    cycle = {
        "status": "RUNNING", "frontier_item_id": "f_1_OPEN", "lease_owner": "fixture-worker",
        "lease_expires_at": (datetime.now(UTC) + timedelta(hours=1 if live else -1)).isoformat(),
    }
    with sqlite3.connect(history_db) as db:
        row = db.execute("SELECT record_json FROM question_orbits WHERE orbit_id='orbit_1'").fetchone()
        orbit = json.loads(row[0])
        orbit["status"] = "ACTIVE"
        db.execute("UPDATE question_orbits SET record_json=? WHERE orbit_id='orbit_1'", (json.dumps(orbit),))
        db.execute("INSERT INTO orbit_cycles VALUES (?,?,?,?)", (
            "orbit_1", "RUNNING", json.dumps(cycle), 100,
        ))
    snapshot = read_wisdom_snapshot(str(history_db))
    orbit = next(o for o in snapshot["orbits"] if o["orbit_id"] == "orbit_1")
    assert orbit["runner_live"] is live
    assert sum(f["stage"] == "RUNNING" for f in orbit["pipeline_items"]) == int(live)


def test_idle_research_keeps_active_knowledge_topic_without_running_fleet_status(tmp_path, monkeypatch):
    adapter = WisdomAdapter(tmp_path, knowledge_path=tmp_path / "absent.db")
    item = ObservatoryItem(
        agent_id="wisdom-oldman", item_id="topic_1", title="Maintained topic",
        kind="knowledge_topic", status="ACTIVE",
        payload={"orbit_info": {"status": "STOPPED", "runner_live": False}},
    )
    assert adapter.workspace_status([item]) == "IDLE"
    registry = object.__new__(AdapterRegistry)
    registry._adapters = {"wisdom-oldman": adapter}
    monkeypatch.setattr(adapter, "list_items", lambda **kwargs: [item])
    monkeypatch.setattr(adapter, "probe_health", lambda: SourceFreshness(
        source_name="fixture", is_available=True,
    ))
    workspace = registry.get_fleet_workspaces()[0]
    assert workspace.status == "IDLE"
    assert workspace.items[0].status == "ACTIVE"
