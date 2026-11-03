from datetime import UTC, datetime, timedelta

import pytest

import uuma.question_orbit as orbit_module
from uuma.knowledge_models import GapRecord, GapType, OrbitStatus, ResearchRun, SatisfactionLevel
from uuma.knowledge_service import KnowledgeService
from uuma.question_orbit import QuestionOrbitService
from uuma.research_quota import ResearchQuota, quota_delay
from uuma.safe_web import RetryAfterError


def started(tmp_path, monkeypatch, limits="{}"):
    monkeypatch.setenv("UUMA_RESEARCH_DAILY_LIMITS_JSON", limits)
    service = KnowledgeService(tmp_path / "wisdom.db")
    gap = service.add_gap(GapRecord(gap_type=GapType.COVERAGE, reason="Missing mechanism evidence",
                                   why_worthwhile="Needed for the research objective"),
                          actor_id="wisdom-oldman")
    orbits = QuestionOrbitService(service)
    item = orbits.start("How does the mechanism work?", "Explain the mechanism",
                        SatisfactionLevel.PROVISIONAL, "Evidence remains incomplete",
                        actor_id="wisdom-oldman", gap_ids=[gap["gap_id"]])
    return service, orbits, item["orbit"]["orbit_id"]


def complete(orbits, cycle, **usage):
    return orbits.complete_cycle(cycle["orbit_cycle_id"], "runner",
                                satisfaction_level=SatisfactionLevel.PROVISIONAL,
                                satisfaction_rationale="Evidence remains incomplete", **usage)


def test_cumulative_usage_reports_without_custom_cap(tmp_path, monkeypatch):
    service, orbits, ref = started(tmp_path, monkeypatch)
    cycle = orbits.acquire_cycle("runner")
    result = complete(orbits, cycle, active_seconds=900_000, model_tokens_used=20_000_000,
                      search_queries_used=9000)
    assert result["orbit"]["status"] == "QUEUED"
    assert result["research_run"]["model_tokens_used"] == 20_000_000
    assert orbits.get(ref)["budget"]["model_tokens"] is None
    assert service.history()["chain_valid"]


def test_daily_reset_preserves_cumulative_usage_and_history(tmp_path, monkeypatch):
    service, orbits, ref = started(tmp_path, monkeypatch, '{"model_tokens":10}')
    cycle = orbits.acquire_cycle("runner")
    waiting = complete(orbits, cycle, active_seconds=1, model_tokens_used=10)
    assert waiting["orbit"]["status"] == "BUDGET_EXHAUSTED"
    assert orbits.acquire_cycle("runner") is None
    assert orbits.has_quota_wait()
    reset = datetime.fromisoformat(waiting["orbit"]["quota_resume_at"])

    class Tomorrow(datetime):
        @classmethod
        def now(cls, tz=None):
            return (reset + timedelta(seconds=1)).astimezone(tz or UTC)

    monkeypatch.setattr(orbit_module, "datetime", Tomorrow)
    next_cycle = orbits.acquire_cycle("runner")
    assert next_cycle and next_cycle["orbit_id"] == ref
    assert orbits.get(ref)["research_run"]["model_tokens_used"] == 10
    assert orbits.get(ref)["budget"]["usage"]["model_tokens"] == 0
    assert service.history()["chain_valid"]


def test_daily_limit_is_shared_across_runs_and_checks_before_work(tmp_path, monkeypatch):
    service, orbits, _ = started(tmp_path, monkeypatch, '{"model_tokens":10}')
    service.start_research_run(ResearchRun(objective="Another research question",
                                         satisfaction_rationale="Initial usage",
                                         model_tokens_used=10), actor_id="wisdom-oldman")
    assert orbits.acquire_cycle("runner") is None
    assert orbits.list()["records"][0]["quota_wait_kind"] == "daily_limit"
    assert orbits.get(orbits.list()["records"][0]["orbit_id"])["research_run"]["status"] == "BUDGET_EXHAUSTED"


def test_provider_wait_survives_three_retries_and_preserves_request(tmp_path, monkeypatch):
    service, orbits, ref = started(tmp_path, monkeypatch)
    clock = datetime.now(UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.astimezone(tz or UTC)

    monkeypatch.setattr(orbit_module, "datetime", Clock)
    cycle = orbits.acquire_cycle("runner")
    first_id = cycle["orbit_cycle_id"]
    for _ in range(5):
        result = orbits.fail_cycle(first_id, "runner", "HTTP 429 quota exhausted",
                                  quota_wait=True, retry_after_seconds=300,
                                  discovery_state={"pending_request_id": "original-request"})
        assert result["retry"] and result["cycle"]["attempt"] == 1
        assert orbits.acquire_cycle("runner") is None
        clock += timedelta(seconds=301)
        cycle = orbits.acquire_cycle("runner")
        assert cycle["orbit_cycle_id"] == first_id
    assert service.history()["chain_valid"]
    assert orbits.discovery_state(ref, cycle["question_id"])["pending_request_id"] == "original-request"


@pytest.mark.parametrize("status", [OrbitStatus.PAUSED, OrbitStatus.STOPPED])
def test_human_pause_and_stop_override_provider_wait(tmp_path, monkeypatch, status):
    service, orbits, ref = started(tmp_path, monkeypatch)
    cycle = orbits.acquire_cycle("runner")
    orbits.fail_cycle(cycle["orbit_cycle_id"], "runner", "HTTP 429", quota_wait=True)
    orbits.transition(ref, status, actor_id="orchestrator", reason="User requested it")
    assert not orbits.has_quota_wait()
    assert orbits.acquire_cycle("runner") is None
    assert orbits.get(ref)["orbit"]["status"] == status.value
    assert service.history()["chain_valid"]


def test_daily_window_timezone_and_invalid_limit(tmp_path, monkeypatch):
    _, orbits, _ = started(tmp_path, monkeypatch)
    with orbits.store.connect() as conn:
        quota = ResearchQuota({"sources": 10}, "Asia/Kuala_Lumpur")
        snap = quota.snapshot(conn, now=datetime(2026, 10, 23, 17, tzinfo=UTC))
    assert snap["period_start"] == "2026-10-23T16:00:00+00:00"
    assert snap["reset_at"] == "2026-10-24T16:00:00+00:00"
    assert snap["provider_reset_at"] is None
    with pytest.raises(ValueError):
        ResearchQuota({"sources": -1})
    with pytest.raises(ValueError):
        ResearchQuota({"sources": float("inf")})


def test_non_quota_errors_keep_bounded_retries():
    assert quota_delay(RuntimeError("HTTP 503 temporarily unavailable")) is None
    assert quota_delay(RetryAfterError("HTTP 429", 7200)) == 7200


def test_planner_preserves_quota_wait_and_original_pending_request():
    from uuma.orbit_planner import AdaptiveResearchPlanner

    class Provider:
        name = "chatgpt-bridge"

        def discover(self, query, **kwargs):
            assert kwargs["pending_request_id"] == "existing-request"
            raise RetryAfterError("HTTP 429 quota exhausted", 7200)

    _, traces, pending = AdaptiveResearchPlanner([Provider()]).execute_discovery(
        "Mechanism", pending_request_id="existing-request", pending_provider="chatgpt-bridge",
    )
    assert pending == "existing-request"
    assert traces[0].metadata["quota_wait"] is True
    assert traces[0].metadata["retry_after_seconds"] == 7200


def test_continue_can_requeue_a_legacy_budget_stop_without_clearing_usage(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from uuma import mcp_knowledge

    service, orbits, ref = started(tmp_path, monkeypatch)
    cycle = orbits.acquire_cycle("runner")
    done = complete(orbits, cycle, active_seconds=900, model_tokens_used=70_000)
    # Explicit old projection fixture: preserve real usage and completed cycle history.
    with service.store.transaction() as conn:
        before = done["orbit"]
        orbits._update(conn, "question_orbits", before,
                       before | {"status": "BUDGET_EXHAUSTED", "stop_reason": "Legacy tier limit"},
                       "LEGACY_QUOTA_FIXTURE", "orchestrator")
    topics = SimpleNamespace(
        conversation_status=lambda route: {},
        get_topic=lambda topic: {"topic": {"status": "ACTIVE"},
                                 "orbits": [orbits.get(ref)["orbit"]]},
    )
    monkeypatch.setattr(mcp_knowledge, "_topics", lambda: topics)
    monkeypatch.setattr(mcp_knowledge, "_orbits", lambda: orbits)
    monkeypatch.setattr(mcp_knowledge, "_global_research_status", lambda: {"active": []})
    monkeypatch.setattr(mcp_knowledge, "_wake_orbit_runner", lambda state: {"requested": True})
    result = mcp_knowledge._control_existing_research("resume", {}, "orchestrator", "topic")
    assert result["changed_orbit_ids"] == [ref]
    assert orbits.get(ref)["orbit"]["status"] == "QUEUED"
    assert orbits.get(ref)["research_run"]["active_seconds"] == 900
    assert orbits.get(ref)["research_run"]["model_tokens_used"] == 70_000
    assert len(service.store.list_records("question_orbits")) == 1
    assert service.history()["chain_valid"]
