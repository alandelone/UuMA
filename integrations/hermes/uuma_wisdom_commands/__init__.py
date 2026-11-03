"""Wisdom-Oldman progress reads: no model, retrieval, route binding or research writes."""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from typing import Any

LABELS = {
    "QUEUED": "排队中",
    "ACTIVE": "研究中",
    "PAUSED": "已暂停",
    "COMPLETED": "已完成",
    "STOPPED": "已停止",
    "BUDGET_EXHAUSTED": "预算已用完",
    "BLOCKED": "受阻",
    "FAILED": "失败",
    "OPEN": "未解决",
    "FILLED": "已补齐",
    "IN_PROGRESS": "进行中",
}


def text(value: Any, limit: int = 160) -> str:
    return " ".join(str(value or "未记录").split())[:limit]


def task_title(row: dict[str, Any]) -> str:
    """Shorten known boilerplate; keep the original objective available in details."""
    reason = str(row.get("stop_reason") or "").casefold()
    original = text(row.get("topic_title") or row.get("objective") or row.get("root_question"), 500)
    if "progress request was incorrectly processed" in reason:
        return "进度查询（历史误建）"
    if "invalid topic originated" in reason:
        return "错误响应（历史误建）"
    if original.casefold().startswith("verify restart-safe unattended research"):
        return "后台研究恢复验证"
    original = re.sub(r"^Resolve the worthwhile evidence gaps for:\s*", "", original, flags=re.IGNORECASE)
    return text(original.strip(" '\"：:"), 48)


def reason_summary(row: dict[str, Any]) -> str:
    raw = text(row.get("stop_reason"), 2000)
    reason = raw.casefold()
    if "progress request was incorrectly processed" in reason:
        return "曾把查进度误当成研究，现已停止。"
    if "invalid topic originated" in reason:
        return "曾把错误响应误当成议题，现已停止。"
    if row.get("status") == "BUDGET_EXHAUSTED" or "research budget limit" in reason:
        return "已达到本次研究预算上限。"
    if "kag recovery failed" in reason:
        return "当时知识服务未能连接。"
    if "urlerror" in reason or "connection" in reason or "timed out" in reason:
        return "当时研究服务连接失败。"
    if "source-linked json" in reason:
        return "未取得有效的带来源研究结果。"
    # User-facing Chinese reasons can remain; logs and unknown technical strings stay in details.
    if (
        re.search(r"[\u4e00-\u9fff]", raw)
        and len(raw) <= 70
        and not re.search(r"[A-Za-z]:[\\/]|https?://|traceback|level=|msg=", raw, re.IGNORECASE)
    ):
        return raw
    return "具体原因见详细记录。" if row.get("stop_reason") else ""


def progress_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Newest first within a stable status group; keep every task individually addressable."""
    group = {"ACTIVE": 0, "QUEUED": 0, "BLOCKED": 1, "PAUSED": 1, "BUDGET_EXHAUSTED": 1}
    return sorted(
        sorted(rows, key=lambda row: str(row.get("updated_at", "")), reverse=True),
        key=lambda row: group.get(row["status"], 2),
    )


def progress_overview(rows: list[dict[str, Any]]) -> str:
    rows = progress_rows(rows)
    counts = Counter(row["status"] for row in rows)
    lines = ["研究进度", ""]
    if not rows:
        return "研究进度\n\n暂无已保存的研究任务。\n\n/topics 查看研究议题"
    running = sum(counts[status] for status in ("ACTIVE", "QUEUED"))
    lines.append(f"进行或排队中：{running} 项" if running else "目前没有正在运行或排队的研究。")
    lines.append(
        f"最近 {len(rows)} 项 · "
        + " · ".join(f"{LABELS.get(status, status)} {count}" for status, count in counts.items())
    )
    previous_group = None
    for index, row in enumerate(rows[:8], start=1):
        status = row["status"]
        group = (
            "当前研究"
            if status in {"ACTIVE", "QUEUED"}
            else "需要留意"
            if status in {"PAUSED", "BLOCKED", "BUDGET_EXHAUSTED"}
            else "历史记录"
        )
        if group != previous_group:
            lines.extend(["", group])
            previous_group = group
        lines.extend(["", f"{index}. {task_title(row)} [/progress_{index}]", f"   {LABELS.get(status, status)}"])
        reason = reason_summary(row)
        if reason:
            lines.append("   " + reason)
    if len(rows) > 8:
        lines.extend(["", "仅展开前 8 项，可用 /progress page 2 [/progress_page_2] 查看更多。"])
    lines.extend([
        "",
        "查看议题：/topics",
        "查看第 1 项原始记录：/progress detail 1 [/progress_1]",
    ])
    return "\n".join(lines)


def task_detail(row: dict[str, Any], index: int) -> str:
    """Explicit drill-down retains evidence without dumping logs into the overview."""
    lines = [
        f"研究记录 · 第 {index} 项",
        "",
        task_title(row),
        "状态：" + LABELS.get(row["status"], row["status"]),
        "更新：" + text(row.get("updated_at")),
        "",
        "原始任务：",
        text(row.get("objective") or row.get("root_question"), 700),
    ]
    if row.get("stop_reason"):
        lines.extend(["", "原始原因（历史记录）：", text(row["stop_reason"], 1500)])
    if row.get("orbit_id"):
        lines.extend(["", "记录ID：" + str(row["orbit_id"])])
    lines.extend(["", "/progress 返回总览"])
    return "\n".join(lines)


class WisdomCommands:
    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx

    def read(self, tool: str, **arguments: Any) -> dict[str, Any]:
        if self.ctx.profile_name != "wisdom-oldman":
            raise PermissionError("Wisdom-only command")
        if tool not in {"knowledge_topic_list", "knowledge_topic_get", "knowledge_orbit_list"}:
            raise PermissionError("Read-only command")
        receipt = self.ctx.call_mcp("wisdom-knowledge", tool, arguments, timeout=30)
        if receipt.get("ok") is False and receipt.get("error") == (
            "MCP server 'wisdom-knowledge' is not connected"
        ):
            # Slash commands can precede the first model turn. Reuse Hermes' scoped client;
            # initialize only this server, then retry the same read through the permission gate.
            from tools.mcp_tool_discovery import discover_mcp_tools

            discover_mcp_tools(allowed_mcp_names=["wisdom-knowledge"])
            receipt = self.ctx.call_mcp("wisdom-knowledge", tool, arguments, timeout=30)
        if receipt.get("ok") is not True or receipt.get("truncated"):
            raise ValueError("Incomplete research receipt")
        result = receipt.get("result")
        if isinstance(result, str):
            result = json.loads(result)
        if not isinstance(result, dict) or result.get("error") or result.get("isError"):
            raise ValueError("Research read failed")
        return result

    def run(self, command: str, args: str = "") -> str:
        try:
            # Handle 1-tap unspaced slash subcommands
            norm_cmd = command.replace("-", "_")
            if norm_cmd.startswith("progress_page_"):
                return self.run("progress", f"page {norm_cmd[14:]}")
            if norm_cmd.startswith("progress_"):
                return self.run("progress", f"detail {norm_cmd[9:]}")
            if norm_cmd.startswith("topics_page_"):
                return self.run("topics", f"{norm_cmd[12:]}")
            if norm_cmd.startswith("topics_"):
                idx = int(norm_cmd[7:])
                topic_rows = self.read("knowledge_topic_list", limit=500)["records"]
                if 1 <= idx <= len(topic_rows):
                    return self.run("progress", str(topic_rows[idx - 1]["topic_id"]))
                return "找不到该编号的议题。用 /topics 查看列表。"
            if command not in {"topics", "progress", "wisdom"}:
                raise ValueError("Unknown command")
            if command == "wisdom":
                return (
                    "🦉 Wisdom-Oldman · 研究进度操作指南\n\n"
                    "👉 快捷命令（点击直接发送）：\n"
                    "• /topics ：查看已保存的研究议题\n"
                    "• /progress ：查看研究总览\n\n"
                    "👉 点击复制发送，查询详情：\n"
                    "`/topics 2` （查看议题第 2 页）\n"
                    "`/progress detail 1` （查看列表第 1 项的原始记录）\n"
                    "`/progress 议题名称或ID` （查看指定议题进度）\n\n"
                    "以上入口只查询已保存状态，不启动或修改研究。"
                )
            if command == "topics":
                page = int(args.strip() or "1")
                if page < 1:
                    raise ValueError("Invalid page")
                rows = self.read("knowledge_topic_list", limit=500)["records"]
                pages = max(1, (len(rows) + 7) // 8)
                if page > pages:
                    return f"没有这一页。请使用 /topics {pages}"
                lines = [f"研究议题（已读取 {len(rows)} 个，第 {page}/{pages} 页）"]
                for idx, row in enumerate(rows[(page - 1) * 8 : page * 8], start=1):
                    item_num = (page - 1) * 8 + idx
                    lines.extend(
                        [
                            f"• {item_num}. {text(row['title'])}〔{text(row.get('status'))}〕 [/topics_{item_num}]",
                            f"  /progress {row['topic_id']}",
                        ]
                    )
                if not rows:
                    lines.append("暂无已保存议题。")
                if len(rows) == 500:
                    lines.append("仅显示最近500个议题，可用已知ID直接查询。")
                if page < pages:
                    lines.append(f"下一页：/topics {page + 1} [/topics_page_{page + 1}]")
                return "\n".join(lines)[:3500]
            selector = args.strip()
            detail = re.fullmatch(r"detail\s+([1-9]\d*)", selector, flags=re.IGNORECASE)
            page = re.fullmatch(r"page\s+([1-9]\d*)", selector, flags=re.IGNORECASE)
            if not selector or detail or page:
                rows = self.read("knowledge_orbit_list", limit=100)["records"]
                if detail:
                    index = int(detail[1])
                    ordered = progress_rows(rows)
                    if index > len(ordered):
                        return "没有这条记录。/progress 查看当前列表。"
                    return task_detail(ordered[index - 1], index)[:3500]
                if page:
                    index = int(page[1])
                    ordered = progress_rows(rows)
                    start = (index - 1) * 8
                    if start >= len(ordered):
                        return "没有这一页。/progress 返回总览。"
                    lines = [f"研究记录 · 第 {index} 页"]
                    for number, row in enumerate(ordered[start : start + 8], start=start + 1):
                        lines.extend(
                            [
                                "",
                                f"{number}. {task_title(row)}",
                                "   " + LABELS.get(row["status"], row["status"]),
                            ]
                        )
                        reason = reason_summary(row)
                        if reason:
                            lines.append("   " + reason)
                    if start + 8 < len(ordered):
                        lines.extend(["", f"下一页：/progress page {index + 1}"])
                    lines.extend(
                        [
                            "",
                            f"原始记录：/progress detail {start + 1}",
                            f"👉 点击复制：`/progress detail {start + 1}`",
                            "/progress 返回总览",
                        ]
                    )
                    return "\n".join(lines)[:3500]
                return progress_overview(rows)[:3500]
            # IDs resolve directly; names must uniquely identify an existing topic.
            rows = self.read("knowledge_topic_list", limit=500)["records"]
            matches = [
                row
                for row in rows
                if selector.casefold()
                in {str(row["topic_id"]).casefold(), str(row["title"]).casefold()}
            ]
            if not matches:
                matches = [
                    row for row in rows if selector.casefold() in str(row["title"]).casefold()
                ]
            if len(matches) > 1:
                return "找到多个议题，请使用ID：\n" + "\n".join(
                    f"{text(row['title'], 100)}\n/progress {row['topic_id']}" for row in matches[:8]
                )
            if not matches and not selector.startswith("topic_"):
                return "找不到这个议题。用 /topics 查看已有议题；查询不会新建议题。"
            data = self.read(
                "knowledge_topic_get", topic_id=matches[0]["topic_id"] if matches else selector
            )
            topic_status = str(data["topic"].get("status") or "未记录")
            lines = [
                text(data["topic"]["title"], 100),
                "",
                "议题："
                + {"ACTIVE": "保留中", "ARCHIVED": "已归档"}.get(topic_status, topic_status),
            ]
            document = data.get("document") or {}
            lines.append("研究文档版本：" + str(document.get("current_version", 0)))
            lines.extend(["", "研究任务"])
            for row in data["orbits"][:6]:
                lines.extend(
                    ["", "• " + task_title(row), "  " + LABELS.get(row["status"], row["status"])]
                )
                if reason_summary(row):
                    lines.append("  " + reason_summary(row))
            if not data["orbits"]:
                lines.append("暂无后台研究任务。")
            lines.append("\n相关问题：")
            for entry in data["questions"][:6]:
                question = entry["question"]
                status = question.get("status", "未记录")
                lines.append(f"• {text(question['text'])}〔{LABELS.get(status, status)}〕")
            if not data["questions"]:
                lines.append("暂无问题记录。")
            if data.get("document_url"):
                lines.append("\n研究文档：" + data["document_url"])
            return "\n".join(lines)[:3500]
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, PermissionError):
            return "进度查询未完成：数据源或连接暂不可用。请稍后重试；未启动或修改研究。"


def register(ctx: Any) -> None:
    if ctx.profile_name != "wisdom-oldman":
        return
    commands = WisdomCommands(ctx)
    for name, description, hint in [
        ("wisdom", "研究进度操作指南", ""),
        ("topics", "查看已保存的研究议题", "[页码]"),
        ("progress", "查看研究任务或议题进度", "[议题名称或ID]"),
    ]:
        handler = lambda raw_args="", c=name: asyncio.to_thread(commands.run, c, raw_args)
        ctx.register_command(name, handler, description=description, args_hint=hint)

    # 1-tap direct progress detail items (/progress_1 to /progress_16)
    for i in range(1, 17):
        desc = f"查看第 {i} 项研究任务详情"
        h_prog = lambda raw_args="", i=i: asyncio.to_thread(commands.run, f"progress_{i}", raw_args)
        ctx.register_command(f"progress_{i}", h_prog, description=desc)
        ctx.register_command(f"progress-{i}", h_prog, description=desc)

    # 1-tap direct progress page items (/progress_page_2 to /progress_page_5)
    for p in range(2, 6):
        desc = f"查看研究记录第 {p} 页"
        h_page = lambda raw_args="", p=p: asyncio.to_thread(commands.run, f"progress_page_{p}", raw_args)
        ctx.register_command(f"progress_page_{p}", h_page, description=desc)
        ctx.register_command(f"progress-page-{p}", h_page, description=desc)

    # 1-tap direct topics items (/topics_1 to /topics_16)
    for i in range(1, 17):
        desc = f"查看第 {i} 个议题详情与研究任务"
        h_top = lambda raw_args="", i=i: asyncio.to_thread(commands.run, f"topics_{i}", raw_args)
        ctx.register_command(f"topics_{i}", h_top, description=desc)
        ctx.register_command(f"topics-{i}", h_top, description=desc)

    # 1-tap direct topics page items (/topics_page_2 to /topics_page_5)
    for p in range(2, 6):
        desc = f"查看研究议题第 {p} 页"
        h_tpage = lambda raw_args="", p=p: asyncio.to_thread(commands.run, f"topics_page_{p}", raw_args)
        ctx.register_command(f"topics_page_{p}", h_tpage, description=desc)
        ctx.register_command(f"topics-page-{p}", h_tpage, description=desc)
