from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import Any, ClassVar
from uuid import uuid4


def canonical_json(value: Any) -> str:
    """Deterministic JSON serialization."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_digest(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def get_timezone(timezone_name: str = "Asia/Kuala_Lumpur") -> tzinfo:
    """Resolve timezone, providing standard fallbacks for Windows without tzdata."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(timezone_name)
    except (ImportError, LookupError, OSError, ValueError):
        if timezone_name in (
            "Asia/Kuala_Lumpur",
            "Asia/Singapore",
            "Asia/Shanghai",
            "Asia/Hong_Kong",
            "UTC+8",
        ):
            return timezone(timedelta(hours=8), name=timezone_name)
        elif timezone_name in ("UTC", "Etc/UTC"):
            return UTC
        return UTC


class RoundStatus:
    PREPARED = "PREPARED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    AWAITING_CHECK = "AWAITING_CHECK"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"

    ACTIVE_STATUSES: ClassVar[set[str]] = {PREPARED, RUNNING, PAUSED, AWAITING_CHECK}


class ActualKind:
    TIMED = "timed"
    USER_REPORTED = "user_reported"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


class EventType:
    PROGRESS = "progress"
    OUTCOME = "outcome"
    STATE_CHANGE = "state_change"
    BACKFILL = "backfill"
    HABIT_TICK = "habit_tick"
    CORRECTION = "correction"
    NOTE = "note"


class AssessmentResult:
    SATISFIED = "SATISFIED"
    INSUFFICIENT = "INSUFFICIENT"
    UNKNOWN = "UNKNOWN"
    BLOCKED = "BLOCKED"


class AssessmentGranularity:
    ROUND = "round"
    TASK = "task"
    MILESTONE = "milestone"


class OutboxStatus:
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCEEDED = "SUCCEEDED"
    CONFLICT = "CONFLICT"
    FAILED = "FAILED"
    NEEDS_HUMAN = "NEEDS_HUMAN"


class TargetSystem:
    GRAPH = "graph"
    NOTION = "notion"


@dataclass
class TrustedInput:
    input_id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str = "default_user"
    entrypoint: str = "hermes_local"  # hermes_local, telegram, direct_call
    profile: str = "honc"
    session_id: str | None = None
    source_receipt_id: str | None = None
    raw_content: str = ""
    received_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    source_digest: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_digest:
            material = {
                "entrypoint": self.entrypoint,
                "user_id": self.user_id,
                "source_receipt_id": self.source_receipt_id or "",
                "raw_content": self.raw_content,
            }
            self.source_digest = compute_digest(material)


@dataclass
class TaskSnapshot:
    snapshot_id: str = field(default_factory=lambda: str(uuid4()))
    graph_database_id: str = ""
    node_id: str = ""
    portfolio_role: str | None = None  # MAIN, SUPPORT, PARKED, None
    graph_version: int = 1
    task_status: str = "TODO"
    title: str = ""
    done_when: str | None = None
    snapshot_digest: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        if not self.snapshot_digest:
            material = {
                "graph_database_id": self.graph_database_id,
                "node_id": self.node_id,
                "graph_version": self.graph_version,
                "task_status": self.task_status,
                "title": self.title,
                "done_when": self.done_when or "",
            }
            self.snapshot_digest = compute_digest(material)


@dataclass
class Round:
    round_id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str = "default_user"
    task_id: str | None = None
    target_outcome: str = ""  # 果象
    tiny_step: str = ""  # 小笨事
    mode: str = "Focus"  # Focus, Gap, etc.
    timer_budget_minutes: int = 25
    criteria_snapshot: str | None = None  # Done 标准快照
    status: str = RoundStatus.PREPARED
    revision: int = 1
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    closed_at: str | None = None


@dataclass
class RoundSegment:
    segment_id: str = field(default_factory=lambda: str(uuid4()))
    round_id: str = ""
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    ended_at: str | None = None
    interruption_reason: str | None = None
    time_source: str = "timer"  # timer, user_reported, estimated
    duration_seconds: int | None = None


@dataclass
class ExecutionEvent:
    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = EventType.PROGRESS
    occurred_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    recorded_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    timezone: str = "Asia/Kuala_Lumpur"
    trusted_input_id: str | None = None
    task_id: str | None = None
    round_id: str | None = None
    habit_id: str | None = None
    outcome: str | None = None  # 成果
    next_step: str | None = None  # Next
    blocker: str | None = None  # Blocker / 坑
    state: str | None = None  # State (energy, location, etc.)
    actual_kind: str = ActualKind.UNKNOWN
    actual_duration_seconds: int | None = None
    correction_ref_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class HabitDefinition:
    habit_id: str = ""
    name: str = ""
    field_type: str = "boolean"  # boolean, number
    unit: str | None = None
    daily_target: float = 1.0
    max_per_day: int = 10
    description: str = ""


@dataclass
class CompletionAssessment:
    assessment_id: str = field(default_factory=lambda: str(uuid4()))
    granularity: str = AssessmentGranularity.TASK
    task_id: str = ""
    criteria_snapshot: str = ""
    satisfied_items: list[str] = field(default_factory=list)
    missing_items: list[str] = field(default_factory=list)
    evidence: str = ""
    trusted_input_id: str | None = None
    result: str = AssessmentResult.UNKNOWN
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class OutboxItem:
    outbox_id: str = field(default_factory=lambda: str(uuid4()))
    target_system: str = TargetSystem.GRAPH
    operation_id: str = ""
    content_digest: str = ""
    preceding_version: int | None = None
    status: str = OutboxStatus.PENDING
    retry_count: int = 0
    lease_expires_at: str | None = None
    last_error: str | None = None
    receipt_json: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class ProjectionBinding:
    binding_id: str = field(default_factory=lambda: str(uuid4()))
    scope_type: str = "round"  # daily_journal, round, task
    scope_id: str = ""
    target_type: str = "notion_block"  # notion_page, notion_block
    target_id: str = ""
    remote_digest: str | None = None
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class DailyReport:
    date: str  # YYYY-MM-DD
    user_id: str
    done_items: list[dict[str, Any]] = field(default_factory=list)
    next_items: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    total_active_seconds: int = 0
    timed_seconds: int = 0
    reported_seconds: int = 0
    estimated_seconds: int = 0
    rounds_count: int = 0
    habits_summary: list[dict[str, Any]] = field(default_factory=list)
    pending_outbox_count: int = 0
    unlinked_events_count: int = 0
