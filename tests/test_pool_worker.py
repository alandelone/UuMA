import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from uuma.gemini_worker import GeminiTask, GeminiWorker, GeminiWorkerSettings


@pytest.fixture
def worker(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    pool = tmp_path / "pool"
    pool.mkdir()
    (pool / "pool.json").write_text('{"schema_version":1}', encoding="utf-8")
    wrapper = tmp_path / "agy-pool"
    wrapper.write_text("# reviewed wrapper", encoding="utf-8")
    monkeypatch.setenv("UUMA_AGY_POOL_ROOT", str(pool))
    monkeypatch.setenv("GEMINI_WORKER_WRAPPER_SHA256",
                       hashlib.sha256(wrapper.read_bytes()).hexdigest())
    settings = GeminiWorkerSettings(allowed_roots=(workspace,), log_root=tmp_path / "receipts",
                                    executable=str(wrapper), timeout_seconds=12,
                                    backend="account_pool")
    return GeminiWorker(settings), workspace


def package(workspace):
    return GeminiTask(task="Compare two bounded proposals", working_directory=str(workspace),
                      context=["A costs 2; B costs 3"], constraints=["Do not write files"],
                      expected_output="Cost comparison", done_when="Both costs stated")


def fake_process(monkeypatch, payload, code=0):
    calls = []

    class Process:
        pid = 123456
        returncode = code

        def __init__(self, command, **kwargs):
            calls.append({"command": command, **kwargs})

        def communicate(self, input=None, timeout=None):
            calls[-1].update(prompt=input, timeout=timeout)
            return json.dumps(payload), ""

    monkeypatch.setattr(subprocess, "Popen", Process)
    return calls


@pytest.mark.parametrize("field", ["response", "result"])
def test_pool_backend_preserves_task_contract_and_review_boundary(worker, monkeypatch, field):
    runtime, workspace = worker
    calls = fake_process(monkeypatch, {field: "A is cheaper", "usage": {"input_tokens": 12}})
    result = runtime.run(package(workspace), "brainstormer")
    assert result["status"] == "completed"
    assert result["result"] == "A is cheaper"
    assert result["actual_model"] is None  # No invented observed model identity.
    assert result["requested_model"] == "gemini-3.8-flash-medium"
    assert result["backend"] == "account_pool"
    assert len(calls) == 1
    command = calls[0]["command"]
    assert command[command.index("--mode") + 1] == "plan"
    assert "--sandbox" in command and "--disable-slash-commands" in command
    assert command[command.index("--print-timeout") + 1] == "12s"
    assert not any(x in command for x in ["--continue", "--dangerously-skip-permissions"])
    assert calls[0]["cwd"] == workspace
    for text in ["Compare two bounded proposals", "A costs 2", "Do not write files",
                 "Cost comparison", "Both costs stated", "stateless worker"]:
        assert text in calls[0]["prompt"]
    assert "Compare two bounded proposals" not in command
    saved = json.loads(Path(result["log_path"]).read_text(encoding="utf-8"))
    assert saved["requested_by"] == "brainstormer"
    assert saved["approval_mode"] == "plan"
    assert saved["task_id"] == result["task_id"]
    assert result["warnings"]  # Do not claim a filesystem audit or automatic acceptance.


@pytest.mark.parametrize("payload", [[], {}, {"result": ""}, {"is_error": True, "result": "bad"},
                                      {"error": "quota", "response": "not success"}])
def test_never_accepts_empty_or_provider_error_results(worker, monkeypatch, payload):
    runtime, workspace = worker
    calls = fake_process(monkeypatch, payload)
    result = runtime.run(package(workspace), "brainstormer")
    assert result["status"] == "error"
    assert len(calls) == 1  # Never blindly replay model work.


def test_busy_pool_does_not_fall_back_or_retry(worker, monkeypatch):
    runtime, workspace = worker
    calls = fake_process(monkeypatch, {}, code=75)
    result = runtime.run(package(workspace), "brainstormer")
    assert result["status"] == "blocked"
    assert result["exit_code"] == 75
    assert len(calls) == 1


def test_scope_identity_mode_and_wrapper_hash_checked_before_launch(worker, monkeypatch):
    runtime, workspace = worker
    calls = fake_process(monkeypatch, {"result": "must not run"})
    with pytest.raises(PermissionError):
        runtime.run(package(workspace), "honc")
    with pytest.raises(PermissionError):
        runtime.run(package(workspace.parent), "brainstormer")
    with pytest.raises(PermissionError, match="plan"):
        GeminiWorker(replace(runtime.settings, approval_mode="auto_edit")).run(
            package(workspace), "brainstormer")
    monkeypatch.setenv("GEMINI_WORKER_WRAPPER_SHA256", "wrong")
    with pytest.raises(PermissionError, match="binding"):
        runtime.run(package(workspace), "brainstormer")
    assert not calls


def test_legacy_gemini_backend_remains_explicit_default(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_WORKER_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.delenv("GEMINI_WORKER_BACKEND", raising=False)
    monkeypatch.delenv("GEMINI_WORKER_EXECUTABLE", raising=False)
    settings = GeminiWorkerSettings.from_env()
    assert settings.backend == "gemini_cli" and settings.executable == "gemini"
    monkeypatch.setenv("GEMINI_WORKER_BACKEND", "account_pool")
    with pytest.raises(ValueError, match="wrapper"):
        GeminiWorkerSettings.from_env()


def test_native_backend_keeps_existing_cli_contract(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("uuma.gemini_worker.shutil.which", lambda _: "/native/gemini")

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, '{"response":"native result"}', "")

    monkeypatch.setattr(subprocess, "run", run)
    settings = GeminiWorkerSettings(allowed_roots=(tmp_path,), log_root=tmp_path / "logs")
    result = GeminiWorker(settings).run(package(tmp_path), "brainstormer")
    assert result["status"] == "completed" and result["result"] == "native result"
    assert len(calls) == 1
    assert calls[0][0][0] == "/native/gemini"
    assert calls[0][0][-2:] == ["--approval-mode", "plan"]
    assert "--prompt" in calls[0][0] and calls[0][1]["cwd"] == tmp_path


def test_timeout_stops_owned_group_and_never_replays(worker, monkeypatch):
    runtime, workspace = worker
    instances = []
    stopped = []

    class Process:
        def __init__(self, *args, **kwargs):
            instances.append(self)

        def communicate(self, *args, **kwargs):
            raise subprocess.TimeoutExpired("owned-wrapper", 12)

    monkeypatch.setattr(subprocess, "Popen", Process)
    monkeypatch.setattr(GeminiWorker, "_stop_pool_process", staticmethod(stopped.append))
    result = runtime.run(package(workspace), "brainstormer")
    assert result["status"] == "error"
    assert result["execution_outcome"] == "requires_reconciliation"
    assert instances == stopped and len(stopped) == 1
