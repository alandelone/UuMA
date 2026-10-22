"""Telegram navigation at the authenticated edge; never invent canonical decisions."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

_LOG = logging.getLogger(__name__)


def parse_command(text: str) -> tuple[str, str] | None:
    text = text.strip()
    match = re.fullmatch(r"/(topics|brainstorm)(?:@[A-Za-z0-9_]+)?(?:\s+(.*))?", text, re.DOTALL)
    if match:
        return match[1], (match[2] or "").strip()
    match = re.fullmatch(
        r"(?:先放下[^，,]+[，,]\s*)?(?:切换到|切换至|回到|我们先谈|我们先讨论)\s*(.+?)[。！!]?",
        text,
    )
    if match:
        return "topics", match[1].strip()
    match = re.fullmatch(r"(?:新建议题|新增议题)[：:\s]*(.+)", text)
    if match:
        return "topics", "new " + match[1].strip()
    if text in {"查看议题", "议题列表"}:
        return "topics", ""
    if text in {"今天先到这里", "今天先到这里，下次继续", "保存进度", "下次继续"}:
        return "brainstorm", "pause"
    return None


def overview(result: dict[str, Any]) -> str:
    context = result.get("context")
    if not context:
        return "还没有选择议题。用 /topics 查看，或 /topics new 议题名称 新建。"
    objects = context["objects"]
    topic = next(x for x in objects if x["kind"] == "topic")
    lines = [f"当前议题：{topic['title']}"]
    for kind, label, predicate in [
        ("decision", "已确认的决定", lambda x: x.get("status") not in {"SUPERSEDED", "REJECTED"}),
        ("question", "还要讨论", lambda x: x.get("status") not in {"RESOLVED", "SUPERSEDED"}),
        ("assumption", "待验证的假设", lambda x: x.get("status") not in {"RESOLVED", "SUPERSEDED"}),
    ]:
        entries = [x["title"][:180] for x in objects if x["kind"] == kind and predicate(x)]
        lines.append(f"\n{label}（{len(entries)}）：")
        lines.extend("• " + x for x in entries[:5])
        if not entries:
            lines.append("暂无记录")
    checkpoint = context.get("latest_checkpoint")
    if checkpoint:
        value = checkpoint.get("text") or checkpoint.get("summary") or checkpoint.get("title", "")
        lines.append("\n上次进度：\n" + str(value)[:700])
    lines.append("\n/topics 切换议题；继续发消息即可接着讨论。")
    return "\n".join(lines)[:3500]


class BrainstormerCommands:
    def __init__(self, ctx: Any) -> None:
        self.owner = str(ctx.get_config("owner_id", ""))
        if not self.owner.isdigit():
            raise ValueError("Brainstormer navigation requires a configured Telegram owner")
        self.chat = str(ctx.get_config("chat_id", self.owner))
        self.user = ctx.get_config("state_user_id", "telegram:" + self.owner)
        self.url = str(ctx.get_config(
            "navigation_url", "http://127.0.0.1:8772/api/v1/navigation"
        )).strip()
        address = urlsplit(self.url)
        if (
            address.scheme != "http" or address.hostname not in {"127.0.0.1", "localhost", "::1"}
            or address.username or address.password or address.query or address.fragment
            or address.path != "/api/v1/navigation"
        ):
            raise ValueError("Brainstormer navigation requires an explicit loopback endpoint")
        self.navigation_identity = str(ctx.get_config(
            "navigation_identity", os.environ.get("UUMA_AGENT_ID", "")
        )).strip()
        self.navigation_token_file = str(ctx.get_config(
            "navigation_token_file", os.environ.get("UUMA_IDENTITY_TOKEN_FILE", "")
        )).strip()
        self.navigation_command_secret_file = str(ctx.get_config("navigation_command_secret_file", ""))
        if self.navigation_token_file and self.navigation_identity not in {
            "orchestrator", "brainstormer",
        }:
            raise ValueError("Navigation credentials require an authorized Agent identity")
        self.pending = OrderedDict()
        self.turns = OrderedDict()
        self.tasks = set()
        self.lock = threading.RLock()

    def rpc(self, action: str, *, human_command: bool = False, **values: Any) -> dict[str, Any]:
        payload = {"action": action, "user_id": self.user, **values}
        headers = {"Content-Type": "application/json"}
        if self.navigation_token_file:
            token = Path(self.navigation_token_file).read_text(encoding="utf-8").strip()
            if not token:
                raise ValueError("Navigation identity token is empty")
            headers.update({"Authorization": f"Bearer {token}",
                            "X-Uuma-Identity": self.navigation_identity})
        if action == "create" and human_command and self.navigation_command_secret_file:
            from uuma.navigation_auth import sign_command

            secret = Path(self.navigation_command_secret_file).read_bytes().strip()
            if len(secret) < 32:
                raise ValueError("Topic command authorization is unavailable")
            timestamp, nonce = str(int(time.time())), secrets.token_urlsafe(24)
            headers.update({
                "X-Uuma-Command-User": self.owner,
                "X-Uuma-Command-Timestamp": timestamp,
                "X-Uuma-Command-Nonce": nonce,
                "X-Uuma-Command-Signature": sign_command(secret, payload, timestamp, nonce, self.owner),
            })
        request = Request(
            self.url,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=12) as response:
            result = json.load(response)
        if not isinstance(result, dict) or result.get("error"):
            raise ValueError("Navigation backend failed")
        return result

    def command(self, name: str, args: str, ref: str) -> tuple[str, list[list[str]]]:
        buttons = []
        if name == "brainstorm":
            result = self.rpc("context")
            prefix = "已保存的进度如下，下次可继续。\n\n" if args == "pause" else ""
            return prefix + overview(result), [["/topics"]]
        if args.startswith("new "):
            return overview(self.rpc(
                "create", human_command=True, title=args[4:].strip(), source_ref=ref,
            )), [
                ["/topics"]
            ]
        page = re.fullmatch(r"page (\d+)", args)
        if args and not page:
            result = self.rpc("switch", selector=args)
            if result["status"] == "not_found":
                return "找不到这个议题。用 /topics 查看，或 /topics new 名称 新建。", []
            if result["status"] == "ambiguous":
                lines = ["找到多个同名或相近议题，请选择："]
                lines.extend(
                    f"{x['title']}\n/topics {x['project_id']}/{x['id']}"
                    for x in result["matches"][:10]
                )
                return "\n".join(lines)[:3500], []
            return "已切换。\n\n" + overview(result), [["/topics", "/brainstorm"]]
        result = self.rpc("list")
        rows = result["topics"]
        index = min(int(page[1]) if page else 1, max(1, (len(rows) + 7) // 8))
        index = max(1, index)
        active = (result.get("binding") or {}).get("active_topic_id")
        lines = [f"议题列表（{len(rows)} 个，第 {index} 页）"]
        for item in rows[(index - 1) * 8 : index * 8]:
            marker = "正在讨论" if item["id"] == active else item.get("status", "ACTIVE")
            lines.append(f"• {item['title'][:100]}〔{marker}〕")
            buttons.append(["切换到 " + item["title"]])
        if not rows:
            lines.append("暂无议题。")
        if index > 1:
            buttons.append([f"/topics page {index - 1}"])
        if len(rows) > index * 8:
            buttons.append([f"/topics page {index + 1}"])
        buttons.append(["/brainstorm"])
        lines.append("\n点下方按钮切换；也可以说“切换到 议题名称”。\n新建：/topics new 议题名称")
        return "\n".join(lines), buttons

    async def deliver(
        self, gateway: Any, source: Any, command: tuple[str, str], ref: str
    ) -> None:
        try:
            text, buttons = await asyncio.to_thread(self.command, *command, ref)
        except (OSError, ValueError, KeyError) as exc:
            _LOG.warning("Brainstormer navigation failed: %s", type(exc).__name__)
            text, buttons = "议题状态暂时无法读取或保存，请稍后重试。", []
        adapter = gateway._delivery_adapter_for(source)
        try:
            if buttons and hasattr(adapter, "_send_control_message"):
                from telegram import ReplyKeyboardMarkup

                await adapter._send_control_message(
                    source.chat_id,
                    text,
                    parse_mode=None,
                    thread_id=None,
                    metadata=None,
                    reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True),
                )
            else:
                result = await adapter.send(source.chat_id, text)
                if getattr(result, "success", True) is False:
                    _LOG.warning("Brainstormer navigation delivery failed")
        except Exception as exc:  # noqa: BLE001 - isolate third-party adapter delivery errors
            _LOG.warning("Brainstormer navigation delivery failed: %s", type(exc).__name__)

    def inbound(self, event: Any = None, gateway: Any = None, **kwargs: Any) -> dict[str, str] | None:
        source = getattr(event, "source", None)
        if (
            not source
            or getattr(event, "internal", True)
            or getattr(source, "is_bot", False)
            or getattr(source, "profile", None) != "brainstormer"
            or getattr(getattr(source, "platform", None), "value", "") != "telegram"
            or getattr(source, "chat_type", None) != "dm"
            or str(source.user_id) != self.owner
            or str(source.chat_id) != self.chat
        ):
            return None
        authorize = getattr(gateway, "_is_user_authorized_for_source", None)
        if not authorize or not authorize(source, allow_adapter_delegation=False):
            return None
        mid = str(getattr(event, "message_id", "") or "")
        text = getattr(event, "text", "") or ""
        if not mid:
            return None
        ref = f"telegram:{self.chat}:{mid}"
        command = parse_command(text)
        if command:
            # The hook precedes native slash authorization; apply it explicitly.
            denied = gateway._check_slash_access(source, command[0])
            if denied:
                return None
            task = asyncio.get_running_loop().create_task(
                self.deliver(gateway, source, command, ref)
            )
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            return {"action": "skip", "reason": "brainstormer_navigation"}
        if not text.startswith("/"):
            with self.lock:
                self.pending[mid] = (text, ref)
                while len(self.pending) > 128:
                    self.pending.popitem(last=False)
        return None

    def pre_llm(self, **kwargs: Any) -> dict[str, str] | None:
        if kwargs.get("parent_session_id") or kwargs.get("platform") != "telegram":
            return None
        from gateway.session_context import get_session_env

        if (
            get_session_env("HERMES_SESSION_PROFILE") != "brainstormer"
            or get_session_env("HERMES_SESSION_USER_ID") != self.owner
            or get_session_env("HERMES_SESSION_CHAT_ID") != self.chat
            or get_session_env("HERMES_CRON_SESSION")
        ):
            return None
        mid = get_session_env("HERMES_SESSION_MESSAGE_ID")
        key = (kwargs.get("session_id"), kwargs.get("turn_id"))
        with self.lock:
            pending = self.pending.pop(mid, None)
        if not pending:
            return None
        text, ref = pending
        try:
            result = self.rpc("context")
            binding = result.get("binding") or {}
            if not binding.get("active_topic_id"):
                return {
                    "context": "尚未选择持久议题。提示用户 /topics 或 /topics new 名称；不要宣称已保存。"
                }
            values = {
                "project_id": binding["active_project_id"],
                "topic_id": binding["active_topic_id"],
                "source_ref": ref,
            }
            # Voice input has no text until transcription; this hook receives the transcript.
            text = text or str(kwargs.get("user_message") or "")
            self.rpc("turn", **values, text=text, role="user")
            with self.lock:
                self.turns[key] = values
                while len(self.turns) > 128:
                    self.turns.popitem(last=False)
            objects = result["context"]["objects"]
            structured = [x for x in objects if x["kind"] != "checkpoint"]
            checkpoints = sorted(
                (x for x in objects if x["kind"] == "checkpoint"),
                key=lambda x: (x.get("updated_at", ""), x["id"]),
            )[-4:]
            context = {
                "project_id": values["project_id"],
                "topic_id": values["topic_id"],
                "objects": structured,
                "recent_progress": checkpoints,
                "decision_map": result["decision_map"],
            }
            return {
                "context": "BRAINSTORMER_ACTIVE_TOPIC\n"
                + json.dumps(context, ensure_ascii=False)
                + "\n本轮只讨论当前议题；旧聊天中的其他议题不可混入。恢复上述进度。"
                "重要问题/假设/证据用已有安全事务工具保存；决定仍需用户审核。"
                "原始对话会保存为进度，不等于已确认决定。切换用 /topics 名称。"
            }
        except (OSError, ValueError, KeyError) as exc:
            _LOG.warning("Brainstormer restore failed: %s", type(exc).__name__)
            return {
                "context": "议题状态读取或保存失败。本轮不要宣称已保存或已恢复，请明确告知用户。"
            }

    def post_llm(self, **kwargs: Any) -> None:
        key = (kwargs.get("session_id"), kwargs.get("turn_id"))
        with self.lock:
            values = self.turns.pop(key, None)
        if values and kwargs.get("assistant_response"):
            try:
                self.rpc("turn", **values, role="assistant", text=str(kwargs["assistant_response"]))
            except (OSError, ValueError, KeyError) as exc:
                _LOG.warning("Brainstormer progress save failed: %s", type(exc).__name__)


def register(ctx: Any) -> None:
    if ctx.profile_name != "brainstormer":
        return
    commands = BrainstormerCommands(ctx)
    for name, description in [
        ("topics", "查看、切换或新建议题"),
        ("brainstorm", "当前议题和已保存进度"),
    ]:
        ctx.register_command(
            name,
            lambda raw_args="": "请在 Brainstormer Telegram 私聊中使用此命令。",
            description=description,
            args_hint="[议题名称 / new 名称]",
        )
    ctx.register_hook("pre_gateway_dispatch", commands.inbound)
    ctx.register_hook("pre_llm_call", commands.pre_llm)
    ctx.register_hook("post_llm_call", commands.post_llm)
