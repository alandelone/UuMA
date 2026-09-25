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
        "同意", "可以", "确认", "同意建立", "同意建主题", "同意建立主题",
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
            arguments = {
                "brainstormer": {"query": message, "limit": 5},
                "wisdom-oldman": {
                    "question": message,
                    "mode": "SIMPLE",
                    "recover_runtime": False,
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
                    f"Report progress and submit the result through Worker MCP.{forge_capture}"
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
        if _profile() == "wisdom-oldman" and name.endswith("knowledge_question_preflight"):
            proposal = _topic_proposal(kwargs.get("result"))
            with _LOCK:
                state = _state(key)
                if proposal:
                    state.pending_topic_question = proposal
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
    if registered and domain_checked:
        if _profile() == "wisdom-oldman" and pending_topic:
            return (
                f"建议建立新主题：{pending_topic}\n\n"
                f"研究范围：{pending_topic}\n\n"
                "目前尚未创建主题或启动这项新研究。是否同意建立并开始研究？"
                "请回复“同意”，或告诉我你要修改的范围。"
            )
        if _profile() == "wisdom-oldman" and kag_degraded:
            return "本轮 KAG 图谱推理失败，已阻止降级回答；请恢复服务后重试。"
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
