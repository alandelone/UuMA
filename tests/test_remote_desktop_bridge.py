import sqlite3
from types import SimpleNamespace

import pytest

from uuma.chatgpt_bridge import BridgeStore, bridge_database_path


def test_remote_bridge_uses_separate_state_and_authoritative_control(tmp_path, monkeypatch):
    monkeypatch.setenv("UUMA_CONTROL_URL", "http://127.0.0.1:8765")
    path = bridge_database_path(tmp_path)
    assert path == tmp_path / "desktop/chatgpt.db"
    control = SimpleNamespace(
        require_run=lambda run_id: {"agent_id": "brainstormer", "status": "RUNNING", "task_id": "t"},
        require_task=lambda task_id: {"current_run_id": "r", "status": "RUNNING"},
    )
    store = BridgeStore(path, control_factory=lambda agent: control)
    with store.connect() as conn:
        store.require_run(conn, "brainstormer", "r")
        with pytest.raises(PermissionError):
            store.require_run(conn, "wisdom-oldman", "r")
        with pytest.raises(PermissionError):
            store.require_run(conn, "brainstormer", "stale-run")
    with sqlite3.connect(path) as conn:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    assert "runs" not in names
    assert "tasks" not in names
    assert not (tmp_path / "uuma.db").exists()


def test_required_remote_control_cannot_use_stale_local_state(tmp_path, monkeypatch):
    monkeypatch.delenv("UUMA_CONTROL_URL", raising=False)
    monkeypatch.setenv("UUMA_REQUIRE_REMOTE_CONTROL", "1")
    store = BridgeStore(bridge_database_path(tmp_path))
    with store.connect() as conn, pytest.raises(PermissionError, match="stale local"):
        store.require_run(conn, "brainstormer", "r")


def test_unconfigured_legacy_bridge_keeps_existing_database_path(tmp_path, monkeypatch):
    monkeypatch.delenv("UUMA_CONTROL_URL", raising=False)
    monkeypatch.delenv("UUMA_REQUIRE_REMOTE_CONTROL", raising=False)
    monkeypatch.delenv("UUMA_CHATGPT_DATABASE_PATH", raising=False)
    assert bridge_database_path(tmp_path) == tmp_path / "uuma.db"
