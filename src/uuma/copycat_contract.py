from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from .models import RiskLevel, StrictModel, utc_now


class CopyCatActionHealth(str, Enum):
    VALID = "VALID"
    DEGRADED = "DEGRADED"
    BROKEN = "BROKEN"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    DISABLED = "DISABLED"


class CopyCatExecutionStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED_FOR_HUMAN = "PAUSED_FOR_HUMAN"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    NEEDS_HUMAN = "NEEDS_HUMAN"


class CopyCatParameter(StrictModel):
    name: str
    value_type: str
    required: bool = True
    description: str
    default: Any | None = None


class CopyCatAction(StrictModel):
    action_id: str
    name: str
    description: str
    version: str
    health: CopyCatActionHealth
    risk_level: RiskLevel
    parameters: list[CopyCatParameter] = Field(default_factory=list)
    reviewed: bool
    replay_enabled: bool
    last_success_at: datetime | None = None
    recent_failures: int = Field(default=0, ge=0)
    contract_hash: str


class CopyCatExecution(StrictModel):
    execution_id: str
    action_id: str
    action_version: str
    status: CopyCatExecutionStatus
    current_step: int = Field(default=0, ge=0)
    total_steps: int | None = Field(default=None, ge=0)
    message: str | None = None
    output_refs: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_detail: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CopyCatClient(ABC):
    @abstractmethod
    def list_actions(self) -> list[CopyCatAction]: ...

    @abstractmethod
    def search_actions(self, query: str) -> list[CopyCatAction]: ...

    @abstractmethod
    def get_action(self, action_id: str) -> CopyCatAction: ...

    @abstractmethod
    def execute_action(
        self,
        action_id: str,
        parameters: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> CopyCatExecution: ...

    @abstractmethod
    def get_execution(self, execution_id: str) -> CopyCatExecution: ...

    @abstractmethod
    def cancel_execution(self, execution_id: str) -> CopyCatExecution: ...


class UnavailableCopyCatClient(CopyCatClient):
    """V1 boundary until the independent CopyCat project is deployed."""

    ERROR = "CopyCat MCP is not configured. The UuMA contract is present, but replay is disabled."

    def list_actions(self) -> list[CopyCatAction]:
        return []

    def search_actions(self, query: str) -> list[CopyCatAction]:
        return []

    def get_action(self, action_id: str) -> CopyCatAction:
        raise RuntimeError(self.ERROR)

    def execute_action(
        self,
        action_id: str,
        parameters: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> CopyCatExecution:
        raise RuntimeError(self.ERROR)

    def get_execution(self, execution_id: str) -> CopyCatExecution:
        raise RuntimeError(self.ERROR)

    def cancel_execution(self, execution_id: str) -> CopyCatExecution:
        raise RuntimeError(self.ERROR)

