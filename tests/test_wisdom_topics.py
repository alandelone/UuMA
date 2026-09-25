from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from uuma.api import create_app
from uuma.knowledge_models import (
    BudgetTier,
    EvidenceRecord,
    OrbitStatus,
    SatisfactionLevel,
    SourceRecord,
)
from uuma.knowledge_service import KnowledgeService
from uuma.question_orbit import QuestionOrbitService
from uuma.settings import Settings
from uuma.wisdom_topics import TopicKnowledgeService, ensure_view_token, grounded_answer
from uuma.wisdom_view import create_wisdom_view_app


def resolve_approved(topics: TopicKnowledgeService, *args, **kwargs):
    """Existing-topic test fixtures model a prior explicit user approval."""
    return topics.resolve_question(*args, allow_new_topic=True, **kwargs)


def test_new_topic_requires_permission_but_existing_topic_reuses_without_it(tmp_path: Path):
    service = KnowledgeService(tmp_path / "wisdom.db")
    topics = TopicKnowledgeService(service)
    before = service.history()
    proposal = topics.resolve_question("scallion cultivation", actor_id="wisdom-oldman")
    assert proposal["requires_topic_approval"]
    assert proposal["proposed_topic"]["title"] == "scallion cultivation"
    assert topics.list_topics()["count"] == 0
    assert service.history() == before
    approved = resolve_approved(topics, "scallion cultivation", actor_id="wisdom-oldman")
    reused = topics.resolve_question("scallion cultivation", actor_id="wisdom-oldman")
    assert reused["topic"]["topic_id"] == approved["topic"]["topic_id"]
    assert topics.list_topics()["count"] == 1


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "uuma.db",
        artifact_dir=tmp_path / "artifacts",
        ingest_spool_dir=tmp_path / "spool",
        hermes_executable=tmp_path / "hermes.exe",
    )


def test_api_error_cannot_create_topic_and_uncited_answer_is_withheld(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path / "wisdom.db")
    topics = TopicKnowledgeService(service)
    with pytest.raises(ValueError, match="API error response"):
        resolve_approved(topics, '{"detail":"Wisdom topic not found"}', actor_id="wisdom-oldman")
    assert topics.list_topics()["count"] == 0
    answer = grounded_answer({
        "answer": "Sylvester comes from Latin.",
        "citations": [],
        "satisfaction_level": "PROVISIONAL",
    })
    assert "Sylvester" not in answer["answer"]
    assert answer["satisfaction_level"] == "INSUFFICIENT"


def test_status_reads_persisted_topic_and_cross_topic_parent_is_not_reused(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path / "wisdom.db")
    topics = TopicKnowledgeService(service)
    route = {"platform": "telegram", "session_id": "one"}
    first = resolve_approved(topics, "scallion cultivation", actor_id="wisdom-oldman", route=route)
    second = resolve_approved(topics, "quantum physics", actor_id="wisdom-oldman")
    related = resolve_approved(topics, "quantum physics experiments", actor_id="wisdom-oldman",
                                      route=route)
    assert related["topic"]["topic_id"] == second["topic"]["topic_id"]
    assert related["question"]["parent_question_id"] == second["question"]["question_id"]
    assert related["question"]["parent_question_id"] != first["question"]["question_id"]
    before = service.history()
    status = topics.conversation_status(route)
    assert status["topic_id"] == second["topic"]["topic_id"]
    assert status["tasks"] == []
    assert service.history() == before


def test_retraction_keeps_old_version_but_changes_visible_overview(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.ensure_directories()
    service = KnowledgeService(settings.knowledge_database_path())
    topics = TopicKnowledgeService(service)
    route = {"platform": "telegram", "chat_id": "one"}
    resolved = resolve_approved(topics, 
        "Invalid imported topic", actor_id="wisdom-oldman", route=route
    )
    topic_id = resolved["topic"]["topic_id"]
    topics.publish_answer(
        topic_id, resolved["question"]["question_id"],
        {"answer": "Unrelated old content", "citations": []},
        actor_id="wisdom-oldman", research_status="QUEUED",
    )
    topics.retract_invalid_topic(
        topic_id, actor_id="wisdom-oldman", reason="The topic came from an API error."
    )
    record = topics.get_topic(topic_id)
    assert record["topic"]["status"] == "ARCHIVED"
    assert record["document"]["current_version"] == 2
    assert "Unrelated old content" not in record["latest_version"]["body_markdown"]
    assert "no traceable citations" in record["versions"][1]["body_markdown"]
    page = TestClient(create_wisdom_view_app(settings)).get(
        f"/wisdom/topics/{topic_id}", params={"token": ensure_view_token(tmp_path)}
    )
    assert page.status_code == 200
    assert '<span id="overview"></span>' in page.text
    assert "Correction and retraction" in page.text
    next_topic = resolve_approved(topics, 
        "focus on scallions", actor_id="wisdom-oldman", route=route
    )
    assert next_topic["topic"]["topic_id"] != topic_id
    assert service.history()["chain_valid"]


def test_topic_continuity_survives_followup_and_new_chat(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path / "wisdom.db")
    topics = TopicKnowledgeService(service)
    first = resolve_approved(topics, 
        "我想了解种青葱",
        actor_id="wisdom-oldman",
        route={"platform": "telegram", "chat_id": "one"},
    )
    focus = resolve_approved(topics, 
        "重点是气雾培和分株",
        actor_id="wisdom-oldman",
        route={"platform": "telegram", "chat_id": "one"},
    )
    followup = resolve_approved(topics, 
        "make it more detail",
        actor_id="wisdom-oldman",
        route={"platform": "telegram", "chat_id": "one"},
    )
    cross_chat = resolve_approved(topics, 
        "青葱分株后怎么缓苗",
        actor_id="wisdom-oldman",
        route={"platform": "telegram", "chat_id": "two"},
    )

    assert focus["topic"]["topic_id"] == first["topic"]["topic_id"]
    assert focus["match_kind"] == "focus_question"
    assert followup["question"]["question_id"] == focus["question"]["question_id"]
    assert followup["match_kind"] == "same_question_followup"
    assert cross_chat["topic"]["topic_id"] == first["topic"]["topic_id"]
    assert cross_chat["question"]["question_id"] != first["question"]["question_id"]
    assert service.history()["chain_valid"]


def test_deep_preflight_reuses_topic_orbit_without_resetting_budget(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path / "wisdom.db")
    topics = TopicKnowledgeService(service)
    orbits = QuestionOrbitService(
        service,
        topics=topics,
        automatic_budget_tier=BudgetTier.DEEP,
    )
    route = {"platform": "telegram", "chat_id": "one"}
    root = resolve_approved(topics, "我想了解种青葱", actor_id="wisdom-oldman", route=route)
    answer = {
        "answer": "当前证据不足。",
        "citations": [],
        "conditions": [],
        "conflicts": [],
        "satisfaction_level": "PROVISIONAL",
        "satisfaction_rationale": "需要系统调查。",
        "remaining_gap_ids": [],
    }
    started = orbits.preflight(
        root["question"]["text"],
        answer,
        actor_id="wisdom-oldman",
        notification_route=route,
        topic_id=root["topic"]["topic_id"],
        question_id=root["question"]["question_id"],
    )
    focus = resolve_approved(topics, 
        "重点是气雾培和分株", actor_id="wisdom-oldman", route=route
    )
    reused = orbits.preflight(
        focus["question"]["text"],
        answer,
        actor_id="wisdom-oldman",
        notification_route=route,
        topic_id=focus["topic"]["topic_id"],
        question_id=focus["question"]["question_id"],
    )

    assert started["budget_tier"] == "DEEP"
    assert reused["orbit_id"] == started["orbit_id"]
    assert reused["orbit_reused"]
    state = orbits.get(started["orbit_id"])
    assert state["research_run"]["active_seconds"] == 0
    assert {item["question_id"] for item in state["frontier"]} == {
        root["question"]["question_id"],
        focus["question"]["question_id"],
    }


def test_topic_followup_does_not_reset_an_exhausted_budget(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path / "wisdom.db")
    topics = TopicKnowledgeService(service)
    orbits = QuestionOrbitService(
        service,
        topics=topics,
        automatic_budget_tier=BudgetTier.DEEP,
    )
    route = {"platform": "telegram", "chat_id": "one"}
    root = resolve_approved(topics, "我想了解种青葱", actor_id="wisdom-oldman", route=route)
    answer = {
        "answer": "当前证据不足。",
        "citations": [],
        "conditions": [],
        "conflicts": [],
        "satisfaction_level": "PROVISIONAL",
        "satisfaction_rationale": "需要系统调查。",
        "remaining_gap_ids": [],
    }
    started = orbits.preflight(
        root["question"]["text"],
        answer,
        actor_id="wisdom-oldman",
        notification_route=route,
        topic_id=root["topic"]["topic_id"],
        question_id=root["question"]["question_id"],
    )
    cycle = orbits.acquire_cycle("runner", actor_id="wisdom-oldman")
    assert cycle is not None
    completed = orbits.complete_cycle(
        cycle["orbit_cycle_id"],
        "runner",
        satisfaction_level=SatisfactionLevel.PROVISIONAL,
        satisfaction_rationale="More research remains.",
        active_seconds=21_600,
        actor_id="wisdom-oldman",
    )
    assert completed["orbit"]["status"] == "BUDGET_EXHAUSTED"

    focus = resolve_approved(topics, 
        "重点是气雾培和分株", actor_id="wisdom-oldman", route=route
    )
    reused = orbits.preflight(
        focus["question"]["text"],
        answer,
        actor_id="wisdom-oldman",
        notification_route=route,
        topic_id=focus["topic"]["topic_id"],
        question_id=focus["question"]["question_id"],
    )

    assert reused["orbit_id"] == started["orbit_id"]
    assert reused["orbit_status"] == "BUDGET_EXHAUSTED"
    state = orbits.get(started["orbit_id"])
    assert state["research_run"]["active_seconds"] == 21_600


def test_topic_followup_preserves_user_stop(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path / "wisdom.db")
    topics = TopicKnowledgeService(service)
    orbits = QuestionOrbitService(service, topics=topics)
    route = {"platform": "telegram", "chat_id": "one"}
    root = resolve_approved(topics, "我想了解种青葱", actor_id="wisdom-oldman", route=route)
    answer = {
        "answer": "当前证据不足。",
        "citations": [],
        "conditions": [],
        "conflicts": [],
        "satisfaction_level": "PROVISIONAL",
        "satisfaction_rationale": "需要系统调查。",
        "remaining_gap_ids": [],
    }
    started = orbits.preflight(
        root["question"]["text"],
        answer,
        actor_id="wisdom-oldman",
        notification_route=route,
        topic_id=root["topic"]["topic_id"],
        question_id=root["question"]["question_id"],
    )
    orbits.transition(
        started["orbit_id"],
        OrbitStatus.STOPPED,
        actor_id="wisdom-oldman",
        reason="Stopped by user.",
    )

    focus = resolve_approved(topics, "重点是分株", actor_id="wisdom-oldman", route=route)
    reused = orbits.preflight(
        focus["question"]["text"],
        answer,
        actor_id="wisdom-oldman",
        notification_route=route,
        topic_id=focus["topic"]["topic_id"],
        question_id=focus["question"]["question_id"],
    )

    assert reused["orbit_id"] == started["orbit_id"]
    assert reused["orbit_status"] == "STOPPED"


def test_broad_topic_framework_creates_distinct_research_branches(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path / "wisdom.db")
    topics = TopicKnowledgeService(service)
    resolved = resolve_approved(topics, "我想了解种青葱", actor_id="wisdom-oldman")

    gaps = topics.ensure_research_framework(
        resolved["topic"]["topic_id"],
        resolved["question"]["question_id"],
        actor_id="wisdom-oldman",
    )
    repeated = topics.ensure_research_framework(
        resolved["topic"]["topic_id"],
        resolved["question"]["question_id"],
        actor_id="wisdom-oldman",
    )

    assert len(gaps) == 5
    assert repeated == gaps
    topic = topics.get_topic(resolved["topic"]["topic_id"])
    subquestions = [
        item for item in topic["questions"] if item["link"]["relationship"] == "SUBQUESTION"
    ]
    assert len(subquestions) == 5
    assert topics.is_broad_topic_request("关于青葱栽培")
    assert not topics.is_broad_topic_request("青葱分株后如何缓苗？")


def test_cycle_publishes_traceable_version_and_digest_notification(tmp_path: Path) -> None:
    service = KnowledgeService(tmp_path / "wisdom.db")
    topics = TopicKnowledgeService(service, view_token="read-token")
    resolved = resolve_approved(topics, 
        "我想了解种青葱",
        actor_id="wisdom-oldman",
        route={"platform": "telegram", "chat_id": "one"},
    )
    source = service.add_source(
        SourceRecord(locator="https://example.test/scallion", title="Scallion guide"),
        actor_id="wisdom-oldman",
    )
    evidence = service.add_evidence(
        EvidenceRecord(
            source_id=source["source_id"],
            excerpt="Division propagation requires a healthy basal plate.",
            location="section 2",
        ),
        actor_id="wisdom-oldman",
    )
    orbits = QuestionOrbitService(service, topics=topics)
    started = orbits.preflight(
        resolved["question"]["text"],
        {
            "answer": "先给当前答案。",
            "satisfaction_level": "PROVISIONAL",
            "satisfaction_rationale": "还需要证据。",
            "remaining_gap_ids": [],
        },
        actor_id="wisdom-oldman",
        topic_id=resolved["topic"]["topic_id"],
        question_id=resolved["question"]["question_id"],
        notification_route={"platform": "telegram", "chat_id": "one"},
    )
    cycle = orbits.acquire_cycle("runner")
    assert cycle is not None
    answer = {
        "answer": "分株时应保留健康茎盘，具体修根长度仍需按品种验证。",
        "citations": [
            {
                "source_id": source["source_id"],
                "evidence_id": evidence["evidence_id"],
                "locator": source["locator"],
                "location": evidence["location"],
            }
        ],
        "conditions": ["适用于具有完整茎盘的健康母株"],
        "conflicts": [],
        "satisfaction_level": "PROVISIONAL",
        "satisfaction_rationale": "仍缺少品种和环境条件数据。",
        "remaining_gap_ids": [],
    }
    completed = orbits.complete_cycle(
        cycle["orbit_cycle_id"],
        "runner",
        satisfaction_level=SatisfactionLevel.PROVISIONAL,
        satisfaction_rationale=answer["satisfaction_rationale"],
        active_seconds=1,
        source_ids=[source["source_id"]],
        evidence_ids=[evidence["evidence_id"]],
        answer=answer,
    )

    version = completed["document_version"]
    assert version["version"] == 1
    assert "https://example.test/scallion" in version["body_markdown"]
    assert version["document_url"].endswith("#overview")
    graph = topics.graph(resolved["topic"]["topic_id"])
    assert any(node["id"] == source["source_id"] for node in graph["nodes"])
    notification = orbits.claim_notification(actor_id="orchestrator")
    assert notification is not None
    assert notification["payload"]["summary"].startswith("分株时")
    assert notification["payload"]["document_url"] == version["document_url"]
    assert started["orbit_id"] == completed["orbit"]["orbit_id"]


def test_local_topic_page_requires_independent_read_token(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.ensure_directories()
    service = KnowledgeService(settings.knowledge_database_path())
    topics = TopicKnowledgeService(service)
    resolved = resolve_approved(topics, "青葱栽培", actor_id="wisdom-oldman")
    topics.publish_answer(
        resolved["topic"]["topic_id"],
        resolved["question"]["question_id"],
        {
            "answer": "这是主题正文。",
            "citations": [],
            "conditions": [],
            "conflicts": [],
            "satisfaction_rationale": "初步版本。",
        },
        actor_id="wisdom-oldman",
        research_status="QUEUED",
    )
    client = TestClient(create_app(settings))
    token = ensure_view_token(tmp_path)
    path = f"/wisdom/topics/{resolved['topic']['topic_id']}"

    assert client.get(path).status_code == 403
    page = client.get(path, params={"token": token})
    assert page.status_code == 200
    assert "No relevant, traceable evidence" in page.text
    graph = client.get(f"/wisdom/api/topics/{resolved['topic']['topic_id']}/graph",
                       params={"token": token})
    assert graph.status_code == 200
    assert graph.json()["topic_id"] == resolved["topic"]["topic_id"]

    read_only_client = TestClient(create_wisdom_view_app(settings))
    assert read_only_client.get("/health").json()["service"] == "wisdom-view"
    assert read_only_client.get(path).status_code == 403
    assert read_only_client.get(path, params={"token": token}).status_code == 200
    assert read_only_client.post(path, params={"token": token}).status_code == 405
    escaped_path = path.replace("_", "%5C_")
    repaired = read_only_client.get(
        escaped_path, params={"token": token.replace("_", "\\_")}
    )
    assert repaired.status_code == 200
    assert repaired.history[0].status_code == 307
    assert read_only_client.get(
        escaped_path, params={"token": "invalid\\_token"}
    ).status_code == 403
    generated_url = TopicKnowledgeService(service, view_token="test_token").topic_url(
        resolved["topic"]["topic_id"]
    )
    assert "_" not in generated_url
    assert "%5F" in generated_url
