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
    match = re.fullmatch(r"/topics_page_(\d+)(?:@[A-Za-z0-9_]+)?", text)
    if match:
        return "topics", f"page {match[1]}"
    match = re.fullmatch(r"/topics_(\d+)(?:@[A-Za-z0-9_]+)?", text)
    if match:
        return "topics", f"index {match[1]}"
    match = re.fullmatch(
        r"/(topics|brainstorm|agenda|issue|checkpoint|newtopic|switchtopic|newissue|progress|guide|cancel)(?:@[A-Za-z0-9_]+)?(?:\s+(.*))?",
        text,
        re.DOTALL,
    )
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
    if text in {"问题树", "议题树", "查看问题", "待讨论问题"}:
        return "agenda", ""
    match = re.fullmatch(r"(?:保存进度|记录检查点)[：:\s]+(.+)", text, re.DOTALL)
    if match:
        return "checkpoint", match[1].strip()
    if text in {"今天先到这里", "今天先到这里，下次继续", "保存进度", "下次继续"}:
        return "brainstorm", "pause"
    return None


def _status_label(status: str) -> str:
    return {
        "READY": "待讨论",
        "OPEN": "待讨论",
        "ACTIVE": "进行中",
        "BLOCKED": "阻塞",
        "RESOLVED": "已解决",
        "DECIDED": "已决定",
        "SUPERSEDED": "已取代",
        "REJECTED": "已拒绝",
        "ACCEPTED": "已确认",
    }.get(str(status).upper(), str(status or "未标记"))


def _tree_lines(hierarchy: list[dict[str, Any]], *, limit: int = 24) -> list[str]:
    lines: list[str] = []

    def add_question(question: dict[str, Any], depth: int) -> None:
        if len(lines) >= limit:
            return
        current = " ← 当前" if question.get("is_current") else ""
        lines.append(
            f"{'  ' * depth}• {question.get('title') or question.get('id')}"
            f"〔{_status_label(question.get('status', ''))}〕{current}"
            f"  ({question.get('id', '')})"
        )
        for child in question.get("subquestions", []):
            add_question(child, depth + 1)

    for topic in hierarchy:
        if len(lines) >= limit:
            break
        lines.append(f"{topic.get('title') or topic.get('topic_id')}")
        questions = topic.get("questions", [])
        if not questions:
            lines.append("  暂无问题")
        for question in questions:
            add_question(question, 1)
    if len(lines) >= limit:
        lines.append("…其余问题请用 /issue <问题ID> 查看")
    return lines


def _command_guide() -> str:
    return (
        "💡 Brainstormer 命令指南\n\n"
        "👉 快捷操作命令（点击直接发送）：\n"
        "• /topics ：查看正式 Topic 与旧记录主题组\n"
        "• /newtopic ：点击后填写新主题名称\n"
        "• /switchtopic ：点击后填写要切换的主题名称\n"
        "• /newissue ：点击后填写问题内容\n"
        "• /progress ：实时后台状态与最近保存的讨论进度\n"
        "• /agenda ：问题树、建议下一项与阻塞原因\n"
        "• /checkpoint ：保存一个明确检查点\n"
        "• /cancel ：取消填写\n"
        "• /brainstorm ：当前讨论总览与快捷选项\n"
        "• /guide ：显示本指南\n\n"
        "👉 点击复制发送，直接交互：\n"
        "`切换到 主题名称`\n"
        "`保存进度：今日讨论结论与下一步`\n"
        "`新建议题：新主题名称`\n"
        "`今天先到这里，下次继续`\n\n"
        "详细操作：/issue <问题ID> 查看问题 · /issue sub <问题ID> 子问题"
    )


def overview(result: dict[str, Any]) -> str:
    context = result.get("context")
    if not context:
        return (
            "还没有选择议题。用 /topics 查看并选择，或 /newtopic 新建正式 Topic。\n\n"
            "可选操作：/agenda 问题树 · /newissue · "
            "/checkpoint · "
            "/guide 命令指南"
        )
    objects = context["objects"]
    selected = result.get("selected_topic") or {}
    topic = next((item for item in objects if item["kind"] == "topic"), None)
    topic_title = selected.get("title") or (topic or {}).get("title", "未命名主题")
    is_canonical_topic = selected.get("is_canonical_topic", topic is not None)
    kind_label = "正式 Topic" if is_canonical_topic else "记录主题组（未建档）"
    counts = {
        "question_count": sum(1 for item in objects if item.get("kind") == "question"),
        "open_question_count": sum(
            1
            for item in objects
            if item.get("kind") == "question"
            and str(item.get("status", "OPEN")).upper()
            not in {"RESOLVED", "DECIDED", "SUPERSEDED", "REJECTED"}
        ),
        "decision_count": sum(1 for item in objects if item.get("kind") == "decision"),
        "assumption_count": sum(1 for item in objects if item.get("kind") == "assumption"),
        "checkpoint_count": sum(1 for item in objects if item.get("kind") == "checkpoint"),
        **selected,
    }
    lines = [
        f"当前讨论：{topic_title}〔{kind_label}〕",
        (
            f"问题 {counts.get('question_count', 0)}"
            f"（待讨论 {counts.get('open_question_count', 0)}） · "
            f"决定 {counts.get('decision_count', 0)} · "
            f"假设 {counts.get('assumption_count', 0)} · "
            f"检查点 {counts.get('checkpoint_count', 0)}"
        ),
    ]
    for kind, label in [
        ("decision", "决定记录（状态照实显示）"),
        ("assumption", "假设记录"),
    ]:
        entries = [item for item in objects if item["kind"] == kind]
        lines.append(f"\n{label}（{len(entries)}）：")
        lines.extend(
            f"• {item['title'][:160]}〔{_status_label(item.get('status', ''))}〕"
            for item in entries[:5]
        )
        if not entries:
            lines.append("暂无记录")

    graph = result.get("decision_map") or {}
    lines.append(f"\n问题树（{counts.get('question_count', 0)}）：")
    lines.extend(_tree_lines(graph.get("hierarchy", []), limit=14) or ["暂无问题"])
    progression = graph.get("progression") or {}
    node_map = {item.get("id"): item for item in graph.get("nodes", [])}
    next_id = progression.get("recommended_next_question_id")
    if next_id:
        next_title = node_map.get(next_id, {}).get("title", next_id)
        lines.append(f"\n建议下一项：{next_title}（{next_id}）")
    blocked = progression.get("blocked_questions", [])
    if blocked:
        blocker_map = {
            item.get("id"): item.get("title", item.get("id"))
            for item in graph.get("nodes", [])
        }
        lines.append("阻塞问题：")
        for item in blocked[:5]:
            blockers = [
                blocker_map.get(value, value) for value in item.get("blocked_by", [])
            ]
            detail = "；阻塞原因：" + "、".join(blockers) if blockers else ""
            lines.append(f"• {blocker_map.get(item.get('id'), item.get('id'))}{detail}")

    checkpoint = context.get("latest_checkpoint")
    if checkpoint:
        value = (
            checkpoint.get("summary")
            or checkpoint.get("text")
            or checkpoint.get("title", "")
        )
        lines.append("\n上次进度：\n" + str(value)[:700])
    lines.append(
        "\n快捷选项：/topics 切换 · /agenda 问题树 · /issue 查看或新增 · "
        "/checkpoint 保存进度 · /guide 命令指南"
    )
    return "\n".join(lines)[:3500]


def _agenda_text(result: dict[str, Any]) -> str:
    if not result.get("context"):
        return "还没有选择议题。先用 /topics 选择一个议题，再用 /agenda 查看问题树。"
    graph = result.get("decision_map") or {}
    lines = ["当前问题树：", *_tree_lines(graph.get("hierarchy", []))]
    progression = graph.get("progression") or {}
    node_map = {item.get("id"): item for item in graph.get("nodes", [])}
    next_id = progression.get("recommended_next_question_id")
    if next_id:
        next_title = node_map.get(next_id, {}).get("title", next_id)
        lines.append(f"\n建议下一项：{next_title}（{next_id}）")
    blocked = progression.get("blocked_questions", [])
    if blocked:
        lines.append("\n阻塞原因：")
        for item in blocked[:8]:
            title = node_map.get(item.get("id"), {}).get("title", item.get("id"))
            reasons = [
                node_map.get(value, {}).get("title", value)
                for value in item.get("blocked_by", [])
            ]
            suffix = "；等待：" + "、".join(reasons) if reasons else ""
            lines.append(f"• {title}{suffix}")
    lines.append("\n用 /issue <问题ID> 看详情；用 /newissue新增问题。")
    return "\n".join(lines)[:3500]


def _issue_detail(result: dict[str, Any], question_id: str) -> str:
    context = result.get("context")
    if not context:
        return "还没有选择议题。先用 /topics 选择一个议题。"
    question = next(
        (
            item
            for item in context.get("objects", [])
            if item.get("id") == question_id and item.get("kind") == "question"
        ),
        None,
    )
    if question is None:
        return "当前议题下找不到这个问题。用 /agenda 查看可用的问题ID。"
    graph = result.get("decision_map") or {}
    node = next(
        (item for item in graph.get("nodes", []) if item.get("id") == question_id),
        {},
    )
    objects = {item.get("id"): item for item in context.get("objects", [])}
    lines = [
        question.get("title", question_id),
        f"ID：{question_id}",
        f"状态：{_status_label(question.get('status', ''))}",
    ]
    parent_ids = node.get("parent_question_ids", [])
    if not parent_ids and question.get("parent_question_id"):
        parent_ids = [question["parent_question_id"]]
    if parent_ids:
        titles = [objects.get(value, {}).get("title", value) for value in parent_ids]
        lines.append("上层问题：" + "、".join(titles))
    children = node.get("subquestion_ids", [])
    if children:
        titles = [
            f"{objects.get(value, {}).get('title', value)}（{value}）" for value in children
        ]
        lines.append("子问题：" + "、".join(titles))
    dependencies = node.get("unresolved_dependencies", [])
    if dependencies:
        titles = [objects.get(value, {}).get("title", value) for value in dependencies]
        lines.append("阻塞原因：" + "、".join(titles))
    grounding = node.get("grounding_ids", [])
    if grounding:
        titles = [objects.get(value, {}).get("title", value) for value in grounding]
        lines.append("关联假设／证据：" + "、".join(titles))
    lines.append(f"\n新增子问题：/issue sub {question_id} 子问题内容")
    return "\n".join(lines)[:3000]


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
        self.delivery_lock = asyncio.Lock()
        self.live_runtime = None
        self.form = None
        self.seen = OrderedDict()
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
        if (
            action in {"create", "question", "checkpoint"}
            and human_command
            and self.navigation_command_secret_file
        ):
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

    def progress(self) -> str:
        from datetime import UTC, datetime

        lines = ["当前运行状态", "查询时间：" + datetime.now(UTC).isoformat(timespec="seconds")]
        snapshot = self.live_runtime
        if snapshot and time.monotonic() - snapshot[0] < 30:
            lines.append("Telegram 网关：在线，本次查询已响应")
            lines.append(f"共享网关正在处理：{snapshot[1]} 个对话（所有机器人合计）")
        else:
            lines.append("共享网关实时对话数量：未知")
        try:
            if self.navigation_identity != "brainstormer" or not self.navigation_token_file:
                raise ValueError("Scoped worker credentials unavailable")
            token = Path(self.navigation_token_file).read_text().strip()
            base = os.environ.get("UUMA_CONTROL_URL", "http://127.0.0.1:8765").rstrip("/")
            address = urlsplit(base)
            if address.scheme != "http" or address.hostname not in {"127.0.0.1", "localhost", "::1"}:
                raise ValueError("Control endpoint must be loopback")

            def read(path: str) -> Any:
                request = Request(base + path, headers={
                    "Authorization": "Bearer " + token, "X-Uuma-Identity": "brainstormer",
                })
                with urlopen(request, timeout=5) as response:
                    return json.load(response)

            runs = read("/worker/runs")
            intake = read("/worker/intake")
            lines.append("后台接收任务：" + ("开放" if intake.get("accepting") else "暂停"))
            active = [r for r in runs if r.get("agent_id") == "brainstormer" and
                      r.get("status") in {"PENDING", "RUNNING", "BLOCKED", "CANCEL_REQUESTED"}]
            lines.append(f"Brainstormer 受管任务：{len(active)} 个未结束")
            for run in active[:5]:
                progress = run.get("progress") or {}
                task = read("/worker/tasks/" + run["task_id"])
                lines.append("• " + str(task.get("title", run["task_id"]))[:160])
                lines.append("  状态：" + str(run.get("status")))
                lines.append("  当前步骤：" + str(progress.get("current_step") or "尚未上报"))
                heartbeat = progress.get("last_heartbeat")
                lines.append("  最近心跳：" + str(heartbeat or "未知"))
                try:
                    age = (datetime.now(UTC) - datetime.fromisoformat(
                        heartbeat
                    )).total_seconds()
                    if age > 300:
                        lines.append("  心跳超过 5 分钟未更新，是否仍在执行待确认。")
                except (ValueError, TypeError, AttributeError):
                    lines.append("  心跳时间不可用，无法确认执行活跃度。")
                if progress.get("blocker"):
                    lines.append("  阻塞：" + str(progress["blocker"])[:300])
            lines.append("任务状态来自当前记录；心跳时间用于判断是否仍在更新。")
            lines.append("普通聊天与共享网关的其他机器人不计入上述任务数量。")
        except (OSError, ValueError, KeyError, TypeError):
            lines.append("受管任务后台：暂时无法读取，当前运行情况未知。")
        try:
            lines.append("\n最近保存的讨论进度（非实时运行状态）\n" + overview(self.rpc("context")))
        except (OSError, ValueError, KeyError):
            lines.append("讨论进度：暂时无法读取。")
        lines.append("\n点 /progress 重新获取最新状态。")
        return "\n".join(lines)[:3900]

    def command(self, name: str, args: str, ref: str) -> tuple[str, list[list[str]]]:
        buttons: list[list[str]] = []
        if name == "expired":
            return "填写已过期，请重新从 Menu 选择操作。刚才的文字没有写入。", buttons
        if name == "guide":
            return _command_guide(), buttons
        if name == "cancel":
            with self.lock:
                self.form = None
            return "已取消填写，可以继续聊天。", buttons
        forms = {
            "newtopic": ("topics", "new ", "请输入新主题名称。"),
            "switchtopic": ("topics", "", "请输入要切换的主题名称。"),
            "newissue": ("issue", "new ", "请输入待讨论的问题。"),
            "issue": ("issue", "", "请输入要查看的问题 ID；点 /agenda 可查看问题树和 ID。"),
            "checkpoint": ("checkpoint", "", "请输入要保存的进度摘要。"),
        }
        if name in forms and not args:
            if name in {"newissue", "issue", "checkpoint"} and not self.rpc("context").get("context"):
                return "还没有选择主题。点 /newtopic 创建主题，或点 /switchtopic 切换。", buttons
            target, prefix, prompt = forms[name]
            with self.lock:
                self.form = (target, prefix, time.monotonic() + 300)
            return prompt + "\n直接发送文字即可，5 分钟内有效；点 /cancel 取消。", buttons
        if name in {"newtopic", "switchtopic", "newissue"}:
            target, prefix, _ = forms[name]
            return self.command(target, prefix + args, ref)
        if name == "progress":
            return self.progress(), buttons
        if name == "brainstorm":
            if args in {"help", "guide"}:
                return _command_guide(), buttons
            if args == "save":
                return self.command("checkpoint", "", ref)
            if args.startswith("save "):
                summary = args[5:].strip()
                if not summary:
                    return "请使用 /checkpoint 保存明确检查点。", buttons
                if not self.rpc("context").get("context"):
                    return "先用 /topics 选择一个主题，再保存检查点。", buttons
                saved = self.rpc(
                    "checkpoint", human_command=True, text=summary, source_ref=ref
                )
                current = self.rpc("context")
                return (
                    f"已保存进度检查点（修订 r{saved.get('revision', '?')}）。\n\n"
                    + overview(current),
                    buttons,
                )
            result = self.rpc("context")
            prefix = "对话内容已按轮次记录；当前进度如下。\n\n" if args == "pause" else ""
            return prefix + overview(result), buttons

        if name == "agenda":
            return _agenda_text(self.rpc("context")), buttons

        if name == "issue":
            if not args:
                return _agenda_text(self.rpc("context")), buttons
            if args == "new":
                return self.command("newissue", "", ref)
            if args.startswith("new "):
                title = args[4:].strip()
                if not title:
                    return "请在命令后补上问题内容：/newissue内容", buttons
                if not self.rpc("context").get("context"):
                    return "先用 /topics 选择一个主题，再新增问题。", buttons
                created = self.rpc(
                    "question", human_command=True, title=title, source_ref=ref
                )
                current = self.rpc("context")
                return (
                    f"已新增待讨论问题：{title}（{created.get('question_id', '')}）\n\n"
                    + _agenda_text(current),
                    buttons,
                )
            if args.startswith("sub "):
                match = re.fullmatch(
                    r"sub\s+([A-Za-z0-9_.-]{1,128})\s+(.+)", args, re.DOTALL
                )
                if not match:
                    return "格式：/issue sub 问题ID 子问题内容", buttons
                parent_id, title = match[1], match[2].strip()
                if not self.rpc("context").get("context"):
                    return "先用 /topics 选择一个主题，再新增子问题。", buttons
                created = self.rpc(
                    "question",
                    human_command=True,
                    selector=parent_id,
                    title=title,
                    source_ref=ref,
                )
                current = self.rpc("context")
                return (
                    f"已新增子问题：{title}（{created.get('question_id', '')}）\n\n"
                    + _agenda_text(current),
                    buttons,
                )
            if args == "sub":
                return "格式：/issue sub 问题ID 子问题内容", buttons
            return _issue_detail(self.rpc("context"), args), buttons

        if name == "checkpoint":
            if not args:
                return (
                    (
                        "请把进度摘要放在命令后：/checkpoint 已确认的内容、未决问题和下一步。\n"
                        "普通对话会按轮次保存；检查点用于标记你明确整理过的进度。"
                    ),
                    buttons,
                )
            if not self.rpc("context").get("context"):
                return "先用 /topics 选择一个主题，再保存检查点。", buttons
            saved = self.rpc(
                "checkpoint", human_command=True, text=args, source_ref=ref
            )
            return (
                f"已保存进度检查点（修订 r{saved.get('revision', '?')}）。\n\n"
                + overview(self.rpc("context")),
                buttons,
            )

        if args.startswith("new "):
            return overview(self.rpc(
                "create", human_command=True, title=args[4:].strip(), source_ref=ref,
            )), buttons
        if args == "new":
            return self.command("newtopic", "", ref)
        page = re.fullmatch(r"page (\d+)", args)
        if args and args.startswith("index "):
            idx = int(args[6:])
            list_res = self.rpc("list")
            all_r = [("formal", item) for item in list_res.get("topics", [])] + [("group", item) for item in list_res.get("topic_groups", [])]
            if 1 <= idx <= len(all_r):
                row_t, it = all_r[idx - 1]
                sel = it["title"] if row_t == "formal" else it.get("button_title", it["title"])
                return self.command("topics", sel, ref)
            return "找不到该编号的议题。用 /topics 查看列表。", buttons
        if args and not page:
            result = self.rpc("switch", selector=args)
            if result["status"] == "not_found":
                return (
                    (
                        "找不到这个议题或主题组。用 /topics 查看，或 /newtopic "
                        "新建正式 Topic。"
                    ),
                    buttons,
                )
            if result["status"] == "ambiguous":
                lines = ["找到多个同名或相近主题，请选择："]
                lines.extend(
                    f"{x['title']}\n/topics {x['project_id']}/{x['id']}"
                    for x in result["matches"][:10]
                )
                return "\n".join(lines)[:3500], buttons
            return "已切换。\n\n" + overview(result), buttons
        result = self.rpc("list")
        topics = result.get("topics", [])
        groups = result.get("topic_groups", [])
        rows = [("formal", item) for item in topics] + [("group", item) for item in groups]
        index = min(int(page[1]) if page else 1, max(1, (len(rows) + 7) // 8))
        index = max(1, index)
        binding = result.get("binding") or {}
        active = (binding.get("active_project_id"), binding.get("active_topic_id"))
        lines = [
            (
                f"主题列表（{len(topics)} 个正式 Topic · "
                f"{len(groups)} 个未建档主题组，第 {index} 页）"
            )
        ]
        previous_type = None
        for idx_row, (row_type, item) in enumerate(rows[(index - 1) * 8 : index * 8], start=1):
            abs_num = (index - 1) * 8 + idx_row
            if row_type != previous_type:
                heading = (
                    "\n正式 Topic："
                    if row_type == "formal"
                    else "\nObservatory 记录主题组（尚无正式 Topic 对象）："
                )
                lines.append(heading)
                previous_type = row_type
            is_active = (item["project_id"], item["id"]) == active
            marker = (
                "当前讨论"
                if is_active
                else ("正式 Topic" if row_type == "formal" else "未建档")
            )
            counts = (
                f"问题 {item.get('question_count', 0)}"
                f"（待讨论 {item.get('open_question_count', 0)}） · "
                f"决定 {item.get('decision_count', 0)} · "
                f"假设 {item.get('assumption_count', 0)} · "
                f"检查点 {item.get('checkpoint_count', 0)}"
            )
            lines.append(f"• {abs_num}. {item['title'][:100]}〔{marker}〕 [/topics_{abs_num}]\n  {counts}")
            selector = (
                item["title"] if row_type == "formal"
                else item.get("button_title", item["title"])
            )
            lines.append(f"  切换：/topics {selector} [/topics_{abs_num}]")
        if not rows:
            lines.append("目前没有正式 Topic，也没有可识别的记录主题组。")
        if index > 1:
            lines.append(f"上一页：/topics page {index - 1} [/topics_page_{index - 1}]")
        if len(rows) > index * 8:
            lines.append(f"下一页：/topics page {index + 1} [/topics_page_{index + 1}]")
        lines.append(
            "\n从左侧 Menu 选择命令；也可说“切换到 主题名称”。\n"
            "新建：/newtopic · 切换：/switchtopic · 指南：/guide"
        )
        return "\n".join(lines), buttons

    async def deliver(
        self, gateway: Any, source: Any, command: tuple[str, str], ref: str
    ) -> None:
        async with self.delivery_lock:
            await self._deliver(gateway, source, command, ref)

    async def _deliver(
        self, gateway: Any, source: Any, command: tuple[str, str], ref: str
    ) -> None:
        with self.lock:
            self.form = None
        if command[0] == "progress":
            snapshotter = getattr(gateway, "_running_agent_items", None)
            try:
                self.live_runtime = (time.monotonic(), len(list(snapshotter()))) if snapshotter else None
            except (TypeError, RuntimeError):
                self.live_runtime = None
        try:
            text, _buttons = await asyncio.to_thread(self.command, *command, ref)
        except (OSError, ValueError, KeyError) as exc:
            _LOG.warning("Brainstormer navigation failed: %s", type(exc).__name__)
            text = "议题状态暂时无法读取或保存，请稍后重试。"
        adapter = gateway._delivery_adapter_for(source)
        try:
            if hasattr(adapter, "_send_control_message"):
                from telegram import ReplyKeyboardRemove

                await adapter._send_control_message(
                    source.chat_id,
                    text,
                    parse_mode=None,
                    thread_id=None,
                    metadata=None,
                    reply_markup=ReplyKeyboardRemove(),
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
        with self.lock:
            if mid in self.seen:
                return {"action": "skip", "reason": "brainstormer_duplicate"}
            if command or text.startswith("/"):
                self.form = None
            elif self.form:
                target, prefix, deadline = self.form
                self.form = None
                if time.monotonic() <= deadline and text.strip():
                    command = (target, prefix + text.strip())
                else:
                    command = ("expired", "")
        if command:
            # The hook precedes native slash authorization; apply it explicitly.
            denied = gateway._check_slash_access(source, command[0])
            if denied:
                return None
            with self.lock:
                self.seen[mid] = True
                while len(self.seen) > 256:
                    self.seen.popitem(last=False)
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
                    "context": "尚未选择持久议题。提示用户 /topics 或 /newtopic；不要宣称已保存。"
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
    topic_subs = [(f"topics_{i}", f"切换到第 {i} 个议题") for i in range(1, 17)] + [
        (f"topics_page_{p}", f"查看议题第 {p} 页") for p in range(2, 6)
    ]
    all_cmds = [
        ("newtopic", "新建主题：点击后填写名称"),
        ("switchtopic", "切换主题：点击后填写名称"),
        ("newissue", "新增问题：点击后填写内容"),
        ("progress", "查看当前运行状态和最新讨论进度"),
        ("guide", "查看命令指南"),
        ("cancel", "取消当前填写"),
        ("topics", "查看、切换或新建议题"),
        ("brainstorm", "当前讨论总览和快捷选项"),
        ("agenda", "查看问题树、建议下一项和阻塞原因"),
        ("issue", "查看问题、添加问题或建立子问题"),
        ("checkpoint", "保存明确的讨论进度检查点"),
    ] + topic_subs
    for name, description in all_cmds:
        ctx.register_command(
            name,
            lambda raw_args="": "请在 Brainstormer Telegram 私聊中使用此命令。",
            description=description,
            args_hint={
                "topics": "[主题名称 / new 名称]",
                "brainstorm": "[help / save 进度摘要]",
                "agenda": "",
                "issue": "[问题ID / new 内容 / sub 问题ID 子问题]",
                "checkpoint": "[进度摘要]",
            }.get(name, ""),
        )
    ctx.register_hook("pre_gateway_dispatch", commands.inbound)
    ctx.register_hook("pre_llm_call", commands.pre_llm)
    ctx.register_hook("post_llm_call", commands.post_llm)
