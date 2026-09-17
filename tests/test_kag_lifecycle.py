from __future__ import annotations

import asyncio
import os
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import Request
from fastapi.responses import Response

from uuma import kag_bridge
from uuma.kag_adapter import KagRuntimeManager, KagUnavailableError
from uuma.kag_lifecycle import KagIdleTracker, runtime_lock


def test_active_request_prevents_idle_shutdown_and_resets_clock() -> None:
    now = [0.0]
    tracker = KagIdleTracker(30, clock=lambda: now[0])
    assert tracker.begin()
    now[0] = 31
    assert not tracker.idle_due()
    assert not tracker.claim_idle_shutdown()
    tracker.end()
    assert not tracker.idle_due()
    now[0] = 62
    assert tracker.idle_due()
    assert tracker.claim_idle_shutdown()
    assert tracker.closing
    assert not tracker.begin()


def test_idle_monitor_stops_only_dedicated_compose_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    compose = tmp_path / "docker-compose-west.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    now = [0.0]
    tracker = KagIdleTracker(30, clock=lambda: now[0])
    now[0] = 31
    server = SimpleNamespace(should_exit=False)
    stopped = threading.Event()
    run = Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setattr(kag_bridge.subprocess, "run", run)
    monitor = threading.Thread(
        target=kag_bridge._stop_when_idle,
        args=(tracker, compose, server, stopped),
        kwargs={"poll_seconds": 0.005},
    )
    monitor.start()
    deadline = time.monotonic() + 2
    while not server.should_exit and time.monotonic() < deadline:
        time.sleep(0.005)
    assert server.should_exit
    assert not run.called  # Wait until the HTTP listener has stopped.
    stopped.set()
    monitor.join(timeout=2)
    assert not monitor.is_alive()
    command = run.call_args.args[0]
    assert command == [
        "docker", "compose", "-p", "uuma-wisdom-kag", "-f", str(compose), "stop",
    ]
    assert "down" not in command


def test_runtime_lock_can_be_reused_without_removing_project_data(tmp_path: Path) -> None:
    compose = tmp_path / "docker-compose-west.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    with runtime_lock(compose):
        assert (tmp_path / ".uuma-kag-runtime.lock").is_file()
    with runtime_lock(compose):
        assert compose.is_file()


def test_bridge_reads_existing_profile_key_without_copying_it_to_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    secrets_file = tmp_path / ".env"
    secrets_file.write_text('OPENROUTER_API_KEY="test-secret"\n', encoding="utf-8")
    runtime = KagRuntimeManager(bridge_url="http://127.0.0.1:8891", secrets_file=secrets_file)

    environment = runtime._bridge_environment(tmp_path / "kag_config.yaml")

    assert environment["OPENAI_API_KEY"] == "test-secret"
    assert environment["UUMA_KAG_CONFIG"] == str(tmp_path / "kag_config.yaml")


def test_bridge_reports_missing_profile_key_without_exposing_file_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    secrets_file = tmp_path / ".env"
    secrets_file.write_text("OTHER_KEY=private-value\n", encoding="utf-8")
    runtime = KagRuntimeManager(bridge_url="http://127.0.0.1:8891", secrets_file=secrets_file)

    with pytest.raises(KagUnavailableError, match="KAG API key is missing") as exc_info:
        runtime._bridge_environment(tmp_path / "kag_config.yaml")

    assert "private-value" not in str(exc_info.value)


def test_health_reports_shutdown_without_initializing_kag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [0.0]
    tracker = KagIdleTracker(30, clock=lambda: now[0])
    now[0] = 31
    assert tracker.claim_idle_shutdown()
    monkeypatch.setattr(kag_bridge, "_idle_tracker", tracker)
    result = kag_bridge.health()
    assert result["ready"] is False
    assert "Idle shutdown" in result["error"]


def test_bridge_tracks_work_but_not_health_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [0.0]
    tracker = KagIdleTracker(30, clock=lambda: now[0])
    monkeypatch.setattr(kag_bridge, "_idle_tracker", tracker)

    async def next_call(_request: Request) -> Response:
        return Response("ok")

    def request(path: str) -> Request:
        return Request({"type": "http", "method": "POST", "path": path, "headers": []})

    now[0] = 31
    asyncio.run(kag_bridge.track_kag_activity(request("/health"), next_call))
    assert tracker.idle_due()
    asyncio.run(kag_bridge.track_kag_activity(request("/retrieve"), next_call))
    assert not tracker.idle_due()
    now[0] = 62
    assert tracker.claim_idle_shutdown()
    response = asyncio.run(kag_bridge.track_kag_activity(request("/retrieve"), next_call))
    assert response.status_code == 503


@pytest.mark.skipif(os.name != "nt", reason="Docker Desktop recovery is Windows-only")
def test_hung_docker_probe_retries_after_desktop_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    desktop = tmp_path / "Docker" / "Docker" / "Docker Desktop.exe"
    desktop.parent.mkdir(parents=True)
    desktop.touch()
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    calls = [0]

    def probe(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls[0] += 1
        if calls[0] == 1:
            raise subprocess.TimeoutExpired(cmd="docker info", timeout=10)
        return subprocess.CompletedProcess([], 0, "ready", "")

    monkeypatch.setattr("uuma.kag_adapter.subprocess.run", probe)
    launched = Mock()
    monkeypatch.setattr("uuma.kag_adapter.subprocess.Popen", launched)
    runtime = KagRuntimeManager(bridge_url="http://127.0.0.1:8891")
    runtime._ensure_docker_engine()
    assert calls[0] == 2
    launched.assert_called_once()
