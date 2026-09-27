"""Fail-closed delegation guard for the UuMA Orchestrator.

The model-facing policy is useful guidance, but this hook is the enforcement
boundary.  A delegation spawn is allowed only after a task was created,
routed, and assigned successfully through the UuMA Control MCP in the same
Hermes session.  Live delegation control actions remain available so an
operator can inspect, steer, or stop work already in flight.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HEALTH_INTERVAL_SECONDS = 300.0
_MAX_TRACKED_SESSIONS = 512
_LOCK = threading.RLock()


@dataclass
class _SessionState:
    created: set[str] = field(default_factory=set)
    routed: set[str] = field(default_factory=set)
    ready: list[str] = field(default_factory=list)
    last_health_check: float = 0.0
    health_ok: bool = False
    direct_run_id: str | None = None
    direct_task_id: str | None = None
    direct_turn_id: str | None = None
    direct_attempted: bool = False
    domain_checked: bool = False
    kag_degraded: bool = False
    result_submitted: bool = False
    graph_ready: bool = False
    pending_topic_question: str | None = None
    approved_topic_question: str | None = None
    wisdom_intent_resolved: bool = False
    wisdom_answer: dict[str, Any] | None = None
    wisdom_document_url: str | None = None
    wisdom_orbit_status: str | None = None
    wisdom_runner_wake: dict[str, Any] | None = None
    wisdom_status: dict[str, Any] | None = None
    brainstormer_capacity_attempted: bool = False
    brainstormer_capacity_result: dict[str, Any] | None = None
    brainstormer_capacity_required: bool = False
    brainstormer_structure_status: str | None = None


_SESSIONS: OrderedDict[str, _SessionState] = OrderedDict()
_CONTEXT: Any = None
_DIRECT_SPECIALISTS = {"brainstormer", "wisdom-oldman", "scholar", "forge-lab-bot", "yonc"}
_DOMAIN_PREFLIGHT = {
    "brainstormer": ("uuma-worker", "brainstormer_search_topics"),
    "wisdom-oldman": ("wisdom-knowledge", "knowledge_question_preflight"),
    "scholar": ("rstv4-worker", "list_catalog_papers"),
    "forge-lab-bot": ("uuma-worker", "inventory_status"),
    "yonc": ("yonc-project", "yonc_status"),
}
_SPECIALIST_FORBIDDEN_TOOLS = {
    "delegate_task",
    "computer_use",
    "terminal",
    "execute_shell",
    "write_file",
    "edit_file",
    "apply_patch",
    "delete_file",
}
_FORGE_DIRECT_FORBIDDEN = {
    "procurement_confirm_order",
    "eschematic_commit_candidate",
    "inventory_receive",
    "inventory_transition",
    "inventory_adjust",
    "lab_create_build",
    "lab_update_build_status",
    "lab_record_commissioning",
    "lab_record_worklog",
    "lab_record_failure",
    "lab_journal_register_snapshot",
    "lab_journal_queue_write",
    "lab_journal_claim_write",
    "lab_journal_finish_write",
    "lab_journal_request_resync",
    "lab_journal_claim_notification",
    "lab_journal_finish_notification",
}
_LOGGER = logging.getLogger(__name__)


def _profile() -> str:
    try:
        from hermes_constants import get_hermes_home_override

        home = get_hermes_home_override()
        if home:
            path = Path(home)
            if path.parent.name.lower() == "profiles":
                return path.name.lower()
            return "orchestrator"
    except ImportError:
        pass
    value = os.environ.get("HERMES_PROFILE") or os.environ.get("HERMES_PROFILE_NAME")
    if not value:
        home = os.environ.get("HERMES_HOME", "")
        path = Path(home) if home else None
        value = path.name if path and path.parent.name.lower() == "profiles" else "default"
    return "orchestrator" if value == "default" else value


def _session_key(kwargs: dict[str, Any]) -> str:
    return str(kwargs.get("session_id") or kwargs.get("task_id") or "unknown")


def _state(key: str) -> _SessionState:
    state = _SESSIONS.get(key)
    if state is None:
        state = _SessionState()
        _SESSIONS[key] = state
        while len(_SESSIONS) > _MAX_TRACKED_SESSIONS:
            _SESSIONS.popitem(last=False)
    else:
        _SESSIONS.move_to_end(key)
    return state


def _normalized_tool_name(tool_name: Any) -> str:
    return str(tool_name or "").strip().lower().replace("-", "_").replace(".", "_")


def _control_operation(tool_name: Any) -> str | None:
    name = _normalized_tool_name(tool_name)
    if "uuma_control" not in name:
        return None
    for operation in ("create_task", "route_task", "assign_task"):
        if name.endswith(operation):
            return operation
    return None


def _is_delegation_spawn(tool_name: Any, args: Any) -> bool:
    name = _normalized_tool_name(tool_name)
    if name == "delegate_task":
        action = str((args or {}).get("action") or "spawn").strip().lower()
        return action in {"", "spawn"}
    return name.startswith(("mcp__uuma_worker__", "mcp__rstv4_worker__"))


def _delegation_count(args: Any) -> int:
    if not isinstance(args, dict):
        return 1
    tasks = args.get("tasks")
    return max(1, len(tasks)) if isinstance(tasks, list) else 1


def _decoded(value: Any) -> Any:
    current = value
    for _ in range(4):
        if not isinstance(current, str):
            return current
        try:
            current = json.loads(current)
        except (TypeError, ValueError):
            return current
    return current


def _topic_proposal(value: Any) -> str | None:
    value = _decoded(value)
    if isinstance(value, dict):
        if value.get("requires_topic_approval") is True:
            proposal = value.get("proposed_topic", {})
            if isinstance(proposal, dict) and isinstance(proposal.get("question"), str):
                return proposal["question"]
        for key in ("result", "structuredContent", "structured_content", "content", "text"):
            if key in value:
                found = _topic_proposal(value[key])
                if found:
                    return found
    if isinstance(value, list):
        for item in value:
            found = _topic_proposal(item)
            if found:
                return found
    return None


def _capture_topic_consent(state: _SessionState, message: str) -> None:
    reply = message.casefold().strip().rstrip(".!。！")
    affirmative = reply in {
        "yes", "yes please", "yes, please", "approve", "approved", "go ahead",
        "ok", "okay", "好的", "好", "同意", "可以", "确认", "同意建立",
        "同意建主题", "同意建立主题",
    }
    state.approved_topic_question = state.pending_topic_question if affirmative else None
    state.pending_topic_question = None


def _find_task_id(value: Any) -> str | None:
    value = _decoded(value)
    if isinstance(value, dict):
        task_id = value.get("task_id")
        if isinstance(task_id, str) and task_id.strip():
            return task_id.strip()
        for key in ("structuredContent", "structured_content", "result", "content"):
            if key in value:
                found = _find_task_id(value[key])
                if found:
                    return found
    if isinstance(value, list):
        for item in value:
            found = _find_task_id(item)
            if found:
                return found
    return None


def _find_run_id(value: Any) -> str | None:
    value = _decoded(value)
    if isinstance(value, dict):
        run_id = value.get("run_id")
        if isinstance(run_id, str) and run_id.strip():
            return run_id.strip()
        for key in ("structuredContent", "structured_content", "result", "content"):
            if key in value:
                found = _find_run_id(value[key])
                if found:
                    return found
    if isinstance(value, list):
        for item in value:
            found = _find_run_id(item)
            if found:
                return found
    return None


def _succeeded(kwargs: dict[str, Any]) -> bool:
    status = str(kwargs.get("status") or "ok").strip().lower()
    if status not in {"", "ok", "success", "completed"}:
        return False
    if kwargs.get("error_message"):
        return False
    value = _decoded(kwargs.get("result"))
    return not _contains_error(value)


def _contains_error(value: Any) -> bool:
    value = _decoded(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized.startswith("error") or "error executing tool" in normalized
    if isinstance(value, dict):
        if value.get("ok") is False or value.get("isError") is True or value.get("is_error") is True:
            return True
        if "error" in value and value.get("error") not in (None, "", False):
            return True
        return any(_contains_error(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_error(item) for item in value)
    return False


def _runtime_status(value: Any) -> str | None:
    value = _decoded(value)
    if isinstance(value, dict):
        status = value.get("runtime_status")
        if isinstance(status, str):
            return status
        for key in ("result", "structuredContent", "structured_content", "content"):
            if key in value:
                found = _runtime_status(value[key])
                if found:
                    return found
    if isinstance(value, list):
        for item in value:
            found = _runtime_status(item)
            if found:
                return found
    return None


def _result_field(value: Any, field_name: str) -> Any:
    value = _decoded(value)
    if isinstance(value, dict):
        if field_name in value:
            return value[field_name]
        for key in ("result", "structuredContent", "structured_content", "content", "text"):
            if key in value:
                found = _result_field(value[key], field_name)
                if found is not None:
                    return found
    if isinstance(value, list):
        for item in value:
            found = _result_field(item, field_name)
            if found is not None:
                return found
    return None


def _brainstormer_capacity_receipt(value: Any) -> dict[str, Any] | None:
    scenario = _result_field(value, "scenario")
    if not isinstance(scenario, dict):
        return None
    keys = (
        "required_sold_kg_per_month", "required_harvested_kg_per_month",
        "sold_kg_per_harvest_batch", "minimum_blocks", "planned_blocks_suffice",
        "net_planting_square_metres_per_block", "net_planting_square_feet_per_block",
        "net_planting_square_metres_total", "gross_land_square_metres",
        "gross_land_square_feet", "gross_land_acres", "sold_kg_per_delivery",
    )
    receipt = {key: _result_field(value, key) for key in keys}
    if any(receipt[key] is None for key in keys if key != "planned_blocks_suffice"):
        return None
    return {"scenario": scenario, **receipt}


def _brainstormer_capacity_reply(receipt: dict[str, Any], response_text: str) -> str:
    scenario = receipt["scenario"]
    minimum = receipt["minimum_blocks"]
    planned = scenario.get("planned_blocks")
    if re.search(r"[\u4e00-\u9fff]", response_text):
        planned_line = (
            f"你计划的 {planned} 块{'够用' if receipt['planned_blocks_suffice'] else '不够'}；"
            if planned is not None else ""
        )
        return (
            "按你提供的假设计算（价格、成本和单产尚未独立验证）：\n"
            f"- 月需售出 {receipt['required_sold_kg_per_month']:,.2f} kg；"
            f"按 {scenario['sellable_fraction']:.0%} 可售率，月需收获 "
            f"{receipt['required_harvested_kg_per_month']:,.2f} kg。\n"
            f"- 每 {scenario['harvest_interval_days']:g} 天收一批，每批需可售 "
            f"{receipt['sold_kg_per_harvest_batch']:,.2f} kg；每周送货 "
            f"{scenario['deliveries_per_week']:g} 次，每次平均 "
            f"{receipt['sold_kg_per_delivery']:,.2f} kg。送货次数不等于收获批次数。\n"
            f"- 生长加整地共 {scenario['growth_days'] + scenario['turnaround_days']:g} 天，"
            f"以 {scenario['harvest_interval_days']:g} 天为一批，至少需 {minimum} 块。"
            f"{planned_line}\n"
            f"- 每块净种植面积约 {receipt['net_planting_square_metres_per_block']:,.2f} m² "
            f"（{receipt['net_planting_square_feet_per_block']:,.0f} 平方尺）；"
            f"{minimum} 块合计净种植面积 "
            f"{receipt['net_planting_square_metres_total']:,.2f} m²。"
            f"按 {scenario['planted_area_fraction']:.0%} 净种植占比，总地约 "
            f"{receipt['gross_land_square_metres']:,.2f} m² "
            f"（{receipt['gross_land_square_feet']:,.0f} 平方尺，"
            f"{receipt['gross_land_acres']:.3f} 英亩）。\n"
            "这是营业利润情景算术；税、融资及设备回本须计入成本后才可称为净收益预测。"
        )
    planned_line = (
        f"Your {planned} planned blocks are "
        f"{'enough' if receipt['planned_blocks_suffice'] else 'insufficient'}. "
        if planned is not None else ""
    )
    return (
        "Scenario arithmetic using your unverified price, cost, and yield inputs:\n"
        f"- Sell {receipt['required_sold_kg_per_month']:,.2f} kg/month and harvest "
        f"{receipt['required_harvested_kg_per_month']:,.2f} kg/month.\n"
        f"- Harvest {receipt['sold_kg_per_harvest_batch']:,.2f} sellable kg every "
        f"{scenario['harvest_interval_days']:g} days; deliver "
        f"{receipt['sold_kg_per_delivery']:,.2f} kg on each of "
        f"{scenario['deliveries_per_week']:g} weekly deliveries. Delivery and harvest "
        "cadences are separate.\n"
        f"- Growth plus turnaround is "
        f"{scenario['growth_days'] + scenario['turnaround_days']:g} days, so at least "
        f"{minimum} blocks are needed. {planned_line}\n"
        f"- Net planted area per block: "
        f"{receipt['net_planting_square_metres_per_block']:,.2f} m² "
        f"({receipt['net_planting_square_feet_per_block']:,.0f} sq ft). "
        f"Gross land: {receipt['gross_land_square_metres']:,.2f} m² "
        f"({receipt['gross_land_acres']:.3f} acres).\n"
        "This is an operating-profit scenario; include tax, financing, and capital recovery "
        "in costs before treating it as a net-income forecast."
    )


def _brainstormer_capacity_question(message: str) -> bool:
    text = message.casefold()
    area = any(term in text for term in (
        "面积", "每块", "区块", "英亩", "平方尺", "多大的地", "亩", "area", "acre",
        "plot", "blocks", "block",
    ))
    objective = any(term in text for term in (
        "利润", "赚", "收入", "产量", "收获", "供货", "种植", "profit", "yield",
        "harvest", "plant", "supply",
    ))
    return area and objective


def _brainstormer_unchecked_capacity_claim(response_text: str) -> bool:
    return bool(
        re.search(
            r"\d[\d,.]*\s*(?:平方米|平方尺|m²|亩|英亩|acres?|sq\.?\s*ft|"
            r"平方公尺)|\d+\s*块.{0,25}(?:够|可行|足够|不足|不够)",
            response_text,
            flags=re.IGNORECASE,
        )
    )


def _explicit_research_request(message: str) -> bool:
    """Only route clear knowledge requests automatically; uncertain intent stays model-resolved."""
    text = message.casefold().strip()
    if len(text) < 5 or text in {"okay", "好的", "thank you", "谢谢"}:
        return False
    if any(word in text for word in (
        "404", "error", "报错", "错误", "打不开", "无法访问", "进度", "研究中",
        "topic 在进行", "topic进行", "状态", "暂停", "停止", "恢复",
    )):
        return False
    return any(word in text for word in (
        "我想了解", "我想知道", "请研究", "针对", "种植", "栽培", "如何", "怎么",
        "怎样", "是什么", "要多少", "为什么", "细节", "研究", "how ", "what ",
        "why ", "?", "？",
    ))


def _remember_wisdom_result(state: _SessionState, value: Any) -> None:
    global_status = _result_field(value, "global_status")
    if isinstance(global_status, dict):
        state.wisdom_status = global_status
    answer = _result_field(value, "answer")
    if isinstance(answer, dict) and isinstance(answer.get("answer"), str):
        state.wisdom_answer = answer
        document_url = _result_field(value, "document_url")
        state.wisdom_document_url = document_url if isinstance(document_url, str) else None
        status = _result_field(value, "orbit_status")
        state.wisdom_orbit_status = status if isinstance(status, str) else None
        wake = _result_field(value, "runner_wake")
        state.wisdom_runner_wake = wake if isinstance(wake, dict) else None


def _wisdom_grounded_reply(state: _SessionState) -> str | None:
    answer = state.wisdom_answer
    if not answer:
        return None
    parts = [str(answer["answer"]).strip()]
    for citation in list(answer.get("citations") or [])[:3]:
        if isinstance(citation, dict):
            locator = str(citation.get("locator") or "")
            if locator.startswith(("https://", "http://")):
                parts.append(f"来源：{locator}")
    if state.wisdom_orbit_status == "QUEUED":
        if state.wisdom_runner_wake and state.wisdom_runner_wake.get("requested"):
            parts.append("后续研究已排队，已请求启动后台研究；运行尚未确认。")
        else:
            parts.append("后续研究已排队，但后台研究进程尚未确认启动。")
    elif state.wisdom_orbit_status == "ACTIVE":
        parts.append("后续研究正在进行。")
    if state.wisdom_document_url:
        parts.append(f"主题文档：{state.wisdom_document_url}")
    return "\n\n".join(part for part in parts if part)


def _wisdom_status_reply(state: _SessionState) -> str | None:
    status = state.wisdom_status
    if not status:
        return None
    active = status.get("active") or []
    paused = status.get("paused") or []
    lines = ["当前正在研究的主题：" if active else "当前没有正在研究的主题。"]
    for item in active[:10]:
        if isinstance(item, dict):
            lines.append(f"- {item.get('topic_title') or '未命名主题'}（{item.get('status')}）")
            if item.get("document_url"):
                lines.append(f"  文档：{item['document_url']}")
    if paused:
        lines.append("\n已暂停或受阻：")
        for item in paused[:10]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('topic_title') or '未命名主题'}（{item.get('status')}）")
    return "\n".join(lines)


def _check_graph(*, recover: bool = True, **kwargs: Any) -> bool:
    if _profile() not in {"scholar", "wisdom-oldman"}:
        return True
    ready = False
    try:
        if _CONTEXT is not None:
            receipt = _CONTEXT.call_mcp(
                "uuma-worker", "knowledge_runtime_preflight", {"recover": recover},
                timeout=420 if recover else 45,
            )
            ready = (
                bool(receipt.get("ok")) and not _contains_error(receipt)
                and _graph_ready(receipt.get("result"))
            )
    except Exception:  # noqa: BLE001 - runtime failures must block knowledge work
        _LOGGER.warning("Knowledge graph preflight failed for %s", _profile())
    with _LOCK:
        _state(_session_key(kwargs)).graph_ready = ready
    return ready


def _graph_ready(value: Any) -> bool:
    if isinstance(value, str):
        try:
            return _graph_ready(json.loads(value))
        except ValueError:
            return False
    if isinstance(value, dict):
        if "ready" in value:
            return value["ready"] is True
        return any(_graph_ready(value.get(k)) for k in ("result", "structuredContent", "content", "text"))
    if isinstance(value, list):
        return any(_graph_ready(item) for item in value)
    return False


def _health_context(**kwargs: Any) -> dict[str, str] | None:
    if _profile() in _DIRECT_SPECIALISTS:
        profile = _profile()
        with _LOCK:
            state = _state(_session_key(kwargs))
            turn_id = str(kwargs.get("turn_id") or "")
            new_turn = bool(turn_id and state.direct_turn_id != turn_id)
            if new_turn:
                state.direct_turn_id = turn_id
                state.direct_run_id = None
                state.direct_task_id = None
                state.direct_attempted = False
                state.domain_checked = False
                state.kag_degraded = False
                state.result_submitted = False
                state.graph_ready = False
                state.wisdom_intent_resolved = False
                state.wisdom_answer = None
                state.wisdom_document_url = None
                state.wisdom_orbit_status = None
                state.wisdom_runner_wake = None
                state.wisdom_status = None
                state.brainstormer_capacity_attempted = False
                state.brainstormer_capacity_result = None
                state.brainstormer_capacity_required = False
                state.brainstormer_structure_status = None
            if profile == "brainstormer":
                state.brainstormer_capacity_required = _brainstormer_capacity_question(
                    str(kwargs.get("user_message") or "")
                )
            if profile == "wisdom-oldman" and (new_turn or not state.direct_attempted):
                _capture_topic_consent(state, str(kwargs.get("user_message") or ""))
            attempted = state.direct_attempted
            state.direct_attempted = True
            registered = state.direct_run_id
        if not attempted and not registered and not kwargs.get("parent_session_id"):
            message = str(kwargs.get("user_message") or "").strip()[:8000]
            if message and _CONTEXT is not None:
                reversible_forge = profile == "forge-lab-bot"
                contract = {
                    "title": message[:240],
                    "objective": (
                        "Respond within safe reversible specialist boundaries: " + message
                        if reversible_forge
                        else "Respond within read-only or proposal-only specialist boundaries: " + message
                    )[:8000],
                    "source": "direct",
                    "risk_level": "REVERSIBLE" if reversible_forge else "READ_ONLY",
                    "requested_by": "user",
                }
                try:
                    result = _CONTEXT.call_mcp(
                        "uuma-worker",
                        "register_direct_run",
                        {"contract_json": json.dumps(contract, ensure_ascii=False)},
                        timeout=20,
                    )
                    run_id = _find_run_id(result) if result.get("ok") else None
                    if run_id:
                        with _LOCK:
                            state = _state(_session_key(kwargs))
                            state.direct_run_id = run_id
                            state.direct_task_id = _find_task_id(result)
                        registered = run_id
                    else:
                        _LOGGER.warning(
                            "Direct Run registration did not return a run_id (ok=%s, error=%s)",
                            result.get("ok"),
                            str(result.get("error") or "none")[:160],
                        )
                except Exception as exc:  # noqa: BLE001 - fail closed if Worker MCP is unavailable
                    _LOGGER.warning("Direct Run registration failed: %s", type(exc).__name__)
        if not registered:
            return {
                "context": (
                    "UuMA specialist direct-chat boundary: automatic Direct Run registration failed. "
                    "Before domain work, call "
                    "mcp__uuma_worker__register_direct_run with a TaskContract using source=direct, "
                    "a safe risk_level, and this user's objective. If this is an Orchestrator "
                    "assignment instead, call mcp__uuma_worker__get_assignment with its task_id. "
                    "If registration fails, explain the blocker rather than answering from "
                    "untracked work. Use your profile's semantic domain MCP before answering. "
                    "Report progress and submit a result through Worker MCP before completing work."
                )
            }
        with _LOCK:
            task_id = _state(_session_key(kwargs)).direct_task_id
        identity_context = (
            "Worker MCP reporting identity: "
            + json.dumps(
                {"run_id": registered, "task_id": task_id, "agent_id": profile},
                ensure_ascii=False,
            )
            + ". Include these exact identifiers in progress_json and result_json. "
        )
        domain_result: Any = None
        if not attempted and not _check_graph(**kwargs):
            return {"context": identity_context + (
                "Knowledge graph unavailable after recovery. Domain work is BLOCKED. "
                "Do not use model-only or text-only fallback, start research, or claim completion. "
                "Report the blocker through Worker MCP."
            )}
        if not attempted and _CONTEXT is not None:
            message = str(kwargs.get("user_message") or "").strip()
            server, tool = _DOMAIN_PREFLIGHT[profile]
            with _LOCK:
                approved_topic = _state(_session_key(kwargs)).approved_topic_question
            arguments = {
                "brainstormer": {"query": message, "limit": 5},
                "wisdom-oldman": {
                    "question": approved_topic or message,
                    "mode": "SIMPLE",
                    "recover_runtime": False,
                    "intent": (
                        "research" if approved_topic or _explicit_research_request(message)
                        else "auto"
                    ),
                    "topic_creation_approved": bool(approved_topic),
                    "uuma_task_id": state.direct_task_id or "",
                    "uuma_run_id": state.direct_run_id or "",
                    "notification_route_json": json.dumps(
                        {
                            key: str(kwargs[key])
                            for key in ("platform", "chat_id", "thread_id", "session_id")
                            if kwargs.get(key)
                        },
                        ensure_ascii=False,
                    ),
                },
                "scholar": {"limit": 5},
                "forge-lab-bot": {},
                "yonc": {},
            }[profile]
            try:
                timeout = 420 if profile == "wisdom-oldman" else 20
                domain_result = _CONTEXT.call_mcp(server, tool, arguments, timeout=timeout)
                if domain_result.get("ok") and not _contains_error(domain_result):
                    with _LOCK:
                        state = _state(_session_key(kwargs))
                        state.domain_checked = True
                        if profile == "wisdom-oldman":
                            state.kag_degraded = _runtime_status(domain_result) == "DEGRADED_KAG"
                            state.wisdom_intent_resolved = (
                                arguments["intent"] == "research"
                                or _result_field(domain_result, "message_intent")
                                in {"status", "feedback", "conversation"}
                            )
                            proposal = _topic_proposal(domain_result)
                            if proposal:
                                state.pending_topic_question = proposal
                            _remember_wisdom_result(state, domain_result)
                            if approved_topic:
                                state.approved_topic_question = None
                else:
                    _LOGGER.warning(
                        "Specialist domain preflight failed for %s/%s: %s",
                        server,
                        tool,
                        str(domain_result.get("error") or "invalid response")[:300],
                    )
            except Exception as exc:  # noqa: BLE001 - unanswered domain lookup must not become fake evidence
                _LOGGER.warning(
                    "Specialist domain preflight raised for %s/%s: %s",
                    server,
                    tool,
                    type(exc).__name__,
                )
        if domain_result is not None and domain_result.get("ok"):
            forge_capture = (
                " If the user wants to record actual lab work, use the lab-worklog conversational "
                "intake: infer Problem/Experiment/Repair/Build, ask only for missing facts, then "
                "call lab_journal_capture_chat once the record is complete. Do not capture generic "
                "advice, hypothetical planning, sourcing discussion, or a user opt-out."
                if profile == "forge-lab-bot"
                else ""
            )
            brainstormer_guidance = (
                " Brainstormer: the latest user correction supersedes earlier assistant estimates. "
                "Answer the current question first. For numerical plans, reverse from the user's "
                "target; distinguish user facts, sourced evidence, and hypothetical inputs. "
                "Do not infer producer price from retail price or net profit from gross margin. "
                "Separate delivery cadence from harvest and planting cadence. Use "
                "brainstormer_calculate_capacity only with complete inputs; otherwise show the "
                "missing variables and a provisional equation. "
                "If complete numeric inputs are present, you MUST call the directly available "
                "mcp__uuma_worker__brainstormer_calculate_capacity before giving an area or "
                "block-sufficiency conclusion; do not use tool_search. "
                "An empty topic search means no "
                "canonical topic was found, not that the conversation is forgotten. For a "
                "substantial new project discussion, call the directly available "
                "brainstormer_propose_project_topic; it remains pending Orchestrator review. "
                "Propose other meaningful state changes through the State Manager. "
                "Never claim another Agent "
                "was called unless an actual tool receipt confirms it."
                if profile == "brainstormer"
                else ""
            )
            return {
                "context": (
                    f"UuMA Direct Run {registered} is registered. {identity_context}"
                    f"{tool} returned: "
                    f"{json.dumps(domain_result.get('result'), ensure_ascii=False, default=str)[:6000]}. "
                    "This is preflight context, not proof of the user's requested claim. "
                    "Use further semantic domain MCP tools as needed, preserve provenance, "
                    "and disclose degraded or incomplete coverage. "
                    "For Wisdom-Oldman, intake is read-only. If needs_intent_resolution is true, "
                    "interpret the message using conversation context: progress reads current_status; "
                    "feedback/errors/conversation must not create topics. Only genuine research "
                    "requests call knowledge_question_preflight again with intent=research and "
                    "the resolved question, preserving returned route/task/run arguments. "
                    "Answer directly and include a document link only when relevant. "
                    "A new topic requires separate user permission: show proposed title and scope, "
                    "ask to create it, and wait. Never set topic_creation_approved on the proposal "
                    "turn. On a later explicit yes to the pending proposal, repeat its exact "
                    "question with intent=research and topic_creation_approved=true. "
                    "Promise continued research only when an orbit_id and "
                    "persisted status were returned. "
                    f"Report progress and submit the result through Worker MCP."
                    f"{forge_capture}{brainstormer_guidance}"
                )
            }
        return {
            "context": (
                f"UuMA Direct Run {registered} is registered, but the domain lookup did not "
                f"succeed. {identity_context}"
                "Call the appropriate semantic MCP tool and report a blocker if it fails."
            )
        }
    if _profile() != "orchestrator":
        return None
    key = _session_key(kwargs)
    now = time.monotonic()
    with _LOCK:
        state = _state(key)
        if now - state.last_health_check < _HEALTH_INTERVAL_SECONDS:
            return None
        state.last_health_check = now
    try:
        result = _CONTEXT.call_mcp("uuma-control", "system_health", {}, timeout=30)
        healthy = bool(result.get("ok")) if isinstance(result, dict) else False
    except Exception:  # noqa: BLE001 - the guard reports failure to the model and stays fail-closed
        healthy = False
    with _LOCK:
        _state(key).health_ok = healthy
    if healthy:
        return None
    return {
        "context": (
            "UuMA control-plane health check failed. Do not delegate specialist work. "
            "Call mcp__uuma_control__system_health and recover the Control MCP first."
        )
    }


def _pre_tool_call(tool_name: str = "", args: Any = None, **kwargs: Any) -> dict[str, str] | None:
    bridge_tool = "chatgpt_bridge" in _normalized_tool_name(tool_name)
    if bridge_tool and (
        _profile() in {"scholar", "yonc"}
        or (_profile() == "forge-lab-bot"
            and _normalized_tool_name(tool_name).endswith("chatgpt_request")
            and (args or {}).get("mode", "chat") != "search")
    ):
        return {"action": "block", "message": "ChatGPT bridge capability denied for this profile."}
    if _profile() in _DIRECT_SPECIALISTS:
        name = _normalized_tool_name(tool_name)
        if _profile() == "brainstormer" and name.endswith("brainstormer_calculate_capacity"):
            with _LOCK:
                _state(_session_key(kwargs)).brainstormer_capacity_attempted = True
        if (
            _profile() == "wisdom-oldman"
            and name.endswith("knowledge_question_preflight")
            and (args or {}).get("topic_creation_approved")
        ):
            with _LOCK:
                approved = _state(_session_key(kwargs)).approved_topic_question
            if not approved or str((args or {}).get("question") or "").strip() != approved:
                return {"action": "block", "message": (
                    "Creating a topic requires the user's explicit approval of the pending "
                    "proposal in a later turn. Do not claim or infer that approval."
                )}
        if (
            name in _SPECIALIST_FORBIDDEN_TOOLS
            or name.startswith("mcp__uuma_control__")
            or name.endswith(("knowledge_apply_patch", "knowledge_reverse_patch"))
            or (_profile() == "forge-lab-bot" and any(name.endswith(tool) for tool in _FORGE_DIRECT_FORBIDDEN))
        ):
            return {
                "action": "block",
                "message": (
                    "Blocked by UuMA specialist policy: control, computer, file mutation, and "
                    "canonical approval actions belong to the Orchestrator/user review boundary."
                ),
            }
        if name.endswith(("register_direct_run", "get_assignment")) and "uuma_worker" in name:
            return None
        with _LOCK:
            registered = bool(_state(_session_key(kwargs)).direct_run_id)
        if not registered:
            return {
                "action": "block",
                "message": (
                    "Blocked by UuMA specialist policy: register a safe Direct Run via "
                    "mcp__uuma_worker__register_direct_run, or validate an Orchestrator assignment "
                    "via mcp__uuma_worker__get_assignment, before using other tools."
                ),
            }
        if _profile() in {"scholar", "wisdom-oldman"}:
            if "uuma_worker" in name and name.endswith(
                ("knowledge_runtime_preflight", "report_progress", "block_run")
            ):
                return None
            if "uuma_worker" in name and name.endswith("submit_result"):
                try:
                    outcome = json.loads((args or {}).get("result_json", "{}" )).get("outcome")
                except (ValueError, TypeError):
                    outcome = None
                if outcome in {"FAILED", "BLOCKED", "CANCELLED"}:
                    return None
            if not _check_graph(**kwargs):
                return {"action": "block", "message": (
                    "Knowledge graph unavailable. Recovery failed; report BLOCKED. "
                    "Knowledge work and completed results require the specialist's own graph."
                )}
        return None
    if _profile() != "orchestrator" or not _is_delegation_spawn(tool_name, args):
        return None
    required = _delegation_count(args)
    with _LOCK:
        state = _state(_session_key(kwargs))
        available = len(state.ready)
    if available >= required:
        return None
    return {
        "action": "block",
        "message": (
            "Blocked by UuMA control policy: specialist delegation requires a successful "
            "mcp__uuma_control__create_task, route_task, and assign_task sequence in this "
            f"session. Ready task contracts: {available}; required for this spawn: {required}. "
            "Create and assign the missing task contract(s), then retry delegation."
        ),
    }


def _post_tool_call(tool_name: str = "", args: Any = None, **kwargs: Any) -> None:
    if not _succeeded(kwargs):
        return
    key = _session_key(kwargs)
    if _profile() in _DIRECT_SPECIALISTS:
        name = _normalized_tool_name(tool_name)
        if _profile() == "brainstormer" and name.endswith("brainstormer_calculate_capacity"):
            receipt = _brainstormer_capacity_receipt(kwargs.get("result"))
            if receipt:
                with _LOCK:
                    _state(key).brainstormer_capacity_result = receipt
        if _profile() == "brainstormer" and name.endswith("brainstormer_propose_project_topic"):
            status = _result_field(kwargs.get("result"), "status")
            if isinstance(status, str):
                with _LOCK:
                    _state(key).brainstormer_structure_status = status
        if _profile() == "wisdom-oldman" and name.endswith("knowledge_question_preflight"):
            proposal = _topic_proposal(kwargs.get("result"))
            with _LOCK:
                state = _state(key)
                if proposal:
                    state.pending_topic_question = proposal
                if (args or {}).get("intent") == "research" or _result_field(
                    kwargs.get("result"), "message_intent"
                ) in {"status", "feedback", "conversation"}:
                    state.wisdom_intent_resolved = True
                _remember_wisdom_result(state, kwargs.get("result"))
                if (args or {}).get("topic_creation_approved"):
                    state.approved_topic_question = None
        if "uuma_worker" in name and name.endswith("knowledge_runtime_preflight"):
            with _LOCK:
                _state(key).graph_ready = _graph_ready(kwargs.get("result"))
            return
        if "uuma_worker" in name and name.endswith("register_direct_run"):
            run_id = _find_run_id(kwargs.get("result"))
            if run_id:
                with _LOCK:
                    state = _state(key)
                    state.direct_run_id = run_id
                    state.direct_task_id = _find_task_id(kwargs.get("result"))
        elif "uuma_worker" in name and name.endswith("get_assignment"):
            task_id = _find_task_id(kwargs.get("result"))
            if task_id:
                with _LOCK:
                    _state(key).direct_run_id = f"assignment:{task_id}"
        elif (
            name.endswith(_DOMAIN_PREFLIGHT[_profile()][1])
            or (_profile() == "brainstormer" and name.endswith("brainstormer_get_context"))
            or (_profile() == "wisdom-oldman" and name.endswith("knowledge_answer"))
        ):
            with _LOCK:
                state = _state(key)
                state.domain_checked = True
                if _profile() == "wisdom-oldman" and name.endswith(
                    ("knowledge_answer", "knowledge_question_preflight")
                ):
                    state.kag_degraded = _runtime_status(kwargs.get("result")) == "DEGRADED_KAG"
        elif "uuma_worker" in name and name.endswith("submit_result"):
            with _LOCK:
                _state(key).result_submitted = True
        return
    if _profile() != "orchestrator":
        return
    operation = _control_operation(tool_name)
    with _LOCK:
        state = _state(key)
        if operation == "create_task":
            task_id = _find_task_id(kwargs.get("result"))
            if task_id:
                state.created.add(task_id)
        elif operation == "route_task":
            task_id = str((args or {}).get("task_id") or "").strip()
            if task_id in state.created:
                state.routed.add(task_id)
        elif operation == "assign_task":
            task_id = str((args or {}).get("task_id") or "").strip()
            if task_id in state.routed and task_id not in state.ready:
                state.ready.append(task_id)
        elif _is_delegation_spawn(tool_name, args):
            count = _delegation_count(args)
            del state.ready[:count]


def _clear_session(**kwargs: Any) -> None:
    keys = {
        str(value)
        for value in (kwargs.get("session_id"), kwargs.get("old_session_id"))
        if value
    }
    with _LOCK:
        for key in keys:
            _SESSIONS.pop(key, None)


def _guard_specialist_output(response_text: str = "", **kwargs: Any) -> str | None:
    if _profile() not in _DIRECT_SPECIALISTS or not response_text:
        return None
    if _profile() in {"scholar", "wisdom-oldman"} and not _check_graph(recover=False, **kwargs):
        return "知识图谱当前不可用，本轮知识工作已阻止。请恢复图谱后重试；本轮没有完成知识回答。"
    with _LOCK:
        state = _state(_session_key(kwargs))
        registered = bool(state.direct_run_id)
        domain_checked = state.domain_checked
        kag_degraded = state.kag_degraded
        pending_topic = state.pending_topic_question
        wisdom_intent_resolved = state.wisdom_intent_resolved
        grounded_reply = _wisdom_grounded_reply(state) if _profile() == "wisdom-oldman" else None
        status_reply = _wisdom_status_reply(state) if _profile() == "wisdom-oldman" else None
        capacity_attempted = state.brainstormer_capacity_attempted
        capacity_result = state.brainstormer_capacity_result
        capacity_required = state.brainstormer_capacity_required
        structure_status = state.brainstormer_structure_status
    if registered and domain_checked:
        if _profile() == "brainstormer" and re.search(
            r"(?:已|已经).{0,4}(?:保存|记录|记住).{0,12}(?:项目|话题)|"
            r"(?:项目|话题).{0,12}(?:已|已经).{0,4}(?:保存|记录)",
            response_text,
        ) and structure_status != "ALREADY_EXISTS":
            if structure_status == "PROPOSED":
                return (
                    "项目和话题结构已提交提案，仍等待 Orchestrator 审核；"
                    "目前不能称为已经保存的规范状态。"
                )
            return "本轮没有完成项目或话题的持久化，不能声称已经保存。"
        if _profile() == "brainstormer" and capacity_attempted:
            if capacity_result:
                return _brainstormer_capacity_reply(capacity_result, response_text)
            return (
                "容量计算工具没有成功返回结果，因此本轮不能给出精确的利润或面积结论。"
                "请检查输入后重试；先前未经核算的数字不能作为租地依据。"
            )
        if (
            _profile() == "brainstormer" and capacity_required
            and _brainstormer_unchecked_capacity_claim(response_text)
        ):
            return (
                "这轮还没有通过容量计算工具核对，不能给出精确土地面积或区块是否足够的结论。"
                "请先确认到手售价、每公斤变动成本、每月固定成本、单丛可售产量、"
                "生长及整地天数、收获间隔和净种植比例；若这些数据已齐，需完成工具核算。"
            )
        if _profile() == "brainstormer" and re.search(
            r"(?:^\s*调用\s*智慧老头\s*[（(]|"
            r"(?:我)?(?:已经|已|刚才|刚刚|正在|现在|马上)\s*"
            r"(?:调用|委派|咨询|交给)\s*(?:了)?\s*"
            r"(?:智慧老头|Wisdom[- ]?Oldman|Scholar|Forge(?: Lab Bot)?))",
            response_text,
            flags=re.IGNORECASE,
        ):
            return (
                "我尚未实际调用或委派其他 Agent，不能把自己的分析说成对方的结论。"
                "这类跨 Agent 请求需要交给 Orchestrator；目前我只能继续整理问题、"
                "列出所需证据，并明确哪些结论仍未经核实。"
            )
        if _profile() == "wisdom-oldman" and pending_topic:
            return (
                f"建议建立新主题：{pending_topic}\n\n"
                f"研究范围：{pending_topic}\n\n"
                "目前尚未创建主题或启动这项新研究。是否同意建立并开始研究？"
                "请回复“同意”，或告诉我你要修改的范围。"
            )
        if _profile() == "wisdom-oldman" and kag_degraded:
            return "本轮 KAG 图谱推理失败，已阻止降级回答；请恢复服务后重试。"
        if _profile() == "wisdom-oldman" and not wisdom_intent_resolved:
            return (
                "我还没有完成这轮问题的知识库检索，不能把直接生成的内容当作研究答案。"
                "请重试，或明确告诉我这是研究问题还是查看研究进度。"
            )
        if _profile() == "wisdom-oldman" and grounded_reply:
            return grounded_reply
        if _profile() == "wisdom-oldman" and status_reply:
            return status_reply
        return None
    return (
        "我目前无法完成 UuMA Direct Run 登记或领域知识／状态检索，所以不能把未经架构追踪"
        "的答案当作已完成。请稍后重试，或请 Orchestrator 检查 MCP 与 profile 路由。"
    )


def _finalize_specialist(**kwargs: Any) -> None:
    profile = _profile()
    if profile not in _DIRECT_SPECIALISTS or _CONTEXT is None:
        return
    with _LOCK:
        state = _state(_session_key(kwargs))
        if state.result_submitted or not state.direct_run_id or not state.direct_task_id:
            return
        if state.direct_run_id.startswith("assignment:"):
            return
        state.result_submitted = True  # at-most-once callback attempt
        run_id = state.direct_run_id
        task_id = state.direct_task_id
        domain_checked = state.domain_checked and (
            profile not in {"scholar", "wisdom-oldman"}
            or (state.graph_ready and not state.kag_degraded)
        )
        if profile == "wisdom-oldman":
            domain_checked = domain_checked and state.wisdom_intent_resolved
    response = str(kwargs.get("assistant_response") or "")[:8000]
    generic_failure = response.strip().lower().startswith("sorry, something went wrong")
    outcome = "COMPLETED" if domain_checked and response and not generic_failure else "FAILED"
    result = {
        "run_id": run_id,
        "task_id": task_id,
        "agent_id": profile,
        "outcome": outcome,
        "summary": response or "Specialist turn ended without an answer.",
    }
    if outcome == "FAILED":
        result["error"] = "Domain preflight or answer unavailable"
    try:
        receipt = _CONTEXT.call_mcp(
            "uuma-worker",
            "submit_result",
            {"result_json": json.dumps(result, ensure_ascii=False)},
            timeout=20,
        )
        if not receipt.get("ok"):
            _LOGGER.warning("Specialist result submission failed: %s", str(receipt.get("error"))[:160])
    except Exception as exc:  # noqa: BLE001 - finalizer must not replace the user's response
        _LOGGER.warning("Specialist result submission raised: %s", type(exc).__name__)


def register(ctx: Any) -> None:
    global _CONTEXT
    _CONTEXT = ctx
    ctx.register_hook("pre_llm_call", _health_context)
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    ctx.register_hook("post_tool_call", _post_tool_call)
    ctx.register_hook("transform_llm_output", _guard_specialist_output)
    ctx.register_hook("post_llm_call", _finalize_specialist)
    ctx.register_hook("on_session_finalize", _clear_session)
    ctx.register_hook("on_session_reset", _clear_session)
