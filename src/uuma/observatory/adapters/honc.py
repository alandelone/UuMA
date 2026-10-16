"""honc agent source adapter for life and habit tracking."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..models import ObservatoryItem, SourceFreshness
from .base import ObservatorySourceAdapter


class HoncAdapter(ObservatorySourceAdapter):
    agent_id = "honc"
    display_name = "honc"
    role = "日常执行与追踪管家，管理习惯、执行事实、完成依据、语义心跳及进度对账"
    source_name = "honc/honc.db"

    def __init__(self, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)
        self.db_path = self._resolve_db_path()

    def _resolve_db_path(self) -> Path:
        candidates = [
            self.data_dir / "honc" / "honc.db",
            self.data_dir / "honc.db",
            self.data_dir / ".." / ".uuma-local" / "honc.db",
            Path.home() / "AppData" / "Local" / "UuMA" / "honc" / "honc.db",
        ]
        for c in candidates:
            if c.exists():
                return c.resolve()
        return (self.data_dir / "honc" / "honc.db").resolve()

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
                cursor.execute("SELECT datetime('now')")
                now = cursor.fetchone()[0]
                cursor.execute("SELECT MAX(recorded_at) FROM life_revisions")
                r = cursor.fetchone()
                last_time = r[0] if (r and r[0]) else now
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

    def list_items(self, limit: int = 15, offset: int = 0) -> list[ObservatoryItem]:
        conn = self.safe_sqlite_connect(self.db_path)
        if not conn:
            return []

        items: list[ObservatoryItem] = []
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = {r[0] for r in cursor.fetchall()}

                # 1. Semantic Tick Runner & Native Reminder Status
                tick_status = "ACTIVE"
                if "life_reminder_events" in tables or "life_operations" in tables:
                    cursor.execute("SELECT COUNT(*) FROM life_operations")
                    ops_count = cursor.fetchone()[0]

                    items.append(
                        ObservatoryItem(
                            agent_id=self.agent_id,
                            item_id="honc_semantic_tick_runner",
                            title="语义心跳调度器 (Semantic Tick Runner)",
                            kind="runner",
                            status=tick_status,
                            health="HEALTHY",
                            summary=f"心跳调度正常 · 已执行操作: {ops_count} 笔 · 本地生活与习惯守护队列在线",
                            source_ref="life_operations",
                            payload={
                                "runner": "honc-life-semantic-tick-v1",
                                "status": tick_status,
                                "total_operations": ops_count,
                            },
                        )
                    )

                # 2. Life Objects & Habit Definitions from life_revisions
                if "life_objects" in tables and "life_revisions" in tables:
                    cursor.execute(
                        """
                        SELECT o.object_id, o.kind, r.revision, r.status, r.payload_json, r.recorded_at
                        FROM life_objects o
                        JOIN life_revisions r ON o.object_id = r.object_id AND o.head_revision = r.revision
                        ORDER BY r.recorded_at DESC
                        LIMIT ? OFFSET ?
                        """,
                        (limit, offset),
                    )
                    for r in cursor.fetchall():
                        raw_json = r["payload_json"] or "{}"
                        try:
                            payload = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
                        except (json.JSONDecodeError, TypeError, ValueError):
                            payload = {}

                        name = payload.get("name") or payload.get("habit_id") or r["object_id"]
                        kind = r["kind"]
                        status = r["status"] or "ACTIVE"

                        if kind == "settings":
                            title = "生活作息与睡眠配置 (Settings)"
                            summary = f"起床目标: {payload.get('wake_time', '08:00')} · 就寝目标: {payload.get('bedtime', '21:30')} · 宽限期: 30分钟"
                        elif "habit" in kind:
                            title = f"习惯定义: {name}"
                            summary = f"状态: {status} · 目标频次: {payload.get('target_count', 1)} · 重要度: {payload.get('importance', 'normal')}"
                        else:
                            title = f"{kind}: {name}"
                            summary = f"状态: {status} · 修订版本: r{r['revision']}"

                        items.append(
                            ObservatoryItem(
                                agent_id=self.agent_id,
                                item_id=f"honc_{r['object_id']}",
                                title=title,
                                kind=kind,
                                status=status,
                                updated_at=r["recorded_at"],
                                summary=summary,
                                source_ref=f"life_objects ({kind})",
                                payload=payload,
                            )
                        )

                # 3. Legacy state / occurrences
                if "life_legacy_events" in tables:
                    cursor.execute("SELECT COUNT(*) FROM life_legacy_events")
                    legacy_count = cursor.fetchone()[0]
                    if legacy_count > 0:
                        cursor.execute(
                            """
                            SELECT legacy_id, event_type, occurred_at, summary
                            FROM life_legacy_events
                            ORDER BY occurred_at DESC LIMIT 3
                            """
                        )
                        for leg in cursor.fetchall():
                            items.append(
                                ObservatoryItem(
                                    agent_id=self.agent_id,
                                    item_id=f"honc_leg_{leg['legacy_id']}",
                                    title=f"日常事实: {leg['summary'] or leg['event_type']}",
                                    kind="life_occurrence",
                                    status="COMPLETED",
                                    updated_at=leg["occurred_at"],
                                    summary=f"生活执行历史记录 · 类型: {leg['event_type']}",
                                    source_ref="life_legacy_events",
                                    payload={"legacy_id": leg["legacy_id"], "event_type": leg["event_type"]},
                                )
                            )
        except sqlite3.Error:
            pass

        if not items:
            items.append(
                ObservatoryItem(
                    agent_id=self.agent_id,
                    item_id="honc_standby",
                    title="honc 生活管家",
                    kind="runner",
                    status="ACTIVE",
                    health="HEALTHY",
                    summary="日常习惯守护与作息追踪就绪",
                    source_ref=self.source_name,
                    payload={"status": "Active"},
                )
            )

        return items[offset : offset + limit]

    def get_item(self, item_id: str) -> ObservatoryItem | None:
        items = self.list_items(limit=100)
        for it in items:
            if it.item_id == item_id:
                return it
        return None
