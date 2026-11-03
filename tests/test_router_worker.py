from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest

from uuma.gemini_worker import GeminiTask, GeminiWorker, GeminiWorkerSettings


def make_worker(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    worker = GeminiWorker(GeminiWorkerSettings(
        allowed_roots=(workspace,), log_root=tmp_path / "receipts", backend="router_api",
        base_url="http://127.0.0.1:8080/v1", model="complex", timeout_seconds=10,
    ))
    package = GeminiTask(
        task="Analyze a synthetic cost fixture", working_directory=str(workspace),
        context=["Assumed cost: 10 MYR"], constraints=["No research or files"],
        expected_output="Provisional calculation", done_when="Unknowns explicit",
    )
    return worker, package


def transport(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr("uuma.gemini_worker.httpx.Client", lambda **kw: original(
        transport=httpx.MockTransport(handler), **kw,
    ))
    monkeypatch.setattr("uuma.gemini_worker.time.sleep", lambda _: None)


def completed(**updates):
    return {"id": "router-one", "status": "completed", "attempts": 1, "response": {
        "id": "completion-one", "model": "observed-model", "usage": {"total_tokens": 12},
        "choices": [{"finish_reason": "stop", "message": {"content": "Assumed: 10 MYR"}}],
        **updates,
    }}


def test_router_submits_once_polls_same_run_and_persists_receipt(tmp_path, monkeypatch):
    worker, package = make_worker(tmp_path)
    calls = []

    def handle(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(202 if request.method == "POST" else 200,
                                  json={"id": "router-one", "status": "running"})
        return httpx.Response(200, json=completed())

    transport(monkeypatch, handle)
    result = worker.run(package, "brainstormer")
    assert result["status"] == "completed"
    assert result["requested_model"] == "complex"
    assert result["actual_model"] == "observed-model"
    assert result["external_run_id"] == "router-one"
    assert [call.method for call in calls] == ["POST", "GET", "GET"]
    body = json.loads(calls[0].content)
    assert body["model"] == "complex" and body["max_attempts"] == 1
    assert "tools" not in body and "Assumed cost: 10 MYR" in body["messages"][1]["content"]
    assert calls[0].headers["idempotency-key"] == result["task_id"]
    assert all(call.url.path.endswith("/router-one") for call in calls[1:])
    saved = json.loads(next((tmp_path / "receipts").rglob("*.json")).read_text())
    assert saved["response_id"] == "completion-one" and saved["stats"]["total_tokens"] == 12


@pytest.mark.parametrize("payload", [
    {"id": "router-one", "status": "failed"},
    {},
    completed(choices=[]),
    completed(choices=[{"finish_reason": "length", "message": {"content": "cut off"}}]),
    completed(choices=[{"finish_reason": "stop", "message": {"content": ""}}]),
    completed(error={"message": "SECRET must not be logged"}),
])
def test_invalid_or_incomplete_results_never_complete_or_replay(tmp_path, monkeypatch, payload):
    worker, package = make_worker(tmp_path)
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=payload)

    transport(monkeypatch, handle)
    result = worker.run(package, "brainstormer")
    assert result["status"] == "error" and len(calls) == 1
    assert "SECRET" not in json.dumps(result)


def test_timeout_preserves_remote_identity_for_reconciliation(tmp_path, monkeypatch):
    worker, package = make_worker(tmp_path)
    clock = [0]

    def tick():
        clock[0] += 20
        return clock[0]

    monkeypatch.setattr("uuma.gemini_worker.time.monotonic", tick)
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(202, json={"id": "router-one", "status": "queued"})

    transport(monkeypatch, handle)
    result = worker.run(package, "brainstormer")
    assert result["execution_outcome"] == "requires_reconciliation"
    assert result["external_run_id"] == "router-one"
    assert len(calls) == 1


def test_http_errors_do_not_expose_credentials_or_retry(tmp_path, monkeypatch):
    worker, package = make_worker(tmp_path)
    monkeypatch.setenv("GEMINI_WORKER_API_KEY", "PRIVATE")
    calls = []

    def handle(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer PRIVATE"
        return httpx.Response(503, json={"error": "PRIVATE"})

    transport(monkeypatch, handle)
    result = worker.run(package, "brainstormer")
    assert len(calls) == 1 and "PRIVATE" not in json.dumps(result)
    assert result["status"] == "error"


def test_scope_mode_and_endpoint_validation_before_submission(tmp_path):
    worker, package = make_worker(tmp_path)
    with pytest.raises(PermissionError):
        worker.run(package, "honc")
    with pytest.raises(PermissionError):
        worker.run(package.model_copy(update={"working_directory": str(tmp_path)}), "brainstormer")
    with pytest.raises(PermissionError, match="plan"):
        GeminiWorker(replace(worker.settings, approval_mode="auto_edit")).run(package, "brainstormer")
    for endpoint in ("", "http://user:secret@host/v1", "http://host/v1?key=secret"):
        with pytest.raises(ValueError, match="base URL"):
            GeminiWorker(replace(worker.settings, base_url=endpoint)).run(package, "brainstormer")


def test_router_backend_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_WORKER_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("GEMINI_WORKER_BACKEND", "router_api")
    monkeypatch.setenv("GEMINI_WORKER_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("GEMINI_WORKER_MODEL", "complex")
    settings = GeminiWorkerSettings.from_env()
    assert settings.backend == "router_api" and settings.model == "complex"
    assert settings.base_url.endswith(":8080/v1")
