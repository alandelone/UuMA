"""Orchestrator source adapter for system runs, delegation, gates, and tasks."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..models import ObservatoryItem, SourceFreshness
from .base import ObservatorySourceAdapter


class OrchestratorAdapter(ObservatorySourceAdapter):
    agent_id = "orchestrator"
    display_name = "Orchestrator"
    role = "建立与路由任务、执行指派、监控 Agent 工作并执行控制政策与阶段门控"
    source_name = "mission_status.json & uuma.db"

    def __init__(self, uuma_db_path: Path | str, mission_status_path: Path | str | None = None) -> None:
        self.db_path = Path(uuma_db_path)
        self.mission_status_path = (
            Path(mission_status_path)
            if mission_status_path
            else (Path(__file__).resolve().parents[4] / "mission_status.json")
        )

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
                cursor.execute("SELECT MAX(occurred_at) FROM events")
                row = cursor.fetchone()
                return SourceFreshness(
                    source_name=self.source_name,
                    is_available=True,
                    last_event_at=row[0] if row else None,
                )
        except sqlite3.Error as exc:
            return SourceFreshness(
                source_name=self.source_name,
                is_available=False,
                error_message=str(exc),
            )

    def list_items(self, limit: int = 15, offset: int = 0) -> list[ObservatoryItem]:
        items: list[ObservatoryItem] = []

        # 1. Mission Status & Current Stage Gate (Top priority)
        if self.mission_status_path.exists():
            try:
                m_data = json.loads(self.mission_status_path.read_text(encoding="utf-8"))
                stage = m_data.get("stage", "verification")
                gate = m_data.get("gate", {})
                current_gate = gate.get("current", "stage-gates/04-verification-report.md")
                gate_status = gate.get("status", "pending_review")
                mission = m_data.get("mission", "UuMA specialist agent trust, deployment, knowledge, and discussion capabilities")

                items.append(
                    ObservatoryItem(
                        agent_id=self.agent_id,
                        item_id="orch_mission_status",
                        title=f"全局使命与阶段门控 (Mission & Stage: {stage})",
                        kind="mission_gate",
                        status="PENDING_REVIEW" if gate_status == "pending_review" else "ACTIVE",
                        health="HEALTHY",
                        updated_at=m_data.get("updated_at"),
                        summary=f"当前阶段: {stage} · 当前门控: {current_gate} (状态: {gate_status}) · 使命: {mission}",
                        source_ref="mission_status.json",
                        payload={
                            "stage": stage,
                            "gate": gate,
                            "mission": mission,
                            "allowed_stages": m_data.get("allowed_stages", []),
                            "updated_at": m_data.get("updated_at"),
                        },
                    )
                )
            except (json.JSONDecodeError, OSError):
                pass

        # 2. System Delegated Runs & Verifications from uuma.db
        if self.db_path.exists():
            conn = self.safe_sqlite_connect(self.db_path)
            if conn:
                try:
                    with conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            SELECT r.run_id, r.task_id, r.agent_id, r.status, e.occurred_at,
                                   t.title, t.contract_json
                            FROM runs r
                            LEFT JOIN tasks t ON r.task_id = t.task_id
                            LEFT JOIN events e ON r.updated_sequence = e.sequence
                            ORDER BY r.updated_sequence DESC LIMIT 8
                            """
                        )
                        for r in cursor.fetchall():
                            contract_data = {}
                            if r["contract_json"]:
                                try:
                                    contract_data = json.loads(r["contract_json"])
                                except (json.JSONDecodeError, TypeError):
                                    pass
                            contract_type = contract_data.get("execution_class") or contract_data.get("contract_type") or "Direct"

                            items.append(
                                ObservatoryItem(
                                    agent_id=self.agent_id,
                                    item_id=f"orch_run_{r['run_id']}",
                                    title=r["title"] or f"Task Run {r['run_id'][:8]}",
                                    kind="delegated_run",
                                    status=r["status"] or "RUNNING",
                                    updated_at=r["occurred_at"],
                                    summary=f"指派给: {r['agent_id']} · 契约: {contract_type} · 状态: {r['status']}",
                                    source_ref="uuma.db:runs",
                                    payload={
                                        "run_id": r["run_id"],
                                        "task_id": r["task_id"],
                                        "delegated_agent": r["agent_id"],
                                        "contract": contract_data,
                                    },
                                )
                            )
                except sqlite3.Error:
                    pass

        return items[offset : offset + limit]

    def get_item(self, item_id: str) -> ObservatoryItem | None:
        items = self.list_items(limit=100)
        for it in items:
            if it.item_id == item_id:
                return it
        return None
