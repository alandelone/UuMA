"""Remote research ownership and credentials, using only isolated stores and HTTP fakes."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from uuma import orbit_runner
from uuma.api import create_app
from uuma.auth import TokenRegistry
from uuma.control_client import ControlClient
from uuma.models import TaskContract
from uuma.service import PolicyDeniedError
from uuma.settings import Settings


def authority(tmp_path):
    settings = Settings(
        tmp_path, tmp_path / "uuma.db", tmp_path / "artifacts", tmp_path / "spool", Path("hermes")
    )
    TokenRegistry(settings.token_file()).initialize()
    return create_app(settings)


def client(app, identity):
    return ControlClient(
        "http://127.0.0.1:8765", identity, app.state.tokens.load()[identity],
        transport=TestClient(app),
    )


def test_worker_run_listing_is_authenticated_and_owner_scoped(tmp_path):
    app = authority(tmp_path)
    wisdom = client(app, "wisdom-oldman")
    first = wisdom.register_direct_run(
        "wisdom-oldman", TaskContract(title="Wisdom", objective="Read sources", source="direct")
    )
    other = client(app, "brainstormer").register_direct_run(
        "brainstormer", TaskContract(title="Other", objective="Compare ideas", source="direct")
    )

    assert [r["run_id"] for r in wisdom.list_runs()] == [first.run_id]
    assert [r["run_id"] for r in wisdom.list_runs(status="RUNNING")] == [first.run_id]
    assert wisdom.list_runs(status="COMPLETED") == []
    assert {r["run_id"] for r in client(app, "orchestrator").list_runs()} == {
        first.run_id, other.run_id
    }
    with pytest.raises(PermissionError):
        wisdom.list_runs(agent_id="brainstormer")
    with pytest.raises(PolicyDeniedError):
        wisdom.request("GET", "/worker/runs?agent_id=brainstormer")
    with pytest.raises(PolicyDeniedError):
        wisdom.request("GET", "/control/runs")
    with pytest.raises(PolicyDeniedError):
        invalid = ControlClient(
            "http://127.0.0.1:8765", "wisdom-oldman", "invalid", transport=TestClient(app)
        )
        invalid.list_runs()


def test_remote_orbit_reuses_only_exact_reference_and_registers_valid_contract(tmp_path):
    app = authority(tmp_path)
    wisdom = client(app, "wisdom-oldman")
    unrelated = wisdom.register_direct_run(
        "wisdom-oldman", TaskContract(title="Other", objective="Another question", source="direct"),
        external_run_ref="other-orbit",
    )

    run_id = orbit_runner._ensure_runner_run(wisdom, "orbit-exact", "Read this question")
    assert run_id and run_id != unrelated.run_id
    assert orbit_runner._ensure_runner_run(wisdom, "orbit-exact", "Read this question") == run_id
    assert len(wisdom.list_runs()) == 2
    run = wisdom.require_run(run_id)
    assert run["external_run_ref"] == "orbit-exact"
    assert run["execution_class"] == "BACKGROUND"
    task = wisdom.require_task(run["task_id"])
    assert task["contract"]["risk_level"] == "READ_ONLY"
    assert task["contract"]["external_task_ref"] == "orbit-exact"


@pytest.mark.parametrize("status", ["PAUSED", "FAILED", "CANCELLED", "COMPLETED", "REVIEW"])
def test_remote_orbit_does_not_resume_existing_inactive_run(monkeypatch, status):
    remote = ControlClient("http://127.0.0.1:8765", "wisdom-oldman", "fixture")
    row = {"run_id": "run-existing", "agent_id": "wisdom-oldman",
           "external_run_ref": "orbit-exact", "status": status}
    monkeypatch.setattr(remote, "list_runs", lambda **kwargs: [row])
    monkeypatch.setattr(remote, "require_run", lambda run_id: row)
    monkeypatch.setattr(remote, "register_direct_run", lambda *a, **k: pytest.fail("Implicit resume"))

    assert orbit_runner._ensure_runner_run(remote, "orbit-exact", "Question") is None


def test_remote_orbit_rejects_ambiguous_binding_without_new_work(monkeypatch):
    remote = ControlClient("http://127.0.0.1:8765", "wisdom-oldman", "fixture")
    row = {"run_id": "run-1", "agent_id": "wisdom-oldman", "external_run_ref": "orbit-exact"}
    monkeypatch.setattr(remote, "list_runs", lambda **kwargs: [row, row | {"run_id": "run-2"}])
    monkeypatch.setattr(remote, "register_direct_run", lambda *a, **k: pytest.fail("Duplicate work"))

    assert orbit_runner._ensure_runner_run(remote, "orbit-exact", "Question") is None


def test_remote_orbit_response_loss_reconciles_exact_registered_run(tmp_path, monkeypatch):
    app = authority(tmp_path)
    remote = client(app, "wisdom-oldman")
    original = remote.register_direct_run

    def lose_response(*args, **kwargs):
        original(*args, **kwargs)
        raise TimeoutError("Receipt lost after registration")

    monkeypatch.setattr(remote, "register_direct_run", lose_response)
    assert orbit_runner._ensure_runner_run(remote, "orbit-exact", "Question") is None
    monkeypatch.setattr(remote, "register_direct_run", original)
    run_id = orbit_runner._ensure_runner_run(remote, "orbit-exact", "Question")

    assert run_id
    assert [r["run_id"] for r in remote.list_runs()] == [run_id]


def configure_runner(monkeypatch, tmp_path):
    domain = tmp_path / "domain"
    token = tmp_path / "identity.token"
    token.write_text("fixture-identity", encoding="utf-8")
    monkeypatch.setenv("UUMA_DATA_DIR", str(domain))
    monkeypatch.setenv("UUMA_KNOWLEDGE_DATA_DIR", str(domain))
    monkeypatch.setenv("UUMA_CONTROL_URL", "http://127.0.0.1:8765")
    monkeypatch.setenv("UUMA_REQUIRE_REMOTE_CONTROL", "1")
    monkeypatch.setenv("UUMA_AGENT_ID", "wisdom-oldman")
    monkeypatch.setenv("UUMA_IDENTITY_TOKEN_FILE", str(token))
    monkeypatch.setenv("UUMA_CHATGPT_AGENT_TOKEN_FILE", str(token))
    monkeypatch.setenv("UUMA_ORBIT_CHATGPT_DISCOVERY", "true")
    monkeypatch.delenv("UUMA_KAG_SECRETS_FILE", raising=False)
    monkeypatch.setattr(orbit_runner, "load_profile_environment", lambda profile: None)
    monkeypatch.setattr(
        orbit_runner, "ControlPlane", lambda *a, **k: pytest.fail("Local control initialized")
    )
    return domain


def test_build_runner_does_not_create_local_control_database(tmp_path, monkeypatch):
    domain = configure_runner(monkeypatch, tmp_path)

    runner = orbit_runner.build_runner(tmp_path / "profile")

    assert runner.knowledge.store.path == domain / "wisdom.db"
    assert not (domain / "uuma.db").exists()


def test_build_runner_missing_remote_never_bootstraps_local_control(tmp_path, monkeypatch):
    domain = configure_runner(monkeypatch, tmp_path)
    monkeypatch.delenv("UUMA_CONTROL_URL")

    with pytest.raises(RuntimeError, match="refusing"):
        orbit_runner.build_runner(tmp_path / "profile")
    assert not (domain / "uuma.db").exists()


def test_build_runner_preserves_durable_explicit_run_reference(tmp_path, monkeypatch):
    domain = configure_runner(monkeypatch, tmp_path)
    remote = ControlClient("http://127.0.0.1:8765", "wisdom-oldman", "fixture")
    monkeypatch.setattr(orbit_runner, "control_backend", lambda: remote)
    requested = []

    def lookup(run_id):
        requested.append(run_id)
        return {"run_id": run_id, "agent_id": "wisdom-oldman", "status": "RUNNING",
                "external_run_ref": "original-Hermes-reference"}

    monkeypatch.setattr(remote, "require_run", lookup)
    monkeypatch.setattr(remote, "list_runs", lambda **kwargs: pytest.fail("Stored binding lost"))
    runner = orbit_runner.build_runner(tmp_path / "profile")
    monkeypatch.setattr(runner.orbits, "get", lambda _: {"orbit": {"uuma_run_id": "run-original"}})
    runner._cycle_hook({"orbit_id": "orbit-exact"})
    provider = next(p for p in runner.providers if p.name == "chatgpt-bridge")

    assert provider.run_id_getter() == "run-original"
    assert requested == ["run-original"]
    assert not (domain / "uuma.db").exists()


@pytest.mark.parametrize(
    ("owner", "status"), [("wisdom-oldman", "PAUSED"), ("wisdom-oldman", "COMPLETED"),
                           ("brainstormer", "RUNNING")]
)
def test_build_runner_does_not_replace_inactive_or_foreign_stored_reference(
    tmp_path, monkeypatch, owner, status
):
    configure_runner(monkeypatch, tmp_path)
    remote = ControlClient("http://127.0.0.1:8765", "wisdom-oldman", "fixture")
    monkeypatch.setattr(orbit_runner, "control_backend", lambda: remote)
    monkeypatch.setattr(
        remote, "require_run", lambda rid: {"run_id": rid, "agent_id": owner, "status": status}
    )
    monkeypatch.setattr(remote, "list_runs", lambda **kwargs: pytest.fail("Stored binding replaced"))
    monkeypatch.setattr(remote, "register_direct_run", lambda *a, **k: pytest.fail("Implicit resume"))
    runner = orbit_runner.build_runner(tmp_path / "profile")
    monkeypatch.setattr(runner.orbits, "get", lambda _: {"orbit": {"uuma_run_id": "run-original"}})
    runner._cycle_hook({"orbit_id": "orbit-exact"})
    provider = next(p for p in runner.providers if p.name == "chatgpt-bridge")

    assert provider.run_id_getter() is None
