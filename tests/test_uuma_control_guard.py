from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import Mock

PLUGIN_PATH = (
    Path(__file__).parents[1]
    / "integrations"
    / "hermes"
    / "uuma_control_guard"
    / "__init__.py"
)
SPEC = importlib.util.spec_from_file_location("uuma_control_guard_test_plugin", PLUGIN_PATH)
assert SPEC and SPEC.loader
PLUGIN = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PLUGIN
SPEC.loader.exec_module(PLUGIN)


def setup_function() -> None:
    PLUGIN._SESSIONS.clear()
    PLUGIN._CONTEXT = None


def _healthy_graph(monkeypatch) -> None:
    def check(**kwargs):
        PLUGIN._state(PLUGIN._session_key(kwargs)).graph_ready = True
        return True
    monkeypatch.setattr(PLUGIN, "_check_graph", check)


def test_new_wisdom_topic_requires_later_user_consent_and_cannot_change_scope(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "wisdom-oldman")
    _healthy_graph(monkeypatch)
    state = PLUGIN._state("consent")
    state.direct_run_id = "one"
    state.direct_turn_id = "one"
    state.direct_attempted = True
    tool = "mcp__wisdom_knowledge__knowledge_question_preflight"
    args = {"question": "scallion cultivation", "intent": "research",
            "topic_creation_approved": True}
    PLUGIN._post_tool_call(tool_name=tool, session_id="consent", result={
        "requires_topic_approval": True,
        "proposed_topic": {"question": "scallion cultivation"},
    })
    prompt = PLUGIN._guard_specialist_output("already researching", session_id="consent")
    assert "scallion cultivation" in prompt
    assert "是否同意" in prompt
    assert "already researching" not in prompt
    assert PLUGIN._pre_tool_call(tool_name=tool, args=args, session_id="consent")[
        "action"
    ] == "block"
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "two", "task_id": "task-two"}},
        {"ok": True, "result": {"needs_intent_resolution": True}},
    ]
    PLUGIN._CONTEXT = context
    PLUGIN._health_context(session_id="consent", turn_id="two", user_message="同意")
    assert PLUGIN._pre_tool_call(tool_name=tool, args=args, session_id="consent") is None
    assert PLUGIN._pre_tool_call(
        tool_name=tool, args=args | {"question": "unrelated topic"}, session_id="consent"
    )["action"] == "block"
    assert PLUGIN._pre_tool_call(tool_name=tool, args=args, session_id="other")["action"] == "block"
    PLUGIN._post_tool_call(tool_name=tool, args=args, session_id="consent", result={"topic_id": "t"})
    assert PLUGIN._pre_tool_call(tool_name=tool, args=args, session_id="consent")["action"] == "block"


def test_topic_consent_denial_or_unrelated_message_clears_pending_proposal():
    for reply in ("no", "不要", "how is your progress?", "change the scope"):
        state = PLUGIN._SessionState(pending_topic_question="scallions")
        PLUGIN._capture_topic_consent(state, reply)
        assert state.approved_topic_question is None
        assert state.pending_topic_question is None


def test_scholar_missing_graph_blocks_catalog_output_and_completion(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "scholar")
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "run-g", "task_id": "task-g"}},
        {"ok": True, "result": {"ready": False, "status": "BLOCKED"}},
    ]
    PLUGIN._CONTEXT = context
    kwargs = {"session_id": "graph-failure", "turn_id": "one"}
    reminder = PLUGIN._health_context(user_message="Research this", **kwargs)
    assert "BLOCKED" in reminder["context"]
    assert [c.args[1] for c in context.call_mcp.call_args_list] == [
        "register_direct_run", "knowledge_runtime_preflight",
    ]
    context.call_mcp.side_effect = None
    context.call_mcp.return_value = {"ok": True, "result": {"ready": False}}
    assert PLUGIN._pre_tool_call(tool_name="mcp__rstv4_worker__list_catalog_papers", **kwargs)[
        "action"
    ] == "block"
    assert PLUGIN._pre_tool_call(tool_name="mcp__uuma_worker__block_run", **kwargs) is None
    assert "知识图谱当前不可用" in PLUGIN._guard_specialist_output("made up answer", **kwargs)
    PLUGIN._finalize_specialist(assistant_response="made up answer", **kwargs)
    assert json.loads(context.call_mcp.call_args.args[2]["result_json"])["outcome"] == "FAILED"


def test_graph_is_rechecked_before_tools_and_output(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "wisdom-oldman")
    state = PLUGIN._state("graph-loss")
    state.direct_run_id = "run-g"
    state.domain_checked = True
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"ready": True}},
        {"ok": True, "result": {"ready": False}},
    ]
    PLUGIN._CONTEXT = context
    assert PLUGIN._pre_tool_call(
        tool_name="mcp__wisdom_knowledge__knowledge_answer", session_id="graph-loss"
    ) is None
    assert "知识图谱当前不可用" in PLUGIN._guard_specialist_output(
        "answer", session_id="graph-loss"
    )
    assert not state.graph_ready


def _record(tool_name: str, args: dict, result: object, session_id: str = "session-1") -> None:
    PLUGIN._post_tool_call(
        tool_name=tool_name,
        args=args,
        result=result,
        status="ok",
        session_id=session_id,
    )


def test_delegation_is_blocked_until_full_control_preflight(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "default")
    call = {"tool_name": "delegate_task", "args": {"tasks": [{"goal": "research"}]}, "session_id": "session-1"}

    assert PLUGIN._pre_tool_call(**call)["action"] == "block"

    nested_result = json.dumps({"result": json.dumps({"task_id": "task-1", "status": "PROPOSED"})})
    _record("mcp__uuma_control__create_task", {"contract_json": "{}"}, nested_result)
    _record("mcp__uuma_control__route_task", {"task_id": "task-1"}, {"selected_agent": "scholar"})
    assert PLUGIN._pre_tool_call(**call)["action"] == "block"

    _record("mcp__uuma_control__assign_task", {"task_id": "task-1"}, {"status": "READY"})
    assert PLUGIN._pre_tool_call(**call) is None

    _record("delegate_task", call["args"], {"status": "dispatched"})
    assert PLUGIN._pre_tool_call(**call)["action"] == "block"


def test_batch_delegation_requires_one_ready_task_per_child(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "orchestrator")
    for task_id in ("task-1", "task-2"):
        _record("mcp__uuma-control__create_task", {}, {"task_id": task_id})
        _record("mcp__uuma-control__route_task", {"task_id": task_id}, {})
        if task_id == "task-1":
            _record("mcp__uuma-control__assign_task", {"task_id": task_id}, {})

    call = {
        "tool_name": "delegate_task",
        "args": {"tasks": [{"goal": "one"}, {"goal": "two"}]},
        "session_id": "session-1",
    }
    assert "Ready task contracts: 1" in PLUGIN._pre_tool_call(**call)["message"]

    _record("mcp__uuma-control__assign_task", {"task_id": "task-2"}, {})
    assert PLUGIN._pre_tool_call(**call) is None


def test_chatgpt_bridge_is_excluded_from_scholar_and_yonc(monkeypatch) -> None:
    for profile in ("scholar", "yonc"):
        monkeypatch.setenv("HERMES_PROFILE", profile)
        decision = PLUGIN._pre_tool_call(
            tool_name="mcp__chatgpt_bridge__chatgpt_request",
            args={"mode": "search"},
            session_id="bridge-exclusion",
        )
        assert decision == {
            "action": "block",
            "message": "ChatGPT bridge capability denied for this profile.",
        }


def test_forge_chatgpt_bridge_is_search_only(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "forge-lab-bot")
    PLUGIN._state("bridge-lab").direct_run_id = "run-lab"
    chat = PLUGIN._pre_tool_call(
        tool_name="mcp__chatgpt_bridge__chatgpt_request",
        args={"mode": "chat"},
        session_id="bridge-lab",
    )
    search = PLUGIN._pre_tool_call(
        tool_name="mcp__chatgpt_bridge__chatgpt_request",
        args={"mode": "search"},
        session_id="bridge-lab",
    )
    assert chat and chat["action"] == "block"
    assert search is None

def test_orchestrator_live_stop_remains_available_but_scholar_spawn_is_blocked(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "default")
    assert PLUGIN._pre_tool_call(
        tool_name="delegate_task",
        args={"action": "stop", "subagent_id": "child-1"},
        session_id="session-1",
    ) is None

    monkeypatch.setenv("HERMES_PROFILE", "scholar")
    assert PLUGIN._pre_tool_call(
        tool_name="delegate_task",
        args={"tasks": [{"goal": "bounded work"}]},
        session_id="session-1",
    )["action"] == "block"


def test_health_check_uses_control_mcp_and_reports_failure(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "default")
    context = Mock()
    context.call_mcp.return_value = {"ok": True, "result": {"status": "ok"}}
    PLUGIN._CONTEXT = context

    assert PLUGIN._health_context(session_id="session-1") is None
    context.call_mcp.assert_called_once_with("uuma-control", "system_health", {}, timeout=30)
    assert PLUGIN._health_context(session_id="session-1") is None
    context.call_mcp.assert_called_once()

    PLUGIN._SESSIONS["session-1"].last_health_check = 0
    context.call_mcp.return_value = {"ok": False, "error": "closed"}
    warning = PLUGIN._health_context(session_id="session-1")
    assert "health check failed" in warning["context"]


def test_failed_control_calls_do_not_authorize_delegation(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "default")
    _record("mcp__uuma_control__create_task", {}, {"task_id": "task-1"})
    PLUGIN._post_tool_call(
        tool_name="mcp__uuma_control__route_task",
        args={"task_id": "task-1"},
        result={"error": "control unavailable"},
        status="error",
        session_id="session-1",
    )
    _record("mcp__uuma_control__assign_task", {"task_id": "task-1"}, {})

    blocked = PLUGIN._pre_tool_call(
        tool_name="delegate_task",
        args={"tasks": [{"goal": "research"}]},
        session_id="session-1",
    )
    assert blocked["action"] == "block"


def test_error_text_without_explicit_status_does_not_authorize(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "default")
    _record("mcp__uuma_control__create_task", {}, {"task_id": "task-1"})
    _record("mcp__uuma_control__route_task", {"task_id": "task-1"}, {})
    _record(
        "mcp__uuma_control__assign_task",
        {"task_id": "task-1"},
        "Error executing tool 'assign_task': transport closed",
    )

    blocked = PLUGIN._pre_tool_call(
        tool_name="delegate_task",
        args={"tasks": [{"goal": "research"}]},
        session_id="session-1",
    )
    assert blocked["action"] == "block"


def test_specialist_requires_direct_run_each_turn(monkeypatch) -> None:
    _healthy_graph(monkeypatch)
    monkeypatch.setenv("HERMES_PROFILE", "wisdom-oldman")
    kwargs = {"session_id": "wisdom-1", "turn_id": "turn-1"}
    reminder = PLUGIN._health_context(**kwargs)
    assert "register_direct_run" in reminder["context"]
    tool = {**kwargs, "tool_name": "mcp__wisdom_knowledge__knowledge_answer", "args": {}}
    assert PLUGIN._pre_tool_call(**tool)["action"] == "block"
    assert PLUGIN._guard_specialist_output("unsupported answer", **kwargs).startswith("我目前无法")

    registration = "mcp__uuma_worker__register_direct_run"
    assert PLUGIN._pre_tool_call(tool_name=registration, args={}, **kwargs) is None
    PLUGIN._post_tool_call(
        tool_name=registration,
        args={},
        result={"run_id": "run-1", "task_id": "task-1"},
        status="ok",
        **kwargs,
    )
    assert PLUGIN._pre_tool_call(**tool) is None
    assert PLUGIN._guard_specialist_output("ungrounded answer", **kwargs) is not None
    _record("mcp__wisdom_knowledge__knowledge_answer", {}, {"answer": "grounded"}, "wisdom-1")
    assert PLUGIN._guard_specialist_output("grounded answer", **kwargs) is None

    assert "register_direct_run" in PLUGIN._health_context(
        session_id="wisdom-1", turn_id="turn-2"
    )["context"]
    assert PLUGIN._pre_tool_call(**{**tool, "turn_id": "turn-2"})["action"] == "block"


def test_failed_registration_does_not_unlock_specialist(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "brainstormer")
    PLUGIN._health_context(session_id="brain-1", turn_id="turn-1")
    PLUGIN._post_tool_call(
        tool_name="mcp__uuma_worker__register_direct_run",
        args={},
        result={"error": "unavailable"},
        status="error",
        session_id="brain-1",
    )
    assert PLUGIN._pre_tool_call(
        tool_name="mcp__uuma_worker__brainstormer_get_context",
        args={},
        session_id="brain-1",
    )["action"] == "block"


def test_direct_run_does_not_grant_specialist_control_actions(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "wisdom-oldman")
    PLUGIN._state("wisdom-safe").direct_run_id = "run-safe"
    for tool in (
        "delegate_task",
        "computer_use",
        "write_file",
        "mcp__uuma_control__create_task",
        "mcp__wisdom_knowledge__knowledge_apply_patch",
    ):
        assert PLUGIN._pre_tool_call(tool_name=tool, session_id="wisdom-safe")["action"] == "block"


def test_multiplexed_profile_home_takes_priority_over_process_env(monkeypatch) -> None:
    import types

    monkeypatch.setenv("HERMES_PROFILE", "default")
    monkeypatch.setitem(
        sys.modules,
        "hermes_constants",
        types.SimpleNamespace(
            get_hermes_home_override=lambda: "C:/Users/user/hermes/profiles/wisdom-oldman"
        ),
    )
    assert PLUGIN._profile() == "wisdom-oldman"


def test_direct_wisdom_turn_auto_registers_and_uses_knowledge_mcp(monkeypatch) -> None:
    _healthy_graph(monkeypatch)
    monkeypatch.setenv("HERMES_PROFILE", "wisdom-oldman")
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "run-auto", "task_id": "task-auto"}},
        {"ok": True, "result": {"answer": "candidate is not canonical"}},
    ]
    PLUGIN._CONTEXT = context
    result = PLUGIN._health_context(
        session_id="wisdom-auto",
        turn_id="turn-auto",
        user_message="What is a knowledge candidate?",
    )
    assert "run-auto" in result["context"]
    assert "candidate is not canonical" in result["context"]
    assert context.call_mcp.call_count == 2
    assert context.call_mcp.call_args_list[0].args[:2] == (
        "uuma-worker",
        "register_direct_run",
    )
    assert context.call_mcp.call_args_list[1].args[:2] == (
        "wisdom-knowledge",
        "knowledge_question_preflight",
    )
    # Recovery now belongs to the mandatory graph gate, before domain reasoning.
    assert context.call_mcp.call_args_list[1].args[2]["recover_runtime"] is False
    assert context.call_mcp.call_args_list[1].args[2]["mode"] == "SIMPLE"
    assert context.call_mcp.call_args_list[1].args[2]["uuma_task_id"] == "task-auto"
    assert context.call_mcp.call_args_list[1].args[2]["uuma_run_id"] == "run-auto"
    assert context.call_mcp.call_args_list[1].kwargs["timeout"] == 420
    assert PLUGIN._guard_specialist_output(
        "grounded", session_id="wisdom-auto", turn_id="turn-auto"
    ) is None
    context.call_mcp.side_effect = None
    context.call_mcp.return_value = {"ok": True, "result": {"event_type": "RUN_COMPLETED"}}
    PLUGIN._finalize_specialist(
        session_id="wisdom-auto", turn_id="turn-auto", assistant_response="grounded answer"
    )
    assert context.call_mcp.call_args.args[:2] == ("uuma-worker", "submit_result")
    result = json.loads(context.call_mcp.call_args.args[2]["result_json"])
    assert result["run_id"] == "run-auto"
    assert result["task_id"] == "task-auto"
    assert result["outcome"] == "COMPLETED"
    PLUGIN._finalize_specialist(session_id="wisdom-auto", assistant_response="grounded answer")
    assert context.call_mcp.call_count == 3


def test_wisdom_degraded_preflight_is_blocked_in_output(monkeypatch) -> None:
    _healthy_graph(monkeypatch)
    monkeypatch.setenv("HERMES_PROFILE", "wisdom-oldman")
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "run-degraded", "task_id": "task-degraded"}},
        {"ok": True, "result": {"runtime_status": "DEGRADED_KAG", "answer": "text evidence"}},
    ]
    PLUGIN._CONTEXT = context
    PLUGIN._health_context(
        session_id="wisdom-degraded", turn_id="turn-1", user_message="What is known?"
    )
    answer = PLUGIN._guard_specialist_output(
        "A claim is reviewed before acceptance.", session_id="wisdom-degraded", turn_id="turn-1"
    )
    assert "已阻止降级回答" in answer
    assert "A claim" not in answer


def test_generic_model_failure_is_not_recorded_as_completed(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "brainstormer")
    context = Mock()
    context.call_mcp.return_value = {"ok": True, "result": {"event_type": "RUN_FAILED"}}
    PLUGIN._CONTEXT = context
    state = PLUGIN._state("brain-failure")
    state.direct_run_id = "run-failure"
    state.direct_task_id = "task-failure"
    state.domain_checked = True
    PLUGIN._finalize_specialist(
        session_id="brain-failure",
        assistant_response="Sorry, something went wrong. Please try your request again.",
    )
    result = json.loads(context.call_mcp.call_args.args[2]["result_json"])
    assert result["outcome"] == "FAILED"


def test_scholar_auto_registers_and_reads_rst_v4_catalog(monkeypatch) -> None:
    _healthy_graph(monkeypatch)
    monkeypatch.setenv("HERMES_PROFILE", "scholar")
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "run-scholar", "task_id": "task-scholar"}},
        {"ok": True, "result": [{"paper_id": "paper-1"}]},
    ]
    PLUGIN._CONTEXT = context
    reminder = PLUGIN._health_context(
        session_id="scholar-session", turn_id="turn-1", user_message="Review literature"
    )
    assert "run-scholar" in reminder["context"]
    assert '"task_id": "task-scholar"' in reminder["context"]
    assert '"agent_id": "scholar"' in reminder["context"]
    assert "progress_json and result_json" in reminder["context"]
    assert context.call_mcp.call_args_list[1].args[:3] == (
        "rstv4-worker", "list_catalog_papers", {"limit": 5}
    )
    assert PLUGIN._guard_specialist_output("review", session_id="scholar-session") is None


def test_scholar_reporting_identity_survives_failed_preflight_and_later_calls(monkeypatch) -> None:
    _healthy_graph(monkeypatch)
    monkeypatch.setenv("HERMES_PROFILE", "scholar")
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "run-scholar", "task_id": "task-scholar"}},
        {"ok": False, "error": "Domain unavailable"},
    ]
    PLUGIN._CONTEXT = context
    for _ in range(2):
        reminder = PLUGIN._health_context(
            session_id="scholar-unavailable", turn_id="turn-1", user_message="Review literature"
        )
        assert '"run_id": "run-scholar"' in reminder["context"]
        assert '"task_id": "task-scholar"' in reminder["context"]
        assert '"agent_id": "scholar"' in reminder["context"]
    assert context.call_mcp.call_count == 2


def test_forge_auto_registers_and_reads_inventory(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "forge-lab-bot")
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "run-forge", "task_id": "task-forge"}},
        {"ok": True, "result": {"inventory_ready": True}},
    ]
    PLUGIN._CONTEXT = context
    reminder = PLUGIN._health_context(
        session_id="forge-session", turn_id="turn-1", user_message="Compare parts"
    )
    assert "run-forge" in reminder["context"]
    assert context.call_mcp.call_args_list[1].args[:3] == (
        "uuma-worker", "inventory_status", {}
    )
    contract = json.loads(context.call_mcp.call_args_list[0].args[2]["contract_json"])
    assert contract["risk_level"] == "REVERSIBLE"
    assert "lab-worklog conversational intake" in reminder["context"]
    assert PLUGIN._pre_tool_call(
        tool_name="mcp__uuma_worker__lab_journal_capture_chat", session_id="forge-session"
    ) is None
    assert PLUGIN._pre_tool_call(
        tool_name="mcp__uuma_worker__lab_journal_queue_write", session_id="forge-session"
    )["action"] == "block"
    assert PLUGIN._pre_tool_call(
        tool_name="mcp__uuma_worker__procurement_confirm_order", session_id="forge-session"
    )["action"] == "block"


def test_forge_chat_capture_still_requires_registered_direct_run(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "forge-lab-bot")
    assert PLUGIN._pre_tool_call(
        tool_name="mcp__uuma_worker__lab_journal_capture_chat", session_id="unregistered"
    )["action"] == "block"


def test_yonc_auto_registers_and_checks_project_identity(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "yonc")
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "run-yonc", "task_id": "task-yonc"}},
        {"ok": True, "result": {"database_identity": "db-1", "graph_version": 7}},
    ]
    PLUGIN._CONTEXT = context
    reminder = PLUGIN._health_context(
        session_id="yonc-session", turn_id="turn-1", user_message="Review my projects"
    )
    assert "run-yonc" in reminder["context"]
    assert context.call_mcp.call_args_list[1].args[:3] == (
        "yonc-project", "yonc_status", {}
    )
    assert PLUGIN._guard_specialist_output("review", session_id="yonc-session") is None
