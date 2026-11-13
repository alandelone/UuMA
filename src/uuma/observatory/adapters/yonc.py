"""Yonc agent source adapter for project graph, task decomposition, and coordination."""
from __future__ import annotations

import datetime
import sqlite3
from pathlib import Path
from typing import Any

from ..models import ObservatoryItem, SourceFreshness
from .base import ObservatorySourceAdapter
from .yonc_graph import RemoteYoncReader, summarize_graph


class YoncAdapter(ObservatorySourceAdapter):
    agent_id = "yonc"
    display_name = "Yonc"
    role = "管理专案图、拆解工作、提出分工并审阅进度"
    source_name = "alandelone-server-001:YONC Project Graph API (read-only)"

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
        # Explicit local files are supported for isolated tests/offline inspection only.
        self.project_graph_db = Path(project_graph_db) if project_graph_db else None
        self.remote_reader = None if project_graph_db else RemoteYoncReader()

    def probe_health(self) -> SourceFreshness:
        data = self._harvest_graph_data()
        return SourceFreshness(
            source_name=self.source_name,
            is_available=data['source_available'],
            last_event_at=data.get('read_at'),
            error_message=data.get('source_error'),
        )

    def _harvest_graph_data(self) -> dict[str, Any]:
        if self.remote_reader is not None:
            graph = self.remote_reader.read()
            if graph is not None:
                return summarize_graph(graph)
            error = self.remote_reader.error
        else:
            conn = self.safe_sqlite_connect(self.project_graph_db)
            if conn is not None:
                try:
                    graph = {
                        'nodes': [dict(r) for r in conn.execute('SELECT * FROM graph_nodes')],
                        'edges': [dict(r) for r in conn.execute('SELECT * FROM graph_edges')],
                    }
                    return summarize_graph(graph)
                except (sqlite3.Error, ValueError, TypeError):
                    pass
                finally:
                    conn.close()
            error = '指定的 Project Graph 数据源不可用。'
        data = summarize_graph({'nodes': [], 'edges': []})
        data.update(source_available=False, source_error=error)
        return data

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

        # Top item: Project Graph Core Topology enriched with Part 1, Part 2, Part 3, and Part 4
        stats = graph_data["part3_macro_stats"]
        available = graph_data["source_available"]
        if available:
            summary = (
                f"全图 {stats['total_projects']} 个专案 · {stats['fully_l4_projects']} 个完全拆至 L4"
                f" · {stats['timeline_assigned_count']} 个已排期"
            )
        else:
            summary = graph_data["source_error"] or "Project Graph 数据暂不可用。"
        core_item = ObservatoryItem(
            agent_id=self.agent_id,
            item_id="yonc_graph_core",
            title="专案图谱拓扑与分工网络 (Project Graph Core)",
            kind="project_graph",
            status="ACTIVE" if available else "WARNING",
            health="HEALTHY" if available else "WARNING",
            summary=summary,
            source_ref=self.source_name,
            payload={
                **graph_data,
                "nodes": stats["total_nodes"],
                "edges": stats["total_edges"],
                "spec": "Yonc_Graph_Project_System_Spec_v0.1.md",
                "coordination_agents": ["forge-lab-bot", "wisdom-oldman", "scholar", "brainstormer", "honc", "orchestrator"],
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
