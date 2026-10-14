from __future__ import annotations

from .conversation import (
    CandidateResolution,
    ConversationResult,
    HoncConversationEngine,
    InputOrigin,
    ValidationResult,
)
from .graph_client import GraphExecutionClient
from .models import (
    ActualKind,
    AssessmentGranularity,
    AssessmentResult,
    CompletionAssessment,
    DailyReport,
    EventType,
    ExecutionEvent,
    HabitDefinition,
    OutboxItem,
    OutboxStatus,
    ProjectionBinding,
    Round,
    RoundSegment,
    RoundStatus,
    TargetSystem,
    TaskSnapshot,
    TrustedInput,
)
from .service import HoncService
from .store import HoncStore


def __getattr__(name: str):
    if name == "mcp":
        # Hermes plugins consume the ledger with their own MCP SDK. Only the
        # separately launched UuMA server needs FastMCP's server implementation.
        from .mcp import mcp

        return mcp
    raise AttributeError(name)


__all__ = [
    "ActualKind",
    "AssessmentGranularity",
    "AssessmentResult",
    "CandidateResolution",
    "CompletionAssessment",
    "ConversationResult",
    "DailyReport",
    "EventType",
    "ExecutionEvent",
    "GraphExecutionClient",
    "HabitDefinition",
    "HoncConversationEngine",
    "HoncService",
    "HoncStore",
    "InputOrigin",
    "OutboxItem",
    "OutboxStatus",
    "ProjectionBinding",
    "Round",
    "RoundSegment",
    "RoundStatus",
    "TargetSystem",
    "TaskSnapshot",
    "TrustedInput",
    "ValidationResult",
    "mcp",
]
