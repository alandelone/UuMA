"""New node identities can use the existing workstation bridge without moving browser state."""

import json

import pytest
from fastapi.testclient import TestClient

from uuma.auth import TokenRegistry
from uuma.chatgpt_server import admin_secret, create_app
from uuma.orbit_discovery import ChatGPTDiscoveryProvider
from uuma.settings import Settings


def test_discovery_uses_scoped_file_and_configured_bridge(monkeypatch, tmp_path):
    token_file = tmp_path / "agent.token"
    token_file.write_text("new-node-token\n", encoding="utf-8")
    monkeypatch.setenv("UUMA_CHATGPT_AGENT_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("UUMA_CHATGPT_BRIDGE_URL", "http://127.0.0.1:8787/")
    monkeypatch.setattr(Settings, "load_tokens", lambda _: pytest.fail("Legacy registry read"))
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            return json.dumps({"status": "RUNNING"})

    provider = ChatGPTDiscoveryProvider(token="legacy-constructor-token", opener=Opener())

    assert provider.check_status("request-existing") == {"status": "RUNNING"}
    assert requests[0].full_url == "http://127.0.0.1:8787/agent/requests/request-existing"
    assert requests[0].get_header("Authorization") == "Bearer new-node-token"
    assert requests[0].get_header("X-uuma-identity") == "wisdom-oldman"


@pytest.mark.parametrize("exists", [False, True])
def test_configured_missing_or_empty_discovery_token_does_not_fallback(
    monkeypatch, tmp_path, exists
):
    path = tmp_path / "agent.token"
    if exists:
        path.write_text(" \n", encoding="utf-8")
    monkeypatch.setenv("UUMA_CHATGPT_AGENT_TOKEN_FILE", str(path))
    monkeypatch.setattr(Settings, "load_tokens", lambda _: pytest.fail("Legacy registry read"))

    assert ChatGPTDiscoveryProvider(token="legacy-token")._resolve_token() is None


def test_bridge_accepts_only_new_registry_while_preserving_desktop_state(monkeypatch, tmp_path):
    desktop = tmp_path / "desktop"
    old = TokenRegistry(desktop / "tokens.json").initialize()
    registry = tmp_path / "new-node" / "tokens.json"
    new = TokenRegistry(registry).initialize()
    secret = admin_secret(desktop)
    old_registry_bytes = (desktop / "tokens.json").read_bytes()
    monkeypatch.setenv("UUMA_CHATGPT_TOKEN_REGISTRY", str(registry))
    monkeypatch.setenv("UUMA_CHATGPT_DATABASE_PATH", str(desktop / "independent-chatgpt.db"))
    app = create_app(desktop, start_worker=False)
    client = TestClient(app, base_url="http://127.0.0.1:8787")

    def headers(identity, token):
        return {"X-UuMA-Identity": identity, "Authorization": "Bearer " + token}

    assert client.get(
        "/agent/threads", headers=headers("wisdom-oldman", new["wisdom-oldman"])
    ).status_code == 200
    assert client.get(
        "/agent/threads", headers=headers("wisdom-oldman", old["wisdom-oldman"])
    ).status_code == 401
    assert client.get(
        "/agent/threads", headers=headers("orchestrator", new["wisdom-oldman"])
    ).status_code == 401
    assert client.get(
        "/agent/threads", headers=headers("honc", new["honc"])
    ).status_code == 403
    assert (desktop / "tokens.json").read_bytes() == old_registry_bytes
    assert admin_secret(desktop) == secret
    assert not (desktop / "uuma.db").exists()


def test_bridge_registry_override_must_exist_before_any_store_is_created(monkeypatch, tmp_path):
    root = tmp_path / "not-created"
    monkeypatch.setenv("UUMA_CHATGPT_TOKEN_REGISTRY", str(tmp_path / "missing.json"))

    with pytest.raises(ValueError, match="must already exist"):
        create_app(root, start_worker=False)

    assert not root.exists()
