from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from uuma.honc.conversation import (
    HoncConversationEngine,
    InputOrigin,
)
from uuma.honc.graph_client import GraphExecutionClient
from uuma.honc.models import (
    ActualKind,
    AssessmentResult,
    RoundStatus,
)
from uuma.honc.service import HoncService
from uuma.honc.store import HoncStore


class FakeGraphExecutionClient(GraphExecutionClient):
    """Fake client simulating Yonc Graph responses for conversation testing."""

    def __init__(self) -> None:
        super().__init__(base_url="http://fake-graph", database_id="fake-db-123")
        self.decisions_submitted: list[dict[str, Any]] = []
        self.receipts_store: dict[str, dict[str, Any]] = {}

    def submit_action_decision(
        self,
        operation_id: str,
        node_id: str,
        action: str,
        decision_origin: dict[str, Any],
    ) -> dict[str, Any]:
        record = {
            "operation_id": operation_id,
            "node_id": node_id,
            "action": action,
            "decision_origin": decision_origin,
            "is_undone": False,
        }
        self.decisions_submitted.append(record)
        receipt = {
            "receipt": {
                "operation_id": operation_id,
                "node_id": node_id,
                "action": action,
                "is_undone": False,
            },
            "node": {"id": node_id, "status": "DONE" if action == "done" else "TODO"},
            "operation_batch_id": f"batch-{operation_id}",
        }
        self.receipts_store[operation_id] = receipt["receipt"]
        return receipt

    def get_receipt(self, operation_id: str) -> dict[str, Any] | None:
        rec = self.receipts_store.get(operation_id)
        return {"receipt": rec} if rec else None


@pytest.fixture
def honc_env(tmp_path: Path):
    db_file = tmp_path / "honc_test.db"
    store = HoncStore(db_file)
    fake_graph = FakeGraphExecutionClient()
    service = HoncService(store=store, graph_client=fake_graph, default_user_id="alice")
    engine = HoncConversationEngine(
        service=service,
        bound_user_id="alice",
        bound_telegram_user_id="tg_12345",
    )
    return {"store": store, "service": service, "graph": fake_graph, "engine": engine}


def test_origin_validation_rules(honc_env: dict[str, Any]) -> None:
    engine: HoncConversationEngine = honc_env["engine"]

    # 1. Hermes local user match -> valid & can authorize
    res1 = engine.validate_origin(
        InputOrigin(sender_id="alice", channel="hermes_local"),
        "完成任务",
    )
    assert res1.valid is True
    assert res1.can_authorize_completion is True
    assert res1.trusted_input is not None

    # 2. Hermes local user mismatch -> invalid
    res2 = engine.validate_origin(
        InputOrigin(sender_id="mallory", channel="hermes_local"),
        "完成任务",
    )
    assert res2.valid is False
    assert res2.can_authorize_completion is False

    # 3. Telegram private chat with bound user -> valid & can authorize
    res3 = engine.validate_origin(
        InputOrigin(
            sender_id="tg_12345",
            channel="telegram",
            chat_type="private",
        ),
        "完成任务",
    )
    assert res3.valid is True
    assert res3.can_authorize_completion is True

    # 4. Telegram group chat -> valid to record fact, but CANNOT authorize completion
    res4 = engine.validate_origin(
        InputOrigin(
            sender_id="tg_12345",
            channel="telegram",
            chat_type="group",
        ),
        "完成任务",
    )
    assert res4.valid is True
    assert res4.can_authorize_completion is False
    assert "群聊" in res4.reason

    # 5. Telegram unbound user -> invalid
    res5 = engine.validate_origin(
        InputOrigin(
            sender_id="tg_intruder",
            channel="telegram",
            chat_type="private",
        ),
        "完成任务",
    )
    assert res5.valid is False

    # 6. Bot or Agent origin -> CANNOT authorize completion
    res6 = engine.validate_origin(
        InputOrigin(
            sender_id="alice",
            channel="hermes_local",
            is_bot_or_agent=True,
        ),
        "完成任务",
    )
    assert res6.valid is True
    assert res6.can_authorize_completion is False
    assert "机器人或其他 Agent" in res6.reason

    # 7. Forward or quote origin -> CANNOT authorize completion
    res7 = engine.validate_origin(
        InputOrigin(
            sender_id="alice",
            channel="hermes_local",
            is_forward_or_quote=True,
        ),
        "完成任务",
    )
    assert res7.valid is True
    assert res7.can_authorize_completion is False
    assert "转述" in res7.reason

    # 8. Profile target mismatch -> invalid
    res8 = engine.validate_origin(
        InputOrigin(sender_id="alice", profile_target="yonc"),
        "完成任务",
    )
    assert res8.valid is False


def test_intent_detection(honc_env: dict[str, Any]) -> None:
    engine: HoncConversationEngine = honc_env["engine"]

    assert engine.detect_intent("写错了，刚才弄错了时间") == "correction"
    assert engine.detect_intent("撤回刚才的完成状态") == "correction"
    assert engine.detect_intent("查看今天做过什么？") == "inquiry"
    assert engine.detect_intent("看下今天的执行日报") == "inquiry"
    assert engine.detect_intent("喝水打卡 500ml") == "habit"
    assert engine.detect_intent("锻体深蹲 30 个") == "habit"
    assert engine.detect_intent("准备回合，果象是提交 PR") == "round_control"
    assert engine.detect_intent("开始专注番茄钟") == "round_control"
    assert engine.detect_intent("暂停回合") == "round_control"
    assert engine.detect_intent("结束回合") == "round_control"
    assert engine.detect_intent("完成了登录模块开发并通过测试") == "complete"
    assert engine.detect_intent("搞定了，所有用例通过") == "complete"

    # Negative qualifiers should not count as explicit completion
    assert engine.detect_intent("今天写了代码，但是还没完成") == "progress"
    assert engine.detect_intent("只完成了初稿，还差测试") == "progress"
    assert engine.detect_intent("正在做后端重构") == "progress"


def test_target_node_resolution(honc_env: dict[str, Any]) -> None:
    engine: HoncConversationEngine = honc_env["engine"]

    nodes = [
        {"id": "task-auth-001", "title": "开发用户鉴权模块", "work_type": "ACTION", "status": "DOING"},
        {"id": "task-auth-002", "title": "鉴权模块编写测试用例", "work_type": "ACTION", "status": "TODO"},
        {"id": "task-ui-003", "title": "侧边栏UI布局优化", "work_type": "ACTION", "status": "TODO"},
    ]

    # 1. Direct ID match
    r1 = engine.resolve_target_node("我已经修好了 task-auth-001 的问题", None, nodes)
    assert r1.resolved_node_id == "task-auth-001"
    assert r1.is_ambiguous is False

    # 2. Unique title keyword match
    r2 = engine.resolve_target_node("搞定了侧边栏UI布局优化", None, nodes)
    assert r2.resolved_node_id == "task-ui-003"
    assert r2.is_ambiguous is False

    # 3. Ambiguous title match ("鉴权模块" matches both auth-001 and auth-002)
    r3 = engine.resolve_target_node("鉴权模块搞定了", None, nodes)
    assert r3.resolved_node_id is None
    assert r3.is_ambiguous is True
    assert len(r3.candidates) == 2

    # 4. Fallback to active round task_id
    prep = engine.service.control_round(
        action="prepare",
        user_id="alice",
        task_id="task-auth-002",
        target_outcome="写用例",
        tiny_step="打开测试文件",
    )
    round_obj = engine.service.store.get_round(prep["round_id"])
    r4 = engine.resolve_target_node("弄完了，测试全绿", round_obj, nodes)
    assert r4.resolved_node_id == "task-auth-002"

    # 5. Single actionable ACTION node auto-match when no active round
    single_node = [{"id": "single-act", "title": "唯一步骤", "work_type": "ACTION", "status": "TODO"}]
    r5 = engine.resolve_target_node("做完了", None, single_node)
    assert r5.resolved_node_id == "single-act"


def test_conversation_satisfies_criteria_and_applies_completion(
    honc_env: dict[str, Any],
) -> None:
    engine: HoncConversationEngine = honc_env["engine"]
    graph: FakeGraphExecutionClient = honc_env["graph"]

    nodes = [
        {
            "id": "task-auth-impl",
            "title": "鉴权实现",
            "work_type": "ACTION",
            "status": "DOING",
            "done_when": "单元测试全部通过；实现Token刷新机制",
        }
    ]

    origin = InputOrigin(sender_id="alice", channel="hermes_local")
    msg = "鉴权实现完成了，单元测试全部通过，并且已经实现Token刷新机制！"

    res = engine.process_message(origin, msg, available_nodes=nodes, duration_seconds=1800)

    assert res.intent_kind == "complete"
    assert res.assessment_result == "SATISFIED"
    assert res.graph_update_status == "SUCCEEDED"
    assert res.task_id == "task-auth-impl"
    assert res.event_id is not None
    assert "✅" in res.reply_text

    # Verify Graph received the decision
    assert len(graph.decisions_submitted) == 1
    assert graph.decisions_submitted[0]["node_id"] == "task-auth-impl"
    assert graph.decisions_submitted[0]["action"] == "done"

    # Verify ledger recorded timed execution
    events = engine.service.store.list_events()
    assert len(events) >= 1
    assert events[0].actual_kind == ActualKind.TIMED
    assert events[0].actual_duration_seconds == 1800


def test_conversation_blocks_incomplete_criteria(honc_env: dict[str, Any]) -> None:
    engine: HoncConversationEngine = honc_env["engine"]
    graph: FakeGraphExecutionClient = honc_env["graph"]

    nodes = [
        {
            "id": "task-auth-impl",
            "title": "鉴权实现",
            "work_type": "ACTION",
            "status": "DOING",
            "done_when": "单元测试全部通过；实现Token刷新机制",
        }
    ]

    origin = InputOrigin(sender_id="alice", channel="hermes_local")
    # Only mentions test passed, omitted Token refresh mechanism
    msg = "鉴权实现完成了，单元测试全部通过。"

    res = engine.process_message(origin, msg, available_nodes=nodes)

    assert res.intent_kind == "insufficient_criteria"
    assert res.assessment_result == AssessmentResult.INSUFFICIENT
    assert res.next_action == "SATISFY_REMAINING_CRITERIA"
    assert "未满足项" in res.reply_text
    assert len(graph.decisions_submitted) == 0  # Graph not updated!

    # But execution fact IS recorded
    events = engine.service.store.list_events()
    assert len(events) >= 1
    assert events[0].outcome == msg


def test_conversation_blocks_unauthorized_origin_completion(
    honc_env: dict[str, Any],
) -> None:
    engine: HoncConversationEngine = honc_env["engine"]
    graph: FakeGraphExecutionClient = honc_env["graph"]

    nodes = [
        {
            "id": "task-auth-impl",
            "title": "鉴权实现",
            "work_type": "ACTION",
            "status": "DOING",
            "done_when": "代码审查通过",
        }
    ]

    # Telegram group chat trying to report completion
    origin = InputOrigin(
        sender_id="tg_12345",
        channel="telegram",
        chat_type="group",
    )
    msg = "鉴权实现完成了，代码审查通过"

    res = engine.process_message(origin, msg, available_nodes=nodes)

    assert res.intent_kind == "progress"
    assert "来源限制" in res.reply_text
    assert len(graph.decisions_submitted) == 0  # Forbidden to call Graph!

    # Execution fact recorded
    events = engine.service.store.list_events()
    assert len(events) >= 1


def test_conversation_blocks_ambiguous_and_unlinked_completion(
    honc_env: dict[str, Any],
) -> None:
    engine: HoncConversationEngine = honc_env["engine"]
    graph: FakeGraphExecutionClient = honc_env["graph"]

    nodes = [
        {"id": "act-1", "title": "任务一", "work_type": "ACTION", "status": "DOING"},
        {"id": "act-2", "title": "任务二", "work_type": "ACTION", "status": "DOING"},
    ]
    origin = InputOrigin(sender_id="alice", channel="hermes_local")

    # 1. Ambiguous completion
    res_amb = engine.process_message(origin, "完成了，验收通过", available_nodes=nodes)
    assert res_amb.intent_kind == "ambiguous_complete"
    assert res_amb.next_action == "CLARIFY_TARGET_TASK"
    assert "多个候选任务" in res_amb.reply_text
    assert len(graph.decisions_submitted) == 0

    # 2. Unlinked completion (no nodes available)
    res_unlink = engine.process_message(origin, "完成了，搞定", available_nodes=[])
    assert res_unlink.intent_kind == "unlinked_complete"
    assert "没有正在进行的任务" in res_unlink.reply_text
    assert len(graph.decisions_submitted) == 0


def test_conversation_blocks_non_action_and_review_nodes(
    honc_env: dict[str, Any],
) -> None:
    engine: HoncConversationEngine = honc_env["engine"]
    graph: FakeGraphExecutionClient = honc_env["graph"]
    origin = InputOrigin(sender_id="alice", channel="hermes_local")

    # 1. MILESTONE node
    nodes = [
        {
            "id": "ms-phase-1",
            "title": "第一阶段里程碑",
            "work_type": "MILESTONE",
            "status": "DOING",
            "done_when": "所有子任务完成",
        }
    ]
    res_ms = engine.process_message(origin, "第一阶段里程碑完成了！", available_nodes=nodes)
    assert res_ms.intent_kind == "blocked_non_action"
    assert "非 ACTION" in res_ms.reply_text
    assert len(graph.decisions_submitted) == 0

    # 2. REVIEW node
    nodes_rev = [
        {
            "id": "act-review-spec",
            "title": "规范复核审查",
            "work_type": "ACTION",
            "status": "REVIEW",
            "done_when": "复核通过",
        }
    ]
    res_rev = engine.process_message(origin, "规范复核审查完成了！", available_nodes=nodes_rev)
    assert res_rev.intent_kind == "blocked_review"
    assert "REVIEW" in res_rev.reply_text
    assert len(graph.decisions_submitted) == 0


def test_conversation_round_lifecycle_and_inquiry(honc_env: dict[str, Any]) -> None:
    engine: HoncConversationEngine = honc_env["engine"]
    origin = InputOrigin(sender_id="alice", channel="hermes_local")

    # 1. Prepare round
    r1 = engine.process_message(origin, "准备写新功能接口，果象是接口通过测试")
    assert r1.intent_kind == "round_control"
    assert r1.next_action == "START_ROUND"

    # 2. Start round
    r2 = engine.process_message(origin, "开始番茄钟")
    assert r2.intent_kind == "round_control"
    active_rnd = engine.service.store.get_active_round("alice")
    assert active_rnd is not None
    assert active_rnd.status == RoundStatus.RUNNING

    # 3. Pause round
    r3 = engine.process_message(origin, "暂停回合")
    assert r3.intent_kind == "round_control"
    assert engine.service.store.get_active_round("alice").status == RoundStatus.PAUSED

    # 4. End round
    r4 = engine.process_message(origin, "结束回合，完成了接口第一版")
    assert r4.intent_kind == "round_control"
    assert engine.service.store.get_active_round("alice") is None

    # 5. Inquiry report
    r5 = engine.process_message(origin, "今天做过什么？查看日报")
    assert r5.intent_kind == "inquiry"
    assert "今日执行概况" in r5.reply_text


def test_conversation_habit_and_correction(honc_env: dict[str, Any]) -> None:
    engine: HoncConversationEngine = honc_env["engine"]
    origin = InputOrigin(sender_id="alice", channel="hermes_local")

    # 1. Habit tick
    h_res = engine.process_message(origin, "喝水打卡 300ml")
    assert h_res.intent_kind == "habit"
    assert "打卡已记录" in h_res.reply_text

    # 2. Correction
    c_res = engine.process_message(origin, "弄错了，刚才喝水其实只有 150ml")
    assert c_res.intent_kind == "correction"
    assert "已追加修正事实" in c_res.reply_text

    # Events history has habit tick + correction event
    events = engine.service.store.list_events()
    assert len(events) >= 2
