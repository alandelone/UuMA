from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import Mock

from uuma.brainstormer_planning import CapacityScenario, calculate_capacity

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


def test_yonc_receives_colleague_capabilities_without_a_model_tool_call(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "yonc")
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "yonc-run", "task_id": "yonc-task"}},
        {"ok": True, "result": {"observed_at": "now", "agents": [
            {"agent_id": "scholar", "role_guidance": {"suitable_work": ["literature"]},
             "runtime_readiness": "NOT_CHECKED"},
        ], "supporting_systems": [], "unregistered_role_ids": [], "has_more": False}},
        {"ok": True, "result": {"ok": True, "graph_version": 18}},
    ]
    PLUGIN._CONTEXT = context
    args = {"session_id": "yonc-chat", "turn_id": "one", "user_message": "誰能整理文獻？"}
    guidance = PLUGIN._health_context(**args)["context"]
    assert "scholar" in guidance and "literature" in guidance
    assert "do not prove" in guidance and "has not assigned any work" in guidance
    context.call_mcp.assert_any_call("uuma-worker", "yonc_get_colleague_capabilities", {}, timeout=20)
    repeated = PLUGIN._health_context(**args)["context"]
    assert "scholar" in repeated
    assert context.call_mcp.call_count == 3


def test_yonc_failed_lookup_is_not_treated_as_absent_colleagues(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "yonc")
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "yonc-run", "task_id": "yonc-task"}},
        {"ok": False, "error": "unavailable"},
        {"ok": True, "result": {"ok": True}},
    ]
    PLUGIN._CONTEXT = context
    guidance = PLUGIN._health_context(session_id="yonc-fail", user_message="分工建議")["context"]
    assert "lookup did not succeed" in guidance
    assert "Do not claim that colleagues are absent" in guidance


def test_brainstormer_preflight_emphasizes_corrections_and_numeric_provenance(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "brainstormer")
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "brain-run", "task_id": "brain-task"}},
        {"ok": True, "result": []},
    ]
    PLUGIN._CONTEXT = context
    guidance = PLUGIN._health_context(
        session_id="brain-chat", turn_id="one", user_message="Why 0.5 acre?"
    )["context"]
    assert "latest user correction supersedes" in guidance
    assert "Do not infer producer price from retail price" in guidance
    assert "brainstormer_calculate_capacity" in guidance
    assert "no canonical topic was found" in guidance
    assert "Never claim another Agent was called" in guidance


def test_brainstormer_unperformed_wisdom_handoff_claim_is_blocked(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "brainstormer")
    state = PLUGIN._state("brain-chat")
    state.direct_run_id = "brain-run"
    state.domain_checked = True
    reply = PLUGIN._guard_specialist_output(
        "调用智慧老头（Wisdom Oldman）来分析分株周期。", session_id="brain-chat"
    )
    assert "尚未实际调用" in reply
    assert "Orchestrator" in reply
    assert PLUGIN._guard_specialist_output(
        "建议请 Orchestrator 委派 Wisdom-Oldman。", session_id="brain-chat"
    ) is None


def test_brainstormer_capacity_receipt_overrides_inconsistent_model_math(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "brainstormer")
    state = PLUGIN._state("capacity")
    state.direct_run_id = "run-capacity"
    state.domain_checked = True
    tool_name = "mcp__uuma_worker__brainstormer_calculate_capacity"
    assert PLUGIN._pre_tool_call(tool_name=tool_name, session_id="capacity") is None
    assert "没有成功" in PLUGIN._guard_specialist_output(
        "四块地足够。", session_id="capacity"
    )
    scenario = CapacityScenario(
        target_monthly_profit=10_000,
        realized_price_per_kg=11,
        variable_cost_per_sold_kg=2,
        fixed_cost_per_month=5_000,
        growth_days=60,
        turnaround_days=5,
        harvest_interval_days=15,
        row_spacing_cm=20,
        plant_spacing_cm=12,
        harvested_kg_per_planting_position=0.1,
        sellable_fraction=0.8,
        planted_area_fraction=0.75,
        deliveries_per_week=2,
        planned_blocks=4,
    )
    PLUGIN._post_tool_call(
        tool_name=tool_name, session_id="capacity", result=calculate_capacity(scenario)
    )
    reply = PLUGIN._guard_specialist_output("四块地足够。", session_id="capacity")
    assert "至少需 5 块" in reply
    assert "计划的 4 块不够" in reply
    assert "250.00 m²" in reply
    assert "四块地足够" not in reply


def test_brainstormer_capacity_claim_without_receipt_is_withheld(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "brainstormer")
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "run-area", "task_id": "task-area"}},
        {"ok": True, "result": []},
    ]
    PLUGIN._CONTEXT = context
    kwargs = {"session_id": "unverified-area", "turn_id": "one"}
    PLUGIN._health_context(
        user_message="每月要赚RM10000，我每块种植面积多大，四块够吗？", **kwargs
    )
    reply = PLUGIN._guard_specialist_output(
        "四块足够，每块138平方米。", **kwargs
    )
    assert "还没有通过容量计算工具核对" in reply
    assert "138" not in reply
    assert PLUGIN._guard_specialist_output(
        "还需要到手售价和单产才能倒推面积。", **kwargs
    ) is None


def test_brainstormer_pending_structure_cannot_be_described_as_saved(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "brainstormer")
    state = PLUGIN._state("brain-structure")
    state.direct_run_id = "run-structure"
    state.domain_checked = True
    assert "没有完成" in PLUGIN._guard_specialist_output(
        "项目已经保存了。", session_id="brain-structure"
    )
    PLUGIN._post_tool_call(
        tool_name="mcp__uuma_worker__brainstormer_propose_project_topic",
        session_id="brain-structure",
        result={"status": "PROPOSED", "review_required": True},
    )
    assert "等待 Orchestrator 审核" in PLUGIN._guard_specialist_output(
        "项目已经保存了。", session_id="brain-structure"
    )


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
        {"ok": True, "result": {"topic_id": "t"}},
    ]
    PLUGIN._CONTEXT = context
    PLUGIN._health_context(session_id="consent", turn_id="two", user_message="同意")
    assert context.call_mcp.call_args.args[2]["topic_creation_approved"] is True
    assert context.call_mcp.call_args.args[2]["question"] == "scallion cultivation"
    assert PLUGIN._pre_tool_call(tool_name=tool, args=args, session_id="consent")[
        "action"
    ] == "block"
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


def test_wisdom_read_only_auto_intake_cannot_authorize_a_research_answer(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "wisdom-oldman")
    _healthy_graph(monkeypatch)
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "run-auto", "task_id": "task-auto"}},
        {"ok": True, "result": {"needs_intent_resolution": True}},
    ]
    PLUGIN._CONTEXT = context
    kwargs = {"session_id": "auto-intake", "turn_id": "one"}
    PLUGIN._health_context(user_message="Please help with this", **kwargs)
    assert context.call_mcp.call_args.args[2]["intent"] == "auto"
    assert PLUGIN._guard_specialist_output("Unsupported technical answer", **kwargs)
    PLUGIN._finalize_specialist(assistant_response="Unsupported technical answer", **kwargs)
    assert json.loads(context.call_mcp.call_args.args[2]["result_json"])["outcome"] == "FAILED"


def test_wisdom_research_request_uses_graph_preflight_before_model_answer(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "wisdom-oldman")
    _healthy_graph(monkeypatch)
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "run-research", "task_id": "task-research"}},
        {"ok": True, "result": {"needs_intent_resolution": True}},
        {"ok": True, "result": {
            "requires_topic_approval": True,
            "proposed_topic": {"question": "针对青葱的气雾栽培细节"},
        }},
    ]
    PLUGIN._CONTEXT = context
    kwargs = {"session_id": "research-intake", "turn_id": "one"}
    PLUGIN._health_context(user_message="针对青葱的气雾栽培细节", **kwargs)
    preflight_args = context.call_mcp.call_args.args[2]
    assert preflight_args["intent"] == "research"
    assert preflight_args["topic_creation_approved"] is False
    assert "针对青葱" in PLUGIN._guard_specialist_output("Unverified answer", **kwargs)


def test_wisdom_ok_approves_only_a_tracked_topic_proposal():
    state = PLUGIN._SessionState(pending_topic_question="scallion aeroponics")
    PLUGIN._capture_topic_consent(state, "ok")
    assert state.approved_topic_question == "scallion aeroponics"
    empty = PLUGIN._SessionState()
    PLUGIN._capture_topic_consent(empty, "ok")
    assert empty.approved_topic_question is None


def test_wisdom_cannot_replace_grounded_preflight_with_unsourced_model_text(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "wisdom-oldman")
    _healthy_graph(monkeypatch)
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "run-grounded", "task_id": "task-grounded"}},
        {"ok": True, "result": {"needs_intent_resolution": True}},
        {"ok": True, "result": {
            "answer": {"answer": "No traceable evidence is available yet.", "citations": []},
            "document_url": "http://127.0.0.1:8767/wisdom/topics/topic-1",
            "orbit_status": "QUEUED", "runner_wake": {"requested": True},
        }},
    ]
    PLUGIN._CONTEXT = context
    kwargs = {"session_id": "grounded", "turn_id": "one"}
    PLUGIN._health_context(user_message="针对青葱的气雾栽培细节", **kwargs)
    reply = PLUGIN._guard_specialist_output("Use a 100 PSI pump without sources", **kwargs)
    assert "100 PSI" not in reply
    assert "No traceable evidence" in reply
    assert "topic-1" in reply
    assert "运行尚未确认" in reply


def test_wisdom_progress_reply_uses_global_durable_status(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "wisdom-oldman")
    _healthy_graph(monkeypatch)
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "run-status", "task_id": "task-status"}},
        {"ok": True, "result": {
            "message_intent": "status",
            "current_status": {"status": "NO_CONTEXT", "tasks": []},
            "global_status": {"active": [{
                "topic_title": "青葱气雾栽培", "status": "ACTIVE",
                "document_url": "http://127.0.0.1:8767/wisdom/topics/topic-1",
            }], "paused": []},
        }},
    ]
    PLUGIN._CONTEXT = context
    kwargs = {"session_id": "status", "turn_id": "one"}
    PLUGIN._health_context(user_message="现在有什么 topic 在进行中？", **kwargs)
    reply = PLUGIN._guard_specialist_output("当前没有进行中的主题", **kwargs)
    assert "青葱气雾栽培" in reply
    assert "当前没有" not in reply
    assert "topic-1" in reply


def test_reported_progress_question_clears_proposal_without_graph_or_research(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "wisdom-oldman")
    graph = Mock(return_value=False)
    monkeypatch.setattr(PLUGIN, "_check_graph", graph)
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "status-run", "task_id": "status-task"}},
        {"ok": True, "result": {
            "message_intent": "status", "needs_intent_resolution": False,
            "global_status": {"active": [], "paused": [{
                "topic_title": "青葱分株", "status": "PAUSED", "stop_reason": "资料缺口尚未解决",
                "document_version": 35, "section_count": 9, "document_updated_at": "yesterday",
                "document_url": "http://127.0.0.1:8767/wisdom/topics/original",
            }], "topics_url": "http://127.0.0.1:8767/wisdom/topics"},
        }},
    ]
    PLUGIN._CONTEXT = context
    PLUGIN._state("reported").pending_topic_question = "how is the progress?"
    args = {"session_id": "reported", "turn_id": "new", "user_message": "how is the progress?"}
    PLUGIN._health_context(**args)
    reply = PLUGIN._guard_specialist_output("Research is running steadily", **args)
    assert "PAUSED" in reply and "资料缺口尚未解决" in reply
    assert "35" in reply and "9 个章节" in reply and "全部主题" in reply
    assert "是否同意" not in reply and "running steadily" not in reply
    assert PLUGIN._state("reported").pending_topic_question is None
    assert context.call_mcp.call_count == 2
    assert context.call_mcp.call_args.args[2]["intent"] == "auto"
    graph.assert_not_called()
    assert PLUGIN._pre_tool_call(tool_name="mcp__wisdom_knowledge__knowledge_question_preflight",
                                args={"intent": "status"}, **args) is None
    assert PLUGIN._pre_tool_call(tool_name="mcp__wisdom_knowledge__knowledge_question_preflight",
                                args={"intent": "research"}, **args)["action"] == "block"


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


def test_forge_purchase_question_uses_search_tool_and_corrects_false_access_claim(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "forge-lab-bot")
    row = {
        "order_id": "2101620723153132851",
        "ordered_at": "2024-03-29 08:32:43",
        "variant": "TPU 白色200克1.75mm",
        "product_url": "https://item.taobao.com/item.htm?id=41604517259",
    }
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "forge-run", "task_id": "forge-task"}},
        {"ok": True, "result": {"purchase_history_count": 1087}},
        {"ok": True, "result": {"rows": [row], "total_count": 1, "has_more": False}},
    ]
    PLUGIN._CONTEXT = context
    kwargs = {"session_id": "forge-purchase", "turn_id": "one"}
    guidance = PLUGIN._health_context(
        user_message="我买过 TPU 白色 200g 1.75mm 吗？给我商品链接。", **kwargs
    )
    calls = context.call_mcp.call_args_list
    assert [call.args[1] for call in calls] == [
        "register_direct_run", "inventory_status", "inventory_search_purchase_history"
    ]
    assert calls[2].args[2]["query"] == "TPU 200 1.75 白色"
    assert row["product_url"] in guidance["context"]
    reply = PLUGIN._guard_specialist_output("我没有权限访问 lab.db。", **kwargs)
    assert row["product_url"] in reply
    assert row["order_id"] in reply


def test_forge_purchase_tool_failure_cannot_be_reported_as_absent(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "forge-lab-bot")
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "forge-run", "task_id": "forge-task"}},
        {"ok": True, "result": {"purchase_history_count": 1087}},
        {"ok": False, "error": "tool unavailable"},
    ]
    PLUGIN._CONTEXT = context
    kwargs = {"session_id": "forge-failed", "turn_id": "one"}
    PLUGIN._health_context(user_message="我购买的 TPU 订单在哪里？", **kwargs)
    reply = PLUGIN._guard_specialist_output("数据库里没有 TPU。", **kwargs)
    assert "查询工具未成功" in reply

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
    _record(
        "mcp__wisdom_knowledge__knowledge_question_preflight",
        {"intent": "research"}, {"answer": "grounded"}, "wisdom-1",
    )
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
        {"ok": True, "result": {"needs_intent_resolution": True}},
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
    assert context.call_mcp.call_count == 3
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
    assert context.call_mcp.call_count == 4


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
        {"ok": True, "result": {"agents": [], "observed_at": "now"}},
        {"ok": True, "result": {"database_identity": "db-1", "graph_version": 7}},
    ]
    PLUGIN._CONTEXT = context
    reminder = PLUGIN._health_context(
        session_id="yonc-session", turn_id="turn-1", user_message="Review my projects"
    )
    assert "run-yonc" in reminder["context"]
    assert context.call_mcp.call_args_list[1].args[:3] == (
        "uuma-worker", "yonc_get_colleague_capabilities", {}
    )
    assert context.call_mcp.call_args_list[2].args[:3] == (
        "yonc-project", "yonc_status", {}
    )
    assert PLUGIN._guard_specialist_output("review", session_id="yonc-session") is None


def test_honc_auto_registers_and_checks_execution_identity(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "honc")
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"run_id": "run-honc", "task_id": "task-honc"}},
        {"ok": True, "result": {"user_id": "default_user", "active_round": None}},
    ]
    PLUGIN._CONTEXT = context
    reminder = PLUGIN._health_context(
        session_id="honc-session", turn_id="turn-1", user_message="今日执行跟踪"
    )
    assert "run-honc" in reminder["context"]
    assert "Honc: manage daily execution facts" in reminder["context"]
    assert context.call_mcp.call_args_list[0].args[:2] == (
        "uuma-worker", "register_direct_run"
    )
    contract = json.loads(context.call_mcp.call_args_list[0].args[2]["contract_json"])
    assert contract["risk_level"] == "REVERSIBLE"
    assert context.call_mcp.call_args_list[1].args[:3] == (
        "honc-execution", "honc_status", {}
    )
    assert PLUGIN._guard_specialist_output(
        "今日已完成 2 个番茄钟。", session_id="honc-session"
    ) is None


def test_wisdom_kanban_worker_env_bypasses_direct_chat_and_preserves_output(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "wisdom-oldman")
    monkeypatch.setenv("HERMES_KANBAN_TASK", "t_263a9b20")
    context = Mock()
    PLUGIN._CONTEXT = context

    reminder = PLUGIN._health_context(
        session_id="kanban-sess-1", turn_id="turn-1", user_message="work kanban task t_263a9b20"
    )
    assert reminder is None
    assert context.call_mcp.call_count == 0

    state = PLUGIN._state("kanban-sess-1")
    assert state.is_kanban is True
    assert state.direct_run_id == "kanban:t_263a9b20"
    assert state.wisdom_intent_resolved is True

    # Kanban tools allowed without direct run error
    assert PLUGIN._pre_tool_call(
        tool_name="kanban_show", args={"task_id": "t_263a9b20"}, session_id="kanban-sess-1"
    ) is None
    assert PLUGIN._pre_tool_call(
        tool_name="kanban_complete", args={"task_id": "t_263a9b20"}, session_id="kanban-sess-1"
    ) is None

    # Output not transformed
    research_report = "青蒜气雾培项目研究报告 — Phase 6: 深入聚焦与量化实施方案\n..."
    transformed = PLUGIN._guard_specialist_output(research_report, session_id="kanban-sess-1")
    assert transformed is None

    # Finalize does not submit a direct run result
    PLUGIN._finalize_specialist(session_id="kanban-sess-1", assistant_response=research_report)
    assert context.call_mcp.call_count == 0


def test_wisdom_kanban_worker_message_prefix_bypasses_direct_chat(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "wisdom-oldman")
    monkeypatch.delenv("HERMES_KANBAN_TASK", raising=False)
    context = Mock()
    PLUGIN._CONTEXT = context

    reminder = PLUGIN._health_context(
        session_id="kanban-sess-2", turn_id="turn-1", user_message="work kanban task t_6eb43810"
    )
    assert reminder is None
    assert context.call_mcp.call_count == 0

    state = PLUGIN._state("kanban-sess-2")
    assert state.is_kanban is True
    assert state.direct_run_id == "kanban:t_6eb43810"

    transformed = PLUGIN._guard_specialist_output("Phase 5 report content", session_id="kanban-sess-2")
    assert transformed is None


def test_kanban_worker_multi_turn_persists_kanban_state(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "wisdom-oldman")
    monkeypatch.setenv("HERMES_KANBAN_TASK", "t_263a9b20")
    context = Mock()
    PLUGIN._CONTEXT = context

    # Turn 1
    PLUGIN._health_context(session_id="kanban-sess-multi", turn_id="turn-1", user_message="work kanban task t_263a9b20")

    # Turn 2 (e.g. nudge or follow-up)
    reminder = PLUGIN._health_context(
        session_id="kanban-sess-multi", turn_id="turn-2", user_message="Please remember to complete the card"
    )
    assert reminder is None
    state = PLUGIN._state("kanban-sess-multi")
    assert state.is_kanban is True
    assert state.direct_run_id == "kanban:t_263a9b20"

    transformed = PLUGIN._guard_specialist_output("Final synthesized text", session_id="kanban-sess-multi")
    assert transformed is None


def test_forge_file_mutation_allowed_in_hardware_workspace(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "forge-lab-bot")
    PLUGIN._state("forge-sess").direct_run_id = "run-forge-1"

    # write_file to Hardware-Lab-Workspace/projects
    path1 = "C:/Users/Alandelone/CodeSpace_Local/Hardware-Lab-Workspace/projects/scallion/plan.md"
    res1 = PLUGIN._pre_tool_call(
        tool_name="write_file",
        args={"path": path1, "content": "# Plan"},
        session_id="forge-sess",
    )
    assert res1 is None

    # edit_file in Hardware-Lab-Workspace/outputs
    path2 = "C:/Users/Alandelone/CodeSpace_Local/Hardware-Lab-Workspace/outputs/bom.json"
    res2 = PLUGIN._pre_tool_call(
        tool_name="edit_file",
        args={"file_path": path2, "content": "{}"},
        session_id="forge-sess",
    )
    assert res2 is None

    # apply_patch with relative path resolving in Hardware-Lab-Workspace
    res3 = PLUGIN._pre_tool_call(
        tool_name="apply_patch",
        args={"path": "projects/scallion/plan.md", "diff": "--- +++"},
        session_id="forge-sess",
    )
    assert res3 is None


def test_forge_file_mutation_allowed_in_kanban_workspace(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "forge-lab-bot")
    state = PLUGIN._state("kanban-forge")
    state.is_kanban = True
    state.direct_run_id = "kanban:t_29be449d"

    # Absolute Windows path in kanban workspace
    path_win = r"C:\Users\Alandelone\AppData\Local\hermes\kanban\workspaces\t_29be449d\系统设计文档.md"
    assert PLUGIN._pre_tool_call(
        tool_name="write_file",
        args={"path": path_win, "content": "# Design"},
        session_id="kanban-forge",
        task_id="t_29be449d",
    ) is None

    # Git Bash posix path in kanban workspace
    path_posix = "/c/Users/Alandelone/AppData/Local/hermes/kanban/workspaces/t_29be449d/硬件清单与预算.md"
    assert PLUGIN._pre_tool_call(
        tool_name="write_file",
        args={"path": path_posix, "content": "# Budget"},
        session_id="kanban-forge",
        task_id="t_29be449d",
    ) is None

    # Relative path in kanban task
    assert PLUGIN._pre_tool_call(
        tool_name="write_file",
        args={"path": "experiment.md", "content": "# Exp"},
        session_id="kanban-forge",
        task_id="t_29be449d",
    ) is None


def test_forge_file_mutation_blocked_outside_project_directory(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "forge-lab-bot")
    PLUGIN._state("forge-sess").direct_run_id = "run-forge-1"

    # System directory
    res_sys = PLUGIN._pre_tool_call(
        tool_name="write_file",
        args={"path": "C:/Windows/System32/cmd.exe", "content": "bad"},
        session_id="forge-sess",
    )
    assert res_sys is not None and res_sys["action"] == "block"
    assert "file mutation is restricted to the project folder" in res_sys["message"]

    # Top-level hermes config
    res_cfg = PLUGIN._pre_tool_call(
        tool_name="write_file",
        args={"path": "C:/Users/Alandelone/AppData/Local/hermes/config.yaml", "content": "bad"},
        session_id="forge-sess",
    )
    assert res_cfg is not None and res_cfg["action"] == "block"
    assert "file mutation is restricted to the project folder" in res_cfg["message"]

    # UuMA code directory
    res_uuma = PLUGIN._pre_tool_call(
        tool_name="write_file",
        args={"path": "C:/Users/Alandelone/CodeSpace_Local/UuMA/src/bad.py", "content": "bad"},
        session_id="forge-sess",
    )
    assert res_uuma is not None and res_uuma["action"] == "block"
    assert "file mutation is restricted to the project folder" in res_uuma["message"]

    # Empty or missing args
    res_empty = PLUGIN._pre_tool_call(
        tool_name="write_file",
        args={},
        session_id="forge-sess",
    )
    assert res_empty is not None and res_empty["action"] == "block"
    assert "file mutation is restricted to the project folder" in res_empty["message"]


def test_forge_delete_file_and_terminal_remain_blocked(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "forge-lab-bot")
    PLUGIN._state("forge-sess").direct_run_id = "run-forge-1"

    # delete_file remains blocked even inside project
    res_del = PLUGIN._pre_tool_call(
        tool_name="delete_file",
        args={"path": "C:/Users/Alandelone/CodeSpace_Local/Hardware-Lab-Workspace/projects/scallion/plan.md"},
        session_id="forge-sess",
    )
    assert res_del is not None and res_del["action"] == "block"
    assert "Blocked by UuMA specialist policy" in res_del["message"]

    # terminal remains blocked
    res_term = PLUGIN._pre_tool_call(
        tool_name="terminal",
        args={"command": "dir"},
        session_id="forge-sess",
    )
    assert res_term is not None and res_term["action"] == "block"


def test_other_specialists_cannot_mutate_files(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "wisdom-oldman")
    PLUGIN._state("wisdom-sess").direct_run_id = "run-wisdom-1"

    res = PLUGIN._pre_tool_call(
        tool_name="write_file",
        args={"path": "C:/Users/Alandelone/CodeSpace_Local/Hardware-Lab-Workspace/projects/plan.md"},
        session_id="wisdom-sess",
    )
    assert res is not None and res["action"] == "block"
    assert "Blocked by UuMA specialist policy: control, computer, file mutation" in res["message"]


