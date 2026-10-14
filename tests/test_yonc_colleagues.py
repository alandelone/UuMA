from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from uuma import mcp_worker
from uuma.colleague_directory import colleague_capabilities
from uuma.models import AgentDefinition, RiskLevel, TaskContract
from uuma.service import ControlPlane
from uuma.settings import Settings

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("deploy_yonc_test", ROOT / "scripts/deploy-yonc-profile.py")
assert SPEC and SPEC.loader
DEPLOY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEPLOY)


@pytest.fixture
def control(tmp_path):
    return ControlPlane(Settings(
        data_dir=tmp_path, database_path=tmp_path / "uuma.db", artifact_dir=tmp_path / "artifacts",
        ingest_spool_dir=tmp_path / "spool", hermes_executable=tmp_path / "hermes.exe",
    ))


def test_directory_preserves_disabled_state_and_only_discloses_aggregate_workload(control):
    control.bootstrap()
    scholar = control.require_agent("scholar").model_copy(update={"enabled": False})
    control.register_agent(scholar, actor_id="system")
    control.register_direct_run("brainstormer", TaskContract(
        title="Private user project", objective="Private project objective", source="direct",
        risk_level=RiskLevel.READ_ONLY, required_capabilities={"brainstorming"},
    ))
    before = control.list_agents()
    result = colleague_capabilities(control)
    records = {record["agent_id"]: record for record in result["agents"]}
    assert records["scholar"]["registered_definition"]["enabled"] is False
    assert records["brainstormer"]["active_run_counts"] == {"RUNNING": 1}
    assert all(record["runtime_readiness"] == "NOT_CHECKED" for record in result["agents"])
    assert "Private user project" not in json.dumps(result)
    assert control.list_agents() == before
    assert len(control.list_runs()) == 1
    assert all(source["sha256"] for record in result["agents"] for source in record["role_sources"])
    filtered = colleague_capabilities(control, capability="research")
    assert [record["agent_id"] for record in filtered["agents"]] == ["scholar"]


def test_empty_registry_is_not_bootstrapped_by_a_capability_read(control):
    result = colleague_capabilities(control)
    assert result["agents"] == []
    assert "scholar" in result["unregistered_role_ids"]
    assert control.list_agents() == []


def test_custom_agents_and_missing_sources_remain_explicit(control, tmp_path):
    control.bootstrap()
    control.register_agent(AgentDefinition(
        agent_id="new-worker", display_name="New worker", description="Operator registered role",
        capabilities={"custom_work"},
    ), actor_id="system")
    custom = colleague_capabilities(control, agent_id="new-worker")["agents"][0]
    assert custom["role_guidance"] is None
    assert custom["role_sources"] == []
    known = colleague_capabilities(control, agent_id="scholar", source_root=tmp_path)["agents"][0]
    assert all(source["available"] is False and source["sha256"] is None
               for source in known["role_sources"])
    assert {entry["name"] for entry in colleague_capabilities(control)["supporting_systems"]} == {
        "CopyCat", "eSchematic",
    }


@pytest.mark.parametrize("agent,mode", [("brainstormer", "standard"), ("yonc", "native")])
def test_lookup_rejects_other_identities_and_native_mode_before_store_access(monkeypatch, agent, mode):
    monkeypatch.setenv("UUMA_AGENT_ID", agent)
    monkeypatch.setenv("UUMA_WORKER_MODE", mode)
    def fail():
        pytest.fail("An unauthorized caller must not open the control store")
    monkeypatch.setattr(mcp_worker, "ControlPlane", fail)
    with pytest.raises(PermissionError):
        mcp_worker.yonc_get_colleague_capabilities()


def test_yonc_lookup_does_not_bootstrap_operator_registry_changes(monkeypatch, control):
    control.bootstrap()
    agent = control.require_agent("scholar").model_copy(update={"enabled": False})
    control.register_agent(agent, actor_id="system")
    monkeypatch.setenv("UUMA_AGENT_ID", "yonc")
    monkeypatch.setenv("UUMA_WORKER_MODE", "standard")
    monkeypatch.setattr(mcp_worker, "ControlPlane", lambda: control)
    assert mcp_worker.yonc_get_colleague_capabilities("scholar")["agents"][0][
        "registered_definition"
    ]["enabled"] is False


def test_deployment_preserves_config_and_custom_preferences_and_installs_sources(tmp_path):
    home = tmp_path / "profiles/yonc"
    home.mkdir(parents=True)
    (home / "SOUL.md").write_text(
        f"User preference\n{DEPLOY.BEGIN}\nOld managed profile\n{DEPLOY.END}\n", encoding="utf-8",
    )
    config = {
        "model": {"default": "thinking"}, "custom_provider": {"api_key": "test-secret"},
        "mcp_servers": {
            "uuma-worker": {"command": sys.executable, "env": {"UUMA_DATA_DIR": str(tmp_path)}},
            "yonc-project": {"command": sys.executable, "env": {
                "PYTHONPATH": str(tmp_path / "project"), "YONC_API_URL": "http://127.0.0.1:9876",
            }},
        },
    }
    yaml = YAML()
    with (home / "config.yaml").open("w", encoding="utf-8") as handle:
        yaml.dump(config, handle)
    unrelated = home / "skills/unrelated/SKILL.md"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("Preserve this unrelated skill", encoding="utf-8")
    report = DEPLOY.deploy(ROOT, home, tmp_path / "backups", apply=True)
    installed = YAML(typ="safe").load((home / "config.yaml").read_text(encoding="utf-8"))
    assert installed["model"] == config["model"]
    assert installed["custom_provider"] == config["custom_provider"]
    assert installed["mcp_servers"]["yonc-project"]["env"]["YONC_API_URL"] == "http://127.0.0.1:9876"
    assert installed["mcp_servers"]["uuma-worker"]["tools"]["include"][-1] == (
        "yonc_get_colleague_capabilities"
    )
    assert "User preference" in (home / "SOUL.md").read_text(encoding="utf-8")
    assert report["quarantined_skill_count"] == 1
    backup = Path(report["backup_home"])
    assert (backup / "skills/yonc/unrelated/SKILL.md").read_text() == "Preserve this unrelated skill"
    refs = home / "skills/yonc-colleagues/references"
    manifest = json.loads((refs / "source-manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["sources"]) == 12
    for item in manifest["sources"]:
        assert (refs / item["file"]).read_bytes() == (ROOT / item["source"]).read_bytes()
    second = DEPLOY.deploy(ROOT, home, tmp_path / "backups", apply=True)
    assert second["quarantined_skill_count"] == 0
    assert "User preference" in (home / "SOUL.md").read_text(encoding="utf-8")


def test_deployment_refuses_unmanaged_soul_customization():
    with pytest.raises(ValueError, match="Custom SOUL"):
        DEPLOY.managed_soul("Custom instructions", "New source", "Previous source")
