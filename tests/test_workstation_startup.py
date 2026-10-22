import importlib.util
import json
from contextlib import nullcontext
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "workstation_startup_test", Path(__file__).parents[1] / "scripts/start-distributed-workstation.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def prepare(tmp_path, monkeypatch, service):
    (tmp_path / "startup.json").write_text(json.dumps({
        "schema_version": 1, "workspace": str(tmp_path), "services": {"desktop": service},
    }))
    monkeypatch.setattr(MODULE, "BrainstormerProcessLock", lambda *_: nullcontext())
    monkeypatch.setattr(MODULE, "alive", lambda *_: False)
    return tmp_path


def test_existing_owned_process_is_reused(tmp_path, monkeypatch):
    profile = prepare(tmp_path, monkeypatch, {"argv": ["python", "-m", "uuma.a2a_node"]})
    monkeypatch.setattr(MODULE, "alive", lambda *_: True)
    monkeypatch.setattr(MODULE.subprocess, "Popen", lambda *_a, **_k: pytest.fail("duplicate process"))
    assert MODULE.start(profile) == {"desktop": "running"}


def test_port_conflict_is_preserved_and_fails_closed(tmp_path, monkeypatch):
    profile = prepare(tmp_path, monkeypatch, {
        "argv": ["python"], "port": 8770, "module": "uuma.a2a_node",
    })
    monkeypatch.setattr(MODULE, "listening", lambda _: True)
    monkeypatch.setattr(MODULE.psutil, "net_connections", lambda **_: [])
    monkeypatch.setattr(MODULE.subprocess, "Popen", lambda *_a, **_k: pytest.fail("port overwritten"))
    with pytest.raises(RuntimeError, match="port conflict"):
        MODULE.start(profile)


def test_new_process_uses_fixed_argv_hidden_no_shell_and_writes_receipt(tmp_path, monkeypatch):
    profile = prepare(tmp_path, monkeypatch, {
        "argv": ["python", "-m", "uuma.a2a_node"], "environment": {"TEST_IDENTITY": "fixture"},
    })
    seen = []

    def popen(argv, **kwargs):
        seen.append((argv, kwargs))
        return type("Owned", (), {"pid": 123})()

    monkeypatch.setattr(MODULE.subprocess, "Popen", popen)
    assert MODULE.start(profile) == {"desktop": "started"}
    assert seen[0][0] == ["python", "-m", "uuma.a2a_node"]
    assert seen[0][1]["shell"] is False
    assert seen[0][1]["env"]["TEST_IDENTITY"] == "fixture"
    assert json.loads((profile / "startup-processes.json").read_text())["desktop"]["pid"] == 123
