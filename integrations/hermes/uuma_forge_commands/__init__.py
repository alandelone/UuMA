"""Forge-only, deterministic slash commands; no model calls or direct SQL access."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml


def _text(value: Any, limit: int = 100) -> str:
    return " ".join(str("未记录" if value is None or value == "" else value).split())[:limit]


class ForgeCommands:
    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx

    def _authorized(self) -> bool:
        return self.ctx.profile_name == "forge-lab-bot"

    def _root(self) -> Path:
        value = self.ctx.get_config("workspace_root", "")
        if not value:
            raise ValueError("Forge 工作区尚未配置。")
        root = Path(value).resolve()
        if not root.is_dir():
            raise ValueError("Forge 工作区当前不可用。")
        return root

    def _read(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self._authorized():
            raise PermissionError("这些指令仅供 forge-lab-bot 使用。")
        receipt = self.ctx.call_mcp("uuma-worker", tool, arguments, timeout=30)
        if not receipt.get("ok") or receipt.get("truncated"):
            raise ValueError("数据读取未成功或返回不完整，请稍后重试。")
        result = receipt.get("result")
        if isinstance(result, str):
            result = json.loads(result)
        if not isinstance(result, dict) or result.get("error"):
            raise ValueError("数据当前不可用，不能据此判断为空。")
        return result

    def run(self, command: str, raw_args: str = "") -> str:
        if not self._authorized():
            return "这些硬件指令仅供 forge-lab-bot 使用。"
        try:
            return str(getattr(self, command)(raw_args.strip()))[:3500]
        except (OSError, ValueError, TypeError, KeyError, PermissionError, RuntimeError, yaml.YAMLError):
            return "查询未完成：数据源或连接暂不可用，请稍后重试。未修改库存或项目记录。"

    def forge(self, _args: str = "") -> str:
        return (
            "锻造 Lab_Bot · Hermes 硬件工作台\n\n"
            "快捷查询由本地代码处理，不调用语言模型：\n"
            "/inventory [元器件ID] — 实际库存与采购证据概况\n"
            "/projects [关键词] — 硬件项目与实际 Build 记录\n"
            "/shortages [项目关键词或BOM相对路径] — BOM 候选与缺料比对\n"
            "/worklog [项目名] — 最近实验、装配及维修日志\n\n"
            "Hermes 会话控制：\n"
            "/model — 查看或切换本会话模型\n"
            "/cancel 或 /stop — 停止当前 Hermes 任务\n"
            "/queue list 或 /queue clear — 查看或清空待处理消息\n"
            "/new 或 /reset — 开启新会话\n"
            "/help — Hermes 完整指令；/forge — 本硬件操作指南\n\n"
            "普通文字、图片和语音继续交给 Hermes Forge；需要记录实验时请明确说明。\n"
            "采购记录不等于已入库；项目设计不等于 As-Built。"
        )

    def cancel(self, _args: str = "") -> str:
        # The profile's native quick alias routes /cancel to /stop before plugin dispatch.
        return "请使用 /stop 停止当前 Hermes 任务；/queue clear 清空待处理消息。"

    def inventory(self, args: str) -> str:
        result = self._read("inventory_get_balances", {"component_id": args}) if args else (
            self._read("inventory_status", {})
        )
        rows = result["balances"]
        if not isinstance(rows, list):
            raise TypeError("Invalid inventory response")
        lines = ["📦 Forge 实际库存（按库存事件计算）"]
        for row in rows[:15]:
            lines.append(
                f"• {_text(row.get('component_id'))}：{_text(row.get('quantity'))}"
                f"；{_text(row.get('bucket'))}；位置 {_text(row.get('location_id'))}"
            )
        if not rows:
            lines.append("没有匹配的已登记库存余额；这不证明实际物料不存在。")
        if len(rows) > 15:
            lines.append("仅列出前 15 项；可带元器件ID缩小范围。")
        if not args:
            lines.append(f"采购证据：{result.get('purchase_history_count', '未知')} 条；采购不等于入库。")
            lines.append(f"待身份核对：{result.get('purchase_review_count', '未知')} 条。")
        return "\n".join(lines)

    def projects(self, args: str) -> str:
        root = self._root()
        lines = ["🏗 Forge 硬件项目（工作区项目定义）"]
        count = 0
        for path in sorted((root / "projects").glob("*/project.yaml")):
            if not path.resolve().is_relative_to(root):
                continue
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                continue
            title = str(data.get("name") or path.parent.name)
            if args and args.casefold() not in (title + path.parent.name).casefold():
                continue
            count += 1
            code = _text(data.get("project_code"))
            lines.append(f"• PROJ-{code} {_text(title)}\n  状态：{_text(data.get('status'))}")
            if count >= 12:
                lines.append("仅列出前 12 项；可带关键词缩小范围。")
                break
        if not count:
            lines.append("没有匹配的项目定义。")
        try:
            builds = self._read("lab_list_builds", {"limit": 5}).get("builds", [])
            lines.append("\n最近实际 Build（独立于项目设计列表）：")
            lines.extend(f"• {_text(row.get('build_id'))}：{_text(row.get('status'))}" for row in builds)
            if not builds:
                lines.append("尚无已登记 Build。")
        except (ValueError, RuntimeError, PermissionError):
            lines.append("Build 数据暂不可用，不能判断为没有 Build。")
        return "\n".join(lines)

    def shortages(self, args: str) -> str:
        root = self._root()
        if args and Path(args.strip('"')).suffix.lower() in {".csv", ".json", ".xlsx"}:
            path = (root / args.strip('"')).resolve()
            if not path.is_relative_to(root / "projects") or "bom" not in path.parts:
                return "请指定工作区 projects/<项目>/bom/ 内的 BOM 文件。"
            if not path.is_file():
                return "指定的 BOM 文件不存在；未进行缺料判断。"
            result = self._read("lab_analyze_bom", {"input_path": str(path)})
            inventory = result.get("inventory")
            if not isinstance(inventory, dict):
                return "BOM 型号身份尚未完成核对，暂不能确认缺料。未创建采购或库存操作。"
            lines = ["BOM 与实际可用库存比对："]
            for item in inventory.get("items", [])[:15]:
                lines.append(
                    f"• {_text(item.get('component_id'))}：需要 {_text(item.get('required'))}，"
                    f"可用 {_text(item.get('available'))}，缺少 {_text(item.get('shortage'))}"
                )
            lines.append(f"比对状态：{_text(inventory.get('status'))}；未创建采购或库存操作。")
            return "\n".join(lines)
        lines = ["📋 Forge BOM 候选文件"]
        count = 0
        for path in sorted((root / "projects").glob("*/bom/*-candidates.csv")):
            if not path.resolve().is_relative_to(root):
                continue
            if args and args.casefold() not in path.parent.parent.name.casefold():
                continue
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = sum(1 for row in csv.DictReader(stream) if any(row.values()))
            lines.append(f"• {path.relative_to(root).as_posix()}：{rows} 条候选")
            count += 1
            if count >= 12:
                break
        if not count:
            lines.append("没有匹配的 BOM 候选文件。")
        lines.append("\n以上是候选条目，不是已确认缺料。")
        lines.append("用 /shortages projects/<项目>/bom/<文件>.csv 执行实际比对。")
        return "\n".join(lines)

    def worklog(self, args: str) -> str:
        rows = self._read("lab_list_worklogs", {"project_name": args, "limit": 5})["worklogs"]
        if not isinstance(rows, list):
            raise TypeError("Invalid worklog response")
        lines = ["📝 Forge 最近实验与维修日志"]
        for row in rows:
            lines.append(
                f"• {_text(row.get('occurred_at'), 10)} · {_text(row.get('project_name'))}\n"
                f"  操作：{_text(row.get('action'))}\n  结果：{_text(row.get('result'))}"
            )
        if not rows:
            lines.append("没有匹配的已登记日志。")
        lines.append("\n需要新记录时，直接发送文字或语音并说明“记录这次实验/维修”。本查询不写入日志。")
        return "\n".join(lines)


def register(ctx: Any) -> None:
    if ctx.profile_name != "forge-lab-bot":
        return
    commands = ForgeCommands(ctx)
    for name, description, hint in (
        ("forge", "Hermes Forge 硬件操作指南（本地代码）", ""),
        ("inventory", "查看实际库存与采购证据（本地代码）", "[元器件ID]"),
        ("projects", "查看硬件项目和实际 Build（本地代码）", "[关键词]"),
        ("shortages", "查看 BOM 候选或执行缺料比对（本地代码）", "[项目或BOM路径]"),
        ("worklog", "查看最近实验与维修日志（本地代码）", "[项目名]"),
        ("cancel", "停止当前 Hermes 任务（等同 /stop）", ""),
    ):
        def handler(raw_args: str = "", command: str = name) -> str:
            return commands.run(command, raw_args)

        ctx.register_command(name, handler, description=description, args_hint=hint)
