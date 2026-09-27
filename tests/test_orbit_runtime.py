from __future__ import annotations

import io
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

import uuma.question_orbit as question_orbit_module
from uuma.knowledge_ingest import ExtractedContent, KnowledgeIngestor
from uuma.knowledge_models import (
    BudgetTier,
    GapRecord,
    GapType,
    OrbitStatus,
    QuestionRecord,
    SatisfactionLevel,
    SourceRecord,
)
from uuma.knowledge_service import KnowledgeAuthorizationError, KnowledgeService
from uuma.orbit_discovery import (
    CrossrefProvider,
    DdgsSearchProvider,
    DiscoveryArtifact,
    DiscoveryResponse,
    FeedSitemapProvider,
    OpenAlexProvider,
    artifact_identity,
    artifact_is_relevant,
    artifact_priority,
    citations_fit_question,
    discovery_queries,
    discovery_query,
)
from uuma.orbit_runner import OrbitNotificationDispatcher, OrbitRunner, _RunnerInstanceLock
from uuma.orbit_synthesis import OrbitCompactSynthesizer
from uuma.question_orbit import QuestionOrbitService
from uuma.safe_web import FetchedResource, RetryAfterError, SafeWebFetcher, UnsafeUrlError
from uuma.wisdom_topics import TopicKnowledgeService


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


class _MisleadingSearchResultFetcher:
    def fetch(self, url: str, **kwargs) -> FetchedResource:
        return FetchedResource(
            body=(
                "<html><head><title>气候变化背景下西藏青稞播期优化与稳产栽培策略"
                "</title></head><body>青稞农业研究</body></html>"
            ).encode(),
            final_url=url,
            content_type="text/html",
            headers={},
        )


def test_ingestor_rechecks_actual_title_before_storing_research_source(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path / "wisdom.db")
    ingestor = KnowledgeIngestor(
        service, tmp_path / "content", fetcher=_MisleadingSearchResultFetcher()
    )

    with pytest.raises(ValueError, match="does not match"):
        ingestor.ingest_web(
            "https://example.com/青葱气雾栽培",
            actor_id="wisdom-oldman",
            topic_question="青葱 气雾栽培 分株法",
        )

    assert service.list_records("source")["count"] == 0


def test_ingestor_uses_downloaded_pdf_title_line_when_filename_is_numeric(
    tmp_path: Path, monkeypatch
) -> None:
    class PdfFetcher:
        def fetch(self, url: str, **kwargs) -> FetchedResource:
            return FetchedResource(
                body=b"%PDF-1.4 test", final_url=url,
                content_type="application/pdf", headers={},
            )

    service = KnowledgeService(tmp_path / "wisdom.db")
    ingestor = KnowledgeIngestor(service, tmp_path / "content", fetcher=PdfFetcher())
    monkeypatch.setattr(
        ingestor, "_extract",
        lambda raw, suffix, url: ExtractedContent(
            "Journal header\nCultivation of green onion (Allium fistulosum L.)\nResults",
            "application/pdf", "15262", {},
        ),
    )

    result = ingestor.ingest_web(
        "https://example.com/download/15262", actor_id="wisdom-oldman",
        topic_question="青葱 气雾栽培 分株法",
    )

    assert "Allium fistulosum" in result["source"]["title"]


def test_malformed_pdf_uses_local_text_fallback_and_keeps_page_locations(
    tmp_path: Path, monkeypatch
) -> None:
    from pypdf.errors import PdfReadError

    def malformed(_raw):
        raise PdfReadError("malformed object stream")

    monkeypatch.setattr("pypdf.PdfReader", malformed)
    monkeypatch.setattr("uuma.knowledge_ingest.shutil.which", lambda name: "pdftotext")
    monkeypatch.setattr(
        "uuma.knowledge_ingest.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=b"Allium fistulosum introduction " + b"A" * 1500
            + b"\fSecond page results " + b"B" * 1500 + b"\f",
        ),
    )
    extracted = KnowledgeIngestor._extract(b"%PDF broken", ".pdf", "paper.pdf")
    assert extracted.metadata == {"page_count": 2, "extractor": "pdftotext"}

    service = KnowledgeService(tmp_path / "wisdom.db")
    ingested = KnowledgeIngestor(service, tmp_path / "content").ingest_text(
        locator="https://example.org/paper.pdf", title="Allium fistulosum study",
        text=extracted.text, media_type="application/pdf", actor_id="wisdom-oldman",
    )
    assert any("page 1" in item["location"] for item in ingested["chunks"])
    assert any("page 2" in item["location"] for item in ingested["chunks"])


def test_compact_synthesis_uses_located_research_and_excludes_forum(
    tmp_path: Path, monkeypatch
) -> None:
    service = KnowledgeService(tmp_path / "wisdom.db")
    ingestor = KnowledgeIngestor(service, tmp_path / "content")
    paper = ingestor.ingest_text(
        locator="https://research.example.edu/allium.pdf",
        title="Allium fistulosum aeroponic study",
        text="Allium fistulosum was compared in fogoponic and hydroponic systems.",
        media_type="application/pdf", actor_id="wisdom-oldman",
    )
    ingestor.ingest_text(
        locator="https://www.douban.com/group/topic/123",
        title="青葱分株经验", text="Forum anecdote.", actor_id="wisdom-oldman",
    )

    class Graph:
        def retrieve_context(self, question: str):
            return {"result_refs": [paper["chunks"][0]["chunk_id"]]}

    monkeypatch.setattr(
        OrbitCompactSynthesizer, "_generate",
        staticmethod(lambda question, snippets: [{
            "text": "有研究比较了青葱的雾培与水培。",
            "sources": ["S1"], "certainty": "evidence",
        }]),
    )
    result = OrbitCompactSynthesizer(service, Graph()).answer(
        "青葱气雾培和分株繁殖", actor_id="wisdom-oldman"
    )
    assert result["satisfaction_level"] == "PROVISIONAL"
    assert len(result["citations"]) == 1
    assert result["citations"][0]["source_id"] == paper["source"]["source_id"]
    assert "allium.pdf#page=1" in result["answer"]
    assert "douban.com" not in result["answer"]


def test_compact_synthesis_retries_short_json_after_empty_model_content(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.org/v1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-key")
    monkeypatch.setenv("UUMA_KAG_LLM_MODEL", "test-model")
    calls = []

    def response(request, timeout):
        calls.append(request)
        content = "" if len(calls) == 1 else json.dumps({"points": [{
            "text": "有可核对的资料。", "sources": ["S1"], "certainty": "evidence",
        }]})
        return io.BytesIO(json.dumps({
            "choices": [{"message": {"content": content}}]
        }).encode())

    monkeypatch.setattr("uuma.orbit_synthesis.urlopen", response)
    points = OrbitCompactSynthesizer._generate("青葱气雾培", [{
        "key": "S1", "title": "Allium fistulosum fogoponic trial",
        "location": "Abstract", "text": "Located evidence.",
    }])

    assert len(calls) == 2
    assert points[0]["sources"] == ["S1"]


def test_compact_synthesis_retries_once_after_network_reset(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.org/v1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-key")
    monkeypatch.setenv("UUMA_KAG_LLM_MODEL", "test-model")
    calls = []

    def response(request, timeout):
        calls.append(request)
        if len(calls) == 1:
            raise URLError("connection reset")
        return io.BytesIO(json.dumps({
            "choices": [{"message": {"content": json.dumps({"points": [{
                "text": "资料仍需核对。", "sources": ["S1"], "certainty": "inference",
            }]})}}]
        }).encode())

    monkeypatch.setattr("uuma.orbit_synthesis.urlopen", response)
    points = OrbitCompactSynthesizer._generate("青葱分株", [{
        "key": "S1", "title": "Allium fistulosum division study",
        "location": "Abstract", "text": "Located evidence.",
    }])

    assert len(calls) == 2
    assert points[0]["certainty"] == "inference"


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
    assert ingestor.existing_web("https://example.com/a")["document"]["document_id"] == (
        first["document"]["document_id"]
    )
    assert ingestor.existing_web("https://example.com/missing") is None


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


def test_discovery_filters_unrelated_hits_before_ingestion():
    question = "针对 青葱 的 气雾栽培细节与核心构建要素，分株法"
    unrelated = DiscoveryArtifact(
        "https://front-sci.com/journal/article", "构建德育课程体系 培养学生核心素养",
        "openalex",
    )
    relevant = DiscoveryArtifact(
        "https://example.org/scallions", "青葱气雾栽培试验", "openalex",
    )
    assert discovery_query(question).startswith("青葱 气雾栽培")
    assert discovery_queries(question)[-1] == "Allium fistulosum aeroponics division propagation"
    assert not artifact_is_relevant(question, unrelated)
    assert artifact_is_relevant(question, relevant)
    assert artifact_priority(
        question,
        DiscoveryArtifact("https://example.org/scallion", "葱的气雾栽培及关键技术", "ddgs"),
    ) > artifact_priority(
        question,
        DiscoveryArtifact("https://example.edu.cn/potato", "马铃薯气雾栽培", "ddgs-academic"),
    )
    assert not artifact_is_relevant(
        question,
        DiscoveryArtifact(
            "https://example.org/aeroponics",
            "气雾栽培箱喷雾条件下温度场的CFD数值模拟",
            "ddgs-academic",
        ),
    )
    assert not artifact_is_relevant(
        question,
        DiscoveryArtifact("https://example.org/division", "分株繁育", "ddgs"),
    )
    assert artifact_is_relevant(
        question,
        DiscoveryArtifact(
            "https://example.edu/allium", "Allium fistulosum fogoponic growth", "openalex",
        ),
    )
    assert not artifact_is_relevant(
        question,
        DiscoveryArtifact(
            "https://example.edu/obesity", "Obesity: Can Allium fistulosum be a remedy?",
            "openalex",
        ),
    )
    assert not artifact_is_relevant(
        question,
        DiscoveryArtifact(
            "https://example.org/barley",
            "气候变化背景下西藏青稞播期优化与稳产栽培策略",
            "openalex",
            snippet="青葱 气雾栽培 分株法",
        ),
    )
    assert not artifact_is_relevant(
        question,
        DiscoveryArtifact(
            "https://example.org/client-challenge",
            "Client Challenge",
            "crossref",
            snippet="青葱 气雾栽培 分株法",
        ),
    )
    assert artifact_is_relevant(
        question, DiscoveryArtifact("https://example.org/file", "User supplied", "user-url")
    )


def test_recovery_discovery_prioritizes_recovery_evidence() -> None:
    question = "青葱分株后缓苗要多久？"
    queries = discovery_queries(question)
    assert "Allium fistulosum division transplant establishment survival" in queries
    assert not artifact_is_relevant(
        question,
        DiscoveryArtifact(
            "https://example.org/hydroponics",
            "Allium fistulosum hydroponic nutrient concentration",
            "openalex",
        ),
    )
    assert artifact_is_relevant(
        question,
        DiscoveryArtifact(
            "https://example.org/transplant",
            "Welsh onion transplant establishment study",
            "openalex",
        ),
    )


def test_aeroponic_parameter_question_excludes_general_growing_pages(tmp_path: Path) -> None:
    question = "青葱气雾培的喷雾间隔与喷头参数是什么？"
    garden = DiscoveryArtifact(
        "https://example.org/spring-onions", "Allium fistulosum growing guide", "ddgs"
    )
    study = DiscoveryArtifact(
        "https://example.edu/study", "Allium fistulosum fogoponic study", "openalex"
    )
    assert not artifact_is_relevant(question, garden)
    assert artifact_is_relevant(question, study)
    assert "Allium fistulosum aeroponic mist interval nutrient solution nozzle" in (
        discovery_queries(question)
    )

    service = KnowledgeService(tmp_path / "wisdom.db")
    paper = KnowledgeIngestor(service, tmp_path / "content").ingest_text(
        locator="https://example.edu/generic-title",
        title="Effect of cultivation method on green onion",
        text="Fogoponic cultivation of Allium fistulosum was compared with hydroponics.",
        media_type="text/plain", actor_id="wisdom-oldman",
    )
    citation = {
        "source_id": paper["source"]["source_id"],
        "chunk_id": paper["chunks"][0]["chunk_id"],
    }
    assert citations_fit_question(service, question, [citation])
    assert OrbitCompactSynthesizer(service, object())._snippets(question, set())


def test_recovery_synthesis_omits_adjacent_growth_claims(tmp_path: Path, monkeypatch) -> None:
    service = KnowledgeService(tmp_path / "wisdom.db")
    paper = KnowledgeIngestor(service, tmp_path / "content").ingest_text(
        locator="https://research.example.edu/allium-transplant.pdf",
        title="Allium fistulosum transplant establishment",
        text="The abstract reviews Allium fistulosum transplant establishment.",
        media_type="application/pdf", actor_id="wisdom-oldman",
    )

    class Graph:
        def retrieve_context(self, question: str):
            return {"result_refs": [paper["chunks"][0]["chunk_id"]]}

    monkeypatch.setattr(
        OrbitCompactSynthesizer, "_generate",
        staticmethod(lambda question, snippets: [
            {"text": "水培条件下叶面积增加。", "sources": ["S1"], "certainty": "evidence"},
            {"text": "所审阅摘录未说明分株后缓苗需要多少天。",
             "sources": ["S1"], "certainty": "evidence"},
        ]),
    )
    answer = OrbitCompactSynthesizer(service, Graph()).answer(
        "青葱分株后缓苗要多久？", actor_id="wisdom-oldman"
    )
    assert "缓苗需要多少天" in answer["answer"]
    assert "水培条件下叶面积增加" not in answer["answer"]
    assert len(answer["citations"]) == 1

    monkeypatch.setattr(
        OrbitCompactSynthesizer, "_generate",
        staticmethod(lambda question, snippets: [
            {"text": "水培条件下叶面积增加。", "sources": ["S1"], "certainty": "evidence"},
        ]),
    )
    insufficient = OrbitCompactSynthesizer(service, Graph()).answer(
        "青葱分株后缓苗要多久？", actor_id="wisdom-oldman"
    )
    assert insufficient["satisfaction_level"] == "INSUFFICIENT"
    assert insufficient["citations"] == []


def test_unrelated_canonical_citation_cannot_ground_topic_answer(tmp_path: Path):
    service = KnowledgeService(tmp_path / "wisdom.db")
    unrelated = service.add_source(
        SourceRecord(
            locator="https://example.org/education", title="构建德育课程体系 培养学生核心素养"
        ),
        actor_id="wisdom-oldman",
    )
    relevant = service.add_source(
        SourceRecord(locator="https://example.org/scallions", title="青葱气雾栽培试验"),
        actor_id="wisdom-oldman",
    )
    method_only = service.add_source(
        SourceRecord(locator="https://example.org/potato", title="马铃薯气雾栽培研究"),
        actor_id="wisdom-oldman",
    )
    question = "青葱气雾栽培细节"
    assert not citations_fit_question(service, question, [{"source_id": unrelated["source_id"]}])
    assert not citations_fit_question(service, question, [{"source_id": method_only["source_id"]}])
    assert citations_fit_question(service, question, [{"source_id": relevant["source_id"]}])
    assert citations_fit_question(
        service, "针对 青葱 的气雾培细节", [{"source_id": relevant["source_id"]}]
    )
    assert not citations_fit_question(
        service,
        question,
        [{"source_id": relevant["source_id"]}, {"source_id": method_only["source_id"]}],
    )


def test_ddgs_discovery_maps_web_results_to_artifacts(monkeypatch):
    import sys
    from types import SimpleNamespace

    class FakeSearch:
        def __init__(self, *, timeout):
            assert timeout == 12

        def text(self, query, *, max_results):
            assert query == "青葱 气雾栽培"
            assert max_results == 3
            return [{
                "href": "https://example.org/aeroponics",
                "title": "青葱气雾栽培",
                "body": "Experimental overview",
            }]

    monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=FakeSearch))
    result = DdgsSearchProvider().discover("青葱 气雾栽培", limit=3)
    assert result.artifacts[0].provider == "ddgs"
    assert result.artifacts[0].snippet == "Experimental overview"


def test_ddgs_academic_search_limits_chinese_query_to_education_sources(monkeypatch):
    import sys
    from types import SimpleNamespace

    class FakeSearch:
        def __init__(self, *, timeout):
            assert timeout == 12

        def text(self, query, *, max_results):
            assert query == "气雾栽培 site:edu.cn"
            return [{"href": "https://example.edu.cn/study", "title": "气雾栽培研究"}]

    monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=FakeSearch))
    result = DdgsSearchProvider(academic=True).discover("气雾栽培", limit=5)
    assert result.artifacts[0].provider == "ddgs-academic"


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


def test_no_new_source_checks_other_open_questions_before_pausing(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path / "wisdom.db")
    questions = [
        service.add_question(
            QuestionRecord(
                text=f"How does scallion growing aspect {index} work?",
                why_worth_knowing="The aspects need separate answers.",
            ),
            actor_id="wisdom-oldman",
        )
        for index in range(2)
    ]
    gaps = [
        service.add_gap(
            GapRecord(
                gap_type=GapType.COVERAGE,
                reason=f"Unresolved aspect {index}",
                why_worthwhile="Each aspect needs independent research.",
                question_id=questions[index]["question_id"],
            ),
            actor_id="wisdom-oldman",
        )
        for index in range(2)
    ]
    orbits = QuestionOrbitService(service)
    orbits.start(
        "How do two aspects of scallion growing work?",
        "Research both unresolved aspects.",
        SatisfactionLevel.PROVISIONAL,
        "Both aspects need evidence.",
        actor_id="wisdom-oldman",
        gap_ids=[item["gap_id"] for item in gaps],
    )
    first = orbits.acquire_cycle("runner-1")
    assert first is not None
    first_result = orbits.complete_cycle(
        first["orbit_cycle_id"], "runner-1",
        satisfaction_level=SatisfactionLevel.PROVISIONAL,
        satisfaction_rationale="No new source for this aspect.",
        active_seconds=1, no_new_source=True,
    )
    assert first_result["orbit"]["status"] == "QUEUED"
    second = orbits.acquire_cycle("runner-2")
    assert second is not None
    assert second["question_id"] != first["question_id"]
    second_result = orbits.complete_cycle(
        second["orbit_cycle_id"], "runner-2",
        satisfaction_level=SatisfactionLevel.PROVISIONAL,
        satisfaction_rationale="No new source for the other aspect.",
        active_seconds=1, no_new_source=True,
    )
    assert second_result["orbit"]["status"] == "PAUSED"
    assert "所有未解决问题" in second_result["orbit"]["stop_reason"]
    assert second_result["research_run"]["stop_reason"] == second_result["orbit"][
        "stop_reason"
    ]
    assert service.history()["chain_valid"]


def test_review_reopens_falsely_filled_gap_without_resetting_budget(tmp_path: Path) -> None:
    service, orbits, orbit_id = _started_orbit(tmp_path)
    gap_id = orbits.frontier(orbit_id)["records"][0]["gap_id"]
    cycle = orbits.acquire_cycle("runner-1")
    assert cycle is not None
    orbits.complete_cycle(
        cycle["orbit_cycle_id"],
        "runner-1",
        satisfaction_level=SatisfactionLevel.SUFFICIENT,
        satisfaction_rationale="Incorrectly considered complete.",
        active_seconds=12,
        source_ids=["src-one"],
        model_tokens_used=100,
    )

    repaired = orbits.reopen_gap(
        orbit_id, gap_id,
        reason="The cited source does not answer the requested parameter.",
        actor_id="orchestrator",
    )
    repeated = orbits.reopen_gap(
        orbit_id, gap_id,
        reason="The cited source does not answer the requested parameter.",
        actor_id="orchestrator",
    )

    assert repaired["reopened"]
    assert not repeated["reopened"]
    assert orbits.get(orbit_id)["orbit"]["status"] == "QUEUED"
    assert orbits.get(orbit_id)["research_run"]["active_seconds"] == 12
    assert orbits.get(orbit_id)["research_run"]["model_tokens_used"] == 100
    assert service._require("gaps", gap_id)["status"] == "OPEN"
    assert orbits.acquire_cycle("runner-2") is not None
    assert service.history()["chain_valid"]


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
    assert OrbitNotificationDispatcher._target({"platform": "telegram"}) is None


def test_invalid_unsent_digest_can_be_cancelled_without_erasing_history(
    tmp_path: Path,
) -> None:
    service, orbits, orbit_id = _started_orbit(tmp_path)
    notice = orbits.enqueue_notification(
        orbit_id, "FIRST_USEFUL_ANSWER", {"summary": "No evidence."},
        dedupe_suffix="first-answer",
    )
    assert notice is not None

    cancelled = orbits.cancel_notification(
        notice["orbit_notification_id"], reason="No grounded answer was present."
    )

    assert cancelled["status"] == "FAILED"
    assert cancelled["attempts"] == 3
    assert orbits.claim_notification(actor_id="orchestrator") is None
    assert service.history()["chain_valid"]


def test_orbit_notification_route_repair_preserves_research_budget(tmp_path: Path) -> None:
    service, orbits, orbit_id = _started_orbit(tmp_path)
    before = orbits.get(orbit_id)

    repaired = orbits.update_notification_route(
        orbit_id,
        {"platform": "telegram", "chat_id": "chat-123", "session_id": "session-1"},
    )

    assert repaired["notification_route"]["chat_id"] == "chat-123"
    assert orbits.get(orbit_id)["research_run"]["sources_used"] == before["research_run"][
        "sources_used"
    ]
    with pytest.raises(ValueError, match="chat ID"):
        orbits.update_notification_route(orbit_id, {"platform": "telegram"})
    assert service.history()["chain_valid"]


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
    def __init__(self, citation_source_id: str = "src-paper") -> None:
        self.calls = 0
        self.citation_source_id = citation_source_id

    def answer(self, question: str, **kwargs):
        self.calls += 1
        level = "PROVISIONAL" if self.calls == 1 else "SUFFICIENT"
        return {
            "answer": "Current evidence" if self.calls == 1 else "Independent evidence found",
            "runtime_status": "KAG",
            "satisfaction_level": level,
            "satisfaction_rationale": "One gap remains." if self.calls == 1 else "Resolved.",
            "remaining_gap_ids": [],
            "citations": [] if self.calls == 1 else [
                {"source_id": self.citation_source_id, "locator": "https://example.com/paper"}
            ],
        }


class _UnavailableReasoner:
    def answer(self, question: str, **kwargs):
        return {"runtime_status": "DEGRADED_KAG"}


class _Provider:
    name = "openalex"

    def discover(self, query: str, *, limit: int = 5):
        return DiscoveryResponse(
            [DiscoveryArtifact("https://example.com/paper", "Battery ageing paper", self.name)],
            "req-1",
        )


class _RetryProvider:
    name = "crossref"

    def discover(self, query: str, *, limit: int = 5):
        raise RetryAfterError("retry later", 60)


class _UnrelatedProvider:
    name = "openalex"

    def discover(self, query: str, *, limit: int = 5):
        return DiscoveryResponse([
            DiscoveryArtifact("https://example.com/education", "Moral education curriculum", self.name)
        ])


class _BraveProvider:
    name = "brave"

    def __init__(self) -> None:
        self.calls = 0

    def discover(self, query: str, *, limit: int = 5):
        self.calls += 1
        return DiscoveryResponse(
            [DiscoveryArtifact("https://example.com/brave", "Battery ageing", self.name)]
        )


class _Ingestor:
    def __init__(self, service: KnowledgeService) -> None:
        self.service = service

    def ingest_web(self, url: str, *, actor_id: str, topic_question: str | None = None):
        self.service.add_source(
            SourceRecord(source_id="src-paper", locator=url, title="Battery ageing paper"),
            actor_id=actor_id,
        )
        return {"source": {"source_id": "src-paper"}, "document": {"document_id": "doc-paper"}}


class _Constructor:
    def extract_document(self, document_id: str, **kwargs):
        return {
            "created": {"evidence": ["ev-paper"]},
            "reused": {"evidence": []},
        }


class _Projection:
    def sync(self, **kwargs):
        raise AssertionError("A slow KAG rebuild must not hold up topic publication")


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
        _Ingestor(service),
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


def test_runner_pauses_after_unrelated_search_hits_without_canonical_ingestion(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("uuma.orbit_runner.ensure_knowledge_graph", lambda *a, **k: {"ready": True})
    service, orbits, orbit_id = _started_orbit(tmp_path)

    class RejectIngestor:
        def ingest_web(self, url: str, *, actor_id: str, topic_question: str | None = None):
            raise AssertionError("An unrelated search hit was sent to ingestion")

    runner = OrbitRunner(
        service, orbits, _Reasoner(), [_UnrelatedProvider()], RejectIngestor(),
        _Constructor(), _Projection(), _Dispatcher(), owner_id="relevance-test",
        heartbeat_interval=0,
    )
    assert runner.run_once()
    assert orbits.get(orbit_id)["orbit"]["status"] == "PAUSED"
    assert service.list_records("source")["records"] == []


def test_one_throttled_provider_does_not_retry_successful_empty_discovery(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("uuma.orbit_runner.ensure_knowledge_graph", lambda *a, **k: {"ready": True})
    service, orbits, orbit_id = _started_orbit(tmp_path)

    class RejectIngestor:
        def ingest_web(self, url: str, *, actor_id: str, topic_question: str | None = None):
            raise AssertionError("An unrelated hit was sent to ingestion")

    runner = OrbitRunner(
        service, orbits, _Reasoner(), [_RetryProvider(), _UnrelatedProvider()],
        RejectIngestor(), _Constructor(), _Projection(), _Dispatcher(),
        owner_id="partial-discovery-test", heartbeat_interval=0,
    )
    assert runner.run_once()
    assert orbits.get(orbit_id)["orbit"]["status"] == "PAUSED"
    assert all(item["status"] != "RETRY" for item in service.store.list_records("orbit_cycles"))


def test_runner_does_not_treat_citation_count_as_answer_completeness() -> None:
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
    reused = OrbitRunner._assess_satisfaction(
        answer | {"citations": [
            {"source_id": "src-a", "chunk_id": "chunk-a"},
            {"source_id": "src-b", "chunk_id": "chunk-b"},
        ]},
        source_ids=[], evidence_ids=[],
    )

    assert assessed["satisfaction_level"] == "PROVISIONAL"
    assert conflicted["satisfaction_level"] == "PROVISIONAL"
    assert one_source["satisfaction_level"] == "PROVISIONAL"
    assert reused["satisfaction_level"] == "PROVISIONAL"


def test_material_change_digest_requires_evidence_change_or_downgrade() -> None:
    original = {
        "answer": "青葱雾培的根系较多。",
        "satisfaction_level": "PROVISIONAL",
        "citations": [{"source_id": "src-a"}],
        "conflicts": [],
    }
    reworded = original | {
        "answer": "雾培处理中，青葱平均根数高于水培。",
        "satisfaction_level": "SUFFICIENT",
    }
    new_source = reworded | {"citations": [{"source_id": "src-b"}]}

    assert not OrbitRunner._materially_changed(original, reworded)
    assert OrbitRunner._materially_changed(original, new_source)
    assert OrbitRunner._materially_changed(
        reworded, original | {"satisfaction_level": "INSUFFICIENT"}
    )


def test_runner_publishes_first_grounded_answer_before_finishing_cycle(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path / "wisdom.db")
    topics = TopicKnowledgeService(service, view_token="test-token")
    resolved = topics.resolve_question(
        "青葱气雾培与分株", actor_id="orchestrator", allow_new_topic=True
    )
    gap = service.add_gap(
        GapRecord(
            gap_type=GapType.COVERAGE, reason="Confirm transplant recovery conditions.",
            why_worthwhile="A reusable topic document needs this condition.",
            question_id=resolved["question"]["question_id"],
        ),
        actor_id="wisdom-oldman",
    )
    orbits = QuestionOrbitService(service, topics=topics)
    started = orbits.start(
        "青葱气雾培与分株", "Build a sourced overview.",
        SatisfactionLevel.PROVISIONAL, "Research continues.",
        actor_id="orchestrator", topic_id=resolved["topic"]["topic_id"],
        root_question_id=resolved["question"]["question_id"],
        gap_ids=[gap["gap_id"]],
        notification_route={"platform": "telegram", "chat_id": "test-chat"},
    )
    source = service.add_source(
        SourceRecord(
            locator="https://example.edu/allium", title="Allium fistulosum fogoponic study"
        ),
        actor_id="wisdom-oldman",
    )
    dispatched = []
    runner = OrbitRunner(
        service, orbits, None, [], None, None, None,
        SimpleNamespace(dispatch_one=lambda: dispatched.append(True)),
    )
    cycle = {
        "orbit_id": started["orbit"]["orbit_id"],
        "question_id": resolved["question"]["question_id"],
    }
    answer = {
        "answer": "资料支持：该研究涉及青葱雾培。",
        "citations": [{"source_id": source["source_id"]}],
        "satisfaction_rationale": "Located evidence is available.",
    }

    runner._publish_first_grounded_answer(cycle, answer)
    runner._publish_first_grounded_answer(cycle, answer)

    topic_state = topics.get_topic(resolved["topic"]["topic_id"])
    document = topic_state["document"]
    assert document["current_version"] == 1
    assert "## 未解决问题" in topic_state["latest_version"]["body_markdown"]
    notifications = service.list_records("orbit_notification")["records"]
    assert len(notifications) == 1
    assert notifications[0]["event_type"] == "FIRST_USEFUL_ANSWER"
    assert len(dispatched) == 1


def test_runner_blocks_before_research_when_graph_is_unavailable(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("uuma.orbit_runner.ensure_knowledge_graph", lambda *a, **k: {"ready": False})
    service, orbits, orbit_id = _started_orbit(tmp_path)
    reasoner = _Reasoner()
    runner = OrbitRunner(
        service, orbits, reasoner, [_Provider()], _Ingestor(service), _Constructor(),
        _Projection(), _Dispatcher(), owner_id="graph-test", heartbeat_interval=0,
    )
    assert runner.run_once()
    assert reasoner.calls == 0
    assert orbits.get(orbit_id)["orbit"]["status"] == "BLOCKED"
    assert orbits.discovery_usage(provider="openalex")["requests"] == 0


def test_runner_retries_transient_graph_reasoning_failure(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("uuma.orbit_runner.ensure_knowledge_graph", lambda *a, **k: {"ready": True})
    service, orbits, orbit_id = _started_orbit(tmp_path)
    runner = OrbitRunner(
        service, orbits, _UnavailableReasoner(), [_Provider()], _Ingestor(service),
        _Constructor(), _Projection(), _Dispatcher(), owner_id="graph-retry-test",
        heartbeat_interval=0,
    )

    assert runner.run_once()
    state = orbits.get(orbit_id)
    assert state["orbit"]["status"] == "ACTIVE"
    assert service.list_records("orbit_cycle")["records"][0]["status"] == "RETRY"
    assert orbits.discovery_usage(provider="openalex")["requests"] == 0


class _TwoSourceProvider:
    name = "openalex"

    def discover(self, query: str, *, limit: int = 5):
        return DiscoveryResponse(
            [
                DiscoveryArtifact("https://example.com/old", "Battery ageing old", self.name),
                DiscoveryArtifact("https://example.com/new", "Battery ageing new", self.name),
            ]
        )


class _TwoSourceIngestor:
    def __init__(self, service: KnowledgeService) -> None:
        self.service = service

    def ingest_web(self, url: str, *, actor_id: str, topic_question: str | None = None):
        suffix = "old" if url.endswith("/old") else "new"
        self.service.add_source(
            SourceRecord(
                source_id=f"src-{suffix}", locator=url, title=f"Battery ageing {suffix}"
            ),
            actor_id=actor_id,
        )
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
        _Reasoner("src-new"),
        [_TwoSourceProvider()],
        _TwoSourceIngestor(service),
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
        _Ingestor(service),
        _Constructor(),
        _Projection(),
        _Dispatcher(),
        owner_id="runner-test",
        heartbeat_interval=0,
    )

    assert runner.run_once()
    assert brave.calls == 0
    assert orbits.get(orbit_id)["orbit"]["status"] == "BLOCKED"
