"""Domain models for UuMA All-in-One Observatory."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class SourceFreshness(StrictModel):
    source_name: str
    is_available: bool
    last_checked: str = Field(default_factory=utc_now_iso)
    last_event_at: str | None = None
    error_message: str | None = None


class ObservatoryItem(StrictModel):
    """Normalized envelope for any agent domain artifact."""
    agent_id: str
    item_id: str
    title: str
    kind: str
    status: str
    health: str = "HEALTHY"  # HEALTHY, WARNING, BLOCKED, UNKNOWN
    updated_at: str | None = Field(default_factory=utc_now_iso)
    summary: str = ""
    source_ref: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class ActivityEvent(StrictModel):
    """Standardized event envelope from audit spool and execution records."""
    event_id: str
    agent_id: str
    hook: str = "activity"
    captured_at: str
    tool_name: str | None = None
    summary: str = ""
    source_path: str = ""
    raw_snippet: str = ""


class SessionMessage(StrictModel):
    message_id: str
    role: str
    content: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    timestamp: str | None = None


class SessionRecord(StrictModel):
    session_id: str
    agent_id: str
    title: str = ""
    started_at: str | None = None
    message_count: int = 0
    messages: list[SessionMessage] = Field(default_factory=list)


class BackfillProgress(StrictModel):
    total_files: int = 0
    indexed_files: int = 0
    is_complete: bool = False
    current_file: str | None = None
    percent: float = 0.0


class AgentWorkspace(StrictModel):
    agent_id: str
    name: str
    role: str
    source_name: str
    status: str = "IDLE"  # RUNNING, IDLE, WAITING, BLOCKED, UNKNOWN
    health: str = "HEALTHY"
    items: list[ObservatoryItem] = Field(default_factory=list)
    total_items: int = 0


class FleetOverview(StrictModel):
    total_agents: int = 7
    running_count: int = 0
    idle_count: int = 0
    blocked_count: int = 0
    agents: list[AgentWorkspace] = Field(default_factory=list)
    backfill: BackfillProgress = Field(default_factory=BackfillProgress)
    sources: dict[str, SourceFreshness] = Field(default_factory=dict)
