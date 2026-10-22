import hashlib
import importlib.util
from pathlib import Path

import anyio
import pytest

from uuma.brainstormer_client import BrainstormerClient
from uuma.brainstormer_state import BrainstormerStore, StateTransaction


@pytest.fixture
def remote_control(tmp_path, monkeypatch):
    from uuma import mcp_control

    token = tmp_path / "identity.token"
    token.write_text("scoped-orchestrator-token", encoding="utf-8")
    monkeypatch.setenv("UUMA_AGENT_ID", "orchestrator")
    monkeypatch.setenv("UUMA_IDENTITY_TOKEN_FILE", str(token))
    monkeypatch.setenv("UUMA_BRAINSTORMER_MCP_URL", "http://127.0.0.1:18769/brainstormer/")
    monkeypatch.setenv("UUMA_DATA_DIR", str(tmp_path / "workstation"))
    mcp_control._brainstormer_store.cache_clear()
    yield mcp_control
    mcp_control._brainstormer_store.cache_clear()


def proposal(store):
    return store.propose(StateTransaction.model_validate({
        "project_id": "project", "rationale": "User requested proposal",
        "operations": [{"action": "CREATE", "kind": "topic", "target_id": "topic",
                        "expected_revision": 0, "values": {"title": "Topic"}}],
    }), requested_by="brainstormer")["proposal_id"]


def test_control_review_changes_only_owner_and_preserves_approval_signature(
    remote_control, tmp_path, monkeypatch,
):
    from uuma import mcp_brainstormer

    owner_data = tmp_path / "server"
    owner = BrainstormerStore(owner_data / "brainstormer")
    identifier = proposal(owner)
    local = BrainstormerStore(tmp_path / "workstation" / "brainstormer")
    local_proposal = proposal(local)
    before = hashlib.sha256(local._proposal_path(local_proposal).read_bytes()).hexdigest()
    calls = []

    async def owner_call(self, name, arguments):
        assert self.identity == "orchestrator"
        assert self.url == "http://127.0.0.1:18769/brainstormer/"
        assert "actor_id" not in arguments
        calls.append((name, arguments))
        # Run the actual owner semantic handler with its fixed authenticated identity.
        with monkeypatch.context() as scoped:
            scoped.setenv("UUMA_DATA_DIR", str(owner_data))
            return mcp_brainstormer.review_brainstormer_transaction(**arguments)

    monkeypatch.setattr(BrainstormerClient, "_call_async", owner_call)
    result = remote_control.review_brainstormer_transaction(identifier, True, "User approved")
    assert len(calls) == 1
    assert calls[0][0] == "review_brainstormer_transaction"
    assert result["status"] == "APPROVED"
    assert result["reviewed_by"] == "orchestrator"
    assert owner.get_context("project")["revision"] == 1
    assert hashlib.sha256(local._proposal_path(local_proposal).read_bytes()).hexdigest() == before


def test_rejected_remote_request_never_falls_back_or_retries(remote_control, monkeypatch):
    calls = []

    async def rejected(self, name, arguments):
        calls.append(name)
        raise PermissionError("Owner rejected identity")

    def forbidden_local(cls):
        pytest.fail("Remote review cannot open the workstation domain")

    monkeypatch.setattr(BrainstormerClient, "_call_async", rejected)
    monkeypatch.setattr(BrainstormerStore, "from_env", classmethod(forbidden_local))
    with pytest.raises(PermissionError, match="rejected"):
        remote_control.review_brainstormer_transaction("proposal", True, "User approved")
    assert calls == ["review_brainstormer_transaction"]


def test_owner_missing_domain_does_not_create_empty_replacement(tmp_path, monkeypatch):
    from uuma import mcp_brainstormer

    missing = tmp_path / "missing"
    monkeypatch.setenv("UUMA_AGENT_ID", "orchestrator")
    monkeypatch.setenv("UUMA_DATA_DIR", str(missing))
    with pytest.raises(RuntimeError, match="refusing to create"):
        mcp_brainstormer.review_brainstormer_transaction("proposal", True, "User approved")
    assert not missing.exists()


def test_specialist_cannot_impersonate_review_actor(monkeypatch):
    from uuma import mcp_brainstormer

    monkeypatch.setenv("UUMA_AGENT_ID", "brainstormer")
    with pytest.raises(PermissionError, match="Orchestrator"):
        mcp_brainstormer.review_brainstormer_transaction("proposal", True, "Forged approval")
    client = BrainstormerClient("http://127.0.0.1:18769/brainstormer", "brainstormer", "token")
    with pytest.raises(PermissionError, match="Orchestrator"):
        client.review("proposal", actor_id="orchestrator", approve=True, note="Forged actor")


@pytest.mark.parametrize("identity", ["brainstormer", "orchestrator"])
def test_owner_discovery_only_advertises_review_to_orchestrator(monkeypatch, identity):
    monkeypatch.setenv("UUMA_AGENT_ID", identity)
    path = Path(__file__).resolve().parents[1] / "src/uuma/mcp_brainstormer.py"
    spec = importlib.util.spec_from_file_location("uuma._review_discovery_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = {tool.name for tool in anyio.run(module.mcp.list_tools)}
    reads = {
        "brainstormer_get_context", "brainstormer_get_decision_map", "brainstormer_search_topics",
    }
    assert names == reads | (
        {"review_brainstormer_transaction"} if identity == "orchestrator" else set()
    )


def test_without_domain_url_retains_local_control_contract(tmp_path, monkeypatch):
    from uuma import mcp_control

    monkeypatch.delenv("UUMA_BRAINSTORMER_MCP_URL", raising=False)
    monkeypatch.setenv("UUMA_DATA_DIR", str(tmp_path))
    mcp_control._brainstormer_store.cache_clear()
    try:
        assert isinstance(mcp_control._brainstormer_store(), BrainstormerStore)
    finally:
        mcp_control._brainstormer_store.cache_clear()
