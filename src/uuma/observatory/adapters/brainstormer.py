"""Brainstormer agent source adapter for design, decisions, and discussions."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..models import ObservatoryItem, SourceFreshness
from .base import ObservatorySourceAdapter


class BrainstormerAdapter(ObservatorySourceAdapter):
    agent_id = "brainstormer"
    display_name = "Brainstormer"
    role = "厘清问题、挑战假设、比较方案并形成可建造的架构设计与讨论检查点"
    source_name = "brainstormer:projects & decision DAG"

    def __init__(self, data_dir: Path | str, hermes_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.projects_dir = self._resolve_projects_dir()
        self.hermes_dir = (
            Path(hermes_dir)
            if hermes_dir
            else Path("C:/Users/Alandelone/AppData/Local/hermes")
        )

    def _resolve_projects_dir(self) -> Path:
        candidates = [
            self.data_dir / "brainstormer" / "projects",
            Path.home() / "AppData" / "Local" / "UuMA" / "brainstormer" / "projects",
            self.data_dir / ".." / ".uuma-local" / "brainstormer" / "projects",
        ]
        for c in candidates:
            if c.exists():
                return c.resolve()
        return (self.data_dir / "brainstormer" / "projects").resolve()

    def probe_health(self) -> SourceFreshness:
        has_state = self.projects_dir.exists() and any(self.projects_dir.iterdir())
        hermes_state = self.hermes_dir / "state.db"
        is_avail = has_state or hermes_state.exists()
        return SourceFreshness(
            source_name=self.source_name,
            is_available=is_avail,
            last_event_at=None,
            error_message=None if is_avail else "No brainstormer state directory or Hermes DB found",
        )

    def list_items(self, limit: int = 15, offset: int = 0) -> list[ObservatoryItem]:
        TOPIC_METADATA = {
            "topic_state_daemon": {
                "title": "本地状态守护与持久化单写者队列 (State Daemon & Storage Queue)",
                "description": "解决本地高并发读写、防数据踩踏与单写者排队同步机制，保障 SQLite 与 JSON 状态原子刷新与无锁并发读取",
                "icon": "⚡",
            },
            "topic_dag_rendering": {
                "title": "架构决策图谱可视化与抽屉交互 (DAG Flow & Inspector UX)",
                "description": "基于 @xyflow/react 与 dagre 拓扑布局的决策 DAG 交互渲染，支持多层级折叠展开与 Notion 风格侧边栏检查",
                "icon": "🎨",
            },
            "topic_voice_telegram": {
                "title": "双入口语音与即时通信接入 (Dual-Entry Voice & Telegram)",
                "description": "探索多模态语音输入流与 Telegram 即时审计通道的无缝接入与意图路由",
                "icon": "🎙️",
            },
        }

        items: list[ObservatoryItem] = []

        # 1. Search for projects in self.projects_dir (both */state.json and *.json)
        state_files: list[Path] = []
        if self.projects_dir.exists():
            state_files.extend(self.projects_dir.glob("*/state.json"))
            state_files.extend(self.projects_dir.glob("*.json"))

        for s_file in sorted(state_files, key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(s_file.read_text(encoding="utf-8"))
                proj_id = data.get("project_id") or s_file.parent.name
                objects = data.get("objects", {})
                links = data.get("links", [])
                revision = data.get("revision", 1)
                updated_at = data.get("updated_at", "")

                # Categorize DAG objects into discussed decisions, open questions, assumptions, evidences, checkpoints
                discussed_decisions = []
                open_questions = []
                assumptions = []
                evidences = []
                checkpoints = []

                # Group by Architecture Topic
                topics_map: dict[str, dict[str, Any]] = {}

                for obj_id, obj in objects.items():
                    o_type = obj.get("kind") or obj.get("type") or (
                        "decision"
                        if obj_id.startswith("dec")
                        else (
                            "question"
                            if obj_id.startswith("que")
                            else (
                                "assumption"
                                if obj_id.startswith("asm")
                                else ("evidence" if obj_id.startswith("evi") else "checkpoint")
                            )
                        )
                    )
                    status = obj.get("status", "open")
                    title = obj.get("title") or obj_id
                    topic_id = obj.get("topic_id") or "topic_general_architecture"

                    # Resolve Topic Info
                    if topic_id not in topics_map:
                        meta = TOPIC_METADATA.get(topic_id, {})
                        # If there is a topic object in objects
                        topic_obj = objects.get(topic_id, {})
                        top_title = meta.get("title") or topic_obj.get("title") or topic_id.replace("_", " ").title()
                        top_desc = meta.get("description") or topic_obj.get("problem") or topic_obj.get("description") or f"架构主题议题: {topic_id}"
                        top_icon = meta.get("icon") or "◈"
                        topics_map[topic_id] = {
                            "topic_id": topic_id,
                            "title": top_title,
                            "description": top_desc,
                            "icon": top_icon,
                            "latest_updated_at": "",
                            "decisions": [],
                            "questions": [],
                            "assumptions": [],
                            "checkpoints": [],
                            "evidences": [],
                        }

                    # Track latest updated timestamp for this topic
                    obj_time = obj.get("updated_at") or obj.get("created_at") or ""
                    topics_map[topic_id]["latest_updated_at"] = max(topics_map[topic_id]["latest_updated_at"], obj_time)

                    # Determine incoming and outgoing links for this node
                    in_links = [l for l in links if l.get("target_id") == obj_id]
                    out_links = [l for l in links if l.get("source_id") == obj_id]

                    node_summary = {
                        "id": obj_id,
                        "type": o_type,
                        "title": title,
                        "status": status,
                        "topic_id": topic_id,
                        "body": obj.get("body", "") or obj.get("content", ""),
                        "rationale": obj.get("rationale", ""),
                        "in_links": in_links,
                        "out_links": out_links,
                    }

                    if o_type == "decision" or (status == "accepted" and not obj_id.startswith("que")):
                        discussed_decisions.append(node_summary)
                        topics_map[topic_id]["decisions"].append(node_summary)
                    elif o_type == "question" or obj_id.startswith("que"):
                        open_questions.append(node_summary)
                        topics_map[topic_id]["questions"].append(node_summary)
                    elif o_type == "assumption" or obj_id.startswith("asm"):
                        assumptions.append(node_summary)
                        topics_map[topic_id]["assumptions"].append(node_summary)
                    elif o_type == "evidence" or obj_id.startswith("evi"):
                        evidences.append(node_summary)
                        topics_map[topic_id]["evidences"].append(node_summary)
                    else:
                        checkpoints.append(node_summary)
                        topics_map[topic_id]["checkpoints"].append(node_summary)

                # Sort topics: newest updated topic first
                topics_list = sorted(
                    topics_map.values(),
                    key=lambda t: t.get("latest_updated_at", ""),
                    reverse=True,
                )

                # Add Master Project Decision Map Item
                summary = (
                    f"架构决策图 (DAG) 状态: {len(topics_list)}个架构议题 (Topics) · "
                    f"已决议 {len(discussed_decisions)} 项 · "
                    f"待讨论 {len(open_questions)} 个问题 · "
                    f"底层假设 {len(assumptions)} 项 · 修订版本 r{revision}"
                )

                items.append(
                    ObservatoryItem(
                        agent_id=self.agent_id,
                        item_id=f"bs_dag_{proj_id}",
                        title=f"专案决策图谱 (DAG): {proj_id}",
                        kind="decision_dag",
                        status="ACTIVE",
                        health="HEALTHY",
                        updated_at=updated_at,
                        summary=summary,
                        source_ref=f"brainstormer/projects/{s_file.parent.name}/{s_file.name}",
                        payload={
                            "project_id": proj_id,
                            "revision": revision,
                            "updated_at": updated_at,
                            "summary": summary,
                            "topics": topics_list,
                            "topics_count": len(topics_list),
                            "discussed_decisions": discussed_decisions,
                            "open_questions": open_questions,
                            "assumptions": assumptions,
                            "evidences": evidences,
                            "checkpoints": checkpoints,
                            "dag_links": links,
                            "raw_objects_count": len(objects),
                        },
                    )
                )

                # Add dedicated Architecture Topic items for direct inspection
                for top in topics_list:
                    items.append(
                        ObservatoryItem(
                            agent_id=self.agent_id,
                            item_id=f"bs_top_{proj_id}_{top['topic_id']}",
                            title=f"架构议题: {top['title']}",
                            kind="architecture_topic",
                            status="ACTIVE",
                            health="HEALTHY",
                            updated_at=updated_at,
                            summary=(
                                f"架构议题 · 已决议 {len(top['decisions'])} 项 · "
                                f"待研讨 {len(top['questions'])} 个问题 · "
                                f"底层假设 {len(top['assumptions'])} 项 · 关联专案: {proj_id}"
                            ),
                            source_ref=f"decision_dag:{top['topic_id']}",
                            payload={
                                "topic": top,
                                "project_id": proj_id,
                                "revision": revision,
                                "all_topics": [
                                    {"topic_id": t["topic_id"], "title": t["title"]}
                                    for t in topics_list
                                ],
                            },
                        )
                    )

                # Add individual sub-items for open questions and discussed decisions
                for q in open_questions:
                    items.append(
                        ObservatoryItem(
                            agent_id=self.agent_id,
                            item_id=f"bs_que_{q['id']}",
                            title=f"待讨论问题: {q['title']}",
                            kind="open_question",
                            status="OPEN",
                            health="HEALTHY",
                            updated_at=updated_at,
                            summary=f"尚未形成决议的架构研讨议题 · 所属议题: {q.get('topic_id', '')} · 专案: {proj_id}",
                            source_ref=f"decision_dag:{q['id']}",
                            payload={"question": q, "project_id": proj_id},
                        )
                    )

                for d in discussed_decisions:
                    items.append(
                        ObservatoryItem(
                            agent_id=self.agent_id,
                            item_id=f"bs_dec_{d['id']}",
                            title=f"已决议: {d['title']}",
                            kind="accepted_decision",
                            status="COMPLETED",
                            health="HEALTHY",
                            updated_at=updated_at,
                            summary=f"已达成共识的架构决策方案 · 所属议题: {d.get('topic_id', '')} · 专案: {proj_id}",
                            source_ref=f"decision_dag:{d['id']}",
                            payload={"decision": d, "project_id": proj_id},
                        )
                    )

            except (json.JSONDecodeError, OSError):
                continue

        # 2. Fallback: If empty, read Hermes sessions for profile 'brainstormer'
        if not items:
            hermes_db = self.hermes_dir / "state.db"
            if hermes_db.exists():
                conn = self.safe_sqlite_connect(hermes_db)
                if conn:
                    try:
                        with conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('sessions', 'chat_sessions')"
                            )
                            tbl = cursor.fetchone()
                            if tbl:
                                tbl_name = tbl[0]
                                cursor.execute(
                                    f"""
                                    SELECT session_id, title, updated_at
                                    FROM {tbl_name}
                                    ORDER BY updated_at DESC LIMIT ? OFFSET ?
                                    """,
                                    (limit, offset),
                                )
                                for r in cursor.fetchall():
                                    items.append(
                                        ObservatoryItem(
                                            agent_id=self.agent_id,
                                            item_id=f"session_{r['session_id']}",
                                            title=r["title"] or f"Discussion {r['session_id'][:8]}",
                                            kind="discussion_session",
                                            status="ACTIVE",
                                            updated_at=r["updated_at"],
                                            summary="来自 Hermes 会话的架构方案讨论",
                                            source_ref=f"hermes:state.db ({tbl_name})",
                                            payload={"session_id": r["session_id"]},
                                        )
                                    )
                    except sqlite3.Error:
                        pass

        if not items:
            items.append(
                ObservatoryItem(
                    agent_id=self.agent_id,
                    item_id="bs_standby",
                    title="Observatory Architecture & Specialization",
                    kind="decision_dag",
                    status="ACTIVE",
                    summary="All-in-One 观测台架构与数据接入研讨检查点",
                    source_ref="brainstormer:checkpoint",
                    payload={"topic": "Observatory Architecture", "checkpoint": "Round 2 completed"},
                )
            )

        return items[offset : offset + limit]

    def get_item(self, item_id: str) -> ObservatoryItem | None:
        items = self.list_items(limit=100)
        for it in items:
            if it.item_id == item_id:
                return it
        return None
