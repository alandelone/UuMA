"""Durable external waits must not become completed research or new submissions."""
from datetime import UTC, datetime, timedelta

import pytest
from test_orbit_runtime import (
    _Constructor,
    _Dispatcher,
    _Ingestor,
    _Projection,
    _started_orbit,
)

from uuma.knowledge_models import GapRecord, GapType, OrbitStatus, SatisfactionLevel
from uuma.orbit_discovery import DiscoveryArtifact, DiscoveryResponse
from uuma.orbit_mcp_discovery import XhsMCPDiscoveryProvider
from uuma.orbit_runner import OrbitRunner
from uuma.orbit_wait import external_wait_state
from uuma.question_orbit import QuestionOrbitService
from uuma.safe_web import RetryAfterError


@pytest.fixture
def clock(monkeypatch):
    class Clock(datetime):
        instant = datetime.now(UTC)

        @classmethod
        def now(cls, tz=None):
            return cls.instant.astimezone(tz) if tz else cls.instant.replace(tzinfo=None)

    monkeypatch.setattr("uuma.question_orbit.datetime", Clock)
    monkeypatch.setattr("uuma.orbit_wait.datetime", Clock)
    return Clock


class PendingProvider:
    name = "chatgpt-bridge"

    def __init__(self):
        self.requests = []
        self.ready = False
        self.failure = None

    def discover(self, query, *, pending_request_id=None, **kwargs):
        self.requests.append(pending_request_id)
        if self.failure:
            raise self.failure
        if self.ready:
            return DiscoveryResponse([
                DiscoveryArtifact("https://example.com/paper", "Battery ageing paper", self.name),
            ], request_id="original-request")
        return DiscoveryResponse([], request_id="original-request", in_progress=True)


class Reasoner:
    def __init__(self, service):
        self.calls = 0
        self.service = service

    def answer(self, question, **kwargs):
        self.calls += 1
        found = bool(self.service.list_records("source")["records"])
        return {
            "answer": "Located battery ageing evidence" if found else "Evidence is incomplete",
            "runtime_status": "KAG", "satisfaction_level": "SUFFICIENT" if found else "PROVISIONAL",
            "satisfaction_rationale": "Located evidence" if found else "Awaiting evidence",
            "remaining_gap_ids": [],
            "citations": [{"source_id": "src-paper"}] if found else [],
        }


def runner_for(service, orbits, provider, reasoner):
    return OrbitRunner(
        service, orbits, reasoner, [provider], _Ingestor(service), _Constructor(),
        _Projection(), _Dispatcher(), owner_id="wait-test", heartbeat_interval=0,
    )


def setup_wait(tmp_path, monkeypatch):
    monkeypatch.setattr("uuma.orbit_runner.ensure_knowledge_graph", lambda *a, **k: {"ready": True})
    service, orbits, orbit_id = _started_orbit(tmp_path)
    provider = PendingProvider()
    reasoner = Reasoner(service)
    runner = runner_for(service, orbits, provider, reasoner)
    assert runner.run_once()
    return service, orbits, orbit_id, provider, reasoner, runner


def test_wait_survives_restart_without_new_cycles_models_or_retries(tmp_path, monkeypatch, clock):
    service, orbits, orbit_id, provider, reasoner, runner = setup_wait(tmp_path, monkeypatch)
    first = service.store.list_records("orbit_cycles")[0]
    assert first["status"] == "RETRY"
    assert first["decision"] == "WAITING_EXTERNAL"
    assert first["completed_at"] is None
    assert not runner.run_once()  # not yet due
    assert provider.requests == [None]
    for delay in (30, 60, 120, 300, 300, 300):
        clock.instant += timedelta(seconds=delay + 1)
        restarted = QuestionOrbitService(service)
        runner = runner_for(service, restarted, provider, reasoner)
        assert runner.run_once()
        cycles = service.store.list_records("orbit_cycles")
        assert len(cycles) == 1
        assert cycles[0]["orbit_cycle_id"] == first["orbit_cycle_id"]
        assert cycles[0]["attempt"] == 1
        assert cycles[0]["completed_at"] is None
    state = orbits.get(orbit_id)
    assert reasoner.calls == 1
    assert provider.requests == [None] + ["original-request"] * 6
    assert state["research_run"]["cycle_count"] == 0
    assert state["research_run"]["search_queries_used"] == 1
    assert state["research_run"]["model_tokens_used"] > 0
    assert orbits.budget()["usage"]["search_queries"] == 1
    assert orbits.discovery_usage(provider=provider.name)["requests"] == 1
    explanation = state["research_run"]["latest_cycle_explanation"]
    assert explanation["status"] == "REQUIRES_ATTENTION"
    assert all(item["outcome"] == "WAITING" for item in explanation["attempts"])
    assert service.history()["chain_valid"]


def test_finished_request_is_ingested_once_and_cleared(tmp_path, monkeypatch, clock):
    service, orbits, orbit_id, provider, _reasoner, runner = setup_wait(tmp_path, monkeypatch)
    provider.ready = True
    clock.instant += timedelta(seconds=31)
    assert runner.run_once()
    state = orbits.get(orbit_id)
    assert state["research_run"]["cycle_count"] == 1
    assert state["research_run"]["sources_used"] == 1
    assert len(service.store.list_records("orbit_cycles")) == 1
    assert provider.requests == [None, "original-request"]
    cursor = orbits.discovery_state(orbit_id, service.store.list_records("orbit_cycles")[0]["question_id"])
    assert cursor["pending_request_id"] is None
    assert "external_wait" not in cursor
    assert not runner.run_once()


@pytest.mark.parametrize("legacy_cursor", [False, True])
def test_xhs_poll_after_restart_uses_the_submitted_query(tmp_path, monkeypatch, clock, legacy_cursor):
    monkeypatch.setattr("uuma.orbit_runner.ensure_knowledge_graph", lambda *a, **k: {"ready": True})
    service, orbits, orbit_id = _started_orbit(tmp_path)

    class XhsProvider:
        name = "xhs"

        def __init__(self):
            self.calls = []

        def discover(self, query, *, pending_request_id=None, **kwargs):
            self.calls.append((query, pending_request_id))
            if not pending_request_id:
                return DiscoveryResponse([], request_id="xhs-1", in_progress=True)
            return XhsMCPDiscoveryProvider.parse_result({
                "status": "success", "job_id": "xhs-1", "query": self.calls[0][0],
                "results": [{"url": "https://www.rednote.com/discovery/item/n1",
                             "title": "Battery ageing accelerated by heat"}],
            }, limit=5, pending=pending_request_id, query=query)

    if legacy_cursor:
        defer = orbits.defer_external_cycle

        def defer_without_query(*args, discovery_state, **kwargs):
            return defer(*args, discovery_state={
                key: value for key, value in discovery_state.items() if key != "pending_query"
            }, **kwargs)

        monkeypatch.setattr(orbits, "defer_external_cycle", defer_without_query)

    provider = XhsProvider()
    reasoner = Reasoner(service)
    assert runner_for(service, orbits, provider, reasoner).run_once()
    waiting = service.store.list_records("orbit_cycles")[0]
    submitted, _ = provider.calls[0]
    cursor = waiting["cycle_explanation"]["discovery_state"]
    assert submitted != cursor["next_query"]
    assert cursor.get("pending_query") == (None if legacy_cursor else submitted)

    restarted = QuestionOrbitService(service)
    restored = restarted.discovery_state(orbit_id, waiting["question_id"])
    assert restored["pending_query"] == submitted
    clock.instant += timedelta(seconds=31)
    assert runner_for(service, restarted, provider, reasoner).run_once()
    assert provider.calls == [(submitted, None), (submitted, "xhs-1")]
    completed = service.store.list_records("orbit_cycles")[0]
    assert completed["orbit_cycle_id"] == waiting["orbit_cycle_id"]
    assert completed["status"] == "COMPLETED"
    assert completed["discovery_attempts"][0]["artifacts_found"] == 1
    assert "pending_query" not in restarted.discovery_state(orbit_id, waiting["question_id"])
    assert service.history()["chain_valid"]


@pytest.mark.parametrize("failure,outcome", [
    (PermissionError("Login required"), "AUTH_REQUIRED"),
    (OSError("Offline"), "TRANSIENT_FAILURE"),
    (RetryAfterError("Provider quota", 1800), "TRANSIENT_FAILURE"),
])
def test_poll_failures_keep_identity_and_honor_provider_delay(
    tmp_path, monkeypatch, clock, failure, outcome,
):
    service, _orbits, _orbit_id, provider, reasoner, runner = setup_wait(tmp_path, monkeypatch)
    provider.failure = failure
    clock.instant += timedelta(seconds=31)
    assert runner.run_once()
    cycle = service.store.list_records("orbit_cycles")[0]
    cursor = cycle["cycle_explanation"]["discovery_state"]
    assert cursor["pending_request_id"] == "original-request"
    assert cursor["external_wait"]["outcome"] == outcome
    if isinstance(failure, RetryAfterError):
        assert cursor["external_wait"]["retry_after_seconds"] >= 1800
    if isinstance(failure, PermissionError):
        assert cursor["external_wait"]["status"] == "REQUIRES_ATTENTION"
    assert reasoner.calls == 1
    assert not runner.run_once()


def test_wait_does_not_block_another_authorized_orbit(tmp_path, monkeypatch, clock):
    service, orbits, orbit_id, *_ = setup_wait(tmp_path, monkeypatch)
    gap = service.add_gap(GapRecord(
        gap_type=GapType.WEAK_EVIDENCE, reason="Humidity evidence missing",
        why_worthwhile="Humidity changes operating conditions",
    ), actor_id="wisdom-oldman")
    other = orbits.start(
        "How does humidity affect battery ageing?", "Review humidity evidence",
        SatisfactionLevel.PROVISIONAL, "Evidence missing", actor_id="wisdom-oldman",
        gap_ids=[gap["gap_id"]],
    )["orbit"]
    cycle = orbits.acquire_cycle("other-worker")
    assert cycle["orbit_id"] == other["orbit_id"]
    assert cycle["orbit_id"] != orbit_id


def test_wait_allows_another_open_frontier_in_same_orbit(tmp_path, monkeypatch, clock):
    service, orbits, orbit_id, *_ = setup_wait(tmp_path, monkeypatch)
    gap = service.add_gap(GapRecord(
        gap_type=GapType.WEAK_EVIDENCE, reason="Humidity evidence missing",
        why_worthwhile="Humidity changes operating conditions",
    ), actor_id="wisdom-oldman")
    frontier = orbits.expand_frontier(orbit_id, [gap["gap_id"]])[0]
    cycle = orbits.acquire_cycle("other-worker")
    assert cycle["orbit_id"] == orbit_id
    assert cycle["question_id"] == frontier["question_id"]
    result = orbits.complete_cycle(
        cycle["orbit_cycle_id"], "other-worker",
        satisfaction_level=SatisfactionLevel.SUFFICIENT, satisfaction_rationale="Resolved sibling",
        active_seconds=1,
    )
    assert result["orbit"]["status"] == "QUEUED"
    clock.instant += timedelta(seconds=31)
    recovered = orbits.acquire_cycle("restart")
    assert recovered["question_id"] != cycle["question_id"]


@pytest.mark.parametrize("status", [OrbitStatus.PAUSED, OrbitStatus.STOPPED])
def test_user_pause_stop_override_wait(tmp_path, monkeypatch, clock, status):
    _service, orbits, orbit_id, *_ = setup_wait(tmp_path, monkeypatch)
    orbits.transition(orbit_id, status, reason="User requested", actor_id="orchestrator")
    clock.instant += timedelta(hours=1)
    assert orbits.acquire_cycle("restart") is None
    assert orbits.get(orbit_id)["orbit"]["status"] == status.value


def test_expired_owner_cannot_save_wait(tmp_path, clock):
    _service, orbits, _ = _started_orbit(tmp_path)
    cycle = orbits.acquire_cycle("first")
    wait = external_wait_state(None, request_id="id", provider="chatgpt-bridge",
                               outcome="WAITING", reason="Pending")
    cursor = {"pending_request_id": "id", "pending_provider": "chatgpt-bridge",
              "external_wait": wait}
    with pytest.raises(PermissionError, match="another runner"):
        orbits.defer_external_cycle(cycle["orbit_cycle_id"], "wrong", discovery_state=cursor,
                                    explanation={})
    clock.instant += timedelta(seconds=181)
    cursor["external_wait"] = external_wait_state(wait, request_id="id", provider="chatgpt-bridge",
                                                 outcome="WAITING", reason="Pending")
    with pytest.raises(PermissionError, match="expired"):
        orbits.defer_external_cycle(cycle["orbit_cycle_id"], "first", discovery_state=cursor,
                                    explanation={})


def test_completed_poll_preserved_if_graph_not_ready(tmp_path, monkeypatch, clock):
    service, orbits, orbit_id, provider, _reasoner, runner = setup_wait(tmp_path, monkeypatch)
    provider.ready = True
    clock.instant += timedelta(seconds=31)
    monkeypatch.setattr("uuma.orbit_runner.ensure_knowledge_graph",
                        lambda *a, **k: {"ready": False, "reason": "TimeoutError"})
    assert runner.run_once()
    cycle = service.store.list_records("orbit_cycles")[0]
    assert cycle["cycle_explanation"]["discovery_state"]["pending_request_id"] == "original-request"
    assert provider.requests == [None, "original-request"]
    assert orbits.get(orbit_id)["research_run"]["cycle_count"] == 0


def test_empty_finished_poll_accounts_for_next_channel_submission(tmp_path, monkeypatch, clock):
    service, orbits, orbit_id, _provider, reasoner, _runner = setup_wait(tmp_path, monkeypatch)

    class NextChannel(PendingProvider):
        name = "xhs-mcp"

    class FinishedEmpty(PendingProvider):
        def discover(self, query, **kwargs):
            assert kwargs["pending_request_id"] == "original-request"
            return DiscoveryResponse([], request_id="original-request")

    next_channel = NextChannel()
    clock.instant += timedelta(seconds=31)
    runner = OrbitRunner(
        service, orbits, reasoner, [FinishedEmpty(), next_channel], _Ingestor(service),
        _Constructor(), _Projection(), _Dispatcher(), owner_id="wait-test", heartbeat_interval=0,
    )
    assert runner.run_once()
    assert reasoner.calls == 1
    assert next_channel.requests == [None]
    assert orbits.discovery_usage(provider="xhs-mcp")["requests"] == 1
    assert orbits.get(orbit_id)["research_run"]["search_queries_used"] == 2


def test_pause_during_poll_cannot_be_overwritten_by_defer(tmp_path, monkeypatch, clock):
    _service, orbits, orbit_id, *_ = setup_wait(tmp_path, monkeypatch)
    clock.instant += timedelta(seconds=31)
    cycle = orbits.acquire_cycle("poller")
    orbits.transition(orbit_id, OrbitStatus.PAUSED, reason="User paused", actor_id="orchestrator")
    cursor = cycle["cycle_explanation"]["discovery_state"]
    cursor["external_wait"] = external_wait_state(
        cursor["external_wait"], request_id="original-request", provider="chatgpt-bridge",
        outcome="WAITING", reason="Still pending",
    )
    result = orbits.defer_external_cycle(
        cycle["orbit_cycle_id"], "poller", discovery_state=cursor, explanation={},
    )
    assert not result["deferred"]
    assert orbits.get(orbit_id)["orbit"]["status"] == "PAUSED"
