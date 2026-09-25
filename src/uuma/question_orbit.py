from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from .knowledge_models import (
    BudgetTier,
    DiscoveryUsageRecord,
    FrontierItemRecord,
    FrontierPriority,
    GapRecord,
    GapType,
    OrbitCycleRecord,
    OrbitCycleStatus,
    OrbitNotificationRecord,
    OrbitNotificationStatus,
    OrbitStatus,
    QuestionOrbitRecord,
    QuestionRecord,
    ResearchRun,
    ResearchRunStatus,
    SatisfactionLevel,
    WorkStatus,
)
from .knowledge_service import KnowledgeService, json_record
from .knowledge_store import TABLE_IDS
from .wisdom_topics import TopicKnowledgeService

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
    if not text or len(text) < 3:
        return False
    if text.strip(" .!?。？！") in {
        "hello", "hi", "hey", "你好", "您好", "谢谢", "thanks", "thank you",
    }:
        return False
    control = {"stop", "pause", "resume", "status", "停止", "暂停", "恢复", "状态"}
    return text not in control


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

    def __init__(
        self,
        knowledge: KnowledgeService,
        *,
        topics: TopicKnowledgeService | None = None,
        automatic_budget_tier: BudgetTier = BudgetTier.QUICK,
    ) -> None:
        self.knowledge = knowledge
        self.store = knowledge.store
        self.topics = topics or TopicKnowledgeService(knowledge)
        self.automatic_budget_tier = automatic_budget_tier

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
        topic_id: str | None = None,
        root_question_id: str | None = None,
        policy_authorized: bool = False,
    ) -> dict[str, Any]:
        self.knowledge.require_writer(actor_id)
        if (
            actor_id == "wisdom-oldman"
            and budget_tier is not BudgetTier.QUICK
            and not policy_authorized
        ):
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
            if topic_id:
                self.knowledge._require("knowledge_topics", topic_id, conn)
                row = conn.execute(
                    "SELECT record_json FROM question_orbits WHERE "
                    "(normalized_root_key = ? OR json_extract(record_json, '$.topic_id') = ?) "
                    "ORDER BY updated_sequence DESC LIMIT 1",
                    (key, topic_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT record_json FROM question_orbits WHERE normalized_root_key = ? "
                    "ORDER BY updated_sequence DESC LIMIT 1",
                    (key,),
                ).fetchone()
            if row:
                existing_orbit = json.loads(row[0])
                run_before = self.knowledge._require(
                    "research_runs", existing_orbit["research_run_id"], conn
                )
                existing_rows = conn.execute(
                    "SELECT record_json FROM orbit_frontier WHERE orbit_id = ?",
                    (existing_orbit["orbit_id"],),
                ).fetchall()
                existing_gap_ids = {
                    item.get("gap_id") for item in (
                        json.loads(item["record_json"]) for item in existing_rows
                    )
                }
                added_gap_ids: list[str] = []
                added_question_ids: list[str] = []
                for gap_id in gap_ids:
                    if gap_id in existing_gap_ids:
                        continue
                    gap = self.knowledge._require("gaps", gap_id, conn)
                    question_id = (
                        gap.get("question_id")
                        or root_question_id
                        or existing_orbit["root_question_id"]
                    )
                    item = FrontierItemRecord(
                        orbit_id=existing_orbit["orbit_id"],
                        question_id=question_id,
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
                    added_gap_ids.append(gap_id)
                    added_question_ids.append(question_id)

                orbit_after = existing_orbit | {"updated_at": now.isoformat()}
                if notification_route:
                    orbit_after["notification_route"] = notification_route
                run_after = run_before | {
                    "active_gap_ids": list(
                        dict.fromkeys([*run_before.get("active_gap_ids", []), *added_gap_ids])
                    ),
                    "updated_at": now.isoformat(),
                }
                budget = self.BUDGETS[existing_orbit["budget_tier"]]
                exhausted = (
                    float(run_before.get("active_seconds", 0)) >= budget["active_seconds"]
                    or int(run_before.get("sources_used", 0)) >= budget["sources"]
                    or int(run_before.get("model_tokens_used", 0)) >= budget["model_tokens"]
                    or int(run_before.get("search_queries_used", 0)) >= budget["search_queries"]
                )
                restartable = existing_orbit["status"] in {
                    OrbitStatus.COMPLETED.value,
                    OrbitStatus.BLOCKED.value,
                    OrbitStatus.FAILED.value,
                }
                if added_gap_ids and restartable and not exhausted:
                    orbit_after |= {
                        "status": OrbitStatus.QUEUED.value,
                        "stop_reason": None,
                    }
                    run_after |= {
                        "status": ResearchRunStatus.ACTIVE.value,
                        "current_question_id": added_question_ids[0],
                        "stop_reason": None,
                    }
                if orbit_after != existing_orbit:
                    self._update(
                        conn,
                        "question_orbits",
                        existing_orbit,
                        orbit_after,
                        "QUESTION_ORBIT_REUSED",
                        actor_id,
                    )
                if run_after != run_before:
                    self._update(
                        conn,
                        "research_runs",
                        run_before,
                        run_after,
                        "RESEARCH_RUN_EXTENDED",
                        actor_id,
                    )
                return {
                    "created": False,
                    "reused": True,
                    "orbit": orbit_after,
                    "budget": budget,
                }
            for gap_id in gap_ids:
                self.knowledge._require("gaps", gap_id, conn)

            orbit_id = f"orbit_{hashlib.sha256(f'{key}:{now.isoformat()}'.encode()).hexdigest()[:32]}"
            if root_question_id:
                question_payload = self.knowledge._require(
                    "questions", root_question_id, conn
                )
                question_record = QuestionRecord.model_validate(question_payload)
            else:
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
                topic_id=topic_id,
                objective=objective,
                uuma_task_id=uuma_task_id,
                uuma_run_id=uuma_run_id,
                budget_tier=budget_tier,
                status=OrbitStatus.QUEUED,
                satisfaction_level=satisfaction_level,
                satisfaction_rationale=satisfaction_rationale,
                notification_route=notification_route,
            )
            if not root_question_id:
                self._insert(conn, "questions", question_record, "QUESTION_ADDED", actor_id)
            self._insert(conn, "research_runs", research_run, "RESEARCH_RUN_STARTED", actor_id)
            self._insert(conn, "question_orbits", orbit, "QUESTION_ORBIT_STARTED", actor_id)
            for gap_id in gap_ids:
                gap = self.knowledge._require("gaps", gap_id, conn)
                item = FrontierItemRecord(
                    orbit_id=orbit_id,
                    question_id=gap.get("question_id") or question_record.question_id,
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
        return TABLE_IDS[table]

    def _update(
        self,
        conn,
        table: str,
        before: dict[str, Any],
        after: dict[str, Any],
        event_type: str,
        actor_id: str,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        record_id = after[self.store_id(table)]
        event = self.store.append_event(
            conn,
            event_type=event_type,
            aggregate_type=self.knowledge.AGGREGATE_TYPES[table],
            aggregate_id=record_id,
            actor_id=actor_id,
            payload={"before": before, "after": after} | (extra or {}),
        )
        self.store.update_record(conn, table, after, event.sequence)

    @staticmethod
    def _ordered_frontier(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        return sorted(
            records,
            key=lambda item: (
                priority_order[item["priority"]],
                priority_order[item["relevance"]],
                priority_order[item["impact"]],
                priority_order[item["uncertainty"]],
                priority_order[item["novelty"]],
                -priority_order[item["estimated_cost"]],
                item["created_at"],
                item["frontier_item_id"],
            ),
        )

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
        records = [
            record for record in self.store.list_records("orbit_frontier", limit=500)
            if record["orbit_id"] == orbit_id
        ]
        records = self._ordered_frontier(records)
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
            now = datetime.now(UTC)
            if status in {OrbitStatus.PAUSED, OrbitStatus.STOPPED}:
                cycle_rows = conn.execute(
                    "SELECT record_json FROM orbit_cycles "
                    "WHERE orbit_id = ? AND status = 'RUNNING'",
                    (orbit_id,),
                ).fetchall()
                for row in cycle_rows:
                    cycle_before = json.loads(row["record_json"])
                    cycle_after = cycle_before | {
                        "status": OrbitCycleStatus.BLOCKED.value,
                        "decision": "CANCELLED",
                        "error": reason or f"Orbit was {status.value.casefold()} by request.",
                        "lease_expires_at": now.isoformat(),
                        "completed_at": now.isoformat(),
                        "updated_at": now.isoformat(),
                    }
                    self._update(
                        conn,
                        "orbit_cycles",
                        cycle_before,
                        cycle_after,
                        "ORBIT_CYCLE_CANCELLED",
                        actor_id,
                    )
                    item_before = self.knowledge._require(
                        "orbit_frontier", cycle_before["frontier_item_id"], conn
                    )
                    item_after = item_before | {
                        "status": WorkStatus.OPEN.value,
                        "updated_at": now.isoformat(),
                    }
                    self._update(
                        conn,
                        "orbit_frontier",
                        item_before,
                        item_after,
                        "ORBIT_FRONTIER_ITEM_RELEASED",
                        actor_id,
                    )
            after = before | {
                "status": status.value,
                "updated_at": now.isoformat(),
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
            run_before = self.knowledge._require(
                "research_runs", before["research_run_id"], conn
            )
            run_status = {
                OrbitStatus.PAUSED: ResearchRunStatus.PAUSED,
                OrbitStatus.QUEUED: ResearchRunStatus.ACTIVE,
                OrbitStatus.STOPPED: ResearchRunStatus.STOPPED,
            }.get(status)
            if run_status is not None:
                run_after = run_before | {
                    "status": run_status.value,
                    "stop_reason": reason if status is OrbitStatus.STOPPED else None,
                    "updated_at": now.isoformat(),
                }
                self._update(
                    conn,
                    "research_runs",
                    run_before,
                    run_after,
                    f"RESEARCH_RUN_{run_status.value}",
                    actor_id,
                )
        return after

    def acquire_cycle(
        self,
        owner_id: str,
        *,
        actor_id: str = "wisdom-oldman",
        lease_seconds: int = 180,
    ) -> dict[str, Any] | None:
        """Lease the single globally runnable cycle, recovering an expired cycle when possible."""
        self.knowledge.require_writer(actor_id)
        if not owner_id.strip():
            raise ValueError("owner_id is required.")
        lease_seconds = max(30, min(lease_seconds, 900))
        now = datetime.now(UTC)
        lease_expires_at = now + timedelta(seconds=lease_seconds)
        with self.store.transaction() as conn:
            active = conn.execute(
                "SELECT record_json FROM orbit_cycles WHERE status = 'RUNNING' "
                "AND lease_expires_at > ? ORDER BY updated_sequence LIMIT 1",
                (now.isoformat(),),
            ).fetchone()
            if active:
                return None

            expired = conn.execute(
                "SELECT record_json FROM orbit_cycles WHERE status IN ('RUNNING', 'RETRY') "
                "AND lease_expires_at <= ? ORDER BY updated_sequence LIMIT 1",
                (now.isoformat(),),
            ).fetchone()
            if expired:
                before = json.loads(expired["record_json"])
                if int(before["attempt"]) < 3:
                    after = before | {
                        "status": OrbitCycleStatus.RUNNING.value,
                        "attempt": int(before["attempt"]) + 1,
                        "lease_owner": owner_id,
                        "lease_expires_at": lease_expires_at.isoformat(),
                        "heartbeat_at": now.isoformat(),
                        "error": None,
                        "updated_at": now.isoformat(),
                    }
                    self._update(
                        conn,
                        "orbit_cycles",
                        before,
                        after,
                        "ORBIT_CYCLE_LEASE_RECOVERED",
                        actor_id,
                    )
                    orbit_before = self.knowledge._require(
                        "question_orbits", after["orbit_id"], conn
                    )
                    if orbit_before["status"] != OrbitStatus.ACTIVE.value:
                        orbit_after = orbit_before | {
                            "status": OrbitStatus.ACTIVE.value,
                            "stop_reason": None,
                            "updated_at": now.isoformat(),
                        }
                        self._update(
                            conn,
                            "question_orbits",
                            orbit_before,
                            orbit_after,
                            "QUESTION_ORBIT_ACTIVE",
                            actor_id,
                        )
                    return after
                self._terminalize_expired_cycle(conn, before, actor_id, now)

            row = conn.execute(
                "SELECT record_json FROM question_orbits WHERE status = 'QUEUED' "
                "ORDER BY updated_sequence LIMIT 1"
            ).fetchone()
            if not row:
                return None
            orbit_before = json.loads(row["record_json"])
            frontier_rows = conn.execute(
                "SELECT record_json FROM orbit_frontier WHERE orbit_id = ? AND status = 'OPEN'",
                (orbit_before["orbit_id"],),
            ).fetchall()
            frontier = self._ordered_frontier(
                [json.loads(item["record_json"]) for item in frontier_rows]
            )
            if not frontier:
                orbit_after = orbit_before | {
                    "status": OrbitStatus.BLOCKED.value,
                    "stop_reason": "No open research frontier remains.",
                    "updated_at": now.isoformat(),
                }
                self._update(
                    conn,
                    "question_orbits",
                    orbit_before,
                    orbit_after,
                    "QUESTION_ORBIT_BLOCKED",
                    actor_id,
                )
                self._enqueue_notification_in_transaction(
                    conn,
                    orbit_after,
                    "BLOCKED",
                    {"reason": orbit_after["stop_reason"]},
                    dedupe_suffix="no-frontier",
                    actor_id=actor_id,
                )
                return None

            item_before = frontier[0]
            cycle_number = int(
                conn.execute(
                    "SELECT COUNT(*) AS count FROM orbit_cycles WHERE orbit_id = ?",
                    (orbit_before["orbit_id"],),
                ).fetchone()["count"]
            ) + 1
            cycle = OrbitCycleRecord(
                orbit_id=orbit_before["orbit_id"],
                cycle_key=f"{orbit_before['orbit_id']}:{cycle_number}",
                frontier_item_id=item_before["frontier_item_id"],
                question_id=item_before["question_id"],
                lease_owner=owner_id,
                lease_expires_at=lease_expires_at,
            )
            self._insert(conn, "orbit_cycles", cycle, "ORBIT_CYCLE_STARTED", actor_id)
            item_after = item_before | {
                "status": WorkStatus.IN_PROGRESS.value,
                "updated_at": now.isoformat(),
            }
            self._update(
                conn,
                "orbit_frontier",
                item_before,
                item_after,
                "ORBIT_FRONTIER_ITEM_STARTED",
                actor_id,
            )
            orbit_after = orbit_before | {
                "status": OrbitStatus.ACTIVE.value,
                "stop_reason": None,
                "updated_at": now.isoformat(),
            }
            self._update(
                conn,
                "question_orbits",
                orbit_before,
                orbit_after,
                "QUESTION_ORBIT_ACTIVE",
                actor_id,
            )
            run_before = self.knowledge._require(
                "research_runs", orbit_before["research_run_id"], conn
            )
            run_after = run_before | {
                "status": ResearchRunStatus.ACTIVE.value,
                "current_question_id": item_before["question_id"],
                "stop_reason": None,
                "updated_at": now.isoformat(),
            }
            self._update(
                conn,
                "research_runs",
                run_before,
                run_after,
                "RESEARCH_RUN_CYCLE_STARTED",
                actor_id,
            )
            return json_record(cycle)

    def set_budget(
        self,
        orbit_id: str,
        budget_tier: BudgetTier,
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        """Apply an explicit Orchestrator/user-review budget decision and resume if exhausted."""
        self.knowledge.require_reviewer(actor_id)
        now = datetime.now(UTC)
        with self.store.transaction() as conn:
            orbit_before = self.knowledge._require("question_orbits", orbit_id, conn)
            run_before = self.knowledge._require(
                "research_runs", orbit_before["research_run_id"], conn
            )
            orbit_status = orbit_before["status"]
            run_status = run_before["status"]
            stop_reason = orbit_before.get("stop_reason")
            run_stop_reason = run_before.get("stop_reason")
            if orbit_status == OrbitStatus.BUDGET_EXHAUSTED.value:
                orbit_status = OrbitStatus.QUEUED.value
                run_status = ResearchRunStatus.ACTIVE.value
                stop_reason = None
                run_stop_reason = None
            orbit_after = orbit_before | {
                "budget_tier": budget_tier.value,
                "status": orbit_status,
                "stop_reason": stop_reason,
                "updated_at": now.isoformat(),
            }
            run_after = run_before | {
                "budget_tier": budget_tier.value,
                "status": run_status,
                "stop_reason": run_stop_reason,
                "updated_at": now.isoformat(),
            }
            if orbit_after != orbit_before:
                self._update(
                    conn,
                    "question_orbits",
                    orbit_before,
                    orbit_after,
                    "QUESTION_ORBIT_BUDGET_REVIEWED",
                    actor_id,
                    extra={"budget": self.BUDGETS[budget_tier.value]},
                )
            if run_after != run_before:
                self._update(
                    conn,
                    "research_runs",
                    run_before,
                    run_after,
                    "RESEARCH_RUN_BUDGET_REVIEWED",
                    actor_id,
                )
            return {
                "orbit": orbit_after,
                "research_run": run_after,
                "budget": self.BUDGETS[budget_tier.value],
            }

    def _terminalize_expired_cycle(
        self, conn, cycle_before: dict[str, Any], actor_id: str, now: datetime
    ) -> None:
        cycle_after = cycle_before | {
            "status": OrbitCycleStatus.FAILED.value,
            "error": cycle_before.get("error") or "Cycle lease expired after three attempts.",
            "completed_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        self._update(
            conn,
            "orbit_cycles",
            cycle_before,
            cycle_after,
            "ORBIT_CYCLE_FAILED",
            actor_id,
        )
        orbit_before = self.knowledge._require(
            "question_orbits", cycle_before["orbit_id"], conn
        )
        orbit_after = orbit_before | {
            "status": OrbitStatus.FAILED.value,
            "stop_reason": cycle_after["error"],
            "updated_at": now.isoformat(),
        }
        self._update(
            conn,
            "question_orbits",
            orbit_before,
            orbit_after,
            "QUESTION_ORBIT_FAILED",
            actor_id,
        )
        self._enqueue_notification_in_transaction(
            conn,
            orbit_after,
            "FAILED",
            {"reason": cycle_after["error"]},
            dedupe_suffix=cycle_before["cycle_key"],
            actor_id=actor_id,
        )

    def heartbeat_cycle(
        self,
        orbit_cycle_id: str,
        owner_id: str,
        *,
        actor_id: str = "wisdom-oldman",
        lease_seconds: int = 180,
    ) -> dict[str, Any]:
        self.knowledge.require_writer(actor_id)
        now = datetime.now(UTC)
        with self.store.transaction() as conn:
            before = self.knowledge._require("orbit_cycles", orbit_cycle_id, conn)
            if before["status"] != OrbitCycleStatus.RUNNING.value:
                raise ValueError("Only a running cycle can be heartbeated.")
            if before["lease_owner"] != owner_id:
                raise PermissionError("Cycle lease belongs to another runner.")
            after = before | {
                "heartbeat_at": now.isoformat(),
                "lease_expires_at": (now + timedelta(seconds=lease_seconds)).isoformat(),
                "updated_at": now.isoformat(),
            }
            self._update(
                conn,
                "orbit_cycles",
                before,
                after,
                "ORBIT_CYCLE_HEARTBEAT",
                actor_id,
            )
            return after

    def expand_frontier(
        self,
        orbit_id: str,
        gap_ids: list[str],
        *,
        actor_id: str = "wisdom-oldman",
        priority: FrontierPriority = FrontierPriority.MEDIUM,
    ) -> list[dict[str, Any]]:
        self.knowledge.require_writer(actor_id)
        created: list[dict[str, Any]] = []
        with self.store.transaction() as conn:
            orbit = self.knowledge._require("question_orbits", orbit_id, conn)
            existing_rows = conn.execute(
                "SELECT record_json FROM orbit_frontier WHERE orbit_id = ?", (orbit_id,)
            ).fetchall()
            existing_gap_ids = {
                record.get("gap_id")
                for record in (json.loads(row["record_json"]) for row in existing_rows)
            }
            for gap_id in dict.fromkeys(gap_ids):
                if gap_id in existing_gap_ids:
                    continue
                gap = self.knowledge._require("gaps", gap_id, conn)
                question_id = gap.get("question_id")
                if question_id:
                    self.knowledge._require("questions", question_id, conn)
                else:
                    question = QuestionRecord(
                        text=f"What evidence resolves this gap: {gap['reason']}",
                        why_worth_knowing=gap["why_worthwhile"],
                        parent_question_id=orbit["root_question_id"],
                        orbit_id=orbit_id,
                    )
                    self._insert(conn, "questions", question, "QUESTION_ADDED", actor_id)
                    question_id = question.question_id
                    gap_after = gap | {
                        "question_id": question_id,
                        "orbit_id": orbit_id,
                        "updated_at": datetime.now(UTC).isoformat(),
                    }
                    self._update(
                        conn,
                        "gaps",
                        gap,
                        gap_after,
                        "GAP_ATTACHED_TO_ORBIT",
                        actor_id,
                    )
                item = FrontierItemRecord(
                    orbit_id=orbit_id,
                    question_id=question_id,
                    gap_id=gap_id,
                    priority=priority,
                    relevance=priority,
                    impact=priority,
                    uncertainty=priority,
                    rationale=gap["why_worthwhile"],
                )
                self._insert(
                    conn, "orbit_frontier", item, "ORBIT_FRONTIER_ITEM_ADDED", actor_id
                )
                created.append(json_record(item))
        return created

    def record_discovery_usage(
        self,
        orbit_id: str,
        provider: str,
        *,
        request_count: int = 1,
        query_count: int = 1,
        result_count: int = 0,
        provider_request_id: str | None = None,
        actor_id: str = "wisdom-oldman",
    ) -> dict[str, Any]:
        self.knowledge.require_writer(actor_id)
        self.knowledge._require("question_orbits", orbit_id)
        record = DiscoveryUsageRecord(
            orbit_id=orbit_id,
            provider=provider,
            month=datetime.now(UTC).strftime("%Y-%m"),
            request_count=request_count,
            query_count=query_count,
            result_count=result_count,
            provider_request_id=provider_request_id,
        )
        with self.store.transaction() as conn:
            self._insert(
                conn, "discovery_usage", record, "DISCOVERY_USAGE_RECORDED", actor_id
            )
        return json_record(record)

    def discovery_usage(
        self, *, provider: str | None = None, month: str | None = None, orbit_id: str | None = None
    ) -> dict[str, int]:
        month = month or datetime.now(UTC).strftime("%Y-%m")
        clauses = ["month = ?"]
        values: list[str] = [month]
        if provider:
            clauses.append("provider = ?")
            values.append(provider)
        if orbit_id:
            clauses.append("orbit_id = ?")
            values.append(orbit_id)
        with self.store.connect() as conn:
            rows = conn.execute(
                f"SELECT record_json FROM discovery_usage WHERE {' AND '.join(clauses)}",
                tuple(values),
            ).fetchall()
        records = [json.loads(row["record_json"]) for row in rows]
        return {
            "requests": sum(int(record["request_count"]) for record in records),
            "queries": sum(int(record["query_count"]) for record in records),
            "results": sum(int(record["result_count"]) for record in records),
        }

    def used_source_ids(self, orbit_id: str) -> set[str]:
        self.knowledge._require("question_orbits", orbit_id)
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT record_json FROM orbit_cycles WHERE orbit_id = ? "
                "AND status = 'COMPLETED'",
                (orbit_id,),
            ).fetchall()
        return {
            source_id
            for row in rows
            for source_id in json.loads(row["record_json"]).get("source_ids", [])
        }

    def complete_cycle(
        self,
        orbit_cycle_id: str,
        owner_id: str,
        *,
        satisfaction_level: SatisfactionLevel,
        satisfaction_rationale: str,
        active_seconds: float,
        source_ids: list[str] | None = None,
        evidence_ids: list[str] | None = None,
        generated_question_ids: list[str] | None = None,
        discovery_queries: list[str] | None = None,
        search_queries_used: int = 0,
        model_tokens_used: int = 0,
        kag_watermark: int = 0,
        decision: str = "CONTINUE",
        answer: dict[str, Any] | None = None,
        actor_id: str = "wisdom-oldman",
    ) -> dict[str, Any]:
        self.knowledge.require_writer(actor_id)
        source_ids = list(dict.fromkeys(source_ids or []))
        evidence_ids = list(dict.fromkeys(evidence_ids or []))
        generated_question_ids = list(dict.fromkeys(generated_question_ids or []))
        discovery_queries = list(dict.fromkeys(discovery_queries or []))
        now = datetime.now(UTC)
        with self.store.transaction() as conn:
            cycle_before = self.knowledge._require("orbit_cycles", orbit_cycle_id, conn)
            if cycle_before["status"] != OrbitCycleStatus.RUNNING.value:
                raise ValueError("Only a running cycle can complete.")
            if cycle_before["lease_owner"] != owner_id:
                raise PermissionError("Cycle lease belongs to another runner.")
            orbit_before = self.knowledge._require(
                "question_orbits", cycle_before["orbit_id"], conn
            )
            run_before = self.knowledge._require(
                "research_runs", orbit_before["research_run_id"], conn
            )
            item_before = self.knowledge._require(
                "orbit_frontier", cycle_before["frontier_item_id"], conn
            )
            cycle_after = cycle_before | {
                "status": OrbitCycleStatus.COMPLETED.value,
                "kag_watermark": max(0, kag_watermark),
                "discovery_queries": discovery_queries,
                "source_ids": source_ids,
                "evidence_ids": evidence_ids,
                "generated_question_ids": generated_question_ids,
                "decision": decision,
                "error": None,
                "completed_at": now.isoformat(),
                "lease_expires_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
            self._update(
                conn,
                "orbit_cycles",
                cycle_before,
                cycle_after,
                "ORBIT_CYCLE_COMPLETED",
                actor_id,
            )
            resolved_current = satisfaction_level in {
                SatisfactionLevel.SUFFICIENT,
                SatisfactionLevel.STRONG,
            }
            item_after = item_before | {
                "status": (
                    WorkStatus.FILLED.value if resolved_current else WorkStatus.OPEN.value
                ),
                "updated_at": now.isoformat(),
            }
            self._update(
                conn,
                "orbit_frontier",
                item_before,
                item_after,
                (
                    "ORBIT_FRONTIER_ITEM_FILLED"
                    if resolved_current
                    else "ORBIT_FRONTIER_ITEM_REOPENED"
                ),
                actor_id,
            )
            if resolved_current and item_before.get("gap_id"):
                gap_before = self.knowledge._require("gaps", item_before["gap_id"], conn)
                gap_after = gap_before | {
                    "status": WorkStatus.FILLED.value,
                    "updated_at": now.isoformat(),
                }
                self._update(
                    conn,
                    "gaps",
                    gap_before,
                    gap_after,
                    "GAP_FILLED_BY_ORBIT",
                    actor_id,
                )
            run_after = run_before | {
                "active_seconds": float(run_before.get("active_seconds", 0)) + active_seconds,
                "sources_used": int(run_before.get("sources_used", 0)) + len(source_ids),
                "model_tokens_used": (
                    int(run_before.get("model_tokens_used", 0)) + model_tokens_used
                ),
                "search_queries_used": (
                    int(run_before.get("search_queries_used", 0)) + search_queries_used
                ),
                "cycle_count": int(run_before.get("cycle_count", 0)) + 1,
                "satisfaction_level": satisfaction_level.value,
                "satisfaction_rationale": satisfaction_rationale,
                "updated_at": now.isoformat(),
            }
            budget = self.BUDGETS[orbit_before["budget_tier"]]
            exhausted = (
                run_after["active_seconds"] >= budget["active_seconds"]
                or run_after["sources_used"] >= budget["sources"]
                or run_after["model_tokens_used"] >= budget["model_tokens"]
                or run_after["search_queries_used"] >= budget["search_queries"]
            )
            open_rows = conn.execute(
                "SELECT record_json FROM orbit_frontier WHERE orbit_id = ? AND status = 'OPEN'",
                (orbit_before["orbit_id"],),
            ).fetchall()
            open_frontier = [json.loads(row["record_json"]) for row in open_rows]
            high_open = any(item["priority"] == FrontierPriority.HIGH.value for item in open_frontier)
            satisfied = satisfaction_level in {
                SatisfactionLevel.SUFFICIENT,
                SatisfactionLevel.STRONG,
            } and not high_open
            if satisfied:
                orbit_status = OrbitStatus.COMPLETED
                run_status = ResearchRunStatus.COMPLETED
                stop_reason = "Knowledge satisfaction reached and no HIGH frontier remains."
            elif exhausted:
                orbit_status = OrbitStatus.BUDGET_EXHAUSTED
                run_status = ResearchRunStatus.BUDGET_EXHAUSTED
                stop_reason = "The Orbit reached at least one configured research budget limit."
            elif not open_frontier:
                orbit_status = OrbitStatus.BLOCKED
                run_status = ResearchRunStatus.PAUSED
                stop_reason = "No open research frontier remains while knowledge is still incomplete."
            else:
                orbit_status = OrbitStatus.QUEUED
                run_status = ResearchRunStatus.ACTIVE
                stop_reason = None
            run_after |= {"status": run_status.value, "stop_reason": stop_reason}
            if orbit_status is not OrbitStatus.QUEUED:
                run_after["current_question_id"] = None
            elif open_frontier:
                run_after["current_question_id"] = self._ordered_frontier(open_frontier)[0][
                    "question_id"
                ]
            self._update(
                conn,
                "research_runs",
                run_before,
                run_after,
                "RESEARCH_RUN_CYCLE_RECORDED",
                actor_id,
            )
            orbit_after = orbit_before | {
                "status": orbit_status.value,
                "satisfaction_level": satisfaction_level.value,
                "satisfaction_rationale": satisfaction_rationale,
                "stop_reason": stop_reason,
                "updated_at": now.isoformat(),
            }
            self._update(
                conn,
                "question_orbits",
                orbit_before,
                orbit_after,
                f"QUESTION_ORBIT_{orbit_status.value}",
                actor_id,
            )
            document_version = None
            notification_payload: dict[str, Any] = {
                "reason": stop_reason,
                "satisfaction_level": satisfaction_level.value,
                "research_status": orbit_status.value,
            }
            if orbit_before.get("topic_id") and answer:
                document_version = self.topics.publish_answer(
                    orbit_before["topic_id"],
                    cycle_before["question_id"],
                    answer,
                    actor_id=actor_id,
                    research_status=orbit_status.value,
                    orbit_id=orbit_before["orbit_id"],
                    orbit_cycle_id=cycle_before["orbit_cycle_id"],
                    source_ids=source_ids,
                    evidence_ids=evidence_ids,
                    conn=conn,
                )
                section = next(
                    (
                        item
                        for item in document_version.get("sections", [])
                        if item.get("question_id") == cycle_before["question_id"]
                    ),
                    {},
                )
                notification_payload |= {
                    "topic_title": document_version["topic_title"],
                    "summary": str(section.get("body") or "")[:2000],
                    "change_summary": document_version["change_summary"],
                    "document_url": document_version["document_url"],
                    "sources": section.get("citations", [])[:8],
                    "remaining_questions": [
                        self.knowledge._require("gaps", item["gap_id"], conn)["reason"]
                        for item in self._ordered_frontier(open_frontier)[:8]
                        if item.get("gap_id")
                    ],
                }
            if source_ids and int(run_before.get("cycle_count", 0)) == 0:
                self._enqueue_notification_in_transaction(
                    conn,
                    orbit_after,
                    "FIRST_USEFUL_ANSWER",
                    notification_payload,
                    dedupe_suffix="first-answer",
                    actor_id=actor_id,
                )
            if orbit_status is not OrbitStatus.QUEUED:
                self._enqueue_notification_in_transaction(
                    conn,
                    orbit_after,
                    orbit_status.value,
                    notification_payload,
                    dedupe_suffix=cycle_before["cycle_key"],
                    actor_id=actor_id,
                )
            return {
                "cycle": cycle_after,
                "orbit": orbit_after,
                "research_run": run_after,
                "document_version": document_version,
            }

    def fail_cycle(
        self,
        orbit_cycle_id: str,
        owner_id: str,
        error: str,
        *,
        recoverable: bool = True,
        blocked: bool = False,
        retry_after_seconds: int = 30,
        actor_id: str = "wisdom-oldman",
    ) -> dict[str, Any]:
        self.knowledge.require_writer(actor_id)
        now = datetime.now(UTC)
        error = error[:8000]
        with self.store.transaction() as conn:
            cycle_before = self.knowledge._require("orbit_cycles", orbit_cycle_id, conn)
            if cycle_before["status"] != OrbitCycleStatus.RUNNING.value:
                orbit = self.knowledge._require(
                    "question_orbits", cycle_before["orbit_id"], conn
                )
                if orbit["status"] in {OrbitStatus.PAUSED.value, OrbitStatus.STOPPED.value}:
                    return {"cycle": cycle_before, "orbit": orbit, "retry": False}
                raise ValueError("Only a running cycle can fail.")
            if cycle_before["lease_owner"] != owner_id:
                raise PermissionError("Cycle lease belongs to another runner.")
            retry = recoverable and not blocked and int(cycle_before["attempt"]) < 3
            cycle_status = OrbitCycleStatus.RETRY if retry else (
                OrbitCycleStatus.BLOCKED if blocked else OrbitCycleStatus.FAILED
            )
            cycle_after = cycle_before | {
                "status": cycle_status.value,
                "error": error,
                "lease_expires_at": (
                    now + timedelta(seconds=max(1, min(retry_after_seconds, 86_400)))
                    if retry else now
                ).isoformat(),
                "completed_at": None if retry else now.isoformat(),
                "updated_at": now.isoformat(),
            }
            self._update(
                conn,
                "orbit_cycles",
                cycle_before,
                cycle_after,
                f"ORBIT_CYCLE_{cycle_status.value}",
                actor_id,
            )
            orbit_before = self.knowledge._require(
                "question_orbits", cycle_before["orbit_id"], conn
            )
            orbit_status = OrbitStatus.ACTIVE if retry else (
                OrbitStatus.BLOCKED if blocked else OrbitStatus.FAILED
            )
            orbit_after = orbit_before | {
                "status": orbit_status.value,
                "stop_reason": None if retry else error,
                "updated_at": now.isoformat(),
            }
            self._update(
                conn,
                "question_orbits",
                orbit_before,
                orbit_after,
                f"QUESTION_ORBIT_{orbit_status.value}",
                actor_id,
            )
            if not retry:
                item_before = self.knowledge._require(
                    "orbit_frontier", cycle_before["frontier_item_id"], conn
                )
                item_after = item_before | {
                    "status": WorkStatus.OPEN.value,
                    "updated_at": now.isoformat(),
                }
                self._update(
                    conn,
                    "orbit_frontier",
                    item_before,
                    item_after,
                    "ORBIT_FRONTIER_ITEM_RELEASED",
                    actor_id,
                )
                self._enqueue_notification_in_transaction(
                    conn,
                    orbit_after,
                    orbit_status.value,
                    {"reason": error},
                    dedupe_suffix=cycle_before["cycle_key"],
                    actor_id=actor_id,
                )
            return {"cycle": cycle_after, "orbit": orbit_after, "retry": retry}

    def _enqueue_notification_in_transaction(
        self,
        conn,
        orbit: dict[str, Any],
        event_type: str,
        payload: dict[str, Any],
        *,
        dedupe_suffix: str,
        actor_id: str,
    ) -> dict[str, Any] | None:
        route = orbit.get("notification_route") or {}
        if not route:
            return None
        dedupe_key = f"{orbit['orbit_id']}:{event_type}:{dedupe_suffix}"
        existing = conn.execute(
            "SELECT record_json FROM orbit_notifications WHERE dedupe_key = ?", (dedupe_key,)
        ).fetchone()
        if existing:
            return json.loads(existing["record_json"])
        notification = OrbitNotificationRecord(
            orbit_id=orbit["orbit_id"],
            event_type=event_type,
            dedupe_key=dedupe_key,
            route=route,
            payload=payload,
        )
        self._insert(
            conn,
            "orbit_notifications",
            notification,
            "ORBIT_NOTIFICATION_QUEUED",
            actor_id,
        )
        return json_record(notification)

    def enqueue_notification(
        self,
        orbit_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        dedupe_suffix: str,
        actor_id: str = "orchestrator",
    ) -> dict[str, Any] | None:
        self.knowledge.require_writer(actor_id)
        with self.store.transaction() as conn:
            orbit = self.knowledge._require("question_orbits", orbit_id, conn)
            return self._enqueue_notification_in_transaction(
                conn,
                orbit,
                event_type,
                payload,
                dedupe_suffix=dedupe_suffix,
                actor_id=actor_id,
            )

    def claim_notification(
        self, *, actor_id: str = "orchestrator"
    ) -> dict[str, Any] | None:
        self.knowledge.require_writer(actor_id)
        now = datetime.now(UTC)
        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT record_json FROM orbit_notifications "
                "WHERE status IN ('PENDING', 'FAILED', 'SENDING') AND available_at <= ? "
                "AND json_extract(record_json, '$.attempts') < 3 "
                "ORDER BY updated_sequence LIMIT 1",
                (now.isoformat(),),
            ).fetchone()
            if not row:
                return None
            before = json.loads(row["record_json"])
            after = before | {
                "status": OrbitNotificationStatus.SENDING.value,
                "attempts": int(before["attempts"]) + 1,
                "available_at": (now + timedelta(minutes=5)).isoformat(),
                "updated_at": now.isoformat(),
            }
            self._update(
                conn,
                "orbit_notifications",
                before,
                after,
                "ORBIT_NOTIFICATION_CLAIMED",
                actor_id,
            )
            return after

    def finish_notification(
        self,
        orbit_notification_id: str,
        *,
        sent: bool,
        error: str | None = None,
        actor_id: str = "orchestrator",
    ) -> dict[str, Any]:
        self.knowledge.require_writer(actor_id)
        now = datetime.now(UTC)
        with self.store.transaction() as conn:
            before = self.knowledge._require(
                "orbit_notifications", orbit_notification_id, conn
            )
            attempts = int(before["attempts"])
            status = OrbitNotificationStatus.SENT if sent else OrbitNotificationStatus.FAILED
            delay_minutes = min(30, 2 ** max(0, attempts - 1))
            after = before | {
                "status": status.value,
                "sent_at": now.isoformat() if sent else None,
                "last_error": None if sent else (error or "Notification delivery failed.")[:8000],
                "available_at": (
                    now if sent else now + timedelta(minutes=delay_minutes)
                ).isoformat(),
                "updated_at": now.isoformat(),
            }
            self._update(
                conn,
                "orbit_notifications",
                before,
                after,
                f"ORBIT_NOTIFICATION_{status.value}",
                actor_id,
            )
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
        topic_id: str | None = None,
        question_id: str | None = None,
    ) -> dict[str, Any]:
        level = SatisfactionLevel(answer["satisfaction_level"])
        gap_ids = list(answer.get("remaining_gap_ids") or [])
        eligible = (
            is_investigative(question)
            and level in {SatisfactionLevel.INSUFFICIENT, SatisfactionLevel.PROVISIONAL}
        )
        if eligible and not gap_ids:
            existing_gap = None
            if question_id:
                with self.store.connect() as conn:
                    row = conn.execute(
                        "SELECT record_json FROM gaps WHERE status = 'OPEN' "
                        "AND json_extract(record_json, '$.question_id') = ? "
                        "ORDER BY updated_sequence DESC LIMIT 1",
                        (question_id,),
                    ).fetchone()
                    existing_gap = json.loads(row["record_json"]) if row else None
            if existing_gap:
                gap_ids.append(existing_gap["gap_id"])
            else:
                gap = self.knowledge.add_gap(
                    GapRecord(
                        gap_type=GapType.HUMAN_REQUEST,
                        reason=f"A complete, sourced treatment is still needed for: {question}",
                        why_worthwhile=(
                            "The user asked Wisdom-Oldman to build durable, reusable knowledge "
                            "rather than provide an unsupported one-off answer."
                        ),
                        question_id=question_id,
                        current_knowledge=str(answer.get("answer") or "")[:16000] or None,
                    ),
                    actor_id=actor_id,
                )
                gap_ids.append(gap["gap_id"])
        result: dict[str, Any] = {"answer": answer, "orbit_started": False}
        if eligible:
            started = self.start(
                question,
                f"Resolve the worthwhile evidence gaps for: {question}",
                level,
                answer["satisfaction_rationale"],
                actor_id=actor_id,
                gap_ids=gap_ids,
                budget_tier=self.automatic_budget_tier,
                uuma_task_id=uuma_task_id,
                uuma_run_id=uuma_run_id,
                notification_route=notification_route,
                topic_id=topic_id,
                root_question_id=question_id,
                policy_authorized=True,
            )
            result |= {
                "orbit_started": started["created"],
                "orbit_reused": started["reused"],
                "orbit_id": started["orbit"]["orbit_id"],
                "orbit_status": started["orbit"]["status"],
                "budget_tier": started["orbit"]["budget_tier"],
            }
        return result
