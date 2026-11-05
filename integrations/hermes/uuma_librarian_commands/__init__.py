"""Deterministic read-only Telegram commands for Librarian."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def source_command(device: str, source: str) -> str:
    key = json.dumps([device, source], ensure_ascii=True, separators=(",", ":"))
    return "library_source_" + hashlib.sha256(key.encode()).hexdigest()[:16]


class LibrarianCommands:
    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx

    def run(self, command: str, args: str = "") -> str:
        if self.ctx.profile_name != "librarian":
            return "这些指令仅供 Librarian 使用。"
        try:
            receipt = self.ctx.call_mcp(
                "uuma-librarian-operations", "librarian_get_operations_status", {}, timeout=30,
            )
            if not receipt.get("ok") or receipt.get("truncated"):
                raise ValueError("Unavailable operations evidence")
            data = receipt["result"]
            if isinstance(data, str):
                data = json.loads(data)
            if not isinstance(data, dict) or data.get("error"):
                raise ValueError("Invalid operations evidence")
            sources = data["sources"]
            if command.startswith("library_source_"):
                row = next((r for r in sources if source_command(
                    r["device"], r["source_id"],
                ) == command), None)
                if row is None:
                    return "该来源当前不可用。返回来源列表 /library_sources"
                freshness_map = {
                    "FRESH": "正常（最新）",
                    "EXPIRING": "即将过期",
                    "OVERDUE": "已超期（未收到今日备份）",
                    "EXPIRED": f"已过期（逾期 {row.get('days_since')} 天）" if row.get("days_since") is not None else "已过期",
                    "NO_BACKUP": "尚无接收记录",
                    "SNAPSHOT": "里程碑快照",
                }
                fresh_label = freshness_map.get(row.get("freshness", ""), "已过期" if row.get("is_expired") else "正常")
                return (
                    f"📁 {row['device']} · {row['source_id']}\n"
                    f"最近批次日期 {row.get('scheduled_date') or '尚无接收记录'}\n"
                    f"备份时效 {fresh_label}\n"
                    f"采集范围状态 {row['coverage']}\n"
                    f"已采集 {row.get('captured_entries', 0)} 项，"
                    f"不可用 {row.get('unavailable_entries', 0)} 项\n"
                    f"NAS 发布回执 {'已有' if row['nas_publication_receipt'] else '待确认'}\n"
                    f"内容查询 {'已接入' if row['content_queryable'] else '待接入'}\n"
                    f"批次 {row.get('batch_id', '无')}\n"
                    "返回 /library_sources · 总览 /library"
                )
            if command in {"library_sources", "library_issues"}:
                if command == "library_issues":
                    sources = [r for r in sources if r["coverage"] != "COMPLETE"
                               or not r["nas_publication_receipt"]
                               or r.get("is_expired", False)]
                page = int(args or "1")
                if page < 1:
                    raise ValueError("Invalid page")
                selected = sources[(page - 1) * 8:page * 8]
                lines = [f"📚 {'待检查来源' if command == 'library_issues' else '备份来源'} · 第 {page} 页"]
                for row in selected:
                    status_tags = []
                    if row["coverage"] != "COMPLETE":
                        status_tags.append(row["coverage"])
                    if not row["nas_publication_receipt"]:
                        status_tags.append("待确认发布")
                    if row.get("is_expired"):
                        status_tags.append("已过期" if row.get("freshness") == "EXPIRED" else "已超期")
                    tag_str = " · ".join(status_tags) if status_tags else "正常"
                    lines.append(
                        f"• {row['device']} / {row['source_id']}\n"
                        f"  {row.get('scheduled_date') or '无接收记录'} · {tag_str}\n"
                        f"  /{source_command(row['device'], row['source_id'])}"
                    )
                if not selected:
                    lines.append("本页没有匹配来源。")
                if page * 8 < len(sources):
                    lines.append(f"下一页 /{command}_page_{page + 1}")
                lines.append("总览 /library · 来源 /library_sources · 待检查 /library_issues")
                return "\n".join(lines)
            catalog = data["catalog"]
            issues_count = data.get(
                "issues_count",
                sum(s["coverage"] != "COMPLETE" or not s["nas_publication_receipt"] or s.get("is_expired", False)
                    for s in sources),
            )
            return (
                "📚 Librarian 总览\n"
                f"节点 {data['node']}\n"
                f"查询时间 {data['observed_at']}\n"
                f"已接收 {data['received_batches']} 个批次 / {data['received_revisions']} 个版本\n"
                f"NAS 发布回执 {data['nas_published_revisions']} 个版本，"
                f"待发布 {data['nas_pending_revisions']} 个版本\n"
                f"来源 {len(data['sources'])} 个（待检查 {issues_count} 个）\n"
                f"可查询目录 {'可用' if catalog['available'] else '暂不可用'}，"
                f"{len(catalog.get('sources', []))} 个来源 / "
                f"{catalog.get('record_versions', 0)} 条记录版本\n"
                "日常备份 每日 00:00（马来西亚）\n"
                "打印机配置 每周日 00:00（马来西亚）\n\n"
                "来源列表 /library_sources\n待检查 /library_issues\n刷新总览 /library\n"
                "状态依据接收与发布回执。本次查询未重新校验备份文件或执行恢复。"
            )
        except (OSError, ValueError, KeyError, TypeError, RuntimeError):
            return "查询未完成，备份证据暂不可用。请稍后点 /library 重试。"


def register(ctx: Any) -> None:
    if ctx.profile_name != "librarian":
        return
    commands = LibrarianCommands(ctx)
    for name, description in (
        ("library", "Librarian 备份总览"),
        ("library_sources", "查看所有备份来源"),
        ("library_issues", "查看采集缺项与待发布来源"),
    ):
        ctx.register_command(name.replace("_", "-"),
                             lambda args="", n=name: commands.run(n, args),
                             description=description)
    # Register stable source keys from a trusted deployment inventory, never list positions.
    for row in ctx.get_config("sources", []):
        name = source_command(row["device"], row["source_id"])
        ctx.register_command(name.replace("_", "-"), lambda args="", n=name: commands.run(n),
                             description="查看备份来源详情")
    for kind in ("library_sources", "library_issues"):
        for page in range(1, 101):
            ctx.register_command(
                f"{kind}_page_{page}".replace("_", "-"),
                lambda args="", n=kind, p=page: commands.run(n, str(p)),
                description="备份来源翻页",
            )
