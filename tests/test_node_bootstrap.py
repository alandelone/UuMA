import json
import sqlite3

import pytest

from uuma.node_bootstrap import initialize


def test_fresh_baseline_keeps_all_agents_but_never_imports_or_resumes_tasks(tmp_path):
    target = tmp_path / "new-control"
    receipt = initialize(target, node="server", authorization="User permits losing old control history")
    assert receipt["task_count"] == receipt["run_count"] == 0
    assert receipt["event_chain_valid"] is True
    assert receipt["production_active"] is False
    assert "scholar" in receipt["agents"]
    with sqlite3.connect(target / "uuma.db") as conn:
        paused = [json.loads(row[0]) for row in conn.execute(
            "SELECT payload_json FROM events WHERE event_type='DEPLOYMENT_INTAKE_CHANGED'"
        )]
        assert len(paused) == len(receipt["agents"])
        assert all(row["paused"] for row in paused)
    tokens = json.loads((target / "tokens.json").read_text())
    assert len(set(tokens.values())) == len(tokens)
    assert (target / "identities/orchestrator.token").read_text().strip() == tokens["orchestrator"]
    assert not (target / "wisdom.db").exists()


def test_bootstrap_refuses_to_touch_existing_directory(tmp_path):
    target = tmp_path / "old"
    target.mkdir()
    (target / "uuma.db").write_bytes(b"preserved damaged database")
    with pytest.raises(FileExistsError):
        initialize(target, node="server", authorization="authorized")
    assert (target / "uuma.db").read_bytes() == b"preserved damaged database"


def test_authorization_required_before_creating_anything(tmp_path):
    target = tmp_path / "new"
    with pytest.raises(ValueError):
        initialize(target, node="server", authorization=" ")
    assert not target.exists()


def test_bootstrap_intake_gate_can_be_addressed_through_authenticated_api(tmp_path):
    from uuma.api import IntakeRequest

    receipt = initialize(tmp_path / "fresh", node="server", authorization="authorized")
    body = IntakeRequest(agents=["brainstormer"], plan_id=receipt["baseline_id"], paused=False)
    assert body.plan_id == receipt["baseline_id"]


def test_control_startup_can_wait_for_knowledge_without_creating_empty_domain_database(
    tmp_path, monkeypatch,
):
    from dataclasses import replace

    from starlette.testclient import TestClient

    from uuma.api import create_app
    from uuma.settings import Settings

    monkeypatch.setenv("UUMA_KNOWLEDGE_REQUIRE_EXISTING", "1")
    directory = tmp_path / "control"
    initialize(directory, node="server", authorization="authorized")
    settings = replace(Settings.from_env(), data_dir=directory, database_path=directory / "uuma.db",
                       artifact_dir=directory / "artifacts", ingest_spool_dir=directory / "spool",
                       knowledge_data_dir=tmp_path / "knowledge")
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/wisdom/topics").status_code == 503
    assert not (tmp_path / "knowledge/wisdom.db").exists()
