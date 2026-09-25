from __future__ import annotations

import io
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

import pytest

import uuma.question_orbit as question_orbit_module
from uuma.knowledge_ingest import KnowledgeIngestor
from uuma.knowledge_models import BudgetTier, GapRecord, GapType, OrbitStatus, SatisfactionLevel
from uuma.knowledge_service import KnowledgeAuthorizationError, KnowledgeService
from uuma.orbit_discovery import (
    CrossrefProvider,
    DiscoveryArtifact,
    DiscoveryResponse,
    FeedSitemapProvider,
    OpenAlexProvider,
    artifact_identity,
)
from uuma.orbit_runner import OrbitNotificationDispatcher, OrbitRunner, _RunnerInstanceLock
from uuma.question_orbit import QuestionOrbitService
from uuma.safe_web import FetchedResource, RetryAfterError, SafeWebFetcher, UnsafeUrlError


class _Headers(Message):
    def get_content_type(self) -> str:
        return super().get_content_type()


class _Response(io.BytesIO):
    def __init__(self, body: bytes, url: str, content_type: str = "text/plain") -> None:
        super().__init__(body)
        self._url = url
        self.headers = _Headers()
        self.headers["Content-Type"] = content_type

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        self.close()


class _RedirectOpener:
    def open(self, request, timeout):
        headers = Message()
        headers["Location"] = "http://127.0.0.1/private"
        raise HTTPError(request.full_url, 302, "Found", headers, None)


class _RetryOpener:
    def open(self, request, timeout):
        headers = Message()
        headers["Retry-After"] = "120"
        raise HTTPError(request.full_url, 429, "Slow down", headers, None)


class _StaticOpener:
    def __init__(self, response: _Response) -> None:
        self.response = response

    def open(self, request, timeout):
        return self.response


def _resolver(hostname: str, port):
    address = "127.0.0.1" if hostname == "127.0.0.1" else "93.184.216.34"
    return [(2, 1, 6, "", (address, 0))]


def test_safe_fetcher_revalidates_redirect_targets() -> None:
    fetcher = SafeWebFetcher(opener=_RedirectOpener(), resolver=_resolver)

    with pytest.raises(UnsafeUrlError):
        fetcher.fetch("https://example.com/start", check_robots=False)


def test_runner_instance_lock_prevents_duplicate_processes(tmp_path: Path) -> None:
    lock_path = tmp_path / "orbit-runner.lock"

    with (
        _RunnerInstanceLock(lock_path),
        pytest.raises(RuntimeError, match="already active"),
        _RunnerInstanceLock(lock_path),
    ):
        pass

    with _RunnerInstanceLock(lock_path):
        pass
    assert json.loads(lock_path.read_text(encoding="utf-8"))["pid"] > 0


def test_windows_runner_task_has_self_healing_and_power_resilience() -> None:
    installer = (
        Path(__file__).parents[1] / "scripts" / "install-orbit-runner.ps1"
    ).read_text(encoding="utf-8")
    launcher = (
        Path(__file__).parents[1] / "scripts" / "start-orbit-runner.ps1"
    ).read_text(encoding="utf-8")
    manager = (
        Path(__file__).parents[1] / "scripts" / "manage-orbit-runner.ps1"
    ).read_text(encoding="utf-8")
    watchdog = (
        Path(__file__).parents[1] / "scripts" / "watch-orbit-runner.ps1"
    ).read_text(encoding="utf-8")

    assert "UuMA Question Orbit Watchdog" in installer
    assert "-StartWhenAvailable" in installer
    assert "-AllowStartIfOnBatteries" in installer
    assert "-DontStopIfGoingOnBatteries" in installer
    assert "-RestartCount 3" in installer
    assert "-RestartInterval (New-TimeSpan -Minutes 1)" in installer
    assert "orbit-runner-lifecycle.log" in launcher
    assert "manage-orbit-runner.ps1" in watchdog
    assert "Unregister-ScheduledTask" in watchdog
    assert "manage-orbit-runner" in manager
    assert "run-once" in manager
    assert "Start-ScheduledTask" in manager
    assert "Stop-ScheduledTask" in manager


def test_safe_fetcher_surfaces_retry_after() -> None:
    fetcher = SafeWebFetcher(opener=_RetryOpener(), resolver=_resolver)

    with pytest.raises(RetryAfterError) as exc_info:
        fetcher.fetch("https://example.com/api", check_robots=False)

    assert exc_info.value.retry_after_seconds == 120


def test_safe_fetcher_rejects_oversize_and_wrong_mime() -> None:
    oversize = _Response(b"small", "https://example.com/file", "text/plain")
    oversize.headers["Content-Length"] = "100"
    fetcher = SafeWebFetcher(
        opener=_StaticOpener(oversize), resolver=_resolver, maximum_bytes=10
    )
    with pytest.raises(ValueError, match="download limit"):
        fetcher.fetch("https://example.com/file", check_robots=False)

    wrong_mime = _Response(b"binary", "https://example.com/file", "application/octet-stream")
    fetcher = SafeWebFetcher(opener=_StaticOpener(wrong_mime), resolver=_resolver)
    with pytest.raises(ValueError, match="content type"):
        fetcher.fetch(
            "https://example.com/file",
            check_robots=False,
            allowed_content_types={"text/plain"},
        )


class _CaptchaFetcher:
    def fetch(self, url: str, **kwargs) -> FetchedResource:
        return FetchedResource(
            body=b"<html><body>Verify you are human CAPTCHA</body></html>",
            final_url=url,
            content_type="text/html",
            headers={},
        )


def test_ingestor_blocks_interactive_challenge_before_persistence(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path / "wisdom.db")
    ingestor = KnowledgeIngestor(service, tmp_path / "content", fetcher=_CaptchaFetcher())

    with pytest.raises(PermissionError, match="CAPTCHA"):
        ingestor.ingest_web("https://example.com/protected", actor_id="wisdom-oldman")

    assert service.list_records("source")["count"] == 0


def test_ingestor_deduplicates_identical_content_across_locators(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path / "wisdom.db")
    ingestor = KnowledgeIngestor(service, tmp_path / "content")
    first = ingestor.ingest_text(
        locator="https://example.com/a",
        title="A",
        text="identical evidence",
        actor_id="wisdom-oldman",
    )
    second = ingestor.ingest_text(
        locator="https://mirror.example/b",
        title="B",
        text="identical evidence",
        actor_id="wisdom-oldman",
    )

    assert second["source"]["source_id"] == first["source"]["source_id"]
    assert second["duplicate_content"]
    assert service.list_records("source")["count"] == 1


def test_discovery_identity_normalizes_doi_and_tracking_parameters() -> None:
    left = DiscoveryArtifact(
        "https://doi.org/10.1000/Example", "Left", "openalex", metadata={"doi": "10.1000/example"}
    )
    right = DiscoveryArtifact(
        "https://dx.doi.org/10.1000/example", "Right", "crossref"
    )
    tracked = DiscoveryArtifact(
        "https://Example.com/path?utm_source=x&a=1#fragment", "Tracked", "brave"
    )
    clean = DiscoveryArtifact("https://example.com/path?a=1", "Clean", "brave")

    assert artifact_identity(left) == artifact_identity(right)
    assert artifact_identity(tracked) == artifact_identity(clean)


class _ProviderFetcher:
    def fetch(self, url: str, **kwargs) -> FetchedResource:
        if "openalex" in url:
            payload = {
                "results": [
                    {
                        "id": "W1",
                        "title": "Open work",
                        "doi": "https://doi.org/10.1000/test",
                        "best_oa_location": {"landing_page_url": "https://example.com/open"},
                        "abstract_inverted_index": {"useful": [0], "evidence": [1]},
                    }
                ]
            }
            content_type = "application/json"
            body = json.dumps(payload).encode()
        elif "crossref" in url:
            payload = {
                "message": {
                    "items": [
                        {
                            "DOI": "10.1000/test",
                            "title": ["Crossref work"],
                            "URL": "https://doi.org/10.1000/test",
                        }
                    ]
                }
            }
            content_type = "application/json"
            body = json.dumps(payload).encode()
        else:
            body = (
                b"<feed xmlns='http://www.w3.org/2005/Atom'><entry>"
                b"<title>Battery evidence</title><link href='https://example.com/feed-paper'/>"
                b"<summary>thermal ageing evidence</summary></entry></feed>"
            )
            content_type = "application/atom+xml"
        return FetchedResource(body, url, content_type, {"x-request-id": "req"})


def test_discovery_providers_parse_mocked_responses_without_network() -> None:
    fetcher = _ProviderFetcher()
    openalex = OpenAlexProvider(fetcher).discover("battery")
    crossref = CrossrefProvider(fetcher).discover("battery")
    feed = FeedSitemapProvider(["https://example.com/feed"], fetcher).discover("battery")

    assert openalex.artifacts[0].snippet == "useful evidence"
    assert crossref.artifacts[0].metadata["doi"] == "10.1000/test"
    assert feed.artifacts[0].locator == "https://example.com/feed-paper"


class _UnsafeXmlFetcher:
    def fetch(self, url: str, **kwargs) -> FetchedResource:
        return FetchedResource(
            b"<!DOCTYPE feed [<!ENTITY x 'unsafe'>]><feed>&x;</feed>",
            url,
            "application/xml",
            {},
        )


def test_feed_discovery_rejects_doctype_and_entities() -> None:
    provider = FeedSitemapProvider(["https://example.com/feed"], _UnsafeXmlFetcher())

    with pytest.raises(ValueError, match="document types"):
        provider.discover("battery")


def _started_orbit(tmp_path: Path) -> tuple[KnowledgeService, QuestionOrbitService, str]:
    service = KnowledgeService(tmp_path / "wisdom.db")
    gap = service.add_gap(
        GapRecord(
            gap_type=GapType.WEAK_EVIDENCE,
            reason="The mechanism has only one source.",
            why_worthwhile="Independent evidence could change the answer.",
        ),
        actor_id="wisdom-oldman",
    )
    orbits = QuestionOrbitService(service)
    started = orbits.start(
        "Why does heat accelerate battery ageing?",
        "Resolve the mechanism with independent evidence.",
        SatisfactionLevel.PROVISIONAL,
        "Evidence is incomplete.",
        actor_id="wisdom-oldman",
        gap_ids=[gap["gap_id"]],
        notification_route={"platform": "telegram", "chat_id": "123"},
    )
    return service, orbits, started["orbit"]["orbit_id"]


def test_existing_database_upgrades_additively_and_preserves_event_chain(tmp_path: Path) -> None:
    path = tmp_path / "wisdom.db"
    service = KnowledgeService(path)
    gap = service.add_gap(
        GapRecord(
            gap_type=GapType.COVERAGE,
            reason="Pre-upgrade gap.",
            why_worthwhile="It must survive the additive migration.",
        ),
        actor_id="wisdom-oldman",
    )
    with sqlite3.connect(path) as conn:
        conn.executescript(
            "DROP TABLE orbit_notifications;"
            "DROP TABLE discovery_usage;"
            "DROP TABLE orbit_cycles;"
        )

    upgraded = KnowledgeService(path)

    assert upgraded.get(gap["gap_id"])["record"]["reason"] == "Pre-upgrade gap."
    assert upgraded.history()["chain_valid"]
    with sqlite3.connect(path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"orbit_cycles", "discovery_usage", "orbit_notifications"} <= tables


def test_cycle_lease_completion_usage_and_notification_outbox(tmp_path: Path) -> None:
    service, orbits, orbit_id = _started_orbit(tmp_path)
    cycle = orbits.acquire_cycle("runner-1")

    assert cycle is not None
    assert orbits.acquire_cycle("runner-2") is None
    orbits.record_discovery_usage(orbit_id, "openalex", result_count=2)
    result = orbits.complete_cycle(
        cycle["orbit_cycle_id"],
        "runner-1",
        satisfaction_level=SatisfactionLevel.SUFFICIENT,
        satisfaction_rationale="Two independent sources now support the mechanism.",
        active_seconds=12,
        source_ids=["src-one", "src-two"],
        evidence_ids=["ev-one"],
        discovery_queries=["battery heat ageing"],
        search_queries_used=1,
        model_tokens_used=100,
        kag_watermark=7,
        decision="COMPLETE",
    )

    assert result["orbit"]["status"] == "COMPLETED"
    assert result["research_run"]["cycle_count"] == 1
    assert orbits.discovery_usage(provider="openalex") == {
        "requests": 1,
        "queries": 1,
        "results": 2,
    }
    notification = orbits.claim_notification(actor_id="orchestrator")
    assert notification is not None
    assert notification["status"] == "SENDING"
    sent = orbits.finish_notification(
        notification["orbit_notification_id"], sent=True, actor_id="orchestrator"
    )
    assert sent["status"] == "SENT"
    assert service.history()["chain_valid"]


def test_provisional_completion_reopens_frontier_for_a_new_cycle(tmp_path: Path) -> None:
    service, orbits, orbit_id = _started_orbit(tmp_path)
    first = orbits.acquire_cycle("runner-1")
    assert first is not None

    result = orbits.complete_cycle(
        first["orbit_cycle_id"],
        "runner-1",
        satisfaction_level=SatisfactionLevel.PROVISIONAL,
        satisfaction_rationale="One source is not enough.",
        active_seconds=1,
        source_ids=["src-one"],
        evidence_ids=["ev-one"],
    )

    assert result["orbit"]["status"] == "QUEUED"
    assert orbits.frontier(orbit_id)["records"][0]["status"] == "OPEN"
    gap_id = orbits.frontier(orbit_id)["records"][0]["gap_id"]
    assert service.get(gap_id)["record"]["status"] == "OPEN"
    second = orbits.acquire_cycle("runner-2")
    assert second is not None
    assert second["cycle_key"] != first["cycle_key"]
    assert second["cycle_key"].endswith(":2")
    assert orbits.used_source_ids(orbit_id) == {"src-one"}


def test_retry_delay_does_not_start_a_duplicate_cycle(tmp_path: Path) -> None:
    service, orbits, first_orbit_id = _started_orbit(tmp_path)
    second_gap = service.add_gap(
        GapRecord(
            gap_type=GapType.COVERAGE,
            reason="A second topic is uncovered.",
            why_worthwhile="It is independently useful.",
        ),
        actor_id="wisdom-oldman",
    )
    second = orbits.start(
        "How should the second battery mechanism be tested?",
        "Resolve a separate topic.",
        SatisfactionLevel.INSUFFICIENT,
        "No evidence yet.",
        actor_id="wisdom-oldman",
        gap_ids=[second_gap["gap_id"]],
    )
    first_cycle = orbits.acquire_cycle("runner-1")
    assert first_cycle is not None
    retry = orbits.fail_cycle(
        first_cycle["orbit_cycle_id"],
        "runner-1",
        "Temporary rate limit.",
        retry_after_seconds=3600,
    )
    assert retry["orbit"]["status"] == "ACTIVE"

    next_cycle = orbits.acquire_cycle("runner-2")

    assert next_cycle is not None
    assert next_cycle["orbit_id"] == second["orbit"]["orbit_id"]
    assert next_cycle["orbit_id"] != first_orbit_id


def test_pause_cancels_active_cycle_and_resume_uses_new_cycle_key(tmp_path: Path) -> None:
    service, orbits, orbit_id = _started_orbit(tmp_path)
    first = orbits.acquire_cycle("runner-1")
    assert first is not None

    paused = orbits.transition(
        orbit_id, OrbitStatus.PAUSED, actor_id="wisdom-oldman", reason="User paused."
    )
    cancelled = service.get(first["orbit_cycle_id"])["record"]
    assert paused["status"] == "PAUSED"
    assert cancelled["status"] == "BLOCKED"
    assert cancelled["decision"] == "CANCELLED"
    with pytest.raises(ValueError, match="running cycle"):
        orbits.complete_cycle(
            first["orbit_cycle_id"],
            "runner-1",
            satisfaction_level=SatisfactionLevel.SUFFICIENT,
            satisfaction_rationale="Must not overwrite pause.",
            active_seconds=1,
        )

    orbits.transition(orbit_id, OrbitStatus.QUEUED, actor_id="wisdom-oldman")
    second = orbits.acquire_cycle("runner-2")
    assert second is not None
    assert second["cycle_key"] != first["cycle_key"]
    assert second["cycle_key"].endswith(":2")


class _Clock(datetime):
    current = datetime.now(UTC)

    @classmethod
    def now(cls, tz=None):
        return cls.current if tz else cls.current.replace(tzinfo=None)


def test_recoverable_cycle_fails_after_three_attempts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(question_orbit_module, "datetime", _Clock)
    _, orbits, _ = _started_orbit(tmp_path)
    cycle = orbits.acquire_cycle("runner-1")
    assert cycle is not None

    for attempt in (1, 2):
        result = orbits.fail_cycle(
            cycle["orbit_cycle_id"],
            f"runner-{attempt}",
            "Temporary provider failure.",
            retry_after_seconds=30,
        )
        assert result["retry"]
        _Clock.current += timedelta(seconds=31)
        cycle = orbits.acquire_cycle(f"runner-{attempt + 1}")
        assert cycle is not None

    terminal = orbits.fail_cycle(
        cycle["orbit_cycle_id"], "runner-3", "Third failure."
    )
    assert not terminal["retry"]
    assert terminal["cycle"]["attempt"] == 3
    assert terminal["orbit"]["status"] == "FAILED"


def test_budget_upgrade_requires_orchestrator_and_resumes_exhausted_orbit(
    tmp_path: Path,
) -> None:
    service, orbits, orbit_id = _started_orbit(tmp_path)
    extra_gap = service.add_gap(
        GapRecord(
            gap_type=GapType.COVERAGE,
            reason="A second high-priority gap remains.",
            why_worthwhile="It affects the final answer.",
        ),
        actor_id="wisdom-oldman",
    )
    created = orbits.expand_frontier(
        orbit_id,
        [extra_gap["gap_id"]],
        priority=question_orbit_module.FrontierPriority.HIGH,
    )
    child = service.get(created[0]["question_id"])["record"]
    assert child["parent_question_id"] == orbits.get(orbit_id)["orbit"]["root_question_id"]
    assert orbits.frontier(orbit_id)["records"][0]["priority"] == "HIGH"
    cycle = orbits.acquire_cycle("runner")
    assert cycle is not None
    exhausted = orbits.complete_cycle(
        cycle["orbit_cycle_id"],
        "runner",
        satisfaction_level=SatisfactionLevel.PROVISIONAL,
        satisfaction_rationale="One high-priority gap remains.",
        active_seconds=600,
    )
    assert exhausted["orbit"]["status"] == "BUDGET_EXHAUSTED"
    with pytest.raises(KnowledgeAuthorizationError):
        orbits.set_budget(orbit_id, BudgetTier.STANDARD, actor_id="wisdom-oldman")

    reviewed = orbits.set_budget(orbit_id, BudgetTier.STANDARD, actor_id="orchestrator")
    assert reviewed["orbit"]["status"] == "QUEUED"
    assert reviewed["research_run"]["budget_tier"] == "STANDARD"


def test_notification_deduplication_and_route_target(tmp_path: Path) -> None:
    service, orbits, orbit_id = _started_orbit(tmp_path)
    first = orbits.enqueue_notification(
        orbit_id,
        "EVIDENCE_CONFLICT",
        {"conflicts": ["a", "b"]},
        dedupe_suffix="same",
    )
    second = orbits.enqueue_notification(
        orbit_id,
        "EVIDENCE_CONFLICT",
        {"conflicts": ["a", "b"]},
        dedupe_suffix="same",
    )

    assert first == second
    assert service.list_records("orbit_notification")["count"] == 1
    assert OrbitNotificationDispatcher._target(
        {"platform": "telegram", "chat_id": "123", "thread_id": "9"}
    ) == "telegram:123:9"


def test_notification_outbox_stops_after_three_failed_deliveries(
    tmp_path: Path, monkeypatch
) -> None:
    _Clock.current = datetime.now(UTC) + timedelta(minutes=1)
    monkeypatch.setattr(question_orbit_module, "datetime", _Clock)
    _, orbits, orbit_id = _started_orbit(tmp_path)
    orbits.enqueue_notification(
        orbit_id, "FAILED", {"reason": "test"}, dedupe_suffix="delivery"
    )

    for _ in range(3):
        notification = orbits.claim_notification(actor_id="orchestrator")
        assert notification is not None
        failed = orbits.finish_notification(
            notification["orbit_notification_id"],
            sent=False,
            error="delivery failed",
            actor_id="orchestrator",
        )
        _Clock.current += timedelta(minutes=10)

    assert failed["attempts"] == 3
    assert failed["status"] == "FAILED"
    assert orbits.claim_notification(actor_id="orchestrator") is None


class _Reasoner:
    def __init__(self) -> None:
        self.calls = 0

    def answer(self, question: str, **kwargs):
        self.calls += 1
        level = "PROVISIONAL" if self.calls == 1 else "SUFFICIENT"
        return {
            "answer": "Current evidence" if self.calls == 1 else "Independent evidence found",
            "runtime_status": "KAG",
            "satisfaction_level": level,
            "satisfaction_rationale": "One gap remains." if self.calls == 1 else "Resolved.",
            "remaining_gap_ids": [],
        }


class _Provider:
    name = "openalex"

    def discover(self, query: str, *, limit: int = 5):
        return DiscoveryResponse(
            [DiscoveryArtifact("https://example.com/paper", "Paper", self.name)], "req-1"
        )


class _RetryProvider:
    name = "crossref"

    def discover(self, query: str, *, limit: int = 5):
        raise RetryAfterError("retry later", 60)


class _BraveProvider:
    name = "brave"

    def __init__(self) -> None:
        self.calls = 0

    def discover(self, query: str, *, limit: int = 5):
        self.calls += 1
        return DiscoveryResponse(
            [DiscoveryArtifact("https://example.com/brave", "Brave", self.name)]
        )


class _Ingestor:
    def ingest_web(self, url: str, *, actor_id: str):
        return {"source": {"source_id": "src-paper"}, "document": {"document_id": "doc-paper"}}


class _Constructor:
    def extract_document(self, document_id: str, **kwargs):
        return {
            "created": {"evidence": ["ev-paper"]},
            "reused": {"evidence": []},
        }


class _Projection:
    def sync(self, **kwargs):
        return {"watermark": 9}


class _Dispatcher:
    def dispatch_one(self) -> bool:
        return False


def test_runner_executes_one_durable_cycle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("uuma.orbit_runner.ensure_knowledge_graph", lambda *a, **k: {"ready": True})
    service, orbits, orbit_id = _started_orbit(tmp_path)
    runner = OrbitRunner(
        service,
        orbits,
        _Reasoner(),
        [_RetryProvider(), _Provider()],
        _Ingestor(),
        _Constructor(),
        _Projection(),
        _Dispatcher(),
        owner_id="runner-test",
        heartbeat_interval=0,
    )

    assert runner.run_once()
    state = orbits.get(orbit_id)
    assert state["orbit"]["status"] == "COMPLETED"
    assert state["research_run"]["sources_used"] == 1
    assert orbits.discovery_usage(provider="openalex")["requests"] == 1


def test_runner_satisfaction_requires_two_new_cited_sources_and_no_conflict() -> None:
    answer = {
        "answer": "Supported answer.",
        "satisfaction_level": "PROVISIONAL",
        "satisfaction_rationale": "The backend does not score completeness.",
        "citations": [{"source_id": "src-a"}, {"source_id": "src-b"}],
        "conflicts": [],
    }

    assessed = OrbitRunner._assess_satisfaction(
        answer, source_ids=["src-a", "src-b"], evidence_ids=["ev-a", "ev-b"]
    )
    conflicted = OrbitRunner._assess_satisfaction(
        answer | {"conflicts": ["The sources disagree."]},
        source_ids=["src-a", "src-b"],
        evidence_ids=["ev-a", "ev-b"],
    )
    one_source = OrbitRunner._assess_satisfaction(
        answer,
        source_ids=["src-a"],
        evidence_ids=["ev-a", "ev-b"],
    )

    assert assessed["satisfaction_level"] == "SUFFICIENT"
    assert conflicted["satisfaction_level"] == "PROVISIONAL"
    assert one_source["satisfaction_level"] == "PROVISIONAL"


def test_runner_blocks_before_research_when_graph_is_unavailable(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("uuma.orbit_runner.ensure_knowledge_graph", lambda *a, **k: {"ready": False})
    service, orbits, orbit_id = _started_orbit(tmp_path)
    reasoner = _Reasoner()
    runner = OrbitRunner(
        service, orbits, reasoner, [_Provider()], _Ingestor(), _Constructor(),
        _Projection(), _Dispatcher(), owner_id="graph-test", heartbeat_interval=0,
    )
    assert runner.run_once()
    assert reasoner.calls == 0
    assert orbits.get(orbit_id)["orbit"]["status"] == "BLOCKED"
    assert orbits.discovery_usage(provider="openalex")["requests"] == 0


class _TwoSourceProvider:
    name = "openalex"

    def discover(self, query: str, *, limit: int = 5):
        return DiscoveryResponse(
            [
                DiscoveryArtifact("https://example.com/old", "Old", self.name),
                DiscoveryArtifact("https://example.com/new", "New", self.name),
            ]
        )


class _TwoSourceIngestor:
    def ingest_web(self, url: str, *, actor_id: str):
        suffix = "old" if url.endswith("/old") else "new"
        return {
            "source": {"source_id": f"src-{suffix}"},
            "document": {"document_id": f"doc-{suffix}"},
        }


def test_runner_skips_sources_used_by_prior_cycles(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("uuma.orbit_runner.ensure_knowledge_graph", lambda *a, **k: {"ready": True})
    service, orbits, orbit_id = _started_orbit(tmp_path)
    first = orbits.acquire_cycle("setup")
    assert first is not None
    orbits.complete_cycle(
        first["orbit_cycle_id"],
        "setup",
        satisfaction_level=SatisfactionLevel.PROVISIONAL,
        satisfaction_rationale="A second source is still needed.",
        active_seconds=1,
        source_ids=["src-old"],
        evidence_ids=["ev-old"],
    )
    runner = OrbitRunner(
        service,
        orbits,
        _Reasoner(),
        [_TwoSourceProvider()],
        _TwoSourceIngestor(),
        _Constructor(),
        _Projection(),
        _Dispatcher(),
        owner_id="runner-test",
        heartbeat_interval=0,
    )

    assert runner.run_once()
    state = orbits.get(orbit_id)
    completed_cycles = [
        cycle
        for cycle in service.list_records("orbit_cycle")["records"]
        if cycle["orbit_id"] == orbit_id and cycle["status"] == "COMPLETED"
    ]
    assert state["orbit"]["status"] == "COMPLETED"
    assert state["research_run"]["sources_used"] == 2
    assert next(cycle for cycle in completed_cycles if cycle["cycle_key"].endswith(":2"))[
        "source_ids"
    ] == ["src-new"]


def test_runner_enforces_brave_monthly_hard_limit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("uuma.orbit_runner.ensure_knowledge_graph", lambda *a, **k: {"ready": True})
    service, orbits, orbit_id = _started_orbit(tmp_path)
    orbits.record_discovery_usage(
        orbit_id, "brave", request_count=950, query_count=950
    )
    brave = _BraveProvider()
    runner = OrbitRunner(
        service,
        orbits,
        _Reasoner(),
        [brave],
        _Ingestor(),
        _Constructor(),
        _Projection(),
        _Dispatcher(),
        owner_id="runner-test",
        heartbeat_interval=0,
    )

    assert runner.run_once()
    assert brave.calls == 0
    assert orbits.get(orbit_id)["orbit"]["status"] == "BLOCKED"
