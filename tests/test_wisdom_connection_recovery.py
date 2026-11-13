"""Provider connection failures must not become duplicate work or false progress."""
from __future__ import annotations

import json
from types import SimpleNamespace
from urllib.error import URLError

import pytest

from uuma.chatgpt_bridge import BridgeStore, Consultation
from uuma.orbit_discovery import ChatGPTDiscoveryProvider, DiscoveryOutcome
from uuma.orbit_mcp_discovery import XhsMCPDiscoveryProvider
from uuma.orbit_planner import AdaptiveResearchPlanner


class Opener:
    def __init__(self, value):
        self.value = value
        self.methods = []

    def open(self, request, timeout):
        self.methods.append(request.get_method())
        if isinstance(self.value, Exception):
            raise self.value
        return json.dumps(self.value)


def test_pending_chatgpt_transport_failure_never_submits_another_request(monkeypatch):
    monkeypatch.delenv("UUMA_CHATGPT_AGENT_TOKEN_FILE", raising=False)
    opener = Opener(URLError("offline fixture"))
    provider = ChatGPTDiscoveryProvider(token="fixture", run_id="run", opener=opener)
    result = provider.discover("existing research", pending_request_id="same-request")
    assert opener.methods == ["GET"]
    assert result.request_id == "same-request"
    assert result.outcome == DiscoveryOutcome.TRANSIENT_FAILURE


@pytest.mark.parametrize("status", ["PAUSED", "NEEDS_REVIEW", "AWAITING_INPUT"])
def test_chatgpt_human_wait_preserves_original_request(monkeypatch, status):
    monkeypatch.delenv("UUMA_CHATGPT_AGENT_TOKEN_FILE", raising=False)
    opener = Opener({"status": status})
    provider = ChatGPTDiscoveryProvider(token="fixture", opener=opener)
    _, traces, pending = AdaptiveResearchPlanner([provider]).execute_discovery(
        "existing research", pending_request_id="same-request"
    )
    assert pending == "same-request"
    assert traces[0].outcome == DiscoveryOutcome.AUTH_REQUIRED
    assert opener.methods == ["GET"]


def test_queued_chatgpt_explains_blocker_without_counting_a_research_success(monkeypatch):
    monkeypatch.delenv("UUMA_CHATGPT_AGENT_TOKEN_FILE", raising=False)
    provider = ChatGPTDiscoveryProvider(token="fixture", opener=Opener({
        "status": "QUEUED", "queue": {
            "reason": "ACCOUNT_REQUEST_BLOCKED",
            "blocker": {"status": "PAUSED", "error": "EXTENSION_UNAVAILABLE"},
        },
    }))
    planner = AdaptiveResearchPlanner([provider])
    artifacts, traces, pending = planner.execute_discovery(
        "existing research", pending_request_id="same-request"
    )
    explanation = planner.compute_cycle_explanation("existing research", traces, "ACTIVE")
    assert not artifacts and pending == "same-request"
    assert traces[0].outcome == DiscoveryOutcome.WAITING
    assert "EXTENSION_UNAVAILABLE" in traces[0].reason
    assert "0 次成功" in explanation.summary
    assert "等待" in explanation.next_step


@pytest.mark.parametrize("payload", [
    {"status": "in_progress", "stage": "queued", "job_id": "same-job"},
    {"status": "accepted", "stage": "searching", "job_id": "same-job"},
])
def test_xhs_real_async_shapes_retain_pending_job_until_completed(payload):
    result = XhsMCPDiscoveryProvider.parse_result(payload, limit=5)
    assert result.in_progress
    assert result.request_id == "same-job"
    assert result.resolve_outcome() == DiscoveryOutcome.WAITING
    completed = XhsMCPDiscoveryProvider.parse_result({
        "status": "success", "stage": "completed", "job_id": "same-job", "results": [
            {"url": "https://www.rednote.com/discovery/item/one", "title": "aeroponics"},
            {"url": "https://www.rednote.com/discovery/item/one?xsec_token=private", "title": "duplicate"},
        ],
    }, pending=result.request_id, limit=5)
    assert not completed.in_progress
    assert len(completed.artifacts) == 1
    assert "private" not in repr(completed.artifacts)


def test_xhs_wrong_job_does_not_supply_unrelated_cached_values():
    result = XhsMCPDiscoveryProvider.parse_result({
        "status": "success", "job_id": "wrong-job", "results": [
            {"url": "https://www.rednote.com/discovery/item/old", "title": "old query"},
        ],
    }, pending="expected-job", limit=5)
    assert result.request_id == "expected-job"
    assert not result.artifacts
    assert result.outcome == DiscoveryOutcome.TRANSIENT_FAILURE


@pytest.mark.parametrize("stage", ["needs_login", "needs_verification"])
def test_xhs_browser_login_wait_keeps_job_instead_of_becoming_empty_result(stage):
    result = XhsMCPDiscoveryProvider.parse_result({
        "status": "error", "stage": stage, "job_id": "same-job", "results": [],
    }, pending="same-job", query="scallion aeroponics", limit=3)
    assert result.request_id == "same-job"
    assert result.outcome == DiscoveryOutcome.AUTH_REQUIRED
    assert not result.artifacts
    assert "verification" in result.error_detail


@pytest.fixture
def bridge(tmp_path):
    control = SimpleNamespace(
        require_run=lambda run_id: {
            "agent_id": "wisdom-oldman", "task_id": "task", "status": "RUNNING",
        },
        require_task=lambda task_id: {"current_run_id": "run", "status": "RUNNING"},
    )
    store = BridgeStore(tmp_path / "bridge.db", control_factory=lambda agent: control)
    store.add_account("original", "old@example.com", "Personal")
    store.add_account("new", "new@example.com", "Personal")
    for alias in ("original", "new"):
        store.account_state(alias, "READY", ["chat", "search", "deep_research"])
    store.bind("wisdom-oldman", "original")
    return store


def submit(bridge, key):
    return bridge.request("wisdom-oldman", Consultation(
        run_id="run", prompt="Existing authorized research", idempotency_key=key,
        mode="deep_research", thread=key,
    ))


def test_reassign_preserves_unsent_id_payload_history_and_agent_routes(bridge):
    request = submit(bridge, "one")
    before_routes = bridge.routes()
    reassigned = bridge.reassign_unsent(request["id"], "new")
    assert reassigned["id"] == request["id"]
    assert reassigned["account"] == "new"
    assert reassigned["payload"] == request["payload"]
    assert reassigned["submitted"] is None
    assert bridge.routes() == before_routes
    with bridge.connect() as conn:
        assert conn.execute("SELECT count(*) FROM chatgpt_requests").fetchone()[0] == 1
        assert [r[0] for r in conn.execute(
            "SELECT kind FROM chatgpt_events WHERE subject=? ORDER BY sequence", (request["id"],)
        )] == ["QUEUED", "UNSENT_ACCOUNT_REASSIGNED"]


def test_reassign_refuses_sent_requests_and_unverified_destinations(bridge):
    request = submit(bridge, "one")
    bridge.account_state("new", "AUTH_REQUIRED")
    with pytest.raises(ValueError, match="verified READY"):
        bridge.reassign_unsent(request["id"], "new")
    bridge.account_state("new", "READY", ["deep_research"])
    bridge.transition(request["id"], "SENDING", expected={"QUEUED"})
    bridge.transition(request["id"], "QUEUED", expected={"SENDING"})
    with pytest.raises(ValueError, match="unsubmitted"):
        bridge.reassign_unsent(request["id"], "new")


def test_queue_blocker_details_respect_agent_identity(bridge):
    first = submit(bridge, "first")
    second = submit(bridge, "second")
    bridge.transition(first["id"], "PAUSED", expected={"QUEUED"}, error="EXTENSION_UNAVAILABLE")
    queued = bridge.get("wisdom-oldman", second["id"])
    assert queued["queue"]["blocker"]["id"] == first["id"]
    assert queued["queue"]["reason"] == "ACCOUNT_REQUEST_BLOCKED"
    with bridge.connect() as conn:
        conn.execute("UPDATE chatgpt_requests SET agent='orchestrator' WHERE id=?", (first["id"],))
    queued = bridge.get("wisdom-oldman", second["id"])
    assert queued["queue"]["blocker_present"] is True
    assert queued["queue"]["blocker"] is None
