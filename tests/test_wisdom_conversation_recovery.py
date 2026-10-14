from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from uuma import mcp_knowledge
from uuma.knowledge_models import KnowledgeTopicRecord, OrbitStatus
from uuma.knowledge_service import KnowledgeAuthorizationError, KnowledgeService
from uuma.question_orbit import QuestionOrbitService
from uuma.settings import Settings
from uuma.wisdom_topics import TopicKnowledgeService, is_progress_request, research_control_intent


def setup_research(monkeypatch, tmp_path):
    knowledge = KnowledgeService(tmp_path / "wisdom.db")
    topics = TopicKnowledgeService(knowledge, view_token="read_only")
    orbits = QuestionOrbitService(knowledge, topics=topics)
    monkeypatch.setenv("UUMA_AGENT_ID", "wisdom-oldman")
    monkeypatch.setenv("UUMA_QUESTION_ORBIT_ENABLED", "true")
    monkeypatch.setattr(mcp_knowledge, "_topics", lambda: topics)
    monkeypatch.setattr(mcp_knowledge, "_orbits", lambda: orbits)
    graph = Mock(return_value={"ready": True})
    reasoner = Mock()
    reasoner.answer.return_value = {
        "runtime_status": "KAG", "answer": "Still missing direct evidence.", "citations": [],
        "satisfaction_level": "INSUFFICIENT", "satisfaction_rationale": "Needs sources",
    }
    monkeypatch.setattr(mcp_knowledge, "ensure_knowledge_graph", graph)
    monkeypatch.setattr(mcp_knowledge, "_reasoner", lambda: reasoner)
    wake = Mock(return_value={"requested": True})
    monkeypatch.setattr(mcp_knowledge, "_wake_orbit_runner", wake)
    route = {"platform": "telegram", "chat_id": "same-chat", "session_id": "old"}
    result = mcp_knowledge.knowledge_question_preflight(
        "青葱气雾培与分株", intent="research", topic_creation_approved=True,
        notification_route_json=json.dumps(route),
    )
    followup = topics.resolve_question("青葱分株后缓苗的适用条件", actor_id="wisdom-oldman")
    topics.publish_answer(result["topic_id"], followup["question"]["question_id"],
                          reasoner.answer.return_value, actor_id="wisdom-oldman",
                          research_status="QUEUED", orbit_id=result["orbit_id"])
    return knowledge, topics, orbits, graph, reasoner, wake, result, route


def test_progress_after_session_reset_reads_paused_research_without_graph(monkeypatch, tmp_path):
    knowledge, topics, orbits, graph, reasoner, wake, result, route = setup_research(
        monkeypatch, tmp_path
    )
    reason = "No additional directly relevant source found; all open branches checked."
    orbits.transition(result["orbit_id"], OrbitStatus.PAUSED,
                      actor_id="wisdom-oldman", reason=reason)
    graph.reset_mock()
    reasoner.reset_mock()
    wake.reset_mock()
    graph.return_value = {"ready": False}
    before = knowledge.history()
    status = mcp_knowledge.knowledge_question_preflight(
        "how is the progress?", intent="research",
        notification_route_json=json.dumps(route | {"session_id": "reset"}),
    )
    assert status["message_intent"] == "status"
    assert not status["knowledge_mutated"] and not status["research_continues"]
    assert status["current_status"]["topic_id"] == result["topic_id"]
    item = status["global_status"]["paused"][0]
    assert item["stop_reason"] == reason
    assert item["document_version"] == 2 and item["section_count"] > 1
    assert item["document_url"] == topics.topic_url(result["topic_id"])
    assert item["open_questions"]
    assert "token=read%5Fonly" in status["global_status"]["topics_url"]
    assert knowledge.history() == before
    graph.assert_not_called()
    reasoner.answer.assert_not_called()
    wake.assert_not_called()


def test_continue_pause_stop_preserve_topic_budget_and_prior_approval(monkeypatch, tmp_path):
    knowledge, topics, orbits, graph, reasoner, _wake, result, route = setup_research(
        monkeypatch, tmp_path
    )
    orbit_id = result["orbit_id"]
    orbits.transition(orbit_id, OrbitStatus.PAUSED, actor_id="wisdom-oldman", reason="User pause")
    before = orbits.get(orbit_id)["research_run"]
    graph.reset_mock()
    reasoner.reset_mock()
    resume = mcp_knowledge.knowledge_question_preflight(
        "continue", notification_route_json=json.dumps(route | {"session_id": "new"})
    )
    assert resume["message_intent"] == "resume"
    assert resume["changed_orbit_ids"] == [orbit_id]
    assert resume["global_status"]["active"][0]["status"] == "QUEUED"
    assert topics.list_topics()["count"] == 1
    after = orbits.get(orbit_id)["research_run"]
    for key in ("research_run_id", "budget_tier", "active_seconds", "sources_used",
                "model_tokens_used", "search_queries_used", "cycle_count"):
        assert after[key] == before[key]
    duplicate = mcp_knowledge.knowledge_question_preflight("continue",
        notification_route_json=json.dumps(route))
    assert duplicate["changed_orbit_ids"] == []
    mcp_knowledge.knowledge_question_preflight("暂停", notification_route_json=json.dumps(route))
    assert orbits.get(orbit_id)["orbit"]["status"] == "PAUSED"
    mcp_knowledge.knowledge_question_preflight("停止", notification_route_json=json.dumps(route))
    stopped = mcp_knowledge.knowledge_question_preflight("continue",
        notification_route_json=json.dumps(route))
    assert stopped["changed_orbit_ids"] == [] and not stopped["research_continues"]
    assert orbits.get(orbit_id)["orbit"]["status"] == "STOPPED"
    assert knowledge.history()["chain_valid"]
    graph.assert_not_called()
    reasoner.answer.assert_not_called()


def test_split_store_link_recovery_requires_review_and_is_reversible(tmp_path):
    knowledge = KnowledgeService(tmp_path / "wisdom.db")
    topics = TopicKnowledgeService(knowledge)
    canonical = topics.resolve_question("青葱气雾栽培分株细节", actor_id="wisdom-oldman",
                                        allow_new_topic=True)
    original = KnowledgeTopicRecord(topic_id="topic_external", title="青葱分株栽培细节",
                                    normalized_key="external", aliases=["青葱分株栽培细节"])
    args = {"reason": "Recovered existing topic navigation after split-store diagnosis.",
            "history_ref": "preserved-external-backup/wisdom.db"}
    with pytest.raises(KnowledgeAuthorizationError):
        topics.recover_topic_link(original, canonical["topic"]["topic_id"],
                                  actor_id="wisdom-oldman", **args)
    archived = topics.recover_topic_link(original, canonical["topic"]["topic_id"],
                                         actor_id="orchestrator", **args)
    assert archived["status"] == "ARCHIVED"
    recovered = topics.get_topic(original.topic_id)
    assert recovered["topic"]["topic_id"] == canonical["topic"]["topic_id"]
    assert recovered["redirected_from"]["recovery_history_ref"] == args["history_ref"]
    assert topics.graph(original.topic_id)["nodes"][0]["id"] == canonical["topic"]["topic_id"]
    before = knowledge.history()
    topics.recover_topic_link(original, canonical["topic"]["topic_id"],
                              actor_id="orchestrator", **args)
    assert knowledge.history() == before
    topics.reverse_topic_link_recovery(original.topic_id, actor_id="orchestrator",
                                       reason="Undo link repair")
    assert topics.get_topic(original.topic_id)["topic"]["topic_id"] == original.topic_id
    assert knowledge.history()["chain_valid"]
    assert knowledge.list_records("claim")["count"] == 0


def test_knowledge_path_can_be_pinned_without_moving_control_state(monkeypatch, tmp_path):
    control_dir, knowledge_dir = tmp_path / "logical", tmp_path / "physical"
    monkeypatch.setenv("UUMA_DATA_DIR", str(control_dir))
    monkeypatch.setenv("UUMA_KNOWLEDGE_DATA_DIR", str(knowledge_dir))
    settings = Settings.from_env()
    assert settings.database_path == control_dir / "uuma.db"
    assert settings.knowledge_database_path() == knowledge_dir / "wisdom.db"
    assert settings.knowledge_content_path() == knowledge_dir / "wisdom-content"


def test_deployed_runner_builds_real_control_and_knowledge_stores(monkeypatch, tmp_path):
    from uuma import orbit_runner

    monkeypatch.setenv("UUMA_DATA_DIR", str(tmp_path / "control"))
    monkeypatch.setenv("UUMA_KNOWLEDGE_DATA_DIR", str(tmp_path / "knowledge"))
    monkeypatch.setenv("UUMA_ORBIT_CHATGPT_DISCOVERY", "false")
    monkeypatch.setattr(orbit_runner.OpenSpgKagBackend, "from_env", lambda **kwargs: Mock())
    monkeypatch.setattr(orbit_runner, "configured_providers", lambda fetcher: [])
    runner = orbit_runner.build_runner(tmp_path / "profile")
    assert runner.knowledge.store.path == tmp_path / "knowledge/wisdom.db"
    assert (tmp_path / "control/uuma.db").is_file()
    assert runner.orbits.topics.topic_url("topic_existing").startswith("http://127.0.0.1:8767/")


def test_user_can_retry_failed_existing_task_without_new_budget(monkeypatch, tmp_path):
    _knowledge, topics, orbits, _graph, _reasoner, _wake, result, route = setup_research(
        monkeypatch, tmp_path
    )
    cycle = orbits.acquire_cycle("failed-cycle-probe")
    orbits.fail_cycle(cycle["orbit_cycle_id"], "failed-cycle-probe", "Temporary service error",
                      recoverable=False)
    before = orbits.get(result["orbit_id"])["research_run"]
    resume = mcp_knowledge.knowledge_question_preflight("continue",
        notification_route_json=json.dumps(route))
    assert resume["changed_orbit_ids"] == [result["orbit_id"]]
    assert orbits.get(result["orbit_id"])["research_run"]["research_run_id"] == before["research_run_id"]
    assert topics.list_topics()["count"] == 1
    assert orbits.acquire_cycle("retry-after-recovery")["orbit_id"] == result["orbit_id"]


def test_progress_discloses_retry_wait_instead_of_claiming_uninterrupted_work(monkeypatch, tmp_path):
    _knowledge, _topics, orbits, _graph, _reasoner, _wake, result, route = setup_research(
        monkeypatch, tmp_path
    )
    cycle = orbits.acquire_cycle("service-retry")
    orbits.fail_cycle(cycle["orbit_cycle_id"], "service-retry", "Graph service retry pending",
                      retry_after_seconds=300)
    status = mcp_knowledge.knowledge_question_preflight("how is the progress?",
        notification_route_json=json.dumps(route))
    task = status["global_status"]["active"][0]
    assert task["orbit_id"] == result["orbit_id"]
    assert task["cycle_status"] == "RETRY"
    assert task["retry_reason"] == "Graph service retry pending" and task["retry_at"]


@pytest.mark.parametrize("question", ["how is the progress?", "how's your progress?",
    "show me all topics", "全部主题列表"])
def test_operational_question_is_not_a_topic(question):
    assert is_progress_request(question)


@pytest.mark.parametrize("question", ["How does scallion division work?",
    "What is recent research progress in fogponics?", "为什么分株后要缓苗？"])
def test_domain_question_still_requires_research_interpretation(question):
    assert not is_progress_request(question)


@pytest.mark.parametrize("message,expected", [("OK，继续继续继续。", "resume"),
    ("please continue", "resume"), ("请先暂停研究吧", "pause"),
    ("continue with a focus on aeroponic pressure", None), ("请研究青葱分株", None)])
def test_conversational_controls_do_not_become_research_questions(message, expected):
    assert research_control_intent(message) == expected
