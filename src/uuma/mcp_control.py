from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .brainstormer_state import BrainstormerStore
from .diagnostics import (
    DiagnosticBackend,
    DiagnosticEngine,
    DiagnosticSettings,
    IncidentContext,
    RemediationStatus,
)
from .models import GraphOperation, TaskContract
from .service import ControlPlane

mcp = FastMCP("uuma-control")


@lru_cache(maxsize=1)
def _brainstormer_store() -> BrainstormerStore:
    return BrainstormerStore.from_env()


@lru_cache(maxsize=1)
def _control_plane() -> ControlPlane:
    control_plane = ControlPlane()
    control_plane.bootstrap()
    return control_plane


def _assert_orchestrator() -> None:
    if os.environ.get("UUMA_AGENT_ID", "").strip() != "orchestrator":
        raise PermissionError("The Control MCP is restricted to the Orchestrator profile.")


@mcp.tool()
def create_task(contract_json: str) -> dict[str, Any]:
    """Create a task from a validated TaskContract JSON document."""
    _assert_orchestrator()
    contract = TaskContract.model_validate_json(contract_json)
    return _control_plane().create_task(contract, actor_id="orchestrator").model_dump(mode="json")


@mcp.tool()
def route_task(task_id: str) -> dict[str, Any]:
    """Filter Agents by capability, permission, dependencies, and workload."""
    _assert_orchestrator()
    return _control_plane().route_task(task_id).model_dump(mode="json")


@mcp.tool()
def assign_task(task_id: str, agent_id: str, user_approved: bool = False) -> dict[str, str]:
    """Assign an approved task to an authorized Agent."""
    _assert_orchestrator()
    _control_plane().assign_task(task_id, agent_id, user_approved=user_approved)
    return {"task_id": task_id, "agent_id": agent_id, "status": "READY"}


@mcp.tool()
def propose_graph_operation(operation_json: str) -> dict[str, str]:
    """Propose a version-checked graph mutation; structural changes await user approval."""
    _assert_orchestrator()
    operation = GraphOperation.model_validate_json(operation_json)
    _control_plane().propose_operation(operation)
    return {"operation_id": operation.operation_id, "status": "PROPOSED"}


@mcp.tool()
def approve_graph_operation(operation_id: str) -> dict[str, str]:
    """Record explicit user approval and apply a proposed graph operation."""
    _assert_orchestrator()
    _control_plane().approve_operation(operation_id)
    return {"operation_id": operation_id, "status": "APPROVED"}


@mcp.tool()
def review_brainstormer_transaction(
    proposal_id: str, approve: bool, review_note: str
) -> dict[str, Any]:
    """Review a Brainstormer structure or decision transaction at the control boundary."""
    _assert_orchestrator()
    return _brainstormer_store().review(
        proposal_id,
        actor_id="orchestrator",
        approve=approve,
        note=review_note,
    )


@mcp.tool()
def list_runs(status: str = "", agent_id: str = "") -> list[dict[str, Any]]:
    """List current Run projections for monitoring."""
    _assert_orchestrator()
    return _control_plane().list_runs(status=status or None, agent_id=agent_id or None)


@mcp.tool()
def get_run(run_id: str) -> dict[str, Any]:
    """Get one Run projection including progress, blocker, attempt, and result."""
    _assert_orchestrator()
    return _control_plane().require_run(run_id)


@mcp.tool()
def request_cancel(run_id: str) -> dict[str, str]:
    """Record a cancellation request; the Hermes adapter performs the external stop."""
    _assert_orchestrator()
    _control_plane().request_cancel(run_id)
    return {"run_id": run_id, "status": "CANCEL_REQUESTED"}


@mcp.tool()
def system_health() -> dict[str, Any]:
    """Verify the immutable event chain and return projection counts."""
    _assert_orchestrator()
    return _control_plane().health()


@lru_cache(maxsize=1)
def _diagnostic_engine() -> DiagnosticEngine:
    return DiagnosticEngine(DiagnosticSettings.from_env())


@mcp.tool()
def diagnose_run(
    run_id: str,
    backend: str = "auto",
    working_directory: str = "",
) -> dict[str, Any]:
    """Diagnose a blocked or failed Run using agy -p or codex exec and propose a remediation patch."""
    _assert_orchestrator()
    run = _control_plane().require_run(run_id)
    task = _control_plane().require_task(run["task_id"])
    progress = run.get("progress") or {}
    result = run.get("result") or {}

    error_message = (
        progress.get("blocker")
        or result.get("error")
        or f"Run {run_id} failed with status {run.get('status')}"
    )

    cwd = working_directory or os.environ.get("UUMA_WORKSPACE_ROOT", str(Path.cwd()))
    incident = IncidentContext(
        run_id=run_id,
        task_id=run["task_id"],
        agent_id=run["agent_id"],
        error_message=error_message,
        working_directory=cwd,
        context_files=[],
        recent_logs=[f"Task Title: {task.get('title')}", f"Status: {run.get('status')}"],
    )

    engine = _diagnostic_engine()
    diag_backend = (
        DiagnosticBackend(backend.lower())
        if backend.lower() in {"agy", "codex", "auto"}
        else DiagnosticBackend.AUTO
    )
    report = engine.run_diagnostics(incident, backend=diag_backend)
    proposal = engine.create_proposal(report, incident)

    return {
        "remediation_id": proposal.remediation_id,
        "incident_id": incident.incident_id,
        "run_id": run_id,
        "agent_id": proposal.agent_id,
        "status": proposal.status.value,
        "backend_used": report.backend_used,
        "root_cause": report.root_cause,
        "impact_analysis": report.impact_analysis,
        "remediation_proposal": report.remediation_proposal,
        "unified_diff": report.unified_diff,
        "target_files": proposal.target_files,
        "verification_plan": report.verification_plan,
        "user_confirmation_required": True,
        "requires_user_approval": True,
    }


@mcp.tool()
def get_remediation(remediation_id: str) -> dict[str, Any]:
    """Get the full diagnostic report and remediation proposal by ID."""
    _assert_orchestrator()
    proposal = _diagnostic_engine().get_proposal(remediation_id)
    if proposal is None:
        raise KeyError(f"Unknown remediation proposal: {remediation_id}")
    return proposal.model_dump(mode="json")


@mcp.tool()
def list_remediations(status: str = "", agent_id: str = "") -> list[dict[str, Any]]:
    """List stored remediation proposals filtered by status or agent_id."""
    _assert_orchestrator()
    st = RemediationStatus(status) if status in RemediationStatus.__members__ else None
    proposals = _diagnostic_engine().list_proposals(status=st, agent_id=agent_id or None)
    return [p.model_dump(mode="json") for p in proposals]


@mcp.tool()
def approve_remediation(
    remediation_id: str,
    approve: bool = True,
    note: str = "",
) -> dict[str, Any]:
    """Record explicit user approval or rejection for a remediation proposal."""
    _assert_orchestrator()
    updated = _diagnostic_engine().approve_proposal(remediation_id, approve=approve, note=note)
    return {
        "remediation_id": remediation_id,
        "status": updated.status.value,
        "approved_at": updated.approved_at.isoformat() if updated.approved_at else None,
        "note": note,
    }


@mcp.tool()
def apply_remediation(
    remediation_id: str,
    working_directory: str = "",
) -> dict[str, Any]:
    """Apply an approved remediation patch to the codebase and record execution."""
    _assert_orchestrator()
    cwd = working_directory or os.environ.get("UUMA_WORKSPACE_ROOT", str(Path.cwd()))
    return _diagnostic_engine().apply_remediation(remediation_id, working_directory=cwd)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

