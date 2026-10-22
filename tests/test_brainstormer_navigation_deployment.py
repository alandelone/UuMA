import hashlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def daemon_module(tmp_path, monkeypatch):
    monkeypatch.setenv("UUMA_DATA_DIR", str(tmp_path / "legacy"))
    monkeypatch.delenv("UUMA_NAVIGATION_DATABASE_PATH", raising=False)
    monkeypatch.delenv("UUMA_REQUIRE_SEPARATE_NAVIGATION_DB", raising=False)
    from uuma import state_daemon

    return state_daemon


def test_independent_navigation_database_does_not_create_control_database(
    daemon_module, tmp_path, monkeypatch,
):
    data = tmp_path / "server"
    navigation = data / "brainstormer-navigation.db"
    monkeypatch.setenv("UUMA_REQUIRE_SEPARATE_NAVIGATION_DB", "1")
    monkeypatch.setenv("UUMA_NAVIGATION_DATABASE_PATH", str(navigation))
    daemon = daemon_module.StateDaemon(data)
    daemon.db.set_binding("owner", "project", "topic")
    assert daemon.db.db_path == navigation
    assert navigation.is_file()
    assert not (data / "uuma.db").exists()
    assert daemon.db.get_binding("owner")["active_topic_id"] == "topic"


@pytest.mark.parametrize("filename", [None, "uuma.db", "wisdom.db", "state.db"])
def test_server_navigation_rejects_missing_or_shared_database(
    daemon_module, tmp_path, monkeypatch, filename,
):
    monkeypatch.setenv("UUMA_REQUIRE_SEPARATE_NAVIGATION_DB", "1")
    data = tmp_path / "server"
    configured = data / filename if filename else None
    with pytest.raises((RuntimeError, ValueError)):
        daemon_module.StateDaemon(data, navigation_database_path=configured)
    assert not data.exists()


def test_navigation_database_default_keeps_existing_workstation_contract(daemon_module, tmp_path):
    daemon = daemon_module.StateDaemon(tmp_path)
    assert daemon.db.db_path == tmp_path / "uuma.db"


def test_navigation_migration_copies_only_three_tables_without_source_changes(
    daemon_module, tmp_path,
):
    source = tmp_path / "legacy.db"
    store = daemon_module.DatabaseManager(source)
    store.set_binding("owner", "project", "topic")
    store.record_turn("owner", "project", "topic", "telegram", "Keep this history")
    store.record_receipt("project", "topic", 6, "COMMITTED", "owner")
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE control_only (value TEXT)")
        db.execute("INSERT INTO control_only VALUES ('not navigation')")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    destination = tmp_path / "navigation.db"
    counts = daemon_module.migrate_navigation_database(source, destination)
    assert counts == {"user_bindings": 1, "discussion_turns": 1, "commit_receipts": 1}
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    with sqlite3.connect(destination) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == set(counts)
        assert db.execute("SELECT text FROM discussion_turns").fetchone()[0] == "Keep this history"
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    with pytest.raises(FileExistsError):
        daemon_module.migrate_navigation_database(source, destination)


def test_missing_navigation_tables_never_create_destination(daemon_module, tmp_path):
    source = tmp_path / "empty.db"
    with sqlite3.connect(source):
        pass
    destination = tmp_path / "navigation.db"
    with pytest.raises(ValueError, match="missing"):
        daemon_module.migrate_navigation_database(source, destination)
    assert not destination.exists()


def test_migration_cli_does_not_construct_default_daemon(daemon_module, tmp_path):
    source = tmp_path / "legacy.db"
    daemon_module.DatabaseManager(source).set_binding("owner", "project", "topic")
    destination = tmp_path / "navigation.db"
    unopened = tmp_path / "never-opened-control-root"
    environment = {
        **os.environ, "UUMA_DATA_DIR": str(unopened),
        "UUMA_REQUIRE_SEPARATE_NAVIGATION_DB": "1",
    }
    environment.pop("UUMA_NAVIGATION_DATABASE_PATH", None)
    result = subprocess.run(
        [sys.executable, "-m", "uuma.state_daemon", "--migrate-navigation",
         str(source), str(destination)],
        env=environment, capture_output=True, text=True, encoding="utf-8", check=True,
    )
    assert json.loads(result.stdout)["user_bindings"] == 1
    assert destination.is_file()
    assert not unopened.exists()


def commands_class():
    path = (
        Path(__file__).resolve().parents[1]
        / "integrations/hermes/uuma_brainstormer_commands/__init__.py"
    )
    spec = importlib.util.spec_from_file_location("navigation_deployment_plugin", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.BrainstormerCommands


@pytest.mark.parametrize("configured", [None, "http://127.0.0.1:8773/api/v1/navigation"])
def test_navigation_url_default_and_server_override(configured):
    values = {"owner_id": "123"}
    if configured:
        values["navigation_url"] = configured

    class Context:
        def get_config(self, key, default):
            return values.get(key, default)

    commands = commands_class()(Context())
    assert commands.url == (configured or "http://127.0.0.1:8772/api/v1/navigation")


@pytest.mark.parametrize("url", [
    "http://example.com/api/v1/navigation", "http://127.0.0.1:8773/api/v1/review",
    "http://owner:secret@127.0.0.1:8773/api/v1/navigation",
])
def test_navigation_rejects_external_or_wrong_endpoint(url):
    class Context:
        def get_config(self, key, default):
            return {"owner_id": "123", "navigation_url": url}.get(key, default)

    with pytest.raises(ValueError, match="loopback"):
        commands_class()(Context())
