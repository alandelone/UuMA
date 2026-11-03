import json

import pytest

from uuma import a2a_client


def test_exact_loopback_origin_maps_to_existing_forward_and_keeps_agent_path(monkeypatch):
    monkeypatch.setenv("UUMA_A2A_LOOPBACK_FORWARDS", json.dumps({
        "http://127.0.0.1:8768": "http://127.0.0.1:18768",
    }))
    assert a2a_client._transport_endpoint("http://127.0.0.1:8768/agents/brainstormer") == (
        "http://127.0.0.1:18768/agents/brainstormer"
    )
    for endpoint in ("http://127.0.0.1:8769/agents/brainstormer",
                     "https://node.example/agents/brainstormer"):
        assert a2a_client._transport_endpoint(endpoint) == endpoint


def test_default_keeps_registered_endpoint(monkeypatch):
    monkeypatch.delenv("UUMA_A2A_LOOPBACK_FORWARDS", raising=False)
    endpoint = "http://127.0.0.1:8768/agents/brainstormer"
    assert a2a_client._transport_endpoint(endpoint) == endpoint


@pytest.mark.parametrize("forward", [
    "https://external.example:443", "http://user:secret@127.0.0.1:18768",
    "http://127.0.0.1:18768/agents", "http://127.0.0.1:18768?token=secret",
    "http://127.0.0.1:18768#fragment", "http://localhost", 18768,
])
def test_forward_cannot_send_credentials_to_non_loopback_or_replace_agent_paths(monkeypatch, forward):
    monkeypatch.setenv("UUMA_A2A_LOOPBACK_FORWARDS", json.dumps({
        "http://127.0.0.1:8768": forward,
    }))
    with pytest.raises((ValueError, TypeError)):
        a2a_client._transport_endpoint("http://127.0.0.1:8768/agents/brainstormer")


def test_dispatch_uses_forward_and_keeps_identity_and_a2a_headers(monkeypatch):
    monkeypatch.setenv("UUMA_A2A_LOOPBACK_FORWARDS", json.dumps({
        "http://127.0.0.1:8768": "http://127.0.0.1:18768",
    }))
    monkeypatch.setattr(a2a_client, "credential", lambda: ("orchestrator", "private"))
    calls = []

    class Client:
        def __init__(self, endpoint, identity, token):
            calls.append((endpoint, identity, token))

        def request(self, *args, **kwargs):
            calls.append((args, kwargs))
            return {"result": {"task": {"id": "received"}}}

    monkeypatch.setattr(a2a_client, "ControlClient", Client)
    result = a2a_client.call({"endpoint": "http://127.0.0.1:8768/agents/brainstormer"},
                             "SendMessage", {"run": "one"}, "message-one")
    assert result["task"]["id"] == "received"
    assert calls[0] == ("http://127.0.0.1:18768/agents/brainstormer", "orchestrator", "private")
    args, kwargs = calls[1]
    assert args[:2] == ("POST", "/rpc")
    assert args[2]["id"] == "message-one" and args[2]["params"] == {"run": "one"}
    assert kwargs["extra_headers"]["A2A-Version"] == "1.0"


def test_forward_does_not_grant_dispatch_authority(monkeypatch):
    monkeypatch.setattr(a2a_client, "credential", lambda: ("brainstormer", "private"))
    with pytest.raises(PermissionError):
        a2a_client.call({"endpoint": "http://127.0.0.1:8768/agents/brainstormer"},
                        "SendMessage", {}, "one")
