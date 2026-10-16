"""Unit and contract tests for AdaptiveResearchPlanner and Deep Research async ingestion."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from uuma.knowledge_construction import KnowledgeConstructor
from uuma.knowledge_ingest import KnowledgeIngestor
from uuma.knowledge_models import GapRecord, GapType, SatisfactionLevel
from uuma.knowledge_service import KnowledgeService
from uuma.orbit_discovery import (
    DiscoveryArtifact,
    DiscoveryResponse,
    artifact_is_relevant,
)
from uuma.orbit_planner import (
    AdaptiveResearchPlanner,
    reformulate_queries,
)
from uuma.question_orbit import QuestionOrbitService
from uuma.safe_web import RetryAfterError


def test_reformulate_queries_generates_domain_synonyms_and_strips_noise():
    q = "针对 青葱 的气雾培细节与喷雾参数是什么？"
    reformulated = reformulate_queries(q)
    assert any("Allium fistulosum" in query for query in reformulated)
    assert any("aeroponics" in query or "fogponics" in query for query in reformulated)
    # Conversational filler stripped
    for query in reformulated:
        assert "针对" not in query
        assert "是什么" not in query


class _MockProvider:
    def __init__(self, name: str, artifacts: list[DiscoveryArtifact] | None = None, fail: bool = False, retry: int | None = None) -> None:
        self.name = name
        self.artifacts = artifacts or []
        self.fail = fail
        self.retry = retry
        self.queries_received: list[str] = []

    def discover(self, query: str, *, limit: int = 5, **kwargs) -> DiscoveryResponse:
        self.queries_received.append(query)
        if self.retry:
            raise RetryAfterError(f"{self.name} rate limited", self.retry)
        if self.fail:
            raise RuntimeError(f"{self.name} failed")
        return DiscoveryResponse(self.artifacts[:limit], request_id=f"req_{self.name}")


def test_planner_multi_tier_escalation_flow():
    # Tier 1 fails, Tier 2 succeeds
    scholarly = _MockProvider("openalex", artifacts=[])
    web = _MockProvider(
        "ddgs",
        artifacts=[DiscoveryArtifact("https://example.com/scallion-doc", "青葱气雾栽培试验研究", "ddgs")],
    )
    chatgpt = _MockProvider("chatgpt-bridge", artifacts=[])

    planner = AdaptiveResearchPlanner([scholarly, web, chatgpt])
    artifacts, traces, pending_req = planner.execute_discovery("青葱气雾培参数", limit=5)

    assert len(artifacts) == 1
    assert artifacts[0].locator == "https://example.com/scallion-doc"
    assert pending_req is None

    # Check white-box trace
    tiers_attempted = [t.tier for t in traces]
    assert 1 in tiers_attempted
    assert 2 in tiers_attempted
    # Tier 2 found results, so Tier 3 did not need to run
    assert 3 not in tiers_attempted


def test_planner_escalates_to_chatgpt_when_scholarly_and_web_empty():
    scholarly = _MockProvider("openalex", artifacts=[])
    web = _MockProvider("ddgs", artifacts=[])
    chatgpt = _MockProvider(
        "chatgpt-bridge",
        artifacts=[DiscoveryArtifact("https://example.com/cgpt-ref", "青葱气雾培研究专报", "chatgpt-bridge")],
    )

    planner = AdaptiveResearchPlanner([scholarly, web, chatgpt])
    artifacts, traces, _pending_req = planner.execute_discovery("青葱气雾培参数", limit=5)

    assert len(artifacts) == 1
    assert artifacts[0].locator == "https://example.com/cgpt-ref"
    tiers_attempted = [t.tier for t in traces]
    assert 1 in tiers_attempted
    assert 2 in tiers_attempted
    assert 3 in tiers_attempted


def test_planner_async_deep_research_pending_and_retrieval():
    class _MockChatGptAsync:
        name = "chatgpt-bridge"
        mode = "deep_research"

        def __init__(self) -> None:
            self.status_calls = 0

        def check_status(self, request_id: str, *, token: str | None = None) -> dict[str, Any] | None:
            self.status_calls += 1
            if self.status_calls == 1:
                return {"id": request_id, "status": "RUNNING"}
            return {
                "id": request_id,
                "status": "COMPLETED",
                "result": {
                    "answer": "# 青葱气雾栽培深度研究报告\n\n气雾栽培喷雾周期应控制在每5分钟喷雾15秒...",
                    "citations": [{"title": "葱类气雾研究", "url": "https://example.com/scallion-ref"}],
                },
            }

        def discover(self, query: str, *, limit: int = 5, pending_request_id: str | None = None, mode: str = "search") -> DiscoveryResponse:
            if pending_request_id:
                state = self.check_status(pending_request_id)
                if state.get("status") != "COMPLETED":
                    return DiscoveryResponse([], request_id=pending_request_id, in_progress=True)
                # Parse completed report
                res = state["result"]
                report = DiscoveryArtifact(
                    locator=f"chatgpt://reports/{pending_request_id}",
                    title="ChatGPT Deep Research Report: 青葱气雾栽培",
                    provider=self.name,
                    snippet=res["answer"][:300],
                    metadata={"is_report": True, "full_text": res["answer"]},
                )
                return DiscoveryResponse([report], request_id=pending_request_id, in_progress=False)
            return DiscoveryResponse([], request_id="cgpt_async_999", in_progress=True)

    chatgpt = _MockChatGptAsync()
    planner = AdaptiveResearchPlanner([chatgpt])

    # Round 1: Initiate Deep Research (returns in_progress=True)
    artifacts_1, traces_1, pending_req_1 = planner.execute_discovery(
        "青葱气雾栽培细节", deep_research_allowed=True
    )
    assert artifacts_1 == []
    assert pending_req_1 == "cgpt_async_999"
    assert any(t.status == "IN_PROGRESS" for t in traces_1)

    # Round 2: Poll pending request (still running)
    artifacts_2, _traces_2, pending_req_2 = planner.execute_discovery(
        "青葱气雾栽培细节", pending_request_id=pending_req_1, deep_research_allowed=True
    )
    assert artifacts_2 == []
    assert pending_req_2 == "cgpt_async_999"

    # Round 3: Poll pending request (completed and report retrieved)
    artifacts_3, traces_3, pending_req_3 = planner.execute_discovery(
        "青葱气雾栽培细节", pending_request_id=pending_req_2, deep_research_allowed=True
    )
    assert len(artifacts_3) == 1
    assert artifacts_3[0].metadata["is_report"] is True
    assert "气雾栽培喷雾周期" in artifacts_3[0].metadata["full_text"]
    assert pending_req_3 is None
    assert any(t.status == "SUCCESS" for t in traces_3)


def test_deep_research_report_ingestion_and_claim_extraction(tmp_path: Path):
    db_path = tmp_path / "wisdom.db"
    service = KnowledgeService(db_path)
    content_dir = tmp_path / "content"
    ingestor = KnowledgeIngestor(service, content_dir)

    class _MockBackend:
        def health(self):
            return {"ready": True}

        def extract(self, chunks: list[dict[str, Any]], **kwargs):
            return {
                "chunks": [
                    {
                        "chunk_id": chunk["chunk_id"],
                        "entities": [
                            {"source_ref": "ent_scallion", "name": "青葱", "entity_type": "Plant"},
                            {"source_ref": "ent_param", "name": "5分钟喷雾15秒", "entity_type": "Parameter"},
                        ],
                        "relations": [
                            {
                                "source_ref": "ent_scallion",
                                "predicate": "适宜喷雾间隔",
                                "target_ref": "ent_param",
                            }
                        ],
                    }
                    for chunk in chunks
                ]
            }

    constructor = KnowledgeConstructor(service, _MockBackend())

    report_text = (
        "# 青葱气雾栽培深度报告\n\n"
        "气雾栽培喷雾周期应控制在每5分钟喷雾15秒，以保证根系透气与湿度平衡。"
    )
    artifact = DiscoveryArtifact(
        locator="chatgpt://reports/cgpt_async_999",
        title="ChatGPT Deep Research Report: 青葱气雾栽培",
        provider="chatgpt-bridge",
        snippet=report_text[:100],
        metadata={"is_report": True, "full_text": report_text},
    )

    assert artifact_is_relevant("青葱气雾栽培", artifact)

    from uuma.knowledge_models import SourceType
    ingested = ingestor.ingest_text(
        locator=artifact.locator,
        title=artifact.title,
        text=artifact.metadata["full_text"],
        media_type="text/markdown",
        source_type=SourceType.OTHER,
        actor_id="wisdom-oldman",
        metadata=artifact.metadata,
    )

    assert ingested["source"]["source_id"] is not None
    assert len(ingested["chunks"]) >= 1

    extracted = constructor.extract_document(
        ingested["document"]["document_id"],
        actor_id="wisdom-oldman",
        max_chunks=10,
    )
    assert extracted["chunks_processed"] >= 1

    claims = service.list_records("claim")["records"]
    assert len(claims) >= 1
    assert claims[0]["status"] == "CANDIDATE"
    assert "适宜喷雾间隔" in claims[0]["statement"]


def test_question_orbit_status_exposes_attempted_routes(tmp_path: Path):
    db_path = tmp_path / "wisdom.db"
    service = KnowledgeService(db_path)
    gap = service.add_gap(
        GapRecord(
            gap_type=GapType.COVERAGE,
            reason="Unresolved scallion mist parameter",
            why_worthwhile="Needed for commercial aeroponics",
        ),
        actor_id="wisdom-oldman",
    )
    orbits = QuestionOrbitService(service)
    started = orbits.start(
        "青葱气雾培的喷雾间隔是多少？",
        "Resolve aeroponic mist interval.",
        SatisfactionLevel.PROVISIONAL,
        "Needs experimental data.",
        actor_id="wisdom-oldman",
        gap_ids=[gap["gap_id"]],
    )
    orbit_id = started["orbit"]["orbit_id"]

    orbits.record_discovery_usage(
        orbit_id, "openalex", result_count=0, provider_request_id="req_alex_1"
    )
    orbits.record_discovery_usage(
        orbit_id, "ddgs", result_count=2, provider_request_id="req_ddgs_2"
    )

    status = orbits.get(orbit_id)
    assert "attempted_routes" in status
    assert len(status["attempted_routes"]) == 2
    assert status["attempted_routes"][0]["provider"] == "ddgs"
    assert status["attempted_routes"][0]["results"] == 2
    assert status["attempted_routes"][1]["provider"] == "openalex"
    assert status["attempted_routes"][1]["results"] == 0


def test_compute_cycle_explanation_structure_and_dynamic_untried_paths():
    p1 = _MockProvider("openalex", artifacts=[])
    # 5 artifacts satisfies discovery capacity so subsequent web provider (brave) and chatgpt are untried
    p2 = _MockProvider(
        "ddgs",
        artifacts=[DiscoveryArtifact(f"https://example.com/{i}", f"Test {i}", "ddgs") for i in range(5)],
    )
    p3 = _MockProvider("brave", artifacts=[])
    p4 = _MockProvider("chatgpt-bridge", artifacts=[])

    planner = AdaptiveResearchPlanner([p1, p2, p3, p4])
    _artifacts, traces, _ = planner.execute_discovery("青葱气雾栽培", limit=5)
    explanation = planner.compute_cycle_explanation("青葱气雾栽培", traces, status="ACTIVE")

    assert explanation.status == "ACTIVE"
    assert len(explanation.attempts) >= 2
    # p1 should be NO_MATCH, p2 should be SUCCESS
    p1_attempt = next(a for a in explanation.attempts if a.provider == "openalex")
    assert p1_attempt.outcome == "NO_MATCH"
    assert p1_attempt.duration_ms >= 0

    p2_attempt = next(a for a in explanation.attempts if a.provider == "ddgs")
    assert p2_attempt.outcome == "SUCCESS"
    assert p2_attempt.artifacts_found == 5

    # Untried paths should dynamically include brave and chatgpt-bridge since search satisfied at p2
    assert "brave" in explanation.untried_paths
    assert "chatgpt-bridge" in explanation.untried_paths
    assert "下阶段将调度待探索途径" in explanation.next_step


def test_whitebox_notification_message_formatting():
    from uuma.orbit_discovery import CycleExplanation, DiscoveryAttempt, DiscoveryOutcome
    from uuma.orbit_runner import OrbitNotificationDispatcher

    exp = CycleExplanation(
        status="ACTIVE",
        summary="本轮共执行 2 次检索尝试（0 次成功，1 次无直接匹配，1 次受阻）。",
        attempts=[
            DiscoveryAttempt(
                tier=1,
                provider="openalex",
                query="Allium fistulosum aeroponics",
                outcome=DiscoveryOutcome.NO_MATCH,
                artifacts_found=0,
                duration_ms=120.5,
            ),
            DiscoveryAttempt(
                tier=2,
                provider="brave",
                query="青葱 气雾培 喷雾间隔",
                outcome=DiscoveryOutcome.BUDGET_REACHED,
                artifacts_found=0,
                error_detail="Monthly limit reached",
                duration_ms=45.0,
            ),
        ],
        untried_paths=["ddgs", "chatgpt-bridge"],
        blocked_paths=["brave"],
        next_step="下阶段将调度待探索途径（ddgs 等）继续深入挖掘。",
    )

    notification = {
        "event_type": "ORBIT_UPDATE",
        "payload": {
            "topic_title": "青葱气雾栽培",
            "research_status": "ACTIVE",
            "summary": "初步发现需要保持喷雾周期在10-15分钟。",
            "cycle_explanation": exp.to_dict(),
        },
    }

    rendered = OrbitNotificationDispatcher._message(notification)
    # Tri-part structure check
    assert "Wisdom-Oldman 研究更新｜青葱气雾栽培" in rendered
    assert "🔍 本轮检索链路（白盒追踪）：" in rendered
    assert "[- [NO_MATCH] openalex" in rendered or "[NO_MATCH] openalex" in rendered
    assert "未检索到匹配公开文献" in rendered
    assert "[BUDGET_REACHED] brave：Monthly limit reached" in rendered
    assert "⏳ 待探索途径：ddgs, chatgpt-bridge" in rendered
    assert "下一步：下阶段将调度待探索途径（ddgs 等）继续深入挖掘。" in rendered


def test_guard_rules_prevent_premature_pause_when_untried_paths_exist(tmp_path: Path):
    from uuma.orbit_discovery import CycleExplanation, DiscoveryAttempt, DiscoveryOutcome

    db_path = tmp_path / "wisdom.db"
    service = KnowledgeService(db_path)
    gap = service.add_gap(
        GapRecord(
            gap_type=GapType.WEAK_EVIDENCE,
            reason="Investigate transplant acclimation.",
            why_worthwhile="Experimental data needed.",
        ),
        actor_id="wisdom-oldman",
    )
    orbits = QuestionOrbitService(service)
    _ = orbits.start(
        "青葱气雾培分株缓苗期？",
        "Investigate transplant acclimation.",
        SatisfactionLevel.PROVISIONAL,
        "Needs experimental data.",
        actor_id="wisdom-oldman",
        gap_ids=[gap["gap_id"]],
    )

    # Acquire cycle
    cycle = orbits.acquire_cycle("test-runner")
    assert cycle is not None

    # Complete cycle with no_new_source=True, but untried_paths exist!
    exp = CycleExplanation(
        status="ACTIVE",
        summary="未找到新来源，但仍有途径未探索",
        attempts=[
            DiscoveryAttempt(
                tier=1, provider="openalex", query="q", outcome=DiscoveryOutcome.NO_MATCH, duration_ms=10.0
            )
        ],
        untried_paths=["ddgs", "chatgpt-bridge"],
        blocked_paths=[],
        next_step="继续探索 ddgs",
    )

    completion = orbits.complete_cycle(
        cycle["orbit_cycle_id"],
        "test-runner",
        satisfaction_level=SatisfactionLevel.PROVISIONAL,
        satisfaction_rationale="More evidence needed",
        active_seconds=2.0,
        no_new_source=True,
        cycle_explanation=exp.to_dict(),
        discovery_attempts=[a.to_dict() for a in exp.attempts],
    )

    # Rule 2: Must NOT prematurely pause! Must remain QUEUED (run is ACTIVE).
    assert completion["orbit"]["status"] == "QUEUED"
    assert completion["research_run"]["status"] == "ACTIVE"
    # Check that explanation is persisted into cycle and run
    stored_cycle = service._require("orbit_cycles", cycle["orbit_cycle_id"])
    assert "cycle_explanation" in stored_cycle
    assert stored_cycle["cycle_explanation"]["untried_paths"] == ["ddgs", "chatgpt-bridge"]
    assert len(stored_cycle["discovery_attempts"]) == 1

    stored_run = service._require("research_runs", completion["research_run"]["research_run_id"])
    assert "latest_cycle_explanation" in stored_run
    assert stored_run["latest_cycle_explanation"]["untried_paths"] == ["ddgs", "chatgpt-bridge"]


def test_guard_rule_blocked_when_all_providers_auth_or_budget_exhausted(tmp_path: Path):
    from uuma.orbit_discovery import CycleExplanation, DiscoveryAttempt, DiscoveryOutcome

    db_path = tmp_path / "wisdom.db"
    service = KnowledgeService(db_path)
    gap = service.add_gap(
        GapRecord(
            gap_type=GapType.WEAK_EVIDENCE,
            reason="Investigate nozzle models.",
            why_worthwhile="Catalog data needed.",
        ),
        actor_id="wisdom-oldman",
    )
    orbits = QuestionOrbitService(service)
    _ = orbits.start(
        "青葱气雾培专用喷头？",
        "Investigate nozzle models.",
        SatisfactionLevel.PROVISIONAL,
        "Needs catalog data.",
        actor_id="wisdom-oldman",
        gap_ids=[gap["gap_id"]],
    )

    cycle = orbits.acquire_cycle("test-runner")
    assert cycle is not None

    exp = CycleExplanation(
        status="BLOCKED",
        summary="所有途径均受限",
        attempts=[
            DiscoveryAttempt(
                tier=1, provider="brave", query="q", outcome=DiscoveryOutcome.BUDGET_REACHED, duration_ms=10.0
            ),
            DiscoveryAttempt(
                tier=2, provider="chatgpt-bridge", query="q", outcome=DiscoveryOutcome.AUTH_REQUIRED, duration_ms=10.0
            ),
        ],
        untried_paths=[],
        blocked_paths=["brave", "chatgpt-bridge"],
        next_step="等待配置凭据或配额重置",
    )

    completion = orbits.complete_cycle(
        cycle["orbit_cycle_id"],
        "test-runner",
        satisfaction_level=SatisfactionLevel.PROVISIONAL,
        satisfaction_rationale="Blocked on provider quota",
        active_seconds=2.0,
        no_new_source=True,
        cycle_explanation=exp.to_dict(),
        discovery_attempts=[a.to_dict() for a in exp.attempts],
    )

    # Rule 3: Must transition to BLOCKED (not PAUSED)
    assert completion["orbit"]["status"] == "BLOCKED"
    assert "All available discovery providers are blocked" in completion["orbit"]["stop_reason"]


def test_observatory_adapter_surfaces_whitebox_explanation(tmp_path: Path):
    from uuma.observatory.adapters.wisdom import WisdomAdapter
    from uuma.orbit_discovery import CycleExplanation, DiscoveryAttempt, DiscoveryOutcome
    from uuma.wisdom_topics import TopicKnowledgeService

    db_path = tmp_path / "wisdom.db"
    service = KnowledgeService(db_path)
    topics = TopicKnowledgeService(service)
    res = topics.resolve_question("青葱气雾培试验", actor_id="wisdom-oldman", allow_new_topic=True)
    topic_id = res["topic"]["topic_id"]

    gap = service.add_gap(
        GapRecord(
            gap_type=GapType.WEAK_EVIDENCE,
            reason="Research parameter",
            why_worthwhile="Needed for aeroponics",
        ),
        actor_id="wisdom-oldman",
    )

    orbits = QuestionOrbitService(service, topics=topics)
    _ = orbits.start(
        "青葱气雾培参数",
        "Objective",
        SatisfactionLevel.PROVISIONAL,
        "Rationale",
        topic_id=topic_id,
        gap_ids=[gap["gap_id"]],
        actor_id="wisdom-oldman",
    )
    cycle = orbits.acquire_cycle("test-runner")
    assert cycle is not None

    exp = CycleExplanation(
        status="ACTIVE",
        summary="完成 1 次检索",
        attempts=[
            DiscoveryAttempt(
                tier=1, provider="ddgs", query="青葱气雾培", outcome=DiscoveryOutcome.SUCCESS,
                artifacts_found=2, duration_ms=200.0,
            )
        ],
        untried_paths=["chatgpt-bridge"],
        blocked_paths=[],
        next_step="继续探索",
    )

    orbits.complete_cycle(
        cycle["orbit_cycle_id"],
        "test-runner",
        satisfaction_level=SatisfactionLevel.PROVISIONAL,
        satisfaction_rationale="Needs more",
        active_seconds=1.0,
        cycle_explanation=exp.to_dict(),
        discovery_attempts=[a.to_dict() for a in exp.attempts],
    )

    adapter = WisdomAdapter(data_dir=tmp_path, knowledge_path=db_path)
    items = adapter.list_items()
    topic_item = next((it for it in items if it.item_id == f"wisdom_topic_{topic_id}"), None)
    assert topic_item is not None
    assert topic_item.payload.get("cycle_explanation") is not None
    assert topic_item.payload["cycle_explanation"]["untried_paths"] == ["chatgpt-bridge"]
    assert topic_item.payload["orbit_info"]["status"] == "QUEUED"

