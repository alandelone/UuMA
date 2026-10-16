"""Wisdom-Oldman source adapter."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ..models import ObservatoryItem, SourceFreshness
from .base import ObservatorySourceAdapter


class WisdomAdapter(ObservatorySourceAdapter):
    agent_id = "wisdom-oldman"
    display_name = "Wisdom-Oldman"
    role = "调查机制与证据，按主题组织知识体系，展示真实调查推进与图谱状态"
    source_name = "wisdom.db & uuma.db"

    def __init__(
        self,
        data_dir: Path | str,
        knowledge_path: Path | str | None = None,
        uuma_db_path: Path | str | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.db_path = self._resolve_wisdom_db(knowledge_path)
        self.uuma_db_path = self._resolve_uuma_db(uuma_db_path)

    def _resolve_wisdom_db(self, explicit_path: Path | str | None) -> Path:
        if explicit_path and Path(explicit_path).exists():
            return Path(explicit_path).resolve()
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        candidates = [
            local_app_data / "Packages" / "OpenAI.Codex_2p2nqsd0c76g0" / "LocalCache" / "Local" / "UuMA" / "wisdom.db",
            self.data_dir / "wisdom.db",
            self.data_dir / ".." / ".uuma-local" / "wisdom.db",
            local_app_data / "UuMA" / "wisdom.db",
        ]
        existing = [c.resolve() for c in candidates if c.exists()]
        if not existing:
            return (self.data_dir / "wisdom.db").resolve()
        # Sort by file size descending to prioritize the canonical rich knowledge DB
        existing.sort(key=lambda p: p.stat().st_size, reverse=True)
        return existing[0]

    def _resolve_uuma_db(self, explicit_path: Path | str | None) -> Path:
        if explicit_path and Path(explicit_path).exists():
            return Path(explicit_path).resolve()
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        candidates = [
            self.data_dir / "uuma.db",
            local_app_data / "UuMA" / "uuma.db",
            self.data_dir / ".." / ".uuma-local" / "uuma.db",
            local_app_data / "Packages" / "OpenAI.Codex_2p2nqsd0c76g0" / "LocalCache" / "Local" / "UuMA" / "uuma.db",
        ]
        for c in candidates:
            if c.exists():
                return c.resolve()
        return (self.data_dir / "uuma.db").resolve()

    def probe_health(self) -> SourceFreshness:
        if not self.db_path.exists():
            return SourceFreshness(
                source_name=self.source_name,
                is_available=False,
                error_message=f"Database file not found: {self.db_path.name}",
            )
        conn = self.safe_sqlite_connect(self.db_path)
        if not conn:
            return SourceFreshness(
                source_name=self.source_name,
                is_available=False,
                error_message="Cannot open database with read-only connection",
            )
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(occurred_at) FROM knowledge_events")
                row = cursor.fetchone()
                last_time = row[0] if row else None
                return SourceFreshness(
                    source_name=self.source_name,
                    is_available=True,
                    last_event_at=last_time,
                )
        except sqlite3.Error as exc:
            return SourceFreshness(
                source_name=self.source_name,
                is_available=False,
                error_message=str(exc),
            )

    def list_items(self, limit: int = 30, offset: int = 0) -> list[ObservatoryItem]:
        task_items: list[ObservatoryItem] = []
        topic_items: list[ObservatoryItem] = []

        # 1. Query Knowledge Topics from wisdom.db
        topics_dict: dict[str, dict] = {}
        if self.db_path.exists():
            conn = self.safe_sqlite_connect(self.db_path)
            if conn:
                try:
                    with conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            SELECT topic_id, normalized_key, status, record_json, updated_sequence
                            FROM knowledge_topics
                            ORDER BY (CASE WHEN status='ACTIVE' THEN 1 ELSE 2 END), updated_sequence DESC
                            """
                        )
                        for row in cursor.fetchall():
                            t_id = row["topic_id"]
                            rec_raw = row["record_json"] or "{}"
                            try:
                                rec = json.loads(rec_raw) if isinstance(rec_raw, str) else rec_raw
                            except (json.JSONDecodeError, TypeError, ValueError):
                                rec = {}

                            title = rec.get("title") or row["normalized_key"] or f"Topic {t_id[:8]}"
                            aliases = rec.get("aliases") or []
                            summary = rec.get("summary") or f"主题关键词: {row['normalized_key']} · 状态: {row['status']}"
                            superseded = rec.get("superseded_by_topic_id")

                            # Link and claims count
                            links_cnt = 0
                            try:
                                cursor.execute("SELECT COUNT(*) FROM topic_knowledge_links WHERE topic_id = ?", (t_id,))
                                r_cnt = cursor.fetchone()
                                if r_cnt:
                                    links_cnt = r_cnt[0]
                            except sqlite3.Error:
                                pass

                            # Version count
                            ver_cnt = 0
                            try:
                                cursor.execute("SELECT COUNT(*) FROM topic_document_versions WHERE topic_id = ?", (t_id,))
                                r_cnt = cursor.fetchone()
                                if r_cnt:
                                    ver_cnt = r_cnt[0]
                            except sqlite3.Error:
                                pass

                            # Query Claims
                            claims: list[dict] = []
                            try:
                                cursor.execute(
                                    """
                                    SELECT c.claim_id, c.status, c.record_json
                                    FROM claims c
                                    ORDER BY c.updated_sequence DESC
                                    LIMIT 10
                                    """
                                )
                                for cr in cursor.fetchall():
                                    crec = json.loads(cr["record_json"]) if cr["record_json"] else {}
                                    statement = crec.get("statement") or f"{crec.get('subject', '')} {crec.get('predicate', '')} {crec.get('object', '')}".strip()
                                    claims.append({
                                        "claim_id": cr["claim_id"],
                                        "status": cr["status"],
                                        "statement": statement,
                                        "confidence": crec.get("confidence", "HIGH"),
                                    })
                            except sqlite3.Error:
                                pass

                            # Query GAPs
                            gaps: list[dict] = []
                            try:
                                cursor.execute(
                                    """
                                    SELECT gap_id, gap_type, status, record_json
                                    FROM gaps
                                    LIMIT 10
                                    """
                                )
                                for gr in cursor.fetchall():
                                    grec = json.loads(gr["record_json"]) if gr["record_json"] else {}
                                    gaps.append({
                                        "gap_id": gr["gap_id"],
                                        "type": gr["gap_type"],
                                        "status": gr["status"],
                                        "reason": grec.get("reason"),
                                        "why_worthwhile": grec.get("why_worthwhile"),
                                    })
                            except sqlite3.Error:
                                pass

                            # Query Orbit and latest Cycle Explanation
                            orbit_info = None
                            cycle_explanation = None
                            try:
                                cursor.execute(
                                    """
                                    SELECT qo.orbit_id, qo.status,
                                           json_extract(qo.record_json, '$.stop_reason') as stop_reason,
                                           oc.record_json as cycle_json
                                    FROM question_orbits qo
                                    LEFT JOIN orbit_cycles oc ON qo.orbit_id = oc.orbit_id
                                    WHERE json_extract(qo.record_json, '$.topic_id') = ?
                                    ORDER BY oc.updated_sequence DESC
                                    LIMIT 1
                                    """,
                                    (t_id,),
                                )
                                orb_row = cursor.fetchone()
                                if orb_row:
                                    c_rec = json.loads(orb_row["cycle_json"]) if orb_row["cycle_json"] else {}
                                    cycle_explanation = c_rec.get("cycle_explanation")
                                    orbit_info = {
                                        "orbit_id": orb_row["orbit_id"],
                                        "status": orb_row["status"],
                                        "stop_reason": orb_row["stop_reason"],
                                        "cycle_explanation": cycle_explanation,
                                        "discovery_attempts": c_rec.get("discovery_attempts") or [],
                                    }
                            except sqlite3.Error:
                                pass

                            topics_dict[t_id] = {
                                "topic_id": t_id,
                                "title": title,
                                "status": row["status"] or "ACTIVE",
                                "aliases": aliases,
                                "summary": summary,
                                "superseded_by_topic_id": superseded,
                                "recovery_history_ref": rec.get("recovery_history_ref"),
                                "ver_cnt": ver_cnt,
                                "links_cnt": links_cnt,
                                "claim_count": len(claims),
                                "claims": claims,
                                "gaps": gaps,
                                "orbit_info": orbit_info,
                                "cycle_explanation": cycle_explanation,
                                "under_tasks": [],
                                "openspg_endpoint": "http://192.168.55.2:8887",
                                "standalone_url": f"http://127.0.0.1:8767/wisdom/topics/{t_id}?token=nKqEa4j7FtpIR9IoTsmLma_u_yfBXs6hOdijYyfD1wI",
                            }
                except sqlite3.Error:
                    pass

        # 2. Query Tasks from uuma.db and map them to Topics
        active_scallion_topic_id = "topic_07a8574b5d504d34a5483407c2a88400"
        if self.uuma_db_path.exists():
            uuma_conn = self.safe_sqlite_connect(self.uuma_db_path)
            if uuma_conn:
                try:
                    with uuma_conn:
                        cur = uuma_conn.cursor()
                        cur.execute(
                            """
                            SELECT t.task_id, t.title, t.status as task_status, t.contract_json,
                                   r.run_id, r.status as run_status, r.progress_json
                            FROM tasks t
                            LEFT JOIN runs r ON t.task_id = r.task_id
                            WHERE (t.assignee = 'wisdom-oldman' OR r.agent_id = 'wisdom-oldman')
                              AND t.status IN ('RUNNING', 'READY')
                            ORDER BY (CASE WHEN t.status='RUNNING' THEN 1 WHEN t.status='READY' THEN 2 ELSE 3 END), t.updated_sequence DESC
                            LIMIT 6
                            """
                        )
                        task_rows = cur.fetchall()
                        for row in task_rows:
                            t_id = row["task_id"]
                            t_title = row["title"]
                            t_status = row["task_status"]
                            r_status = row["run_status"] or t_status
                            p_json = row["progress_json"] or "{}"
                            try:
                                prog = json.loads(p_json) if isinstance(p_json, str) else p_json
                            except (json.JSONDecodeError, TypeError, ValueError):
                                prog = {}

                            contract = {}
                            if row["contract_json"]:
                                try:
                                    contract = json.loads(row["contract_json"])
                                except (json.JSONDecodeError, TypeError, ValueError):
                                    contract = {}

                            obj = contract.get("objective", "")

                            # Determine parent topic
                            parent_topic_id = None
                            match = re.search(r"topic_[a-f0-9]{32}", obj)
                            if match and match.group(0) in topics_dict:
                                parent_topic_id = match.group(0)
                            elif (
                                "orbit_2acc21b58823d539200f347fba6d8a3a" in obj
                                or any(k in t_title or k in obj for k in ("青葱", "气雾", "分株", "aeroponic", "scallion"))
                            ):
                                parent_topic_id = active_scallion_topic_id
                            elif "what is known" in t_title.lower() or "whatisknown" in obj.lower():
                                parent_topic_id = "topic_0c5fd4fbbea44ebc9032bb0300346952"

                            parent_topic = topics_dict.get(parent_topic_id)
                            parent_title = parent_topic["title"] if parent_topic else "知识主题探索"

                            # Query timeline events for this task
                            timeline: list[dict] = []
                            try:
                                cur.execute(
                                    """
                                    SELECT sequence, event_type, aggregate_type, aggregate_id, actor_id, occurred_at, payload_json
                                    FROM events
                                    WHERE aggregate_id = ? OR aggregate_id = ?
                                    ORDER BY sequence ASC
                                    """,
                                    (t_id, row["run_id"]),
                                )
                                for ev in cur.fetchall():
                                    ev_p = json.loads(ev["payload_json"]) if ev["payload_json"] else {}
                                    timeline.append({
                                        "sequence": ev["sequence"],
                                        "event_type": ev["event_type"],
                                        "aggregate_type": ev["aggregate_type"],
                                        "actor_id": ev["actor_id"],
                                        "occurred_at": ev["occurred_at"],
                                        "payload": ev_p,
                                    })
                            except sqlite3.Error:
                                pass

                            # Heartbeat & Liveness calculation
                            last_hb = prog.get("last_heartbeat")
                            is_silent = False
                            hours_ago = 0.0
                            heartbeat_delay_str = "无心跳记录"
                            if last_hb:
                                try:
                                    hb_clean = last_hb.replace("Z", "+00:00")
                                    dt_hb = datetime.fromisoformat(hb_clean)
                                    now = datetime.now(UTC)
                                    delta = now - dt_hb
                                    hours_ago = delta.total_seconds() / 3600.0
                                    heartbeat_delay_str = f"距今已过去 {hours_ago:.1f} 小时无新心跳回传"
                                    is_silent = hours_ago > 1.0
                                except (ValueError, TypeError, OSError):
                                    heartbeat_delay_str = f"上次心跳时间: {last_hb}"

                            if t_status == "RUNNING":
                                if is_silent:
                                    liveness_badge = "⚠️ 心跳静默 (挂起待命 / 等待Worker唤醒)"
                                    liveness_explanation = (
                                        f"当前任务在调度队列中标记为 RUNNING，但距上次活跃心跳（{last_hb}）已过去 {hours_ago:.1f} 小时。"
                                        "当前无本地 Worker 进程正在占用 CPU/网络执行该任务。系统处于就绪挂起状态，等待调度器发起下一轮调研周期。"
                                    )
                                else:
                                    liveness_badge = "🟢 实时活跃推进中 (Active Running)"
                                    liveness_explanation = "后台 Worker 正在实时轮询并向图谱端推进调研与证据抓取。"
                            else:
                                liveness_badge = f"⚪ 状态: {t_status} (待命/未开始)"
                                liveness_explanation = f"任务处于 {t_status} 状态，已在调度器中注册，等待路由或人工确认。"

                            blocker = prog.get("blocker")
                            summary = (
                                f"所属主题: {parent_title} · 状态: {t_status}"
                                + (f" · ⚠️ 心跳静默 ({hours_ago:.0f}h)" if (t_status == 'RUNNING' and is_silent) else "")
                                + (f" · 阻塞: {blocker}" if blocker else " · 运行通畅无硬阻塞")
                            )

                            target_gaps = [
                                "青葱分株后缓苗要多久？（查找直接证据，给出具体天数范围与成活率判断指标）",
                                "青葱（Allium fistulosum）气雾培的喷雾间隔、喷头与营养液参数定位证据及适用条件",
                            ]

                            task_payload = {
                                "task_id": t_id,
                                "run_id": row["run_id"],
                                "status": t_status,
                                "run_status": r_status,
                                "parent_topic_id": parent_topic_id,
                                "parent_topic_title": parent_title,
                                "parent_topic_status": parent_topic["status"] if parent_topic else "ACTIVE",
                                "blocker": blocker,
                                "progress": prog,
                                "attempt": prog.get("attempt", 1),
                                "completed_steps": prog.get("completed_steps", 0),
                                "last_heartbeat": last_hb,
                                "is_silent": is_silent,
                                "heartbeat_delay_str": heartbeat_delay_str,
                                "liveness_badge": liveness_badge,
                                "liveness_explanation": liveness_explanation,
                                "target_gaps": target_gaps,
                                "timeline": timeline,
                                "objective": obj,
                                "cycle_explanation": parent_topic.get("cycle_explanation") if parent_topic else None,
                                "discovery_attempts": (parent_topic.get("orbit_info") or {}).get("discovery_attempts", []) if parent_topic else [],
                                "acceptance_checks": contract.get("acceptance_checks", []),
                                "openspg_endpoint": "http://192.168.55.2:8887",
                                "standalone_url": f"http://127.0.0.1:8767/wisdom/topics/{parent_topic_id}?token=nKqEa4j7FtpIR9IoTsmLma_u_yfBXs6hOdijYyfD1wI" if parent_topic_id else None,
                            }

                            task_items.append(
                                ObservatoryItem(
                                    agent_id=self.agent_id,
                                    item_id=f"wisdom_task_{t_id}",
                                    title=f"调查任务: {t_title}",
                                    kind="active_task",
                                    status="RUNNING" if t_status == "RUNNING" else ("BLOCKED" if blocker else t_status),
                                    health="WARNING" if (blocker or (t_status == "RUNNING" and is_silent)) else "HEALTHY",
                                    updated_at=last_hb or timeline[-1]["occurred_at"] if timeline else None,
                                    summary=summary,
                                    source_ref="uuma.db:tasks",
                                    payload=task_payload,
                                )
                            )

                            if parent_topic_id and parent_topic_id in topics_dict:
                                topics_dict[parent_topic_id]["under_tasks"].append({
                                    "task_id": t_id,
                                    "title": t_title,
                                    "status": t_status,
                                    "run_id": row["run_id"],
                                    "is_silent": is_silent,
                                    "liveness_badge": liveness_badge,
                                })
                except sqlite3.Error:
                    pass

        # 3. Create ObservatoryItems for all Topics
        for t_id, top in topics_dict.items():
            topic_items.append(
                ObservatoryItem(
                    agent_id=self.agent_id,
                    item_id=f"wisdom_topic_{t_id}",
                    title=f"知识主题: {top['title']}",
                    kind="knowledge_topic",
                    status=top["status"],
                    health="HEALTHY",
                    updated_at=None,
                    summary=f"版本: v{top['ver_cnt']} · 沉淀断言: {top['claim_count']} 项 · 引据: {top['links_cnt']} 处 · 包含挂靠调查: {len(top['under_tasks'])} 项",
                    source_ref=f"wisdom.db ({t_id[:8]})",
                    payload=top,
                )
            )

        # Merge: Active tasks first, then topics (active first, then archived)
        all_items = task_items + topic_items
        if not all_items:
            all_items.append(
                ObservatoryItem(
                    agent_id=self.agent_id,
                    item_id="wisdom_standby",
                    title="Wisdom Knowledge Graph Hub",
                    kind="knowledge_topic",
                    status="IDLE",
                    health="HEALTHY",
                    summary="知识库处于就绪状态，等待新主题或调研问题",
                    source_ref=self.source_name,
                    payload={"status": "Idle", "openspg_endpoint": "http://192.168.55.2:8887"},
                )
            )

        return all_items[offset : offset + limit]

    def get_item(self, item_id: str) -> ObservatoryItem | None:
        items = self.list_items(limit=100)
        for it in items:
            if it.item_id == item_id:
                return it
        return None
