"""Hermes edge plugin: authenticate sources, inject context, preserve prompt prefixes."""

from __future__ import annotations

import json
import logging
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)
_LOCK = threading.RLock()
_PENDING: dict[tuple[str, ...], tuple[str, datetime, str]] = {}
_TURNS: dict[tuple[str, str], str] = {}
_BROKER = None
_CONFIG: dict[str, Any] = {}


def _profile() -> str:
    from hermes_cli.profiles import get_active_profile_name

    return get_active_profile_name() or "default"


def _pre_gateway_dispatch(event=None, gateway=None, **kwargs):
    source = getattr(event, "source", None)
    if source is None or getattr(event, "internal", True) or getattr(source, "is_bot", False):
        return
    if (getattr(source, "profile", None) or _profile()) != "honc":
        return
    if getattr(source, "chat_type", None) != "dm":
        return
    actor, chat = (
        str(getattr(source, "user_id", "") or ""),
        str(getattr(source, "chat_id", "") or ""),
    )
    platform = getattr(getattr(source, "platform", None), "value", "")
    message_id = str(getattr(event, "message_id", "") or getattr(source, "message_id", "") or "")
    expected = _CONFIG["delivery_binding"]
    if (
        actor != _CONFIG["owner_id"]
        or chat != expected["chat_id"]
        or platform != expected["platform"]
        or not message_id
    ):
        return
    check = getattr(gateway, "_is_user_authorized_for_source", None)
    if check is None or not check(source, allow_adapter_delegation=False):
        return
    text = getattr(event, "text", "")
    media_type = getattr(getattr(event, "message_type", None), "value", "")
    if not isinstance(text, str) or (not text.strip() and media_type not in {"voice", "audio"}):
        return
    with _LOCK:
        _PENDING[(platform, actor, chat, message_id)] = (text, datetime.now(UTC), media_type)
        while len(_PENDING) > 128:
            _PENDING.pop(next(iter(_PENDING)))
    return


def _pre_llm_call(**kwargs):
    if _profile() != "honc" or kwargs.get("parent_session_id"):
        return None
    from gateway.session_context import get_session_env

    from uuma.honc.life_models import LOCAL_TIMEZONE

    if get_session_env("HERMES_CRON_SESSION"):
        return None
    input_kind = "text"
    platform = str(kwargs.get("platform") or "")
    session = str(kwargs.get("session_id") or "")
    turn = str(kwargs.get("turn_id") or "")
    if not session or not turn:
        return None
    raw = kwargs.get("user_message")
    if not isinstance(raw, str):
        return None
    if platform in {"telegram", "discord", "slack"}:
        actor = str(kwargs.get("sender_id") or "")
        chat = str(kwargs.get("chat_id") or "")
        mid = get_session_env("HERMES_SESSION_MESSAGE_ID")
        if (
            actor != _CONFIG["owner_id"]
            or chat != _CONFIG["delivery_binding"]["chat_id"]
            or get_session_env("HERMES_SESSION_USER_ID") != actor
            or get_session_env("HERMES_SESSION_CHAT_ID") != chat
            or get_session_env("HERMES_SESSION_PLATFORM") != platform
        ):
            return None
        with _LOCK:
            pending = _PENDING.pop((platform, actor, chat, mid), None)
        if pending is None:
            return {
                "context": "生活记录入口尚未核实这条真实消息。只读，不要编造 request_ref 或宣称保存。"
            }
        authored, received, media_type = pending
        if media_type in {"voice", "audio"} and not authored.strip():
            input_kind = "voice_transcript"
        raw = authored if authored.strip() else raw
        transport = f"{platform}:{chat}:{mid}"
    elif platform in {"cli", "terminal", ""}:
        # Local terminal is the OS user's direct input; cron/delegated turns were excluded above.
        actor, received = _CONFIG["owner_id"], datetime.now(UTC)
        transport = f"local:{session}:{turn}"
    else:
        return None
    token, receipt = _BROKER.open_message(
        raw_content=raw,
        transport_id=transport,
        session_id=session,
        turn_id=turn,
        received_at=received,
        actor_id=actor,
        input_kind=input_kind,
    )
    with _LOCK:
        _TURNS[(session, turn)] = token
    return {
        "context": "HONC_LIFE_CURRENT_MESSAGE\n"
        + json.dumps(
            {
                "source_ref": receipt["source_ref"],
                "request_refs": receipt["request_refs"],
                "today": received.astimezone(LOCAL_TIMEZONE).date().isoformat(),
                "timezone": "Asia/Kuala_Lumpur",
                "instructions": "先读 honc_get_life_context；工具的 context_ref 由宿主注入，别自己填写。"
                "只能用当前 request_refs，保留原文与未知字段。身体记录不追问。日记只调用 save_diary，别重复打卡。",
            },
            ensure_ascii=False,
        )
    }


def _pre_tool_call(tool_name="", args=None, **kwargs):
    if _profile() != "honc":
        return None
    name = tool_name.replace("-", "_").lower()
    if name in {
        "skill_manage",
        "cronjob",
        "manage_connections",
        "write_file",
        "patch_file",
        "edit_file",
        "terminal",
        "execute_code",
        "delegate_task",
    } or name.startswith("kanban_"):
        return {
            "action": "block",
            "message": "honc 的手册、调度和外部写入由部署配置管理；生活修改请用当前语义工具。",
        }
    if "honc_execution" not in name:
        return None
    operation = name.split("__")[-1]
    values = dict(args or {})
    if operation == "honc_check_habit" or (
        operation == "honc_record_execution" and values.get("habit_id")
    ):
        return {
            "action": "block",
            "message": "生活事实请使用 honc_record_habit／body／diary；旧打卡路径不能绕过当前消息来源。",
        }
    life_names = {
        "honc_get_life_context",
        "honc_configure_habit",
        "honc_update_life_settings",
        "honc_record_habit",
        "honc_record_body",
        "honc_save_diary",
        "honc_correct_life_record",
        "honc_record_anchor",
        "honc_get_life_operation",
        "honc_get_life_history",
    }
    if operation in life_names:
        key = (str(kwargs.get("session_id") or ""), str(kwargs.get("turn_id") or ""))
        with _LOCK:
            token = _TURNS.get(key)
        if not token:
            return {
                "action": "block",
                "message": "当前消息没有已核实的生活上下文。不可伪造来源或跨会话重用引用。",
            }
        values["context_ref"] = token
    elif operation in {
        "honc_status",
        "honc_get_context",
        "honc_record_execution",
        "honc_control_round",
        "honc_apply_completion",
        "honc_correct_record",
        "honc_get_report",
    }:
        values["user_id"] = _CONFIG["owner_id"]
    return {"action": "modify", "args": values}


def _close(**kwargs):
    session, turn = str(kwargs.get("session_id") or ""), str(kwargs.get("turn_id") or "")
    with _LOCK:
        keys = [key for key in _TURNS if key[0] == session and (not turn or key[1] == turn)]
        for key in keys:
            _TURNS.pop(key, None)
            _BROKER.close_turn(*key)


def register(ctx):
    global _BROKER, _CONFIG
    path = Path(__file__).parent / "runtime.json"
    if not path.is_file():
        _LOGGER.warning("honc_life has no installed runtime binding; remaining disabled")
        return
    _CONFIG = json.loads(path.read_text(encoding="utf-8"))
    sys.path.insert(0, str(Path(_CONFIG["repository_root"]) / "src"))
    from uuma.honc.life_context import LifeContextBroker

    _BROKER = LifeContextBroker(_CONFIG)
    ctx.register_hook("pre_gateway_dispatch", _pre_gateway_dispatch)
    ctx.register_hook("pre_llm_call", _pre_llm_call)
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    for event in ("post_llm_call", "on_session_finalize", "on_session_reset"):
        ctx.register_hook(event, _close)
