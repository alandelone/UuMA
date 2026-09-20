from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any, ClassVar

from .knowledge_models import (
    BudgetTier,
    FrontierItemRecord,
    FrontierPriority,
    OrbitStatus,
    QuestionOrbitRecord,
    QuestionRecord,
    ResearchRun,
    ResearchRunStatus,
    SatisfactionLevel,
)
from .knowledge_service import KnowledgeService, json_record

ACTIVE_ORBIT_STATUSES = {
    OrbitStatus.QUEUED.value,
    OrbitStatus.ACTIVE.value,
    OrbitStatus.PAUSED.value,
    OrbitStatus.BLOCKED.value,
}


def normalized_question_key(question: str) -> str:
    normalized = unicodedata.normalize("NFKC", question).casefold()
    normalized = re.sub(r"\s+", " ", normalized).strip(" .?!。？！")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def is_investigative(question: str) -> bool:
    text = unicodedata.normalize("NFKC", question).casefold().strip()
    if not text or len(text) < 12:
        return False
    if text in {"hello", "hi", "你好", "谢谢", "thanks"}:
        return False
    signals = (
        "why", "how", "compare", "evidence", "mechanism", "cause", "trend",
        "conflict", "investigate", "analyze", "research", "which is better",
        "为什么", "如何", "比较", "证据", "机理", "机制", "原因", "趋势", "冲突",
        "调查", "研究", "分析",
    )
    return any(signal in text for signal in signals)


class QuestionOrbitService:
    """Governed, durable lifecycle for Wisdom-Oldman's background research questions."""

    BUDGETS: ClassVar[dict[str, dict[str, int]]] = {
        "QUICK": {"active_seconds": 600, "sources": 10, "model_tokens": 50_000,
                  "search_queries": 20},
        "STANDARD": {"active_seconds": 3_600, "sources": 30, "model_tokens": 250_000,
                     "search_queries": 75},
        "DEEP": {"active_seconds": 21_600, "sources": 100, "model_tokens": 1_000_000,
                 "search_queries": 250},
    }

    def __init__(self, knowledge: KnowledgeService) -> None:
        self.knowledge = knowledge
        self.store = knowledge.store

    def start(
        self,
        question: str,
        objective: str,
        satisfaction_level: SatisfactionLevel,
        satisfaction_rationale: str,
        *,
        actor_id: str,
        gap_ids: list[str] | None = None,
        budget_tier: BudgetTier = BudgetTier.QUICK,
        uuma_task_id: str | None = None,
        uuma_run_id: str | None = None,
        notification_route: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.knowledge.require_writer(actor_id)
        if actor_id == "wisdom-oldman" and budget_tier is not BudgetTier.QUICK:
            raise PermissionError(
                "Wisdom-Oldman may only start QUICK Orbits; a higher tier requires Orchestrator review."
            )
        notification_route = notification_route or {}
        allowed_route_keys = {"platform", "chat_id", "thread_id", "session_id"}
        if set(notification_route) - allowed_route_keys:
            raise ValueError("Notification route contains unsupported fields.")
        if any(len(value) > 500 for value in notification_route.values()):
            raise ValueError("Notification route values must not exceed 500 characters.")
        key = normalized_question_key(question)
        gap_ids = list(dict.fromkeys(gap_ids or []))
        now = datetime.now(UTC)
        with self.store.transaction() as conn:
            placeholders = ",".join("?" for _ in ACTIVE_ORBIT_STATUSES)
            row = conn.execute(
                "SELECT record_json FROM question_orbits WHERE normalized_root_key = ? "
                f"AND status IN ({placeholders}) ORDER BY updated_sequence DESC LIMIT 1",
                (key, *sorted(ACTIVE_ORBIT_STATUSES)),
            ).fetchone()
            if row:
                import json

                return {"created": False, "reused": True, "orbit": json.loads(row[0])}
            for gap_id in gap_ids:
                self.knowledge._require("gaps", gap_id, conn)

            orbit_id = f"orbit_{hashlib.sha256(f'{key}:{now.isoformat()}'.encode()).hexdigest()[:32]}"
            question_record = QuestionRecord(
                text=question,
                why_worth_knowing=objective,
                orbit_id=orbit_id,
            )
            research_run = ResearchRun(
                objective=objective,
                root_question_id=question_record.question_id,
                active_gap_ids=gap_ids,
                status=ResearchRunStatus.ACTIVE,
                satisfaction_level=satisfaction_level,
                satisfaction_rationale=satisfaction_rationale,
                budget_tier=budget_tier,
                orbit_id=orbit_id,
                current_question_id=question_record.question_id,
            )
            orbit = QuestionOrbitRecord(
                orbit_id=orbit_id,
                normalized_root_key=key,
                root_question_id=question_record.question_id,
                research_run_id=research_run.research_run_id,
                objective=objective,
                uuma_task_id=uuma_task_id,
                uuma_run_id=uuma_run_id,
                budget_tier=budget_tier,
                status=OrbitStatus.QUEUED,
                satisfaction_level=satisfaction_level,
                satisfaction_rationale=satisfaction_rationale,
                notification_route=notification_route,
            )
            self._insert(conn, "questions", question_record, "QUESTION_ADDED", actor_id)
            self._insert(conn, "research_runs", research_run, "RESEARCH_RUN_STARTED", actor_id)
            self._insert(conn, "question_orbits", orbit, "QUESTION_ORBIT_STARTED", actor_id)
            for gap_id in gap_ids:
                gap = self.knowledge._require("gaps", gap_id, conn)
                item = FrontierItemRecord(
                    orbit_id=orbit_id,
                    question_id=question_record.question_id,
                    gap_id=gap_id,
                    priority=FrontierPriority.HIGH,
                    relevance=FrontierPriority.HIGH,
                    impact=FrontierPriority.HIGH,
                    uncertainty=FrontierPriority.HIGH,
                    rationale=gap["why_worthwhile"],
                )
                self._insert(
                    conn, "orbit_frontier", item, "ORBIT_FRONTIER_ITEM_ADDED", actor_id
                )
        return {
            "created": True,
            "reused": False,
            "orbit": json_record(orbit),
            "budget": self.BUDGETS[budget_tier.value],
        }

    def _insert(self, conn, table: str, model, event_type: str, actor_id: str) -> None:
        payload = json_record(model)
        record_id = payload[self.store_id(table)]
        event = self.store.append_event(
            conn,
            event_type=event_type,
            aggregate_type=self.knowledge.AGGREGATE_TYPES[table],
            aggregate_id=record_id,
            actor_id=actor_id,
            payload={"record": payload},
        )
        self.store.insert_record(conn, table, payload, event.sequence)

    @staticmethod
    def store_id(table: str) -> str:
        return {
            "questions": "question_id",
            "research_runs": "research_run_id",
            "question_orbits": "orbit_id",
            "orbit_frontier": "frontier_item_id",
        }[table]

    def get(self, orbit_id: str) -> dict[str, Any]:
        orbit = self.knowledge._require("question_orbits", orbit_id)
        return {
            "orbit": orbit,
            "research_run": self.knowledge._require("research_runs", orbit["research_run_id"]),
            "frontier": self.frontier(orbit_id)["records"],
            "budget": self.BUDGETS[orbit["budget_tier"]],
        }

    def list(self, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        records = self.store.list_records("question_orbits", status=status, limit=limit)
        return {"count": len(records), "records": records}

    def frontier(self, orbit_id: str) -> dict[str, Any]:
        self.knowledge._require("question_orbits", orbit_id)
        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        records = [
            record for record in self.store.list_records("orbit_frontier", limit=500)
            if record["orbit_id"] == orbit_id
        ]
        records.sort(
            key=lambda item: (
                priority_order[item["priority"]],
                priority_order[item["relevance"]],
                priority_order[item["impact"]],
                priority_order[item["uncertainty"]],
                priority_order[item["novelty"]],
                -priority_order[item["estimated_cost"]],
                item["created_at"],
                item["frontier_item_id"],
            )
        )
        return {"orbit_id": orbit_id, "count": len(records), "records": records}

    def transition(
        self, orbit_id: str, status: OrbitStatus, *, actor_id: str, reason: str | None = None
    ) -> dict[str, Any]:
        self.knowledge.require_writer(actor_id)
        with self.store.transaction() as conn:
            before = self.knowledge._require("question_orbits", orbit_id, conn)
            allowed = {
                "QUEUED": {"ACTIVE", "PAUSED", "STOPPED"},
                "ACTIVE": {"PAUSED", "COMPLETED", "STOPPED", "BUDGET_EXHAUSTED", "BLOCKED", "FAILED"},
                "PAUSED": {"QUEUED", "STOPPED"},
                "BLOCKED": {"QUEUED", "STOPPED"},
            }
            if status.value not in allowed.get(before["status"], set()):
                raise ValueError(f"Invalid orbit transition: {before['status']} -> {status.value}")
            after = before | {
                "status": status.value,
                "updated_at": datetime.now(UTC).isoformat(),
                "stop_reason": reason if status.value not in ACTIVE_ORBIT_STATUSES else None,
            }
            event = self.store.append_event(
                conn,
                event_type=f"QUESTION_ORBIT_{status.value}",
                aggregate_type="question_orbit",
                aggregate_id=orbit_id,
                actor_id=actor_id,
                payload={"before": before, "after": after, "reason": reason},
            )
            self.store.update_record(conn, "question_orbits", after, event.sequence)
        return after

    def preflight(
        self,
        question: str,
        answer: dict[str, Any],
        *,
        actor_id: str,
        uuma_task_id: str | None = None,
        uuma_run_id: str | None = None,
        notification_route: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        level = SatisfactionLevel(answer["satisfaction_level"])
        gap_ids = answer.get("remaining_gap_ids") or []
        eligible = (
            is_investigative(question)
            and level in {SatisfactionLevel.INSUFFICIENT, SatisfactionLevel.PROVISIONAL}
            and bool(gap_ids)
        )
        result: dict[str, Any] = {"answer": answer, "orbit_started": False}
        if eligible:
            started = self.start(
                question,
                f"Resolve the worthwhile evidence gaps for: {question}",
                level,
                answer["satisfaction_rationale"],
                actor_id=actor_id,
                gap_ids=gap_ids,
                uuma_task_id=uuma_task_id,
                uuma_run_id=uuma_run_id,
                notification_route=notification_route,
            )
            result |= {
                "orbit_started": started["created"],
                "orbit_reused": started["reused"],
                "orbit_id": started["orbit"]["orbit_id"],
                "orbit_status": started["orbit"]["status"],
            }
        return result
