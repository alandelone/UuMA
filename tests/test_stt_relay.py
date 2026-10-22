import base64
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from uuma import stt_relay


@pytest.fixture
def relay(tmp_path, monkeypatch):
    python, script, registry = (
        tmp_path / "python.exe", tmp_path / "hermes_stt.py", tmp_path / "tokens.json"
    )
    python.touch()
    script.touch()
    registry.write_text(json.dumps({"brainstormer": "speech-token", "yonc": "yonc-token",
                                    "orchestrator": "not-allowed"}), encoding="utf-8")
    settings = stt_relay.RelaySettings(python, script, registry, tmp_path)
    monkeypatch.setenv("UUMA_AGENT_ID", "brainstormer")
    token = tmp_path / "speech.token"
    token.write_text("speech-token", encoding="utf-8")
    monkeypatch.setenv("UUMA_STT_TOKEN_FILE", str(token))
    monkeypatch.setenv("UUMA_STT_RELAY_URL", "http://127.0.0.1:8774")
    return settings, TestClient(stt_relay.create_app(settings))


def payload(**changes):
    return {"audio_base64": base64.b64encode(b"audio").decode(), "extension": ".ogg", **changes}


def headers(identity="brainstormer", token="speech-token"):
    return {"Authorization": f"Bearer {token}", "X-Uuma-Identity": identity}


def test_authenticated_relay_runs_only_fixed_local_command_and_cleans_audio(relay, monkeypatch):
    settings, client = relay
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        assert command[:2] == [str(settings.python), str(settings.script)]
        assert command[2::2] == ["--input", "--output", "--language", "--model"]
        assert command[-3:] == ["auto", "--model", "stt"]
        assert kwargs["shell"] is False
        assert kwargs["timeout"] == 150
        assert "env" not in kwargs  # Credentials stay in the workstation's local environment.
        assert Path(command[3]).read_bytes() == b"audio"
        Path(command[5]).write_text("语音内容", encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(stt_relay.subprocess, "run", run)
    response = client.post("/v1/transcribe", headers=headers(), json=payload())
    assert response.status_code == 200
    assert response.json() == {"transcript": "语音内容", "agent_id": "brainstormer"}
    assert len(commands) == 1
    assert not Path(commands[0][3]).exists()
    assert not Path(commands[0][5]).parent.exists()


@pytest.mark.parametrize("identity, token", [
    ("brainstormer", "yonc-token"), ("orchestrator", "not-allowed"),
    ("scholar", "speech-token"), ("brainstormer", "wrong"),
])
def test_relay_rejects_identity_spoofing_and_unapproved_agents(relay, monkeypatch, identity, token):
    _settings, client = relay
    monkeypatch.setattr(stt_relay.subprocess, "run", lambda *_a, **_k: pytest.fail("must not run"))
    response = client.post("/v1/transcribe", headers=headers(identity, token), json=payload())
    assert response.status_code == 403


@pytest.mark.parametrize("changes", [
    {"extension": ".exe"}, {"audio_base64": "not base64"}, {"audio_base64": ""},
    {"path": "C:/private.wav"}, {"command": "anything"}, {"url": "https://example.invalid"},
    {"model": "--router-url"}, {"language": "--help"},
])
def test_relay_rejects_unbounded_or_arbitrary_inputs(relay, monkeypatch, changes):
    _settings, client = relay
    monkeypatch.setattr(stt_relay.subprocess, "run", lambda *_a, **_k: pytest.fail("must not run"))
    response = client.post("/v1/transcribe", headers=headers(), json=payload(**changes))
    assert response.status_code == 422


def test_relay_enforces_decoded_and_request_size_limits(relay, monkeypatch):
    _settings, client = relay
    monkeypatch.setattr(stt_relay, "MAX_AUDIO_BYTES", 3)
    assert client.post("/v1/transcribe", headers=headers(), json=payload()).status_code == 422
    monkeypatch.setattr(stt_relay, "MAX_REQUEST_BYTES", 4)
    assert client.post("/v1/transcribe", headers=headers(), json=payload()).status_code == 413


def test_relay_timeout_returns_waiting_failure_and_cleans_audio(relay, monkeypatch):
    settings, client = relay
    calls = []

    def timeout(command, **_kwargs):
        calls.append(command)
        raise subprocess.TimeoutExpired(command, 150)

    monkeypatch.setattr(stt_relay.subprocess, "run", timeout)
    response = client.post("/v1/transcribe", headers=headers(), json=payload())
    assert response.status_code == 503
    assert "desktop_unavailable" in response.json()["detail"]
    assert "transcript" not in response.json()
    assert len(calls) == 1
    assert not list(settings.temporary_root.glob("uuma-stt-*"))


def test_remote_client_disconnect_is_one_request_and_writes_no_transcript(relay, tmp_path):
    calls = []

    def disconnected(request):
        calls.append(request)
        raise httpx.ReadTimeout("response lost", request=request)

    audio, output = tmp_path / "voice.ogg", tmp_path / "output.txt"
    audio.write_bytes(b"audio")
    with (
        httpx.Client(transport=httpx.MockTransport(disconnected)) as client,
        pytest.raises(stt_relay.RelayUnavailable, match="not retried"),
    ):
        stt_relay.transcribe_remote(audio, output, client=client)
    assert len(calls) == 1
    assert not output.exists()


def test_remote_client_writes_plain_text_on_success(relay, tmp_path):
    calls = []

    def success(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer speech-token"
        assert json.loads(request.content)["model"] == "stt"
        return httpx.Response(200, json={"transcript": "hello", "agent_id": "brainstormer"})

    audio, output = tmp_path / "voice.ogg", tmp_path / "output.txt"
    audio.write_bytes(b"audio")
    with httpx.Client(transport=httpx.MockTransport(success)) as client:
        stt_relay.transcribe_remote(audio, output, client=client)
    assert output.read_text(encoding="utf-8") == "hello"
    assert len(calls) == 1
