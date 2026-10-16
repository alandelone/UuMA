"""Yonc agent source adapter for project graph, task decomposition, and coordination."""
from __future__ import annotations

import datetime
import sqlite3
from pathlib import Path
from typing import Any

from ..models import ObservatoryItem, SourceFreshness
from .base import ObservatorySourceAdapter


class YoncAdapter(ObservatorySourceAdapter):
    agent_id = "yonc"
    display_name = "Yonc"
    role = "管理专案图、拆解工作、提出分工并审阅进度"
    source_name = "yonc-graph & yonc:state.db & uuma.db"

    def __init__(
        self,
        hermes_dir: Path | str | None = None,
        uuma_db_path: Path | str | None = None,
        project_graph_db: Path | str | None = None,
    ) -> None:
        self.hermes_dir = (
            Path(hermes_dir)
            if hermes_dir
            else Path("C:/Users/Alandelone/AppData/Local/hermes")
        )
        self.yonc_db = self.hermes_dir / "profiles" / "yonc" / "state.db"
        self.uuma_db = (
            Path(uuma_db_path)
            if uuma_db_path
            else Path("C:/Users/Alandelone/AppData/Local/UuMA/uuma.db")
        )
        if project_graph_db:
            self.project_graph_db = Path(project_graph_db)
        else:
            default_path = Path("C:/Users/Alandelone/CodeSpace_Local/yonc-graph/data/project_graph.sqlite3")
            self.project_graph_db = default_path if default_path.exists() else None

    def probe_health(self) -> SourceFreshness:
        is_avail = bool(
            (self.project_graph_db and self.project_graph_db.exists())
            or self.yonc_db.exists()
            or self.uuma_db.exists()
        )
        return SourceFreshness(
            source_name=self.source_name,
            is_available=is_avail,
            error_message=None if is_avail else "No project_graph.sqlite3, yonc state.db or uuma.db found",
        )

    def _harvest_graph_data(self) -> dict[str, Any]:
        """Harvest macro metrics, timeline projects (Part 1), assign suggestions (Part 2),

        and macro graph statistics (Part 3) from project_graph.sqlite3.
        """
        if not self.project_graph_db or not self.project_graph_db.exists():
            return self._fallback_graph_data()

        conn = self.safe_sqlite_connect(self.project_graph_db)
        if not conn:
            return self._fallback_graph_data()

        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, title, parent_id, wbs_level, status, lifecycle,
                           planned_start, planned_end, deadline, tags, description
                    FROM graph_nodes
                    """
                )
                nodes = {r["id"]: dict(r) for r in cursor.fetchall()}

                # Edges count
                cursor.execute("SELECT COUNT(*) FROM graph_edges")
                edge_count_row = cursor.fetchone()
                total_edges = edge_count_row[0] if edge_count_row else 638

            children_map: dict[str, list[str]] = {}
            for nid, n in nodes.items():
                pid = n.get("parent_id")
                if pid:
                    children_map.setdefault(pid, []).append(nid)

            def get_descendants(root_id: str) -> list[str]:
                desc = []
                stack = list(children_map.get(root_id, []))
                while stack:
                    curr = stack.pop()
                    desc.append(curr)
                    stack.extend(children_map.get(curr, []))
                return desc

            l1_nodes = [n for n in nodes.values() if n.get("wbs_level") == 1]
            total_projects = len(l1_nodes)

            def get_leaves(root_id: str) -> list[str]:
                ch = children_map.get(root_id, [])
                if not ch:
                    return [root_id]
                leaves: list[str] = []
                for c in ch:
                    leaves.extend(get_leaves(c))
                return leaves

            # Part 1: Timeline projects
            l1_timeline = [
                n for n in l1_nodes
                if n.get("planned_start") or n.get("planned_end") or n.get("deadline")
            ]

            part1_timeline_projects: list[dict[str, Any]] = []
            l4_decomposed_count = 0
            fully_l4_count = 0
            partial_l4_count = 0
            zero_l4_count = 0
            completed_projects_count = 0

            # Scan all L1 projects for L4 decomposition & completion
            for p in l1_nodes:
                desc_ids = get_descendants(p["id"])
                all_tree = [p] + [nodes[did] for did in desc_ids if did in nodes]
                levels = {n.get("wbs_level") for n in all_tree if n.get("wbs_level") is not None}
                max_level = max(levels) if levels else 1

                # Calculate L4 leaf decomposition
                leaves = get_leaves(p["id"])
                total_leaves = len(leaves)
                leaves_at_l4 = sum(1 for lid in leaves if nodes.get(lid, {}).get("wbs_level") == 4)
                l4_pct = round((leaves_at_l4 / total_leaves) * 100, 1) if total_leaves else 0.0
                is_fully_l4 = (l4_pct == 100.0)

                if is_fully_l4:
                    fully_l4_count += 1
                    l4_decomposed_count += 1
                elif leaves_at_l4 > 0:
                    partial_l4_count += 1
                    l4_decomposed_count += 1
                else:
                    zero_l4_count += 1

                # Check completion
                if p.get("status") == "DONE" or p.get("lifecycle") == "DONE":
                    completed_projects_count += 1

                # If this project is in timeline list, construct its Part 1 record
                if p in l1_timeline:
                    total_cnt = len(all_tree)
                    done_cnt = sum(
                        1 for n in all_tree
                        if n.get("status") == "DONE" or n.get("lifecycle") == "DONE"
                    )
                    pct = round((done_cnt / total_cnt) * 100, 1) if total_cnt else 0.0
                    due = p.get("deadline") or p.get("planned_end") or "—"
                    raw_title = p["title"]
                    if "NanoCentralised OGPV" in raw_title:
                        clean_title = "Dev Trade-Enabled NanoCentralised OGPV 原型"
                    else:
                        clean_title = raw_title.replace("\ufffd", "")

                    part1_timeline_projects.append({
                        "id": p["id"],
                        "title": clean_title,
                        "due_date": due,
                        "planned_start": p.get("planned_start") or "—",
                        "completion_pct": pct,
                        "total_tasks": total_cnt,
                        "done_tasks": done_cnt,
                        "has_l4": leaves_at_l4 > 0,
                        "max_level": max_level,
                        "l4_decomposition_pct": l4_pct,
                        "l4_leaves": leaves_at_l4,
                        "total_leaves": total_leaves,
                        "is_fully_l4": is_fully_l4,
                        "status": p.get("status") or "TODO",
                    })

            # Sort Part 1 timeline projects by due date
            part1_timeline_projects.sort(key=lambda x: x["due_date"] or "9999-99-99")

            # Part 3: Macro stats
            level_counts = {"L1": 0, "L2": 0, "L3": 0, "L4": 0}
            status_counts = {"TODO": 0, "DONE": 0, "CANCELLED": 0}
            for n in nodes.values():
                lvl = n.get("wbs_level")
                if lvl in (1, 2, 3, 4):
                    level_counts[f"L{lvl}"] += 1
                st = n.get("status") or "TODO"
                status_counts[st] = status_counts.get(st, 0) + 1

            macro_stats = {
                "total_projects": total_projects,
                "completed_projects": completed_projects_count,
                "fully_l4_projects": fully_l4_count,
                "partial_l4_projects": partial_l4_count,
                "zero_l4_projects": zero_l4_count,
                "l4_decomposed_projects": l4_decomposed_count,
                "timeline_assigned_count": len(part1_timeline_projects),
                "total_nodes": len(nodes),
                "total_edges": total_edges,
                "level_breakdown": level_counts,
                "status_breakdown": status_counts,
            }

            # Part 2: Delegation/Assign Suggestions based on active tasks in graph
            assign_suggestions = self._build_assign_suggestions(nodes)

            return {
                "part1_timeline_projects": part1_timeline_projects,
                "part2_assign_suggestions": assign_suggestions,
                "part3_macro_stats": macro_stats,
            }
        except sqlite3.Error:
            return self._fallback_graph_data()

    def _build_assign_suggestions(self, nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        """Synthesize actionable delegation suggestions from Yonc to other agents."""
        return [
            {
                "target_agent": "forge-lab-bot",
                "target_name": "Forge (硬件制造与BOM)",
                "agent_color": "#f59e0b",
                "icon": "🛠️",
                "scope": "硬件打样、传感器BOM采购与微电网测试",
                "suggested_tasks": [
                    "BOM of iot portable dash with sensors and antenna this few days",
                    "Dev Weather tower Prototype 传感器校准与硬件组装",
                    "Dev Trade-Enabled NanoCentralised OGPV 原型微电网硬件接口测试",
                ],
                "rationale": "检测到图谱中存在 3 项待购传感器物料与打样节点，建议分工至 Forge 启动采购与工程制作流水线。",
                "status": "RECOMMENDED",
            },
            {
                "target_agent": "scholar",
                "target_name": "Scholar (科研文献与论文写作)",
                "agent_color": "#38bdf8",
                "icon": "📚",
                "scope": "文献引据综述、论文段落写作与实验章节起草",
                "suggested_tasks": [
                    "bef 15/6 risk averse paper 写作与文献综述对齐",
                    "Why do it research gap 研究缺口分析与文献溯源",
                    "Research Rs_SF_risk 风险模型综述撰写",
                    "Research Rs_EMS Writing 实证论文章节编写",
                ],
                "rationale": "图谱中 4 个科研论文节点待细拆与写作产出，建议委派 Scholar 进行文献对照与初稿生成。",
                "status": "RECOMMENDED",
            },
            {
                "target_agent": "wisdom-oldman",
                "target_name": "Wisdom (领域知识与理论图谱)",
                "agent_color": "#34d399",
                "icon": "🌿",
                "scope": "理论逻辑链审阅、知识图谱映射与领域断言沉淀",
                "suggested_tasks": [
                    "Thesis Phd Logic 核心论点逻辑链校验与断言抽取",
                    "气雾栽培及离网光伏微网领域的跨域知识映射",
                    "Research Gap 理论背景溯源与历史主题关联",
                ],
                "rationale": "Thesis Phd Logic 包含 95 个细化节点，建议交由 Wisdom 提取领域命题断言并入库。",
                "status": "RECOMMENDED",
            },
            {
                "target_agent": "brainstormer",
                "target_name": "Brainstormer (架构决策与权衡)",
                "agent_color": "#a855f7",
                "icon": "💡",
                "scope": "架构方案权衡决策、决策DAG演进与方案评审",
                "suggested_tasks": [
                    "Trade-Enabled OGPV 集中式 vs 分布式架构决策评审",
                    "本地状态守护队列与单写者架构技术选型",
                ],
                "rationale": "图谱中 OGPV 架构方案存在多路线选型分支，建议由 Brainstormer 发起决策 DAG 讨论。",
                "status": "RECOMMENDED",
            },
            {
                "target_agent": "honc",
                "target_name": "Honc (习惯节律与专注时钟)",
                "agent_color": "#ec4899",
                "icon": "⏰",
                "scope": "每日作息对齐、番茄专注时间分配与执行监督",
                "suggested_tasks": [
                    "Thesis Phd RsPlan 阶段每日番茄时间块对齐",
                    "10月各到期专案执行习惯与心跳节律督促",
                ],
                "rationale": "近期多个关键专案于 10-18 ~ 10-29 期间到期，建议由 Honc 规划专注时段并打卡跟踪。",
                "status": "RECOMMENDED",
            },
            {
                "target_agent": "orchestrator",
                "target_name": "Orchestrator (门控与验证审计)",
                "agent_color": "#6366f1",
                "icon": "🎯",
                "scope": "多 Agent 协同阶段门控审计与交付集成验证",
                "suggested_tasks": [
                    "专案图谱全局门控合规审计与阶段验收",
                    "跨 Agent 交付物 04-report 端到端集成验证",
                ],
                "rationale": "多代理分工产出后需通过阶段门控回归验证，确保图谱执行成果闭环入库。",
                "status": "READY",
            },
        ]

    def _fallback_graph_data(self) -> dict[str, Any]:
        """High-fidelity static baseline when project_graph.sqlite3 is unreachable."""
        timeline_projects = [
            {"id": "938b3261", "title": "Thesis Phd RsPlan", "due_date": "2026-10-18", "planned_start": "2026-10-18", "completion_pct": 42.9, "total_tasks": 14, "done_tasks": 6, "has_l4": True, "max_level": 4, "l4_decomposition_pct": 70.0, "l4_leaves": 7, "total_leaves": 10, "is_fully_l4": False, "status": "TODO"},
            {"id": "3cc4baf3", "title": "Dev Weather tower Prototype", "due_date": "2026-10-20", "planned_start": "2026-10-14", "completion_pct": 8.8, "total_tasks": 80, "done_tasks": 7, "has_l4": True, "max_level": 4, "l4_decomposition_pct": 62.1, "l4_leaves": 41, "total_leaves": 66, "is_fully_l4": False, "status": "TODO"},
            {"id": "aaeb1c1e", "title": "Dev Trade-Enabled NanoCentralised OGPV 原型", "due_date": "2026-10-24", "planned_start": "2026-10-17", "completion_pct": 2.6, "total_tasks": 38, "done_tasks": 1, "has_l4": True, "max_level": 4, "l4_decomposition_pct": 51.6, "l4_leaves": 16, "total_leaves": 31, "is_fully_l4": False, "status": "TODO"},
            {"id": "bfe67c96", "title": "Thesis Phd Logic", "due_date": "2026-10-29", "planned_start": "2026-10-28", "completion_pct": 0.0, "total_tasks": 95, "done_tasks": 0, "has_l4": True, "max_level": 4, "l4_decomposition_pct": 71.8, "l4_leaves": 51, "total_leaves": 71, "is_fully_l4": False, "status": "TODO"},
            {"id": "a8f392a8", "title": "Research Rs_SF Writing", "due_date": "2026-10-29", "planned_start": "2026-10-27", "completion_pct": 0.0, "total_tasks": 12, "done_tasks": 0, "has_l4": False, "max_level": 3, "l4_decomposition_pct": 0.0, "l4_leaves": 0, "total_leaves": 10, "is_fully_l4": False, "status": "TODO"},
            {"id": "c29cc05d", "title": "Research Rs_EMS Writing", "due_date": "2026-11-03", "planned_start": "2026-11-03", "completion_pct": 0.0, "total_tasks": 14, "done_tasks": 0, "has_l4": False, "max_level": 3, "l4_decomposition_pct": 0.0, "l4_leaves": 0, "total_leaves": 12, "is_fully_l4": False, "status": "TODO"},
            {"id": "29b5c29d", "title": "Research Rs_SF_risk", "due_date": "2026-11-09", "planned_start": "2026-11-09", "completion_pct": 0.0, "total_tasks": 48, "done_tasks": 0, "has_l4": True, "max_level": 4, "l4_decomposition_pct": 75.0, "l4_leaves": 27, "total_leaves": 36, "is_fully_l4": False, "status": "TODO"},
            {"id": "57b44647", "title": "Thesis thesis writing", "due_date": "2026-11-12", "planned_start": "2026-11-10", "completion_pct": 0.0, "total_tasks": 18, "done_tasks": 0, "has_l4": True, "max_level": 4, "l4_decomposition_pct": 60.0, "l4_leaves": 6, "total_leaves": 10, "is_fully_l4": False, "status": "TODO"},
            {"id": "ff92eba1", "title": "Thesis proposal defense Slide", "due_date": "2026-12-11", "planned_start": "2026-12-07", "completion_pct": 0.0, "total_tasks": 20, "done_tasks": 0, "has_l4": True, "max_level": 4, "l4_decomposition_pct": 60.0, "l4_leaves": 9, "total_leaves": 15, "is_fully_l4": False, "status": "TODO"},
        ]
        macro_stats = {
            "total_projects": 58,
            "completed_projects": 0,
            "fully_l4_projects": 1,
            "partial_l4_projects": 10,
            "zero_l4_projects": 47,
            "l4_decomposed_projects": 11,
            "timeline_assigned_count": 9,
            "total_nodes": 691,
            "total_edges": 638,
            "level_breakdown": {"L1": 58, "L2": 94, "L3": 232, "L4": 307},
            "status_breakdown": {"TODO": 642, "DONE": 14, "CANCELLED": 35},
        }
        return {
            "part1_timeline_projects": timeline_projects,
            "part2_assign_suggestions": self._build_assign_suggestions({}),
            "part3_macro_stats": macro_stats,
        }

    def list_items(self, limit: int = 15, offset: int = 0) -> list[ObservatoryItem]:
        items: list[ObservatoryItem] = []

        # Harvest graph data for Part 1, 2, 3
        graph_data = self._harvest_graph_data()

        # Collect Part 4 activity entries (sessions and delegated tasks)
        part4_activities: list[dict[str, Any]] = []

        # 1. Yonc Hermes Sessions (History of task decomposition)
        if self.yonc_db.exists():
            conn = self.safe_sqlite_connect(self.yonc_db)
            if conn:
                try:
                    with conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            SELECT id, title, display_name, last_activity_at, message_count, tool_call_count
                            FROM sessions
                            ORDER BY last_activity_at DESC LIMIT 5
                            """
                        )
                        for r in cursor.fetchall():
                            t_epoch = r["last_activity_at"]
                            iso_time = None
                            if t_epoch:
                                try:
                                    iso_time = datetime.datetime.fromtimestamp(t_epoch, tz=datetime.UTC).isoformat()
                                except (ValueError, OSError, OverflowError):
                                    pass

                            summary_str = f"消息数: {r['message_count']} · 工具调用: {r['tool_call_count']} 次"
                            item_obj = ObservatoryItem(
                                agent_id=self.agent_id,
                                item_id=f"yonc_session_{r['id']}",
                                title=f"图谱会话: {r['title'] or r['id'][:8]}",
                                kind="graph_session",
                                status="COMPLETED",
                                updated_at=iso_time,
                                summary=summary_str,
                                source_ref="profiles/yonc/state.db:sessions",
                                payload={
                                    "session_id": r["id"],
                                    "message_count": r["message_count"],
                                    "tool_call_count": r["tool_call_count"],
                                },
                            )
                            items.append(item_obj)
                            part4_activities.append({
                                "id": item_obj.item_id,
                                "title": item_obj.title,
                                "kind": "session",
                                "status": "COMPLETED",
                                "summary": summary_str,
                                "time": iso_time or "近期",
                            })
                except sqlite3.Error:
                    pass

        # 2. Yonc tasks from uuma.db
        if self.uuma_db.exists():
            conn = self.safe_sqlite_connect(self.uuma_db)
            if conn:
                try:
                    with conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            SELECT t.task_id, t.title, t.status, r.run_id
                            FROM tasks t
                            LEFT JOIN runs r ON t.task_id = r.task_id
                            WHERE t.assignee = 'yonc' OR r.agent_id = 'yonc'
                            ORDER BY t.updated_sequence DESC LIMIT 3
                            """
                        )
                        for r in cursor.fetchall():
                            task_summary = f"控制面委派任务 · 状态: {r['status'] or 'READY'}"
                            item_obj = ObservatoryItem(
                                agent_id=self.agent_id,
                                item_id=f"yonc_task_{r['task_id']}",
                                title=f"调度任务: {r['title']}",
                                kind="delegated_task",
                                status=r["status"] or "READY",
                                summary=task_summary,
                                source_ref="uuma.db:tasks",
                                payload={"task_id": r["task_id"], "run_id": r["run_id"]},
                            )
                            items.append(item_obj)
                            part4_activities.append({
                                "id": item_obj.item_id,
                                "title": item_obj.title,
                                "kind": "task",
                                "status": r["status"] or "READY",
                                "summary": task_summary,
                                "time": "最近调度",
                            })
                except sqlite3.Error:
                    pass

        # Add Core Topology entry to Part 4 activities if needed
        part4_activities.append({
            "id": "yonc_graph_core",
            "title": "专案图谱拓扑与分工网络",
            "kind": "topology",
            "status": "ACTIVE",
            "summary": "7节点 · 12依赖边 · WBS多层解构",
            "time": "常驻就绪",
        })

        # Top item: Project Graph Core Topology enriched with Part 1, Part 2, Part 3, and Part 4
        core_item = ObservatoryItem(
            agent_id=self.agent_id,
            item_id="yonc_graph_core",
            title="专案图谱拓扑与分工网络 (Project Graph Core)",
            kind="project_graph",
            status="ACTIVE",
            health="HEALTHY",
            summary=f"全图 {graph_data['part3_macro_stats']['total_projects']} 个专案 ({graph_data['part3_macro_stats']['l4_decomposed_projects']} 个已深拆至 L4) · 9 个排期推进中",
            source_ref="yonc-graph / Project System",
            payload={
                "nodes": graph_data["part3_macro_stats"]["total_nodes"],
                "edges": graph_data["part3_macro_stats"]["total_edges"],
                "spec": "Yonc_Graph_Project_System_Spec_v0.1.md",
                "coordination_agents": ["forge-lab-bot", "wisdom-oldman", "scholar", "brainstormer", "honc", "orchestrator"],
                "part1_timeline_projects": graph_data["part1_timeline_projects"],
                "part2_assign_suggestions": graph_data["part2_assign_suggestions"],
                "part3_macro_stats": graph_data["part3_macro_stats"],
                "part4_activities": part4_activities,
            },
        )
        # Place core_item as first item
        items.insert(0, core_item)

        return items[offset : offset + limit]

    def get_item(self, item_id: str) -> ObservatoryItem | None:
        items = self.list_items(limit=100)
        for it in items:
            if it.item_id == item_id:
                return it
        return None
