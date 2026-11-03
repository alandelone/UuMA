import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def connector(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/check-scholar-graph-connector.py"
    spec = importlib.util.spec_from_file_location("scholar_connector", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    project = tmp_path / "project"
    profile = project / "connector"
    profile.mkdir(parents=True)
    launcher = project / "scripts/start-distributed-workstation.py"
    launcher.parent.mkdir()
    launcher.write_text("# fixture only", encoding="utf-8")
    config = profile / "startup.json"
    config.write_text(json.dumps({"schema_version": 1, "workspace": str(project),
                                  "services": module.expected_services()}), encoding="utf-8")
    marker = project / "owner.json"
    marker.write_text(json.dumps({"node_id": "alandelone-server-001", "namespace": "ScholarFieldKG",
                                  "project_id": "2", "local_url": "http://127.0.0.1:8892",
                                  "canonical_catalog_owner": "workstation"}), encoding="utf-8")
    calls = []
    monkeypatch.setattr(module.psutil, "net_connections", lambda **_kw: [])
    monkeypatch.setattr(module.runpy, "run_path", lambda _path: {
        "start": lambda root: calls.append(root) or {"scholar_fieldkg_tunnel": "started"}})
    values = {"config_sha256": module.sha(config), "launcher_sha256": module.sha(launcher)}
    return module, project, profile, marker, values, calls


def test_connector_restores_only_exact_existing_scope_and_never_restarts_receivers(connector):
    module, project, profile, marker, values, calls = connector
    result = module.run_once(project, profile, marker, **values)
    assert calls == [profile]
    assert result["services"]["scholar_fieldkg_tunnel"] == "started"
    assert not any(result[key] for key in ("server_restarted", "gateway_restarted", "catalog_modified"))


@pytest.mark.parametrize("barrier", ["config_hash", "launcher_hash", "extra_service", "owner"])
def test_connector_rejects_drift_or_broader_scope_before_starting(connector, barrier):
    module, project, profile, marker, values, calls = connector
    if barrier == "config_hash":
        values["config_sha256"] = "0" * 64
    elif barrier == "launcher_hash":
        values["launcher_sha256"] = "0" * 64
    elif barrier == "extra_service":
        config = profile / "startup.json"
        data = json.loads(config.read_text())
        data["services"]["other_agent"] = {}
        config.write_text(json.dumps(data))
        values["config_sha256"] = module.sha(config)
    else:
        data = json.loads(marker.read_text())
        data["project_id"] = "1"
        marker.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        module.run_once(project, profile, marker, **values)
    assert calls == []


@pytest.mark.parametrize("kind", ["foreign_process", "wrong_ssh", "public_bind", "no_owner"])
def test_connector_preserves_unexpected_listeners_without_launch_or_kill(connector, monkeypatch, kind):
    module, project, profile, marker, values, calls = connector
    local = SimpleNamespace(ip="0.0.0.0" if kind == "public_bind" else "127.0.0.1", port=8892)
    monkeypatch.setattr(module.psutil, "net_connections", lambda **_kw: [
        SimpleNamespace(status="LISTEN", laddr=local, pid=None if kind == "no_owner" else 123)])
    argv = ["python", "foreign"] if kind == "foreign_process" else ["ssh", "-N", "other-server"]
    monkeypatch.setattr(module.psutil, "Process", lambda _pid: SimpleNamespace(cmdline=lambda: argv))
    with pytest.raises(RuntimeError):
        module.run_once(project, profile, marker, **values)
    assert calls == []
