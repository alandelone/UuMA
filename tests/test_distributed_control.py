from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from uuma.api import create_app
from uuma.auth import TokenRegistry
from uuma.control_client import ControlClient, control_backend, validate_endpoint
from uuma.models import TaskContract
from uuma.service import PolicyDeniedError
from uuma.settings import Settings


def test_real_control_prepares_pending_execution_for_a2a(app, tmp_path):
    import asyncio

    from uuma.a2a_node import DispatchCoordinator
    from uuma.models import RunRegistration
    from uuma.node_journal import NodeJournal

    control = client(app, "orchestrator")
    task = control.create_task(
        TaskContract(title="Read-only pilot", objective="Read the existing snapshot",
                     required_capabilities={"brainstorming"}),
        actor_id="orchestrator",
    )
    control.route_task(task.task_id, actor_id="orchestrator")
    control.assign_task(task.task_id, "brainstormer", actor_id="orchestrator")
    registration = control.register_run(
        RunRegistration(task_id=task.task_id, agent_id="brainstormer",
                        execution_class="INTERACTIVE", source="orchestrator",
                        initial_status="PENDING"), actor_id="orchestrator",
    )
    run = control.require_run(registration.run_id)
    assert run["status"] == "PENDING"
    assert run["progress"]["status"] == "PENDING"
    assert control.require_task(task.task_id)["status"] == "READY"

    class Adapter:
        starts = 0

        async def start(self, key, payload):
            self.starts += 1
            return "runtime-receipt"

    adapter = Adapter()
    coordinator = DispatchCoordinator(control, NodeJournal(tmp_path / "node.db"),
                                      {"brainstormer": adapter})
    first = asyncio.run(coordinator.dispatch("brainstormer", registration.run_id,
                                            registration.execution_epoch, "a2a-task"))
    second = asyncio.run(coordinator.dispatch("brainstormer", registration.run_id,
                                             registration.execution_epoch, "a2a-task"))
    assert first == second
    assert first["phase"] == "ACCEPTED"
    assert adapter.starts == 1


def test_pending_registration_requires_control_authority(app, tmp_path):
    from uuma.models import RunRegistration
    from uuma.service import ControlPlane

    control = ControlPlane(Settings(tmp_path, tmp_path / "isolated.db", tmp_path / "a",
                                    tmp_path / "s", Path("hermes")))
    registration = RunRegistration(task_id="no-task", agent_id="brainstormer",
                                   execution_class="INTERACTIVE", source="orchestrator",
                                   initial_status="PENDING")
    with pytest.raises(PolicyDeniedError, match="Only control"):
        control.register_run(registration, actor_id="brainstormer")
    with pytest.raises(PolicyDeniedError, match="Only control"):
        control.register_run(registration.model_copy(update={"source": "direct"}),
                             actor_id="orchestrator")


@pytest.fixture
def app(tmp_path):
    settings = Settings(
        tmp_path, tmp_path / "uuma.db", tmp_path / "artifacts", tmp_path / "spool", Path("hermes")
    )
    TokenRegistry(settings.token_file()).initialize()
    return create_app(settings)


def client(app, identity):
    return ControlClient(
        "http://127.0.0.1:8765",
        identity,
        app.state.tokens.load()[identity],
        transport=TestClient(app),
    )


def test_remote_worker_and_control_share_one_authority(app):
    worker = client(app, "brainstormer")
    run = worker.register_direct_run(
        "brainstormer", TaskContract(title="Design", objective="Compare", source="direct")
    )
    assert worker.require_task(run.task_id)["assignee"] == "brainstormer"
    assert client(app, "orchestrator").require_run(run.run_id)["agent_id"] == "brainstormer"
    with pytest.raises(PolicyDeniedError):
        client(app, "honc").require_run(run.run_id)
    with pytest.raises(PolicyDeniedError):
        worker.create_task(
            TaskContract(title="Invalid", objective="Invalid"), actor_id="brainstormer"
        )


def test_remote_actor_cannot_be_spoofed(app):
    with pytest.raises(PermissionError):
        client(app, "brainstormer").create_task(
            TaskContract(title="Invalid", objective="Invalid"), actor_id="orchestrator"
        )


def test_deployment_gate_blocks_new_runs_and_requires_its_owner(app):
    from uuma.service import ConflictError

    worker = client(app, "brainstormer")
    control = client(app, "orchestrator")
    plan = "a" * 64
    control.request(
        "POST",
        "/control/deployment/intake",
        {
            "agents": ["brainstormer"],
            "plan_id": plan,
            "paused": True,
        },
    )
    assert worker.request("GET", "/worker/intake")["accepting"] is False
    with pytest.raises(ConflictError):
        worker.register_direct_run(
            "brainstormer",
            TaskContract(title="Wait", objective="Wait for release", source="direct"),
        )
    with pytest.raises(ConflictError):
        control.request(
            "POST",
            "/control/deployment/intake",
            {
                "agents": ["brainstormer"],
                "plan_id": "b" * 64,
                "paused": False,
            },
        )
    control.request(
        "POST",
        "/control/deployment/intake",
        {
            "agents": ["brainstormer"],
            "plan_id": plan,
            "paused": False,
        },
    )
    assert worker.request("GET", "/worker/intake")["accepting"] is True


def test_binding_endpoint_validation_returns_422(app):
    from uuma.service import ContractValidationError

    with pytest.raises(ContractValidationError):
        client(app, "orchestrator").request(
            "PUT",
            "/control/agents/brainstormer/endpoint",
            {
                "agent_id": "brainstormer",
                "node_id": "server",
                "runtime": "hermes",
                "endpoint": "http://192.168.55.2",
                "revision": "fixture",
            },
        )


def test_remote_mode_does_not_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("UUMA_DATA_DIR", str(tmp_path / "must-not-exist"))
    monkeypatch.delenv("UUMA_CONTROL_URL", raising=False)
    monkeypatch.setenv("UUMA_REQUIRE_REMOTE_CONTROL", "1")
    with pytest.raises(RuntimeError, match="refusing"):
        control_backend()
    assert not (tmp_path / "must-not-exist").exists()


def test_configured_remote_does_not_bootstrap_local_db(tmp_path, monkeypatch):
    token = tmp_path / "agent.token"
    token.write_text("fake-token")
    monkeypatch.setenv("UUMA_DATA_DIR", str(tmp_path / "must-not-exist"))
    monkeypatch.setenv("UUMA_CONTROL_URL", "http://127.0.0.1:8765")
    monkeypatch.setenv("UUMA_AGENT_ID", "scholar")
    monkeypatch.setenv("UUMA_IDENTITY_TOKEN_FILE", str(token))
    assert isinstance(control_backend(), ControlClient)
    assert not (tmp_path / "must-not-exist").exists()


@pytest.mark.parametrize("url", ["http://192.168.55.2:8765", "http://a:b@localhost", "file:///x"])
def test_unprotected_network_and_embedded_credentials_rejected(url):
    with pytest.raises(ValueError):
        validate_endpoint(url)
