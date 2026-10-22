import pytest

from uuma.runtime_registry import EndpointBinding, RuntimeRegistry
from uuma.service import ControlPlane, PolicyDeniedError
from uuma.settings import Settings


def test_endpoint_binding_is_audited_and_requires_control_identity(tmp_path):
    control = ControlPlane(
        Settings(
            tmp_path,
            tmp_path / "uuma.db",
            tmp_path / "artifacts",
            tmp_path / "spool",
            tmp_path / "hermes",
        )
    )
    control.bootstrap()
    registry = RuntimeRegistry(control)
    binding = EndpointBinding(
        agent_id="brainstormer",
        node_id="server",
        runtime="hermes",
        endpoint="http://127.0.0.1:8768/agents/brainstormer",
        revision="fixture",
    )
    assert registry.list() == []
    with pytest.raises(PolicyDeniedError):
        registry.bind(binding, actor_id="brainstormer")
    registry.bind(binding, actor_id="orchestrator")
    assert registry.get("brainstormer") == binding.model_dump(mode="json")
    assert control.events.verify_chain()[0]
    assert list(control.events.iter_events())[-1].event_type == "AGENT_ENDPOINT_BOUND"


def test_send_run_uses_sdk_types_and_current_execution_epoch(monkeypatch):
    pytest.importorskip("a2a")
    from uuma import a2a_client

    def call(binding, method, params, request_id):
        assert method == "SendMessage"
        assert params["metadata"]["execution_epoch"] == 4
        assert params["configuration"]["returnImmediately"] is True
        assert params["message"]["messageId"] == "uuma:run:4"
        return {"ok": True}

    monkeypatch.setattr(a2a_client, "call", call)
    assert a2a_client.send_run({}, {"run_id": "run", "execution_epoch": 4}) == {"ok": True}
