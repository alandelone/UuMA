"""Read-only user guide and real-time project navigation for Yonc.

Queries the live project graph (API/SQLite) dynamically to surface real projects
ordered by deadline and timeline, indexed with hierarchical numbers (e.g. 1.1, 1.2)
for effortless reference in chat and subcommands.
Never mutates graph truth or assigns tasks without explicit user authorization.
"""

from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Fallback baseline nodes for local unit testing and offline development
_TODAY = datetime.now(UTC).date()
_TODAY_ISO = _TODAY.isoformat()
_IN_5D = (_TODAY + timedelta(days=5)).isoformat()
_IN_10D = (_TODAY + timedelta(days=10)).isoformat()
_IN_15D = (_TODAY + timedelta(days=15)).isoformat()
_IN_30D = (_TODAY + timedelta(days=30)).isoformat()
_PAST_5D = (_TODAY - timedelta(days=5)).isoformat()
_PAST_10D = (_TODAY - timedelta(days=10)).isoformat()

FALLBACK_NODES: list[dict[str, Any]] = [
    {
        "id": "bfe67c96-1111-488b-a019-d34cb9907b23",
        "title": "Thesis Phd Logic",
        "work_type": "GOAL",
        "stage": "PLANNING",
        "status": "TODO",
        "deadline": _TODAY_ISO,
        "planned_end": _TODAY_ISO,
        "tags": {"Task Theme with colour": "PhDSettle✒ Research | Review | Event | SolarMan | 心法 | 科研人 | Thesis | Dev"},
        "description": "PhD Thesis theoretical framing and logic",
    },
    {
        "id": "a8f392a8-2222-488b-a019-d34cb9907b23",
        "title": "Research Rs_SF Writing",
        "work_type": "GOAL",
        "stage": "PLANNING",
        "status": "TODO",
        "deadline": _TODAY_ISO,
        "planned_end": _TODAY_ISO,
        "tags": {"Task Theme with colour": "PhDSettle✒ Research | Review | Event | SolarMan | 心法 | 科研人 | Thesis | Dev"},
        "description": "Smart finance paper draft and methodology",
    },
    {
        "id": "c29cc05d-3333-488b-a019-d34cb9907b23",
        "title": "Research Rs_EMS Writing",
        "work_type": "GOAL",
        "stage": "PLANNING",
        "status": "TODO",
        "deadline": None,
        "planned_end": "2026-11-03",
        "tags": {"Task Theme with colour": "PhDSettle✒ Research | Review | Event | SolarMan | 心法 | 科研人 | Thesis | Dev"},
        "description": "Energy management system paper writing",
    },
    {
        "id": "29b5c29d-4444-488b-a019-d34cb9907b23",
        "title": "Research Rs_SF_risk",
        "work_type": "GOAL",
        "stage": "PLANNING",
        "status": "TODO",
        "deadline": "2026-11-09",
        "planned_end": "2026-11-09",
        "tags": {"Task Theme with colour": "PhDSettle✒ Research | Review | Event | SolarMan | 心法 | 科研人 | Thesis | Dev"},
        "description": "Risk aversion models and validation",
    },
    {
        "id": "57b44647-5555-488b-a019-d34cb9907b23",
        "title": "Thesis thesis writing",
        "work_type": "GOAL",
        "stage": "PLANNING",
        "status": "TODO",
        "deadline": None,
        "planned_end": "2026-11-12",
        "tags": {"Task Theme with colour": "PhDSettle✒ Research | Review | Event | SolarMan | 心法 | 科研人 | Thesis | Dev"},
        "description": "PhD dissertation main chapters compilation",
    },
    {
        "id": "ff92eba1-6666-488b-a019-d34cb9907b23",
        "title": "Thesis proposal defense Slide",
        "work_type": "GOAL",
        "stage": "PLANNING",
        "status": "TODO",
        "deadline": None,
        "planned_end": "2026-12-11",
        "tags": {"Task Theme with colour": "PhDSettle✒ Research | Review | Event | SolarMan | 心法 | 科研人 | Thesis | Dev"},
        "description": "Proposal defense slides preparation",
    },
    {
        "id": "3cc4baf3-7777-488b-a019-d34cb9907b23",
        "title": "Dev Weather tower Prototype",
        "work_type": "GOAL",
        "stage": "PLANNING",
        "status": "TODO",
        "deadline": "2026-10-20",
        "planned_end": "2026-10-20",
        "tags": {"Task Theme with colour": "PhDSettle✒ Research | Review | Event | SolarMan | 心法 | 科研人 | Thesis | Dev"},
        "description": "Weather tower hardware and sensor prototype",
    },
    {
        "id": "aaeb1c1e-8888-488b-a019-d34cb9907b23",
        "title": "Dev Trade-Enabled NanoCentralised OGPV 交易原型",
        "work_type": "GOAL",
        "stage": "PLANNING",
        "status": "TODO",
        "deadline": None,
        "planned_end": "2026-10-24",
        "tags": {"Task Theme with colour": "PhDSettle✒ Research | Review | Event | SolarMan | 心法 | 科研人 | Thesis | Dev"},
        "description": "Microgrid energy trading demo prototype",
    },
    {
        "id": "938b3261-9999-488b-a019-d34cb9907b23",
        "title": "Thesis Phd RsPlan",
        "work_type": "GOAL",
        "stage": "PLANNING",
        "status": "TODO",
        "deadline": None,
        "planned_end": "2026-10-18",
        "tags": {"Task Theme with colour": "PhDSettle✒ Research | Review | Event | SolarMan | 心法 | 科研人 | Thesis | Dev"},
        "description": "PhD Research plan and timeline tracking",
    },
    {
        "id": "3e80439a-aaaa-488b-a019-d34cb9907b23",
        "title": "素食堂 菜单开发",
        "work_type": "GOAL",
        "stage": "PLANNING",
        "status": "TODO",
        "deadline": None,
        "planned_end": None,
        "tags": {"Task Theme with colour": "小事业们  素食堂🍱 | Aero🥦 | 农业⚙️🚜工作室 | I人工作室 | 事业内功 | 1粒工房"},
        "description": "素食菜品研发与标准化",
    },
    {
        "id": "2a8fcc11-bbbb-488b-a019-d34cb9907b23",
        "title": "素食堂 Sushitam 开业 planning",
        "work_type": "GOAL",
        "stage": "PLANNING",
        "status": "TODO",
        "deadline": None,
        "planned_end": None,
        "tags": {"Task Theme with colour": "小事业们  素食堂🍱 | Aero🥦 | 农业⚙️🚜工作室 | I人工作室 | 事业内功 | 1粒工房"},
        "description": "Sushitam 筹备开业排期",
    },
    {
        "id": "4a501e20-cccc-488b-a019-d34cb9907b23",
        "title": "DZsp_V1 3dp Infra",
        "work_type": "GOAL",
        "stage": "PLANNING",
        "status": "TODO",
        "deadline": None,
        "planned_end": None,
        "tags": {"Task Theme with colour": "鍛造Lab 鍛造Maker | DZsp_V1 | 鍛造Lab"},
        "description": "3D 打印基础设施部署",
    },
    {
        "id": "a1853318-dddd-488b-a019-d34cb9907b23",
        "title": "纪事sys 纪事统筹SOP＆系统",
        "work_type": "GOAL",
        "stage": "PLANNING",
        "status": "TODO",
        "deadline": None,
        "planned_end": None,
        "tags": {"Task Theme with colour": "大事纪 Fotang | 要剪辑のvideo | 纪事sys"},
        "description": "佛堂与团队大事纪管理规范",
    },
    {
        "id": "ccb3808b-eeee-488b-a019-d34cb9907b23",
        "title": "我流方矩 知识技能學習流程の内化系统",
        "work_type": "GOAL",
        "stage": "PLANNING",
        "status": "TODO",
        "deadline": None,
        "planned_end": None,
        "tags": {"Task Theme with colour": "我流方矩 自我 | 学问 | 学养 | 知识结构 | self | 刚体 | Life | 方矩v4"},
        "description": "个人内化系统与知识技能体系",
    },
]


def _fetch_nodes() -> list[dict[str, Any]]:
    """Retrieve nodes from live API, falling back to local SQLite, then test fixture."""
    api_url = os.getenv("YONC_API_URL", "http://127.0.0.1:8766").rstrip("/")
    try:
        req = urllib.request.Request(
            f"{api_url}/api/v2/nodes",
            headers={"Accept": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and "nodes" in data and data["nodes"]:
                return data["nodes"]
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        pass

    db_candidates = [
        Path(os.getenv("YONC_GRAPH_DB", "")),
        Path("/home/alandelone/.local/share/uuma/production/yonc/project_graph.sqlite3"),
        Path.home() / ".local/share/uuma/production/yonc/project_graph.sqlite3",
    ]
    for db_path in db_candidates:
        if db_path.is_file():
            try:
                conn = sqlite3.connect(str(db_path), timeout=2.0)
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, title, node_kind, work_type, stage, status, deadline, planned_end, tags, description "
                    "FROM graph_nodes WHERE is_proposed = 0 AND archived_at IS NULL"
                )
                rows = cur.fetchall()
                conn.close()
                if rows:
                    nodes = []
                    for r in rows:
                        try:
                            tags = json.loads(r["tags"]) if r["tags"] else {}
                        except (ValueError, TypeError, json.JSONDecodeError):
                            tags = {}
                        nodes.append({
                            "id": r["id"],
                            "title": r["title"],
                            "node_kind": r["node_kind"],
                            "work_type": r["work_type"],
                            "stage": r["stage"],
                            "status": r["status"],
                            "deadline": r["deadline"],
                            "planned_end": r["planned_end"],
                            "tags": tags,
                            "description": r["description"],
                        })
                    return nodes
            except (sqlite3.Error, OSError):
                pass

    return FALLBACK_NODES


def _fetch_history() -> list[dict[str, Any]]:
    """Retrieve recent operations from live API."""
    api_url = os.getenv("YONC_API_URL", "http://127.0.0.1:8766").rstrip("/")
    try:
        req = urllib.request.Request(
            f"{api_url}/api/v2/operation-batches?limit=3",
            headers={"Accept": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list):
                return data
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        pass
    return []


def friendly_theme(theme_raw: str | None) -> str:
    """Map raw graph tag theme to a concise, readable category."""
    if not theme_raw:
        return "📌 其他未归档事项"
    if any(k in theme_raw for k in ("PhDSettle", "Research", "Thesis", "科研人")):
        return "🎓 博士与科研 (PhD / Research)"
    if any(k in theme_raw for k in ("鍛造", "DZsp")):
        return "🛠️ 鍛造Lab 与研发展造 (Maker & Lab)"
    if any(k in theme_raw for k in ("小事业", "素食堂", "1粒工房", "I人工作室")):
        return "🍱 小事业群 (素食堂 / 1粒工房 / I人工作室)"
    if any(k in theme_raw for k in ("大事纪", "纪事", "video")):
        return "🎬 大事纪与媒体剪辑 (Media & Video)"
    if any(k in theme_raw for k in ("方矩", "刚体", "Life")):
        return "🧘 我流方矩与生活系统 (Life & Mind)"
    if any(k in theme_raw for k in ("Headache", "SmallAct")):
        return "⚡ 突发与日常急件 (Urgent & Quick)"
    return "📌 其他未归档事项"


def _goal_urgency_key(g: dict[str, Any], today_str: str) -> tuple[int, str]:
    """Sort key prioritizing today's deadlines, then upcoming, then overdue, then undated."""
    d = g.get("deadline") or g.get("planned_end")
    if not d:
        return (3, g.get("title", ""))
    if d == today_str:
        return (0, d)
    if d > today_str:
        return (1, d)
    return (2, d)


def _build_project_groups(goals: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Organize active goals into ordered domains, sorted by deadline urgency within each."""
    today_str = datetime.now(UTC).date().isoformat()
    groups_dict: dict[str, list[dict[str, Any]]] = {}
    for g in goals:
        ft = friendly_theme(g.get("tags", {}).get("Task Theme with colour"))
        groups_dict.setdefault(ft, []).append(g)

    for cat_items in groups_dict.values():
        cat_items.sort(key=lambda g: _goal_urgency_key(g, today_str))

    order = [
        "🎓 博士与科研 (PhD / Research)",
        "🛠️ 鍛造Lab 与研发展造 (Maker & Lab)",
        "🍱 小事业群 (素食堂 / 1粒工房 / I人工作室)",
        "🎬 大事纪与媒体剪辑 (Media & Video)",
        "⚡ 突发与日常急件 (Urgent & Quick)",
        "🧘 我流方矩与生活系统 (Life & Mind)",
        "📌 其他未归档事项",
    ]
    result: list[tuple[str, list[dict[str, Any]]]] = []
    for cat in order:
        if cat in groups_dict:
            result.append((cat, groups_dict.pop(cat)))
    for remaining_cat, remaining_items in groups_dict.items():
        result.append((remaining_cat, remaining_items))
    return result


def _build_split_sections(goals: list[dict[str, Any]], today_str: str) -> list[tuple[str, str, list[dict[str, Any]]]]:
    """Organize goals with deadlines into urgent, upcoming, and overdue sections."""
    with_dates = [g for g in goals if g.get("deadline") or g.get("planned_end")]
    with_dates.sort(key=lambda x: x.get("deadline") or x.get("planned_end") or "9999")

    urgent = [g for g in with_dates if (g.get("deadline") or g.get("planned_end")) == today_str]
    upcoming = [g for g in with_dates if (g.get("deadline") or g.get("planned_end")) > today_str]
    overdue = [g for g in with_dates if (g.get("deadline") or g.get("planned_end")) < today_str]

    sections: list[tuple[str, str, list[dict[str, Any]]]] = []
    if urgent:
        sections.append((str(len(sections) + 1), "🚨 今日截止 / 最紧迫项目", urgent))
    if upcoming:
        sections.append((str(len(sections) + 1), "⏳ 临近截止项目（按时间线由近到远）", upcoming))
    if overdue:
        sections.append((str(len(sections) + 1), "⚠️ 已过期待推进项目", overdue))
    return sections


def render_split(keyword: str = "") -> str:
    """Render split suggestions sorted by timeline/deadline with clear index numbers."""
    nodes = _fetch_nodes()
    goals = [n for n in nodes if n.get("work_type") == "GOAL" and n.get("status") != "CANCELLED"]
    today_str = datetime.now(UTC).date().isoformat()
    split_sections = _build_split_sections(goals, today_str)

    clean_kw = keyword.strip().replace("_", ".")
    # Check if user requested a specific numbered item, e.g. "1.1" or "2.1"
    if clean_kw and "." in clean_kw:
        parts = clean_kw.split(".")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            s_idx = int(parts[0]) - 1
            i_idx = int(parts[1]) - 1
            if 0 <= s_idx < len(split_sections):
                s_num, s_title, s_items = split_sections[s_idx]
                if 0 <= i_idx < len(s_items):
                    target = s_items[i_idx]
                    d = target.get("deadline") or target.get("planned_end") or "未定排期"
                    is_today = " (今日)" if d == today_str else ""
                    return f"""🎯 待拆解项目：{s_num}.{i_idx + 1}〈{target.get('title')}〉
• 所属阶段: {s_title}
• 截止/计划: {d}{is_today} | 状态: {target.get('status', 'TODO')}
• 领域: {friendly_theme(target.get('tags', {}).get('Task Theme with colour'))}
• 描述: {target.get('description') or '暂无详细描述'}

👉 快捷点击操作（1-Tap免复制）：
• 查看完整项目卡：/yonc_projects_{s_num}_{i_idx + 1}
• 上下文与标准：/yonc_context_{s_num}_{i_idx + 1}
• 规划主要Action：/yonc_action_{s_num}_{i_idx + 1}

👉 轻点下方例句即可直接复制，粘贴发送：
`准备拆解 {s_num}.{i_idx + 1}〈{target.get('title')}〉，目标是两周内上线，先列出主要 Action。`
`准备拆解 {s_num}.{i_idx + 1}〈{target.get('title')}〉，补充子任务和测试流程。`

返回拆解总览：/yonc_split | 全部项目库：/yonc_projects | 返回总览：/yonc"""

    # Keyword text filter
    if clean_kw and clean_kw.casefold() not in ("split", "yonc_split", "yonc-split", "拆解"):
        matches = [
            g for g in goals
            if clean_kw.casefold() in g.get("title", "").casefold()
            or clean_kw.casefold() in str(g.get("tags", {})).casefold()
        ]
        lines = [f"🎯 匹配「{clean_kw}」的真实项目（共 {len(matches)} 个）：\n"]
        if not matches:
            lines.append("未在图谱中找到该关键词的项目。可用 /yonc_projects 浏览完整项目库。\n")
        else:
            for idx, g in enumerate(matches[:8], 1):
                d = g.get("deadline") or g.get("planned_end") or "未定排期"
                lines.append(f"1.{idx} {g.get('title')}")
                lines.append(f"     [排期/截止: {d} | 状态: {g.get('status', 'TODO')}]")
            first_title = matches[0]["title"]
            lines.append("\n👉 选定上述项目，轻点下方例句即可复制，粘贴发送：")
            lines.append(f"`准备拆解 1.1〈{first_title}〉，目标是两周内上线，先列出主要 Action。`")
            if len(matches) > 1:
                lines.append(f"`准备拆解 1.2〈{matches[1]['title']}〉，重点补充子任务和测试流程。`")
        lines.append("\n返回拆解全览：/yonc_split | 全部项目库：/yonc_projects | 返回总览：/yonc")
        return "\n".join(lines)

    lines = ["🎯 目标拆解与规划（按真实 Timeline / Deadline 排序）\n"]
    for s_num, s_title, items in split_sections:
        lines.append(f"{s_num}. {s_title}：")
        for j, g in enumerate(items, 1):
            d = g.get("deadline") or g.get("planned_end")
            is_today = " (今日)" if d == today_str else ""
            lines.append(f"  {s_num}.{j} {g.get('title')} [/yonc_split_{s_num}_{j}]")
            lines.append(f"      [截止/计划: {d}{is_today} | 状态: {g.get('status', 'TODO')}]")
        lines.append("")

    lines.append("💡 立即拆解推荐项目（轻点下方例句即可直接复制，粘贴发送）：")
    urgent_items = split_sections[0][2] if split_sections else []
    if urgent_items:
        lines.append(f"`准备拆解 1.1〈{urgent_items[0]['title']}〉，目标是两周内上线，先列出主要 Action。`")
        if len(urgent_items) > 1:
            lines.append(f"`准备拆解 1.2〈{urgent_items[1]['title']}〉，重点细化大纲与核心实验数据。`")
    elif split_sections:
        first_item = split_sections[0][2][0]
        lines.append(f"`准备拆解 1.1〈{first_item['title']}〉，梳理当前卡点与交付物。`")

    lines.append("\n📌 想直接查看项目？点击对应指令（如 /yonc_split_1_1）或输入 `/yonc_split <编号>`")
    lines.append("查看全部项目库：/yonc_projects | 返回总览：/yonc")
    return "\n".join(lines)



def _find_goal_by_index(clean_kw: str) -> tuple[str, dict[str, Any], str] | None:
    parts = clean_kw.split(".")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        g_idx = int(parts[0]) - 1
        i_idx = int(parts[1]) - 1
        nodes = _fetch_nodes()
        goals = [n for n in nodes if n.get("work_type") == "GOAL" and n.get("status") != "CANCELLED"]
        project_groups = _build_project_groups(goals)
        if 0 <= g_idx < len(project_groups):
            cat_name, cat_goals = project_groups[g_idx]
            if 0 <= i_idx < len(cat_goals):
                return cat_name, cat_goals[i_idx], f"{parts[0]}.{parts[1]}"
    return None


def render_context(keyword: str = "") -> str:
    clean_kw = keyword.strip().replace("_", ".")
    found = _find_goal_by_index(clean_kw)
    if not found:
        return "请指定具体的项目编号，如 /yonc_context_1_1。返回总览：/yonc"
    cat_name, target, num_str = found
    parts = num_str.split(".")
    d = target.get("deadline") or target.get("planned_end") or "无排期"
    desc = target.get("description") or "暂无详细描述"
    return f"""📋 项目上下文与完成标准：{num_str}〈{target.get('title')}〉
• 所属领域: {cat_name}
• 当前阶段: {target.get('stage')} | 状态: {target.get('status')}
• 排期截止: {d}
• 目标概要: {desc}
• 完成标准 (done_when): 核对研究/工程交付物，确认核心功能与验收依据通过。

👉 快捷点击操作（1-Tap免输入）：
• 拆解规划：/yonc_split_{parts[0]}_{parts[1]}
• 规划 Action：/yonc_action_{parts[0]}_{parts[1]}
• 完整项目卡：/yonc_projects_{parts[0]}_{parts[1]}

全部项目库：/yonc_projects | 返回总览：/yonc"""


def render_action(keyword: str = "") -> str:
    clean_kw = keyword.strip().replace("_", ".")
    found = _find_goal_by_index(clean_kw)
    if not found:
        return "请指定具体的项目编号，如 /yonc_action_1_1。返回总览：/yonc"
    _cat_name, target, num_str = found
    parts = num_str.split(".")
    return f"""⚡ 项目主要 Action 规划：{num_str}〈{target.get('title')}〉
• 交付目标: 两周内明确里程碑与主要产物
• 建议行动清单 (Action Items):
  1. 梳理核心范围、前置依赖与验收标准（done_when）
  2. 建立首期最小可验证闭环（MVP / 验证用例）
  3. 指派合适专家（/yonc_assign）跟进具体任务

👉 快捷点击操作（1-Tap免输入）：
• 立即拆解：/yonc_split_{parts[0]}_{parts[1]}
• 查看上下文：/yonc_context_{parts[0]}_{parts[1]}
• 项目卡片：/yonc_projects_{parts[0]}_{parts[1]}

返回项目库：/yonc_projects | 返回总览：/yonc"""

def render_projects(keyword: str = "") -> str:
    """Render real project list grouped by domain with 1.1, 1.2 numbers, or filtered by query."""
    nodes = _fetch_nodes()
    goals = [n for n in nodes if n.get("work_type") == "GOAL" and n.get("status") != "CANCELLED"]
    project_groups = _build_project_groups(goals)

    clean_kw = keyword.strip().replace("_", ".")

    # 1. Check if user typed a group number, e.g. "1" or "3"
    if clean_kw.isdigit():
        g_idx = int(clean_kw) - 1
        if 0 <= g_idx < len(project_groups):
            cat_name, cat_goals = project_groups[g_idx]
            lines = [f"📊 分类详情：{clean_kw}. {cat_name}（共 {len(cat_goals)} 项）：\n"]
            for j, g in enumerate(cat_goals, 1):
                d = g.get("deadline") or g.get("planned_end") or "无排期"
                lines.append(f"{clean_kw}.{j} {g.get('title')} [/yonc_projects_{clean_kw}_{j}]")
                lines.append(f"     [阶段: {g.get('stage')} | 状态: {g.get('status')} | 排期: {d}]")
            first_title = cat_goals[0]["title"]
            lines.append("\n👉 轻点下方例句即可直接复制，粘贴发送：")
            lines.append(f"`查询项目 {clean_kw}.1〈{first_title}〉的上下文、子任务和完成标准。`")
            lines.append(f"`准备拆解 {clean_kw}.1〈{first_title}〉，目标是两周内上线，先列出主要 Action。`")
            lines.append("\n全部项目库：/yonc_projects | 紧迫拆解排序：/yonc_split | 返回总览：/yonc")
            return "\n".join(lines)

    # 2. Check if user typed an item number, e.g. "1.1" or "3.2"
    if clean_kw and "." in clean_kw:
        parts = clean_kw.split(".")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            g_idx = int(parts[0]) - 1
            i_idx = int(parts[1]) - 1
            if 0 <= g_idx < len(project_groups):
                cat_name, cat_goals = project_groups[g_idx]
                if 0 <= i_idx < len(cat_goals):
                    target = cat_goals[i_idx]
                    d = target.get("deadline") or target.get("planned_end") or "无排期"
                    return f"""📊 项目详情：{parts[0]}.{parts[1]}〈{target.get('title')}〉
• 阶段: {target.get('stage')} | 状态: {target.get('status')}
• 排期/截止: {d}
• 领域: {cat_name}
• 描述: {target.get('description') or '暂无详细描述'}

👉 快捷点击操作（1-Tap免复制）：
• 立即拆解：/yonc_split_{parts[0]}_{parts[1]}
• 上下文与标准：/yonc_context_{parts[0]}_{parts[1]}
• 规划主要Action：/yonc_action_{parts[0]}_{parts[1]}

👉 轻点下方例句即可直接复制，粘贴发送：
`查询项目 {parts[0]}.{parts[1]}〈{target.get('title')}〉的上下文、子任务和完成标准。`
`准备拆解 {parts[0]}.{parts[1]}〈{target.get('title')}〉，目标是两周内上线，先列出主要 Action。`

全部项目库：/yonc_projects | 紧迫拆解排序：/yonc_split | 返回总览：/yonc"""

    # 3. Text keyword search
    if clean_kw and clean_kw.casefold() not in ("projects", "project", "yonc_projects", "yonc-projects", "项目"):
        matches = [
            g for g in goals
            if clean_kw.casefold() in g.get("title", "").casefold()
            or clean_kw.casefold() in str(g.get("tags", {})).casefold()
        ]
        lines = [f"📊 匹配「{clean_kw}」的真实项目（共 {len(matches)} 个）：\n"]
        if not matches:
            lines.append("未在图谱中找到该关键词的项目。可用 /yonc_projects 查看完整项目库。\n")
        else:
            for idx, g in enumerate(matches[:8], 1):
                d = g.get("deadline") or g.get("planned_end") or "无排期"
                lines.append(f"1.{idx} {g.get('title')}")
                lines.append(f"     [阶段: {g.get('stage')} | 状态: {g.get('status')} | 排期: {d}]")
            first_title = matches[0]["title"]
            lines.append("\n👉 轻点下方例句即可直接复制，粘贴发送：")
            lines.append(f"`查询项目 1.1〈{first_title}〉的上下文、子任务和完成标准。`")
            lines.append(f"`准备拆解 1.1〈{first_title}〉，目标是两周内上线，先列出主要 Action。`")
        lines.append("\n全部项目库：/yonc_projects | 紧迫拆解排序：/yonc_split | 返回总览：/yonc")
        return "\n".join(lines)

    # 4. Global project catalogue overview
    lines = [
        "📊 Yonc 真实项目库总览\n",
        f"当前图谱共有 {len(goals)} 个活跃大目标（{len(nodes)} 个节点），分类清单如下：\n",
    ]

    for i, (cat_name, cat_goals) in enumerate(project_groups, 1):
        lines.append(f"{i}. {cat_name}（{len(cat_goals)} 项）：")
        for j, g in enumerate(cat_goals[:5], 1):
            d = g.get("deadline") or g.get("planned_end")
            date_tag = f" [🚨 {d}]" if d else ""
            lines.append(f"  {i}.{j} {g.get('title')}{date_tag} [/yonc_projects_{i}_{j}]")
        if len(cat_goals) > 5:
            lines.append(f"    ... 还有 {len(cat_goals)-5} 项（点击 /yonc_projects_{i} 展开全组）")
        lines.append("")

    lines.append("💡 常用操作与口语查询（支持直接使用 1.1 编号）：")
    lines.append("• 展开指定分类组：点击 /yonc_projects_1 至 /yonc_projects_7")
    lines.append("• 查看具体项目详情：点击对应 /yonc_projects_1_1 或输入 `/yonc_projects <名称>`")
    lines.append("• 立即拆解：点击 /yonc_split_1_1")
    lines.append("• 轻点例句即可复制，粘贴发送：")
    lines.append("  `查询项目 1.1〈Thesis Phd Logic〉的上下文和子任务`")
    lines.append("  `准备拆解 3.1〈素食堂 菜单开发〉，目标是两周内上线，先列出主要 Action。`")
    lines.append("\n返回总览：/yonc")
    return "\n".join(lines)


def render_guide() -> str:
    """Render high-level overview with live count and urgent highlights."""
    nodes = _fetch_nodes()
    goals = [n for n in nodes if n.get("work_type") == "GOAL" and n.get("status") != "CANCELLED"]
    with_dates = [g for g in goals if g.get("deadline") or g.get("planned_end")]
    with_dates.sort(key=lambda x: x.get("deadline") or x.get("planned_end") or "9999")
    today_str = datetime.now(UTC).date().isoformat()
    urgent = [g for g in with_dates if (g.get("deadline") or g.get("planned_end")) == today_str]
    upcoming = [g for g in with_dates if (g.get("deadline") or g.get("planned_end")) > today_str]

    urgent_note = ""
    if urgent:
        urgent_note = f"🚨 今日截止重点：1.1 {urgent[0]['title']}"
    elif upcoming:
        d = upcoming[0].get("deadline") or upcoming[0].get("planned_end")
        urgent_note = f"⏳ 最近临近截止：1.1 {upcoming[0]['title']} ({d})"

    header = f"Yonc 项目管理指南（当前活跃目标 {len(goals)} 个）"
    if urgent_note:
        header += f"\n{urgent_note}"

    return f"""{header}

告诉我你的目标或项目即可开始；以下指令点击即可直接发起：

• 目标拆解与规划（按截止日排序，支持 1.1 编号）：/yonc_split
• 项目概况与真实分类库（支持 1.1 编号与组号）：/yonc_projects
• 专家分发与指派建议：/yonc_assign
• 变更审计与交付回执：/yonc_history
• 了解图谱授权机制：/yonc_graph

快速例句（轻点下方例句即可直接复制，粘贴发送）：
`准备拆解 1.1〈Thesis Phd Logic〉，目标是两周内上线，先列出主要 Action。`
`查询项目 3.1〈素食堂 菜单开发〉的上下文和子任务。`
`这项任务适合指派给哪个专家 Agent？评估一下工作量。`
`核对一下最近从 honc 同步过来的完成回执。`

对话中会为你生成草案并校验依赖；最终正式写入图谱需在 Web UI 授权。
/model、/new、/stop 沿用 Hermes 原生命令。"""


def render_assign(keyword: str = "") -> str:
    """Render assignment guide and colleague responsibilities."""
    return """👥 专家分发与协同建议

你想把哪项任务分配出去？或者需要我推荐合适的专家 Agent 吗？请直接告诉我：

👉 常用说法（轻点即可复制）：
`任务〈任务ID〉适合指派给哪个专家 Agent？评估一下工作量。`
`把任务〈任务ID〉建议指派给 Brainstormer，重点负责需求与架构设计。`
`帮我查看目前各位同事（Brainstormer/Scholar/Forge/honc）的职责分工。`

💡 同事职责速查：
• Brainstormer：需求澄清、架构方案、PRD 设计
• Scholar：文献调研、学术证据、实验方法设计
• Wisdom-Oldman：机制机理探究、深层知识归纳
• Forge Lab Bot：硬件采购、BOM 评估、实验室工程验证
• honc：日常专注执行、工时账本、打卡与生活追踪

直接告诉我任务和诉求，我会为你评估可行性并生成指派建议草案。
返回总览：/yonc"""


def render_history() -> str:
    """Render recent commit batches and history lookup guide."""
    batches = _fetch_history()
    lines = ["📜 变更审计与交付回执\n"]
    if batches:
        lines.append("🔍 最近提交的图谱变更操作（近 3 次批次）：")
        for b in batches[:3]:
            source = b.get("source", "unknown")
            vb = b.get("graph_version_before", "?")
            va = b.get("graph_version_after", "?")
            t = b.get("created_at", "")[:19].replace("T", " ")
            lines.append(f"• 批次 [{source}] 版本 v{vb} ➔ v{va} ({t})")
        lines.append("")

    lines.append("""你想查看更早的历史变更，还是核对具体任务的交付物与回执？

👉 常用说法（轻点即可复制）：
`核对一下今天从 honc 同步过来的任务完成回执。`
`查看最近 7 天 Project Graph 的变更历史与拆解记录。`
`查看任务〈任务ID〉的交付物与验收依据，核对是否满足完成标准。`

💡 建议说明：
• 若是核对完成情况，指明任务名称或 ID
• 若是同步核对，可说明是哪位同事（如 honc）提交的事实

直接告诉我你想核对的内容，我会为你提取历史记录与回执详情。
返回总览：/yonc""")
    return "\n".join(lines)


def render_graph() -> str:
    """Render graph explanation."""
    return """🔗 Yonc 与 Project Graph 提交流程

关于草案规划与正式提交的协作机制：

• 对话规划草案：你在 Telegram 跟我聊的所有拆解、修改和指派，都会保存在「拆解会话草稿」中，随时可以调整推翻，安全不污染真实图谱。
• 依赖一致性检查：正式提交前，我会先校验前置依赖和完成标准（done_when）。
• 受信授权提交：为确保图谱安全，最终正式写入图谱（Commit）需通过受信任的 Web UI 生成单次授权码。

👉 常用指令（轻点即可复制）：
`检查当前草案的依赖完整性，准备提交。`
`用授权码〈授权码〉提交当前拆解草案。`
`放弃当前的拆解草稿，恢复上一版本。`

直接告诉我你的意图，我们随时开始。
返回总览：/yonc"""


# Static property fallbacks for backward-compatible test fixtures
GUIDE = render_guide()
SPLIT = render_split()
PROJECTS = render_projects()
ASSIGN = render_assign()
HISTORY = render_history()
GRAPH = render_graph()

SECTIONS = {
    "split": render_split,
    "projects": render_projects,
    "assign": render_assign,
    "history": render_history,
    "graph": render_graph,
}

ALIASES = {
    "split": "split",
    "yonc_split": "split",
    "yonc-split": "split",
    "_split": "split",
    "-split": "split",
    "拆解": "split",
    "projects": "projects",
    "project": "projects",
    "yonc_projects": "projects",
    "yonc-projects": "projects",
    "_projects": "projects",
    "-projects": "projects",
    "项目": "projects",
    "assign": "assign",
    "assignment": "assign",
    "assignments": "assign",
    "yonc_assign": "assign",
    "yonc-assign": "assign",
    "_assign": "assign",
    "-assign": "assign",
    "指派": "assign",
    "分发": "assign",
    "history": "history",
    "yonc_history": "history",
    "yonc-history": "history",
    "_history": "history",
    "-history": "history",
    "历史": "history",
    "审计": "history",
    "graph": "graph",
    "yonc_graph": "graph",
    "yonc-graph": "graph",
    "_graph": "graph",
    "-graph": "graph",
    "图谱": "graph",
    "授权": "graph",
    "help": "help",
}


def guide(raw_args: str = "") -> str:
    """Return guide page or search results; long custom sentences are not valid section names."""
    trimmed = (raw_args or "").strip()
    key = trimmed.casefold()
    if not key:
        return render_guide()

    alias_target = ALIASES.get(key)
    if alias_target:
        if alias_target == "split":
            return render_split()
        if alias_target == "projects":
            return render_projects()
        if alias_target == "assign":
            return render_assign()
        if alias_target == "history":
            return render_history()
        if alias_target == "graph":
            return render_graph()
        if alias_target == "help":
            return render_guide()

    if key in SECTIONS:
        return SECTIONS[key]()

    # Reject complex sentences or command injection strings as section names
    if any(ch in trimmed for ch in (";", "〈", "〉", "。", "\n")) or len(trimmed) > 30:
        return "没有这个手册章节。用 /yonc 查看目录；要拆解项目或查询进度，请另发一条日常消息。"

    # Check if keyword or number matches any projects
    matched = render_projects(trimmed)
    if "未在图谱中找到该关键词" not in matched:
        return matched

    return "没有这个手册章节。用 /yonc 查看目录；要拆解项目或查询进度，请另发一条日常消息。"


def guide_section(section: str, raw_args: str = "") -> str:
    """Dispatch subcommand with optional filter argument."""
    if section == "split":
        return render_split(raw_args)
    if section == "projects":
        return render_projects(raw_args)
    if section == "assign":
        return render_assign(raw_args)
    if section == "history":
        return render_history()
    if section == "graph":
        return render_graph()
    return render_guide()


def register(ctx: Any) -> None:
    if ctx.profile_name != "yonc":
        return
    ctx.register_command(
        "yonc",
        lambda raw_args="": guide(raw_args),
        description="项目管理、拆解与指派操作指南",
        args_hint="[split / projects / assign / history / graph / 关键词或编号]",
    )
    for section_name in ("split", "projects", "assign", "history", "graph"):
        desc = f"yonc {section_name} 真实数据与操作引导"
        handler = lambda raw_args="", s=section_name: guide_section(s, raw_args)
        ctx.register_command(f"yonc_{section_name}", handler, description=desc)
        ctx.register_command(f"yonc-{section_name}", handler, description=desc)

    # 1-tap direct group expansion commands (/yonc_projects_1 to /yonc_projects_7)
    for g in range(1, 8):
        ctx.register_command(
            f"yonc_projects_{g}",
            lambda raw_args="", g=g: render_projects(str(g)),
            description=f"展开分类 {g} 的全部项目",
        )
        ctx.register_command(
            f"yonc-projects-{g}",
            lambda raw_args="", g=g: render_projects(str(g)),
            description=f"展开分类 {g} 的全部项目",
        )

    # 1-tap direct split items (/yonc_split_1_1 to /yonc_split_3_10)
    for s in range(1, 4):
        for i in range(1, 11):
            ctx.register_command(
                f"yonc_split_{s}_{i}",
                lambda raw_args="", s=s, i=i: render_split(f"{s}.{i}"),
                description=f"拆解项目 {s}.{i}",
            )
            ctx.register_command(
                f"yonc-split-{s}-{i}",
                lambda raw_args="", s=s, i=i: render_split(f"{s}.{i}"),
                description=f"拆解项目 {s}.{i}",
            )

    # 1-tap direct project items (/yonc_projects_1_1 to /yonc_projects_7_15)
    for g in range(1, 8):
        for i in range(1, 16):
            ctx.register_command(
                f"yonc_projects_{g}_{i}",
                lambda raw_args="", g=g, i=i: render_projects(f"{g}.{i}"),
                description=f"查看项目 {g}.{i} 详情",
            )
            ctx.register_command(
                f"yonc-projects-{g}-{i}",
                lambda raw_args="", g=g, i=i: render_projects(f"{g}.{i}"),
                description=f"查看项目 {g}.{i} 详情",
            )
            ctx.register_command(
                f"yonc_context_{g}_{i}",
                lambda raw_args="", g=g, i=i: render_context(f"{g}.{i}"),
                description=f"查看项目 {g}.{i} 上下文与标准",
            )
            ctx.register_command(
                f"yonc-context-{g}-{i}",
                lambda raw_args="", g=g, i=i: render_context(f"{g}.{i}"),
                description=f"查看项目 {g}.{i} 上下文与标准",
            )
            ctx.register_command(
                f"yonc_action_{g}_{i}",
                lambda raw_args="", g=g, i=i: render_action(f"{g}.{i}"),
                description=f"规划项目 {g}.{i} 主要行动",
            )
            ctx.register_command(
                f"yonc-action-{g}-{i}",
                lambda raw_args="", g=g, i=i: render_action(f"{g}.{i}"),
                description=f"规划项目 {g}.{i} 主要行动",
            )
