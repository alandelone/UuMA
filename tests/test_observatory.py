"""Tests for UuMA All-in-One Observatory."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from uuma.observatory.adapters.forge import ForgeAdapter
from uuma.observatory.adapters.honc import HoncAdapter
from uuma.observatory.adapters.registry import AdapterRegistry
from uuma.observatory.harvester import parse_spool_file
from uuma.observatory.models import ActivityEvent, SourceFreshness
from uuma.observatory.server import create_observatory_app
from uuma.observatory.storage import ObservatoryStorage
from uuma.settings import Settings


@pytest.fixture
def obs_storage(tmp_path: Path) -> ObservatoryStorage:
    db_file = tmp_path / "test_observatory.db"
    return ObservatoryStorage(db_file)


def test_storage_fts5_and_cursors(obs_storage: ObservatoryStorage):
    ev1 = ActivityEvent(
        event_id="ev_001",
        agent_id="orchestrator",
        hook="pre_tool_call",
        captured_at="2026-10-14T10:00:00Z",
        tool_name="terminal",
        summary="Terminal: docker ps -a",
        source_path="/tmp/spool/ev1.json",
        raw_snippet='{"command": "docker ps -a"}',
    )
    ev2 = ActivityEvent(
        event_id="ev_002",
        agent_id="wisdom-oldman",
        hook="knowledge_update",
        captured_at="2026-10-14T10:05:00Z",
        tool_name="web_search",
        summary="Web Search: agent runtime observability",
        source_path="/tmp/spool/ev2.json",
        raw_snippet='{"query": "agent runtime observability"}',
    )

    inserted = obs_storage.insert_events([ev1, ev2])
    assert inserted == 2

    # Query all
    events, total = obs_storage.query_events(limit=10)
    assert total == 2
    assert len(events) == 2

    # Query by agent filter
    events, total = obs_storage.query_events(agent_id="wisdom-oldman")
    assert total == 1
    assert events[0].event_id == "ev_002"

    # Query by FTS5 keyword
    events, total = obs_storage.query_events(query="docker")
    assert total == 1
    assert events[0].event_id == "ev_001"

    # Cursor & Health
    obs_storage.update_cursor("hermes_spool", "ev2.json", "2026-10-14T10:05:00Z")
    cursor = obs_storage.get_cursor("hermes_spool")
    assert cursor is not None
    assert cursor["last_file"] == "ev2.json"

    obs_storage.update_source_health(
        SourceFreshness(source_name="wisdom.db", is_available=True, last_event_at="2026-10-14T10:05:00Z")
    )
    health_map = obs_storage.get_all_source_health()
    assert "wisdom.db" in health_map
    assert health_map["wisdom.db"].is_available is True


def test_harvester_parsing(tmp_path: Path):
    spool_file = tmp_path / "test_spool.json"
    payload = {
        "captured_at": "2026-10-14T08:00:00Z",
        "profile": "honc",
        "hook": "pre_tool_call",
        "uuma_event_id": "test_honc_01",
        "data": {
            "tool_name": "file_write",
            "args": {"path": "workspace/notes.md"},
        },
    }
    spool_file.write_text(json.dumps(payload), encoding="utf-8")

    event = parse_spool_file(spool_file)
    assert event is not None
    assert event.agent_id == "honc"
    assert event.tool_name == "file_write"
    assert "File Write: workspace/notes.md" in event.summary


def test_adapters_read_only_protection(tmp_path: Path):
    # Create a dummy sqlite database
    test_db = tmp_path / "test_source.db"
    conn = sqlite3.connect(test_db)
    conn.execute("CREATE TABLE items (id TEXT PRIMARY KEY, val TEXT)")
    conn.execute("INSERT INTO items VALUES ('1', 'hello')")
    conn.commit()
    conn.close()

    adapter = ForgeAdapter(tmp_path)
    ro_conn = adapter.safe_sqlite_connect(test_db)
    assert ro_conn is not None

    # Verify attempt to write fails with read-only operational error
    with pytest.raises(sqlite3.OperationalError, match="readonly"), ro_conn:
        ro_conn.execute("INSERT INTO items VALUES ('2', 'world')")


def test_adapter_registry_discovery(tmp_path: Path):
    registry = AdapterRegistry(tmp_path)
    adapters = registry.list_all_adapters()
    assert len(adapters) >= 7

    agent_ids = [a.agent_id for a in adapters]
    expected = [
        "forge-lab-bot",
        "wisdom-oldman",
        "scholar",
        "brainstormer",
        "yonc",
        "honc",
        "orchestrator",
    ]
    for exp in expected:
        assert exp in agent_ids

    # Unknown agent should fall back to generic
    generic = registry.get_adapter("unknown-bot")
    assert generic.agent_id == "unknown-bot"


def test_api_auth_and_endpoints(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path / "uuma_data",
        database_path=tmp_path / "uuma_data" / "uuma.db",
        artifact_dir=tmp_path / "uuma_data" / "artifacts",
        ingest_spool_dir=tmp_path / "uuma_data" / "spool",
        hermes_executable=tmp_path / "hermes.exe",
    )
    token = "secret-test-token"
    app = create_observatory_app(settings, auth_token=token)

    with TestClient(app) as client:
        # Unauthorized request
        res = client.get("/api/observatory/agents")
        assert res.status_code == 401

        # Authorized via Query param
        res = client.get(f"/api/observatory/agents?auth={token}")
        assert res.status_code == 200
        data = res.json()
        assert data["total_agents"] >= 7
        assert len(data["agents"]) >= 7

        # Authorized via Cookie
        client.cookies.set("uuma_obs_token", token)
        res = client.get("/api/observatory/agents")
        assert res.status_code == 200

        # Query events
        res = client.get("/api/observatory/events")
        assert res.status_code == 200
        assert "events" in res.json()

        # Query sources
        res = client.get("/api/observatory/sources")
        assert res.status_code == 200

        # Query specific agent items
        res = client.get("/api/observatory/agents/forge-lab-bot/items")
        assert res.status_code == 200
        assert "items" in res.json()


def test_api_loopback_passwordless(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path / "uuma_data",
        database_path=tmp_path / "uuma_data" / "uuma.db",
        artifact_dir=tmp_path / "uuma_data" / "artifacts",
        ingest_spool_dir=tmp_path / "uuma_data" / "spool",
        hermes_executable=tmp_path / "hermes.exe",
    )
    token = "secret-test-token"
    app = create_observatory_app(settings, auth_token=token, allow_loopback_without_auth=True)

    # TestClient with loopback IP client host
    with TestClient(app, client=("127.0.0.1", 54321)) as client:
        # Loopback root returns HTML index directly without redirect or 401
        res = client.get("/")
        assert res.status_code == 200
        assert "UuMA All-in-One Observatory" in res.text

        # Loopback API calls succeed without auth token or cookie
        res = client.get("/api/observatory/agents")
        assert res.status_code == 200
        data = res.json()
        assert data["total_agents"] >= 7


def test_specialized_adapters_and_endpoints(tmp_path: Path):
    data_dir = tmp_path / "uuma_data"
    data_dir.mkdir(parents=True)
    uuma_db = data_dir / "uuma.db"
    conn = sqlite3.connect(uuma_db)
    conn.execute("CREATE TABLE tasks (task_id TEXT PRIMARY KEY, title TEXT, status TEXT, assignee TEXT, contract_json TEXT, updated_sequence INTEGER)")
    conn.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, task_id TEXT, agent_id TEXT, status TEXT, progress_json TEXT, updated_sequence INTEGER)")
    conn.execute("CREATE TABLE events (sequence INTEGER PRIMARY KEY, occurred_at TEXT)")
    conn.execute("INSERT INTO tasks VALUES ('t_w1', 'Investigate Aeroponics', 'RUNNING', 'wisdom-oldman', '{}', 1)")
    conn.execute("INSERT INTO runs VALUES ('r_w1', 't_w1', 'wisdom-oldman', 'RUNNING', '{\"blocker\": null}', 1)")
    conn.execute("INSERT INTO events VALUES (1, '2026-10-14T10:00:00Z')")
    conn.commit()
    conn.close()

    # Create dummy brainstormer state
    bs_dir = data_dir / "brainstormer" / "projects" / "test_proj"
    bs_dir.mkdir(parents=True)
    state_file = bs_dir / "state.json"
    state_file.write_text(json.dumps({
        "project_id": "test_proj",
        "revision": 2,
        "updated_at": "2026-10-14T10:00:00Z",
        "objects": {
            "dec_1": {"type": "decision", "status": "accepted", "title": "Use Local SQLite"},
            "que_1": {"type": "question", "status": "open", "title": "How to scale?"},
        },
        "links": []
    }), encoding="utf-8")

    settings = Settings(
        data_dir=data_dir,
        database_path=uuma_db,
        artifact_dir=data_dir / "artifacts",
        ingest_spool_dir=data_dir / "spool",
        hermes_executable=tmp_path / "hermes.exe",
    )
    token = "secret-specialized-token"
    app = create_observatory_app(settings, auth_token=token)

    with TestClient(app) as client:
        # Agent overview endpoint
        res = client.get(f"/api/observatory/agents/brainstormer?auth={token}")
        assert res.status_code == 200
        bs_data = res.json()
        assert bs_data["agent_id"] == "brainstormer"
        assert len(bs_data["items"]) >= 1

        # Check item detail endpoint for the DAG item
        dag_item_id = bs_data["items"][0]["item_id"]
        res = client.get(f"/api/observatory/items/{dag_item_id}?auth={token}")
        assert res.status_code == 200
        item_data = res.json()
        assert item_data["item"]["kind"] == "decision_dag"
        assert len(item_data["item"]["payload"]["discussed_decisions"]) == 1
        assert len(item_data["item"]["payload"]["open_questions"]) == 1
        assert "topics" in item_data["item"]["payload"]
        assert len(item_data["item"]["payload"]["topics"]) >= 1
        assert any(it["kind"] == "architecture_topic" for it in bs_data["items"])

        # Check scholar stage progress item
        res = client.get(f"/api/observatory/agents/scholar?auth={token}")
        assert res.status_code == 200
        sc_data = res.json()
        assert any(it["kind"] == "stage_progress" for it in sc_data["items"])

        # Check wisdom active task item
        res = client.get(f"/api/observatory/agents/wisdom-oldman?auth={token}")
        assert res.status_code == 200
        ws_data = res.json()
        assert any("Investigate Aeroponics" in it["title"] for it in ws_data["items"])

        # Check yonc specialized items: Part 1, Part 2, Part 3, Part 4
        res = client.get(f"/api/observatory/agents/yonc?auth={token}")
        assert res.status_code == 200
        yonc_data = res.json()
        assert yonc_data["agent_id"] == "yonc"
        core_item = next((it for it in yonc_data["items"] if it["kind"] == "project_graph"), None)
        assert core_item is not None
        payload = core_item["payload"]
        assert "part1_timeline_projects" in payload
        assert "part2_assign_suggestions" in payload
        assert "part3_macro_stats" in payload
        assert "part4_activities" in payload
        assert len(payload["part1_timeline_projects"]) >= 1
        assert len(payload["part2_assign_suggestions"]) >= 1
        assert payload["part3_macro_stats"]["total_projects"] >= 1


def test_forge_project_codes_and_documents(tmp_path: Path):
    ws_dir = tmp_path / "Hardware-Lab-Workspace"
    proj_dir = ws_dir / "projects"
    proj1 = proj_dir / "p1-alpha"
    proj2 = proj_dir / "p2-beta"
    proj1.mkdir(parents=True)
    proj2.mkdir(parents=True)

    # p1 has explicit code "001" and a BOM file
    (proj1 / "project.yaml").write_text("project_id: p1-alpha\nproject_code: '001'\nname: Project Alpha\n", encoding="utf-8")
    (proj1 / "bom").mkdir()
    (proj1 / "bom" / "sample-bom.csv").write_text("part,qty\nresistor,10\n", encoding="utf-8")
    (proj1 / "docs").mkdir()
    (proj1 / "docs" / "arch.md").write_text("# Architecture\nDetails here.", encoding="utf-8")

    # p2 has no code (should be auto-assigned "002" -> "PROJ-002")
    (proj2 / "project.yaml").write_text("project_id: p2-beta\nname: Project Beta\n", encoding="utf-8")

    adapter = ForgeAdapter(tmp_path)
    adapter.workspace_dir = ws_dir
    adapter.projects_dir = proj_dir

    items = adapter.list_items()
    projs = [it for it in items if it.kind == "forge_project"]
    assert len(projs) == 2

    p1_item = next(p for p in projs if p.payload["folder_name"] == "p1-alpha")
    assert p1_item.payload["project_code"] == "001"
    assert p1_item.payload["display_code"] == "PROJ-001"
    assert "PROJ-001" in p1_item.title
    assert len(p1_item.payload["bom_files_details"]) == 1
    assert p1_item.payload["bom_files_details"][0]["name"] == "sample-bom.csv"
    assert len(p1_item.payload["docs_files_details"]) == 1

    p2_item = next(p for p in projs if p.payload["folder_name"] == "p2-beta")
    assert p2_item.payload["project_code"] == "002"
    assert p2_item.payload["display_code"] == "PROJ-002"
    assert "PROJ-002" in p2_item.title


def test_api_get_project_document(tmp_path: Path):
    data_dir = tmp_path / "uuma_data"
    data_dir.mkdir(parents=True)
    ws_dir = tmp_path / "Hardware-Lab-Workspace"
    proj_dir = ws_dir / "projects" / "test-sys"
    proj_dir.mkdir(parents=True)
    (proj_dir / "project.yaml").write_text("project_id: test-sys\nproject_code: '001'\nname: Test System\n", encoding="utf-8")
    (proj_dir / "bom").mkdir()
    (proj_dir / "bom" / "parts.csv").write_text("part,count\nmotor,2\n", encoding="utf-8")

    settings = Settings(
        data_dir=data_dir,
        database_path=data_dir / "uuma.db",
        artifact_dir=data_dir / "artifacts",
        ingest_spool_dir=data_dir / "spool",
        hermes_executable=tmp_path / "hermes.exe",
    )
    token = "secret-doc-token"
    app = create_observatory_app(settings, auth_token=token)

    # Point adapter to our test workspace
    forge = app.state.registry.get_adapter("forge-lab-bot")
    forge.workspace_dir = ws_dir
    forge.projects_dir = ws_dir / "projects"

    with TestClient(app) as client:
        # 1. Fetch valid doc
        res = client.get(f"/api/observatory/doc?project_id=test-sys&path=bom/parts.csv&auth={token}")
        assert res.status_code == 200
        doc = res.json()
        assert doc["filename"] == "parts.csv"
        assert "motor,2" in doc["content"]
        assert doc["extension"] == ".csv"

        # 2. Path traversal attack prevented
        res = client.get(f"/api/observatory/doc?project_id=test-sys&path=../../secret.txt&auth={token}")
        assert res.status_code == 400

        # 3. Missing file returns 404
        res = client.get(f"/api/observatory/doc?project_id=test-sys&path=bom/nonexistent.md&auth={token}")
        assert res.status_code == 404


def test_honc_adapter_and_endpoints(tmp_path: Path):
    data_dir = tmp_path / "uuma_data"
    data_dir.mkdir(parents=True)
    honc_dir = data_dir / "honc"
    honc_dir.mkdir(parents=True)
    honc_db = honc_dir / "honc.db"

    conn = sqlite3.connect(honc_db)
    conn.execute("CREATE TABLE life_operations (operation_id TEXT PRIMARY KEY, recorded_at TEXT)")
    conn.execute("CREATE TABLE life_objects (object_id TEXT PRIMARY KEY, kind TEXT, head_revision INTEGER)")
    conn.execute("CREATE TABLE life_revisions (object_id TEXT, revision INTEGER, status TEXT, payload_json TEXT, recorded_at TEXT)")
    conn.execute("INSERT INTO life_operations VALUES ('op_1', '2026-10-15T12:00:00Z')")
    conn.execute("INSERT INTO life_objects VALUES ('settings_1', 'settings', 1)")
    conn.execute(
        "INSERT INTO life_revisions VALUES ('settings_1', 1, 'active', "
        "'{\"wake_time\": \"08:00\", \"bedtime\": \"21:30\", \"grace_period_mins\": 30}', "
        "'2026-10-15T12:00:00Z')"
    )
    conn.execute("INSERT INTO life_objects VALUES ('habit_1', 'habit_definition', 1)")
    conn.execute(
        "INSERT INTO life_revisions VALUES ('habit_1', 1, 'active', "
        "'{\"definition\": {\"name\": \"运动健身\", \"semantic_role\": \"habit\"}, \"reminder\": {\"count\": 1, \"slots\": [{\"fixed_time\": \"16:00\"}]}}', "
        "'2026-10-15T12:00:00Z')"
    )
    conn.commit()
    conn.close()

    adapter = HoncAdapter(data_dir)
    items = adapter.list_items()
    assert len(items) >= 3
    assert any(it.kind == "runner" for it in items)
    assert any(it.kind == "settings" for it in items)
    assert any(it.kind == "habit_definition" for it in items)
    runner = next(it for it in items if it.kind == "runner")
    assert runner.payload["total_operations"] == 1

