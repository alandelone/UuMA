from __future__ import annotations

from unittest.mock import Mock

import pytest

from uuma import knowledge_runtime as runtime
from uuma.kag_adapter import KagRuntimeManager, KagUnavailableError


def test_readiness_reads_correct_project_schema_and_graph_even_when_empty(monkeypatch):
    request = Mock(side_effect=[
        {"ready": True, "project_id": "2", "host_addr": "http://127.0.0.1:8887"},
        [{"id": 2, "namespace": "ScholarFieldKG"}],
        {"spgTypes": [{"basicInfo": {"name": {
            "namespace": "ScholarFieldKG", "nameEn": "FieldKnowledgeObject",
        }}}]},
        [],
    ])
    monkeypatch.setattr(runtime, "_request", request)
    manager = KagRuntimeManager("http://127.0.0.1:8892")
    runtime._probe(manager, "ScholarFieldKG", "2", "FieldKnowledgeObject")
    assert request.call_args.args[1]["projectId"] == 2
    assert request.call_args.args[1]["spgType"] == "ScholarFieldKG.FieldKnowledgeObject"


@pytest.mark.parametrize("responses", [
    [{"ready": True, "project_id": 1}],
    [{"ready": True, "project_id": 2, "host_addr": "http://127.0.0.1:8887"},
     [{"id": 2, "namespace": "Uuma"}]],
    [{"ready": True, "project_id": 2, "host_addr": "http://127.0.0.1:8887"},
     [{"id": 2, "namespace": "ScholarFieldKG"}], {"spgTypes": []}],
])
def test_live_bridge_cannot_hide_wrong_project_or_missing_schema(monkeypatch, responses):
    monkeypatch.setattr(runtime, "_request", Mock(side_effect=responses))
    with pytest.raises(KagUnavailableError):
        runtime._probe(KagRuntimeManager("http://127.0.0.1:8892"),
                       "ScholarFieldKG", "2", "FieldKnowledgeObject")


def test_failed_storage_read_is_blocked_without_recovery(monkeypatch):
    manager = KagRuntimeManager("http://127.0.0.1:8892")
    monkeypatch.setattr(runtime, "_configuration", lambda _: (manager, "ScholarFieldKG", "2", "K"))
    monkeypatch.setattr(runtime, "_probe", Mock(side_effect=OSError("graph offline")))
    assert runtime.ensure_knowledge_graph("scholar", recover=False)["status"] == "BLOCKED"


def test_recovery_is_verified_again_and_does_not_create_a_graph(monkeypatch, tmp_path):
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}")
    manager = KagRuntimeManager("http://127.0.0.1:8892", compose_file=compose)
    recover = Mock(return_value={"ready": True})
    monkeypatch.setattr(manager, "_recover_locked", recover)
    monkeypatch.setattr(runtime, "_configuration", lambda _: (manager, "ScholarFieldKG", "2", "K"))
    probe = Mock(side_effect=[OSError("offline"), None])
    monkeypatch.setattr(runtime, "_probe", probe)
    assert runtime.ensure_knowledge_graph("scholar") == {
        "ready": True, "graph": "ScholarFieldKG", "recovered": True,
    }
    assert probe.call_count == 2
    recover.assert_called_once_with(compose)


def test_unrelated_profile_cannot_start_graph_services():
    with pytest.raises(PermissionError):
        runtime.ensure_knowledge_graph("forge-lab-bot")


def test_worker_refuses_completed_result_when_graph_unavailable(monkeypatch):
    from uuma import mcp_worker
    monkeypatch.setenv("UUMA_AGENT_ID", "scholar")
    monkeypatch.setattr(mcp_worker, "ensure_knowledge_graph", lambda *a, **kw: {"ready": False})
    control = Mock()
    monkeypatch.setattr(mcp_worker, "_control_plane", lambda: control)
    with pytest.raises(RuntimeError, match="not COMPLETED"):
        mcp_worker.submit_result(
            '{"run_id":"r","task_id":"t","agent_id":"scholar",'
            '"outcome":"COMPLETED","summary":"unsupported completion"}'
        )
    control.submit_result.assert_not_called()


def test_wisdom_does_not_start_orbit_from_degraded_answer(monkeypatch):
    from uuma import mcp_knowledge
    monkeypatch.setenv("UUMA_AGENT_ID", "wisdom-oldman")
    monkeypatch.setenv("UUMA_QUESTION_ORBIT_ENABLED", "true")
    topics = Mock()
    topics.resolve_question.return_value = {"requires_topic_approval": False}
    monkeypatch.setattr(mcp_knowledge, "_topics", lambda: topics)
    monkeypatch.setattr(mcp_knowledge, "ensure_knowledge_graph", lambda *a, **k: {"ready": True})
    monkeypatch.setattr(mcp_knowledge, "_reasoner", lambda: Mock(
        answer=Mock(return_value={"runtime_status": "DEGRADED_KAG"})
    ))
    orbits = Mock()
    monkeypatch.setattr(mcp_knowledge, "_orbits", orbits)
    with pytest.raises(KagUnavailableError, match="no fallback"):
        mcp_knowledge.knowledge_question_preflight("What is known?", intent="research")
    orbits.assert_not_called()


def test_wisdom_rejects_pasted_api_error_before_graph_or_topic_work(monkeypatch):
    from uuma import mcp_knowledge

    monkeypatch.setenv("UUMA_AGENT_ID", "wisdom-oldman")
    graph = Mock()
    topics = Mock()
    topics.conversation_status.return_value = {"tasks": [], "status": "NO_CONTEXT"}
    monkeypatch.setattr(mcp_knowledge, "ensure_knowledge_graph", graph)
    monkeypatch.setattr(mcp_knowledge, "_topics", lambda: topics)
    result = mcp_knowledge.knowledge_question_preflight('{"detail":"Wisdom topic not found"}')
    assert result["message_intent"] == "feedback"
    assert result["knowledge_mutated"] is False
    graph.assert_not_called()
    topics.resolve_question.assert_not_called()


@pytest.mark.parametrize("message,intent,expected", [
    ("how is your progress?", "auto", "status"),
    ("how is your progress?", "research", "status"),
    ("研究进度？", "auto", "status"),
    ("This page is wrong, why?", "auto", "auto"),
    ("我想了解种青葱", "auto", "auto"),
    ("The citations are unrelated", "feedback", "feedback"),
])
def test_intake_has_no_knowledge_side_effects(monkeypatch, tmp_path, message, intent, expected):
    from uuma import mcp_knowledge
    from uuma.knowledge_service import KnowledgeService
    from uuma.wisdom_topics import TopicKnowledgeService

    service = KnowledgeService(tmp_path / "wisdom.db")
    topics = TopicKnowledgeService(service)
    monkeypatch.setenv("UUMA_AGENT_ID", "wisdom-oldman")
    monkeypatch.setattr(mcp_knowledge, "_topics", lambda: topics)
    graph, reasoner, orbits = Mock(), Mock(), Mock()
    monkeypatch.setattr(mcp_knowledge, "ensure_knowledge_graph", graph)
    monkeypatch.setattr(mcp_knowledge, "_reasoner", reasoner)
    monkeypatch.setattr(mcp_knowledge, "_orbits", orbits)
    before = service.history()
    result = mcp_knowledge.knowledge_question_preflight(message, intent=intent)
    assert result["message_intent"] == expected
    assert result["knowledge_mutated"] is False
    assert result["current_status"]["status"] == "NO_CONTEXT"
    assert service.history() == before
    assert topics.list_topics()["count"] == 0
    graph.assert_not_called()
    reasoner.assert_not_called()
    orbits.assert_not_called()


def test_research_intent_starts_work_but_progress_only_reads_it(monkeypatch, tmp_path):
    from uuma import mcp_knowledge
    from uuma.knowledge_service import KnowledgeService
    from uuma.question_orbit import QuestionOrbitService
    from uuma.wisdom_topics import TopicKnowledgeService

    service = KnowledgeService(tmp_path / "wisdom.db")
    topics = TopicKnowledgeService(service)
    orbits = QuestionOrbitService(service, topics=topics)
    reasoner = Mock()
    reasoner.answer.return_value = {
        "runtime_status": "KAG", "answer": "Unsupported retrieval", "citations": [],
        "satisfaction_level": "PROVISIONAL", "satisfaction_rationale": "Unverified",
    }
    monkeypatch.setenv("UUMA_AGENT_ID", "wisdom-oldman")
    monkeypatch.setenv("UUMA_QUESTION_ORBIT_ENABLED", "true")
    monkeypatch.setattr(mcp_knowledge, "_topics", lambda: topics)
    monkeypatch.setattr(mcp_knowledge, "_orbits", lambda: orbits)
    monkeypatch.setattr(mcp_knowledge, "_reasoner", lambda: reasoner)
    monkeypatch.setattr(mcp_knowledge, "ensure_knowledge_graph", lambda *a, **k: {"ready": True})
    route = '{"platform":"telegram","session_id":"one"}'
    intake = mcp_knowledge.knowledge_question_preflight(
        "scallion cultivation", notification_route_json=route
    )
    assert intake["needs_intent_resolution"]
    assert topics.list_topics()["count"] == 0
    proposal = mcp_knowledge.knowledge_question_preflight(
        "scallion cultivation", intent="research", notification_route_json=route
    )
    assert proposal["requires_topic_approval"]
    assert proposal["knowledge_mutated"] is False
    assert topics.list_topics()["count"] == 0
    reasoner.answer.assert_not_called()
    research = mcp_knowledge.knowledge_question_preflight(
        "scallion cultivation", intent="research", notification_route_json=route,
        topic_creation_approved=True,
    )
    assert research["orbit_started"]
    assert research["research_continues"]
    assert topics.list_topics()["count"] == 1
    before = service.history()
    status = mcp_knowledge.knowledge_question_preflight(
        "how is your progress?", notification_route_json=route
    )
    assert status["current_status"]["tasks"][0]["orbit_id"] == research["orbit_id"]
    assert status["current_status"]["tasks"][0]["status"] == "QUEUED"
    assert service.history() == before
    reasoner.answer.assert_called_once()
