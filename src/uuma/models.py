from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RiskLevel(str, Enum):
    READ_ONLY = "READ_ONLY"
    REVERSIBLE = "REVERSIBLE"
    COMMITTING = "COMMITTING"
    PROHIBITED = "PROHIBITED"

    @property
    def rank(self) -> int:
        return {
            RiskLevel.READ_ONLY: 0,
            RiskLevel.REVERSIBLE: 1,
            RiskLevel.COMMITTING: 2,
            RiskLevel.PROHIBITED: 3,
        }[self]


class ExecutionClass(str, Enum):
    INTERACTIVE = "INTERACTIVE"
    BACKGROUND = "BACKGROUND"
    SCHEDULED = "SCHEDULED"
    CONTINUOUS = "CONTINUOUS"


class TaskStatus(str, Enum):
    PROPOSED = "PROPOSED"
    TODO = "TODO"
    READY = "READY"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    REVIEW = "REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"
    REVIEW = "REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"


class ResultOutcome(str, Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    CANCELLED = "CANCELLED"


class OperationKind(str, Enum):
    UPSERT_NODE = "UPSERT_NODE"
    UPSERT_EDGE = "UPSERT_EDGE"
    SPLIT_TASK = "SPLIT_TASK"
    LINK_DEPENDENCY = "LINK_DEPENDENCY"
    CORRECT = "CORRECT"
    SUPERSEDE = "SUPERSEDE"
    REVERSE = "REVERSE"


class AgentDefinition(StrictModel):
    agent_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    display_name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    capabilities: set[str] = Field(default_factory=set)
    tools: set[str] = Field(default_factory=set)
    maximum_risk: RiskLevel = RiskLevel.REVERSIBLE
    can_control_computer: bool = False
    can_use_copycat: bool = False
    can_coordinate_agents: bool = False
    enabled: bool = True


class TaskContract(StrictModel):
    task_id: str = Field(default_factory=lambda: new_id("task"))
    title: str = Field(min_length=1, max_length=240)
    objective: str = Field(min_length=1, max_length=8000)
    requested_by: str = "user"
    source: Literal["orchestrator", "direct", "scheduled", "system"] = "orchestrator"
    required_capabilities: set[str] = Field(default_factory=set)
    required_tools: set[str] = Field(default_factory=set)
    risk_level: RiskLevel = RiskLevel.READ_ONLY
    execution_class: ExecutionClass = ExecutionClass.INTERACTIVE
    input_refs: list[str] = Field(default_factory=list)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    acceptance_checks: list[str] = Field(default_factory=list)
    external_project_ref: str | None = None
    external_task_ref: str | None = None
    idempotency_key: str | None = None
    user_visible_structure_change: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class GraphOperation(StrictModel):
    operation_id: str = Field(default_factory=lambda: new_id("op"))
    kind: OperationKind
    target_type: str
    target_id: str
    expected_revision: int | None = Field(default=None, ge=0)
    changes: dict[str, Any]
    rationale: str = Field(min_length=1, max_length=8000)
    requested_by: str
    requires_user_approval: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class RouteDecision(StrictModel):
    task_id: str
    selected_agent: str | None
    candidates: list[str] = Field(default_factory=list)
    denied: bool = False
    requires_orchestrator: bool = False
    rationale: list[str] = Field(default_factory=list)


class RunRegistration(StrictModel):
    run_id: str = Field(default_factory=lambda: new_id("run"))
    task_id: str
    agent_id: str
    execution_class: ExecutionClass
    source: Literal["orchestrator", "direct", "kanban", "scheduled"]
    external_run_ref: str | None = None
    started_at: datetime = Field(default_factory=utc_now)


class RunProgress(StrictModel):
    run_id: str
    task_id: str
    agent_id: str
    status: RunStatus = RunStatus.RUNNING
    completed_steps: int = Field(default=0, ge=0)
    total_steps: int | None = Field(default=None, ge=0)
    current_step: str | None = Field(default=None, max_length=1000)
    last_heartbeat: datetime = Field(default_factory=utc_now)
    blocker: str | None = Field(default=None, max_length=4000)
    attempt: int = Field(default=1, ge=1, le=3)
    elapsed_seconds: float = Field(default=0, ge=0)
    artifact_refs: list[str] = Field(default_factory=list)
    eta_seconds: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def completed_steps_fit_total(self) -> RunProgress:
        if self.total_steps is not None and self.completed_steps > self.total_steps:
            raise ValueError("completed_steps cannot exceed total_steps")
        return self


class CheckResult(StrictModel):
    name: str
    passed: bool
    detail: str | None = None


class ResultContract(StrictModel):
    run_id: str
    task_id: str
    agent_id: str
    outcome: ResultOutcome
    summary: str = Field(min_length=1, max_length=16000)
    artifact_refs: list[str] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)
    structured_rationale: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    error: str | None = None
    partial_state: dict[str, Any] = Field(default_factory=dict)
    completed_at: datetime = Field(default_factory=utc_now)


class ArtifactRecord(StrictModel):
    artifact_id: str = Field(default_factory=lambda: new_id("artifact"))
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    media_type: str
    size_bytes: int = Field(ge=0)
    logical_name: str
    local_path: str
    created_by: str
    task_id: str | None = None
    run_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class EventEnvelope(StrictModel):
    sequence: int
    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    actor_type: str
    actor_id: str
    occurred_at: datetime
    correlation_id: str | None = None
    causation_id: str | None = None
    payload: dict[str, Any]
    metadata: dict[str, Any]
    previous_hash: str
    event_hash: str

