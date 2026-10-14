from __future__ import annotations

import argparse
import json
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..settings import Settings
from .graph_client import GraphExecutionClient
from .service import HoncService
from .store import HoncStore

mcp = FastMCP("honc-execution")

_OVERRIDE_SERVICE: HoncService | None = None


def set_service(service: HoncService | None) -> None:
    """Inject a test or mock service for testing purposes."""
    global _OVERRIDE_SERVICE
    _OVERRIDE_SERVICE = service


@lru_cache(maxsize=1)
def _default_service() -> HoncService:
    settings = Settings.from_env()
    store = HoncStore(settings.honc_database_path())
    graph_url = os.environ.get("YONC_GRAPH_URL", "http://localhost:8000")
    graph_db_id = os.environ.get("YONC_GRAPH_DATABASE_ID")
    graph_client = GraphExecutionClient(base_url=graph_url, database_id=graph_db_id)
    return HoncService(store=store, graph_client=graph_client)


def _get_service() -> HoncService:
    if _OVERRIDE_SERVICE is not None:
        return _OVERRIDE_SERVICE
    return _default_service()


@mcp.tool()
def honc_status(user_id: str = "default_user") -> dict[str, Any]:
    """Return the active round, datasource identity, connection state, and pending items."""
    return _get_service().get_status(user_id=user_id)


@mcp.tool()
def honc_get_context(task_id: str = "", user_id: str = "default_user") -> dict[str, Any]:
    """Read accepted task snapshot, done_when criteria, recent events, and active Next."""
    tid = task_id.strip() or None
    return _get_service().get_context(task_id=tid, user_id=user_id)


@mcp.tool()
def honc_record_execution(
    raw_content: str,
    user_id: str = "default_user",
    entrypoint: str = "hermes_local",
    task_id: str = "",
    round_id: str = "",
    habit_id: str = "",
    outcome: str = "",
    next_step: str = "",
    blocker: str = "",
    state: str = "",
    actual_kind: str = "unknown",
    actual_duration_seconds: int | None = None,
    occurred_at: str = "",
) -> dict[str, Any]:
    """Record execution facts, progress, outcome, next, blocker, or backfill."""
    return _get_service().record_execution(
        raw_content=raw_content,
        user_id=user_id,
        entrypoint=entrypoint,
        task_id=task_id.strip() or None,
        round_id=round_id.strip() or None,
        habit_id=habit_id.strip() or None,
        outcome=outcome.strip() or None,
        next_step=next_step.strip() or None,
        blocker=blocker.strip() or None,
        state=state.strip() or None,
        actual_kind=actual_kind,
        actual_duration_seconds=actual_duration_seconds,
        occurred_at=occurred_at.strip() or None,
    )


@mcp.tool()
def honc_control_round(
    action: str,
    user_id: str = "default_user",
    round_id: str = "",
    task_id: str = "",
    target_outcome: str = "",
    tiny_step: str = "",
    mode: str = "Focus",
    timer_budget_minutes: int = 25,
    interruption_reason: str = "",
    outcome: str = "",
) -> dict[str, Any]:
    """Control round lifecycle: prepare, start, pause, resume, end, cancel."""
    return _get_service().control_round(
        action=action,
        user_id=user_id,
        round_id=round_id.strip() or None,
        task_id=task_id.strip() or None,
        target_outcome=target_outcome,
        tiny_step=tiny_step,
        mode=mode,
        timer_budget_minutes=timer_budget_minutes,
        interruption_reason=interruption_reason.strip() or None,
        outcome=outcome.strip() or None,
    )


@mcp.tool()
def honc_check_habit(
    habit_id: str,
    quantity: float = 1.0,
    user_report: str = "",
    user_id: str = "default_user",
    occurred_at: str = "",
) -> dict[str, Any]:
    """Record a single habit tick occurrence, quantity, or user report."""
    return _get_service().check_habit(
        habit_id=habit_id,
        user_id=user_id,
        quantity=quantity,
        user_report=user_report,
        occurred_at=occurred_at.strip() or None,
    )


@mcp.tool()
def honc_assess_completion(
    task_id: str,
    evidence: str,
    criteria_override: str = "",
    trusted_input_id: str = "",
) -> dict[str, Any]:
    """Assess whether execution evidence satisfies task done_when criteria."""
    return _get_service().assess_completion(
        task_id=task_id,
        evidence=evidence,
        criteria_override=criteria_override.strip() or None,
        trusted_input_id=trusted_input_id.strip() or None,
    )


@mcp.tool()
def honc_apply_completion(
    task_id: str,
    trusted_input_id: str,
    user_id: str = "default_user",
    operation_id: str = "",
    assessment_id: str = "",
) -> dict[str, Any]:
    """Submit a verified user completion decision to Yonc Graph with execution receipt."""
    return _get_service().apply_completion(
        task_id=task_id,
        trusted_input_id=trusted_input_id,
        user_id=user_id,
        operation_id=operation_id.strip() or None,
        assessment_id=assessment_id.strip() or None,
    )


@mcp.tool()
def honc_correct_record(
    original_event_id: str,
    reason: str,
    user_id: str = "default_user",
    corrected_outcome: str = "",
    compensating_action: str = "",
) -> dict[str, Any]:
    """Append an immutable correction event and queue compensating action if needed."""
    return _get_service().correct_record(
        original_event_id=original_event_id,
        reason=reason,
        user_id=user_id,
        corrected_outcome=corrected_outcome.strip() or None,
        compensating_action=compensating_action.strip() or None,
    )


@mcp.tool()
def honc_get_report(
    date_str: str = "",
    user_id: str = "default_user",
    timezone_name: str = "Asia/Kuala_Lumpur",
) -> dict[str, Any]:
    """Query daily or weekly summary of Done, Next, Blocker, durations, and pending items."""
    return _get_service().get_report(
        date_str=date_str.strip() or None,
        user_id=user_id,
        timezone_name=timezone_name,
    )


@mcp.tool()
def honc_reconcile_updates() -> dict[str, Any]:
    """Check pending outbox operations and reconcile without inventing new events."""
    return _get_service().reconcile_updates()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="honc execution and scoped life tools")
    parser.add_argument("--life-config", type=Path)
    args = parser.parse_args(argv or [])
    if args.life_config:
        from .life_context import LifeContextBroker
        from .life_mcp import register_life_tools

        broker = LifeContextBroker(json.loads(args.life_config.read_text(encoding="utf-8")))
        register_life_tools(mcp, lambda: broker.service(None), context_provider=broker.service)
    mcp.run()


if __name__ == "__main__":
    main(sys.argv[1:])
