import hashlib
import importlib.util
import io
import json
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from uuma.navigation_auth import sign_command


@pytest.fixture
def authenticated_navigation(tmp_path, monkeypatch):
    monkeypatch.setenv("UUMA_DATA_DIR", str(tmp_path / "bootstrap"))
    for name in (
        "UUMA_NAVIGATION_TOKEN_REGISTRY", "UUMA_NAVIGATION_COMMAND_SECRET_FILE",
        "UUMA_REQUIRE_SEPARATE_NAVIGATION_DB", "UUMA_NAVIGATION_DATABASE_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    from uuma import state_daemon

    registry = tmp_path / "tokens.json"
    registry.write_text(json.dumps({
        "orchestrator": "orchestrator-token", "brainstormer": "brainstormer-token",
        "wisdom-oldman": "wisdom-token",
    }))
    secret = tmp_path / "command.secret"
    secret.write_bytes(b"isolated-test-command-secret-value-32-bytes")
    data = tmp_path / "owner"
    monkeypatch.setenv("UUMA_NAVIGATION_TOKEN_REGISTRY", str(registry))
    monkeypatch.setenv("UUMA_NAVIGATION_DATABASE_PATH", str(data / "navigation.db"))
    monkeypatch.setenv("UUMA_REQUIRE_SEPARATE_NAVIGATION_DB", "1")
    monkeypatch.setenv("UUMA_NAVIGATION_COMMAND_SECRET_FILE", str(secret))
    monkeypatch.setenv("UUMA_NAVIGATION_COMMAND_USERS", "123")
    daemon = state_daemon.StateDaemon(data)
    monkeypatch.setattr(state_daemon, "daemon", daemon)
    return TestClient(state_daemon.app), daemon, secret


def bearer(identity="brainstormer"):
    return {"Authorization": f"Bearer {identity}-token", "X-Uuma-Identity": identity}


def signed(secret, payload, *, nonce="test-command-nonce-0001", timestamp=None, user="123"):
    timestamp = str(int(time.time())) if timestamp is None else str(timestamp)
    return {
        **bearer(), "X-Uuma-Command-User": user,
        "X-Uuma-Command-Timestamp": timestamp, "X-Uuma-Command-Nonce": nonce,
        "X-Uuma-Command-Signature": sign_command(
            secret.read_bytes(), payload, timestamp, nonce, user,
        ),
    }


@pytest.mark.parametrize("headers", [
    {}, {"Authorization": "Bearer wrong", "X-Uuma-Identity": "brainstormer"},
    {"Authorization": "Bearer brainstormer-token", "X-Uuma-Identity": "orchestrator"},
    {"Authorization": "Bearer wisdom-token", "X-Uuma-Identity": "wisdom-oldman"},
])
def test_navigation_rejects_missing_wrong_or_impersonated_identity(
    authenticated_navigation, headers,
):
    client, _, _ = authenticated_navigation
    assert client.get("/api/v1/context/owner", headers=headers).status_code == 403
    assert client.post("/api/v1/review", headers=headers, json={}).status_code == 403


def test_review_requires_orchestrator_and_actor_is_transport_identity(authenticated_navigation):
    client, daemon, _ = authenticated_navigation
    transaction = {
        "project_id": "project", "rationale": "Test explicit structural review",
        "operations": [{"action": "CREATE", "kind": "topic", "target_id": "topic",
                        "values": {"title": "Topic"}}],
    }
    proposed = client.post("/api/v1/commit", headers=bearer(), json={
        "user_id": "owner", "project_id": "project", "transaction": transaction,
        "requested_by": "orchestrator", "auto_approve": True,
    })
    assert proposed.status_code == 200, proposed.text
    assert proposed.json()["status"] == "pending_review"
    identifier = proposed.json()["proposal_id"]
    assert daemon.store.get_proposal(identifier)["requested_by"] == "brainstormer"
    review = {"proposal_id": identifier, "project_id": "project", "approve": True,
              "actor_id": "user", "note": "Explicit approval"}
    assert client.post("/api/v1/review", headers=bearer(), json=review).status_code == 403
    assert daemon.store.get_context("project")["revision"] == 0
    approved = client.post("/api/v1/review", headers=bearer("orchestrator"), json=review)
    assert approved.status_code == 200, approved.text
    assert approved.json()["reviewed_by"] == "orchestrator"
    assert daemon.store.get_proposal(identifier)["reviewed_by"] == "orchestrator"


def test_signed_human_create_preserves_command_and_returns_original_receipt(
    authenticated_navigation,
):
    client, daemon, secret = authenticated_navigation
    payload = {"action": "create", "user_id": "telegram:123", "title": "咖啡计划",
               "source_ref": "telegram:123:456"}
    headers = signed(secret, payload)
    assert client.post("/api/v1/navigation", headers=bearer(), json=payload).status_code == 403
    created = client.post("/api/v1/navigation", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    assert created.json()["status"] == "created"
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in daemon.store.projects.glob("*/state.json")}
    assert client.post("/api/v1/navigation", headers=headers, json=payload).json() == created.json()
    # A fresh nonce cannot bypass a prior intent's durable receipt either.
    retry = signed(secret, payload, nonce="test-command-nonce-0002")
    assert client.post("/api/v1/navigation", headers=retry, json=payload).json() == created.json()
    assert hashes == {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in daemon.store.projects.glob("*/state.json")}
    proposal = json.loads(next(daemon.store.proposals.glob("*.json")).read_text(encoding="utf-8"))
    assert proposal["requested_by"] == "user"
    assert proposal["reviewed_by"] == "user"
    with sqlite3.connect(daemon.db.db_path) as db:
        assert db.execute("SELECT phase FROM navigation_commands").fetchall() == [("COMPLETED",)]
    assert not (daemon.data_dir / "uuma.db").exists()


@pytest.mark.parametrize("case", ["tamper", "expired", "wrong-user"])
def test_invalid_signed_creation_cannot_write(authenticated_navigation, case):
    client, daemon, secret = authenticated_navigation
    payload = {"action": "create", "user_id": "telegram:123", "title": "Topic",
               "source_ref": "telegram:123:456"}
    headers = signed(
        secret, payload, timestamp=int(time.time()) - 301 if case == "expired" else None,
        user="999" if case == "wrong-user" else "123",
    )
    if case == "tamper":
        payload["title"] = "Tampered"
    assert client.post("/api/v1/navigation", headers=headers, json=payload).status_code == 403
    assert not list(daemon.store.projects.glob("*/state.json"))


def test_reserved_command_is_uncertain_and_never_replayed(authenticated_navigation):
    client, daemon, secret = authenticated_navigation
    payload = {"action": "create", "user_id": "telegram:123", "title": "Topic",
               "source_ref": "telegram:123:456"}
    headers = signed(secret, payload)
    daemon.navigation_commands.reserve(
        payload, {key.lower(): value for key, value in headers.items()},
    )
    response = client.post("/api/v1/navigation", headers=headers, json=payload)
    assert response.status_code == 409
    assert not list(daemon.store.projects.glob("*/state.json"))
    new_nonce = signed(secret, payload, nonce="another-command-nonce-0001")
    assert client.post("/api/v1/navigation", headers=new_nonce, json=payload).status_code == 409


def test_navigation_turn_uses_authenticated_actor_not_user_binding(authenticated_navigation):
    client, daemon, secret = authenticated_navigation
    create = {"action": "create", "user_id": "telegram:123", "title": "Topic",
              "source_ref": "telegram:123:456"}
    created = client.post("/api/v1/navigation", headers=signed(secret, create), json=create)
    assert created.status_code == 200
    binding = created.json()["binding"]
    turn = client.post("/api/v1/navigation", headers=bearer(), json={
        "action": "turn", "user_id": "orchestrator", "authenticated_actor": "orchestrator",
        "project_id": binding["active_project_id"], "topic_id": binding["active_topic_id"],
        "text": "Preserve a genuine discussion", "source_ref": "telegram:123:457",
        "role": "user",
    })
    assert turn.status_code == 200, turn.text
    proposals = [json.loads(path.read_text(encoding="utf-8"))
                 for path in daemon.store.proposals.glob("*.json")]
    saved = next(proposal for proposal in proposals
                 if proposal["transaction"]["rationale"].startswith("Preserve authored"))
    assert saved["requested_by"] == "brainstormer"
    assert saved["reviewed_by"] == "brainstormer"


def test_signed_nonce_cannot_authorize_different_intent(authenticated_navigation):
    client, _, secret = authenticated_navigation
    first = {"action": "create", "user_id": "telegram:123", "title": "First",
             "source_ref": "telegram:123:456"}
    initial = client.post("/api/v1/navigation", headers=signed(secret, first), json=first)
    assert initial.status_code == 200
    second = {**first, "title": "Second", "source_ref": "telegram:123:457"}
    assert client.post(
        "/api/v1/navigation", headers=signed(secret, second), json=second,
    ).status_code == 403


def test_missing_registry_fails_before_creating_domain(
    authenticated_navigation, tmp_path, monkeypatch,
):
    from uuma.state_daemon import StateDaemon

    monkeypatch.setenv("UUMA_NAVIGATION_TOKEN_REGISTRY", str(tmp_path / "missing.json"))
    absent = tmp_path / "absent-domain"
    with pytest.raises(FileNotFoundError, match="already exist"):
        StateDaemon(absent)
    assert not absent.exists()


def test_plugin_signs_only_actual_create_command_path(tmp_path, monkeypatch):
    path = (Path(__file__).resolve().parents[1]
            / "integrations/hermes/uuma_brainstormer_commands/__init__.py")
    spec = importlib.util.spec_from_file_location("navigation_signed_plugin_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    token, secret = tmp_path / "identity.token", tmp_path / "command.secret"
    token.write_text("brainstormer-token")
    secret.write_bytes(b"isolated-test-command-secret-value-32-bytes")
    values = {"owner_id": "123", "navigation_identity": "brainstormer",
              "navigation_token_file": str(token), "navigation_command_secret_file": str(secret),
              "navigation_url": "http://127.0.0.1:8773/api/v1/navigation"}

    class Context:
        def get_config(self, key, default):
            return values.get(key, default)

    requests = []

    def request(request, timeout):
        requests.append(request)
        return io.StringIO(json.dumps({"context": None}))

    monkeypatch.setattr(module, "urlopen", request)
    commands = module.BrainstormerCommands(Context())
    commands.rpc("create", title="Agent-originated", source_ref="model:1")
    assert "x-uuma-command-signature" not in {
        key.lower(): value for key, value in requests[-1].header_items()
    }
    commands.command("topics", "new 人类议题", "telegram:123:456")
    sent = requests[-1]
    headers = {key.lower(): value for key, value in sent.header_items()}
    assert headers["authorization"] == "Bearer brainstormer-token"
    assert headers["x-uuma-identity"] == "brainstormer"
    assert headers["x-uuma-command-signature"] == sign_command(
        secret.read_bytes(), json.loads(sent.data), headers["x-uuma-command-timestamp"],
        headers["x-uuma-command-nonce"], "123",
    )
    assert "brainstormer-token" not in sent.full_url
