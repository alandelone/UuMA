"""Librarian-only remote worker MCP; domain mutations remain with their owners."""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from uuma.control_client import ControlClient
from uuma.models import ResultContract, RunProgress, TaskContract

mcp = FastMCP("uuma-librarian-worker")


def client() -> ControlClient:
    """Require the actual scoped identity and remote authority, with no local fallback."""
    if os.environ.get("UUMA_AGENT_ID") != "librarian":
        raise PermissionError("This worker requires the Librarian identity")
    return ControlClient.from_env()


@mcp.tool()
def worker_intake_status() -> dict[str, Any]:
    """Read whether the control authority currently accepts Librarian work."""
    return client().request("GET", "/worker/intake")


@mcp.tool()
def register_direct_run(contract_json: str, external_run_ref: str = "") -> dict[str, Any]:
    """Register a read-only retrieval requested in the current conversation."""
    control = client()
    task = TaskContract.model_validate_json(contract_json)
    if task.risk_level.value != "READ_ONLY" or task.user_visible_structure_change:
        raise PermissionError("Librarian only accepts read-only retrieval work")
    return control.register_direct_run(
        "librarian", task, external_run_ref=external_run_ref or None,
    ).model_dump(mode="json")


@mcp.tool()
def get_assignment(
    task_id: str, run_id: str | None = None, execution_epoch: int | None = None,
) -> dict[str, Any]:
    """Read an owned task and validate the current assigned execution when supplied."""
    control = client()
    task = control.require_task(task_id)
    if task["assignee"] != "librarian":
        raise PermissionError("Task belongs to another agent")
    if run_id is not None or execution_epoch is not None:
        if not run_id or execution_epoch is None:
            raise PermissionError("Both run and execution epoch are required")
        run = control.require_run(run_id)
        if (
            task.get("current_run_id") != run_id or run["task_id"] != task_id
            or run["agent_id"] != "librarian" or run["status"] not in {"PENDING", "RUNNING"}
            or int(run.get("execution_epoch", 0)) != execution_epoch
            or int(task.get("execution_epoch", 0)) != execution_epoch
        ):
            raise PermissionError("Assigned execution is stale or not owned by Librarian")
        return {**task, "runtime_binding": {
            "run_id": run_id, "execution_epoch": execution_epoch,
            "agent_id": "librarian", "authorized": True,
        }}
    return task


def owned_progress(progress_json: str) -> RunProgress:
    progress = RunProgress.model_validate_json(progress_json)
    if progress.agent_id != "librarian":
        raise PermissionError("Progress belongs to another agent")
    return progress


@mcp.tool()
def report_progress(progress_json: str) -> dict[str, str]:
    """Report progress to the sole control authority."""
    control = client()
    progress = owned_progress(progress_json)
    control.report_progress(progress, actor_id="librarian")
    return {"run_id": progress.run_id, "status": progress.status.value}


@mcp.tool()
def block_run(progress_json: str) -> dict[str, str]:
    """Retain a blocked execution without inventing successful retrieval."""
    control = client()
    progress = owned_progress(progress_json)
    control.block_run(progress, actor_id="librarian")
    return {"run_id": progress.run_id, "status": "BLOCKED"}


@mcp.tool()
def submit_result(result_json: str) -> dict[str, str]:
    """Submit the retrieval result for independent acceptance; never approve it here."""
    control = client()
    result = ResultContract.model_validate_json(result_json)
    if result.agent_id != "librarian":
        raise PermissionError("Result belongs to another agent")
    event = control.submit_result(result, actor_id="librarian")
    return {"run_id": result.run_id, "event_type": event}


if __name__ == "__main__":
    mcp.run()
