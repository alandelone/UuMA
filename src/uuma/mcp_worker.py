from __future__ import annotations

import json
import os
import subprocess
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:

    class FastMCP:  # type: ignore[no-redef]
        def __init__(self, name: str):
            self.name = name

        def tool(self):
            def decorator(func):
                return func

            return decorator

        def run(self):
            pass


from .brainstormer_state import BrainstormerStore, StateTransaction
from .eschematic_bridge import ESchematicBridge
from .forge_journal import ForgeJournalStore
from .knowledge_runtime import ensure_knowledge_graph
from .lab_crawler import CrawlerConfig, SourcingCrawlerEngine
from .lab_inventory import InventoryStore
from .lab_procurement import ProcurementStore
from .models import GraphOperation, ResultContract, RunProgress, TaskContract
from .order_workbook import preview_order_workbook
from .service import ControlPlane

mcp = FastMCP("uuma-worker")


@lru_cache(maxsize=1)
def _brainstormer_store() -> BrainstormerStore:
    return BrainstormerStore.from_env()


@lru_cache(maxsize=1)
def _control_plane() -> ControlPlane:
    control_plane = ControlPlane()
    control_plane.bootstrap()
    return control_plane


def _agent_id() -> str:
    agent_id = os.environ.get("UUMA_AGENT_ID", "").strip()
    if agent_id not in {"brainstormer", "scholar", "wisdom-oldman", "forge-lab-bot", "yonc"}:
        raise PermissionError("Worker MCP requires an authorized specialized profile identity.")
    return agent_id


def _require_brainstormer() -> str:
    agent_id = _agent_id()
    if agent_id != "brainstormer":
        raise PermissionError("This discussion-state tool is restricted to Brainstormer.")
    return agent_id


def _require_forge_lab_bot() -> str:
    agent_id = _agent_id()
    if agent_id != "forge-lab-bot":
        raise PermissionError("This hardware-lab tool is restricted to forge-lab-bot.")
    return agent_id


@lru_cache(maxsize=1)
def _eschematic() -> ESchematicBridge:
    return ESchematicBridge.from_env()


@lru_cache(maxsize=1)
def _inventory() -> InventoryStore:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    data_dir = Path(os.environ.get("UUMA_DATA_DIR", local_app_data / "UuMA"))
    path = Path(os.environ.get("LAB_DATABASE_PATH", data_dir / "forge-lab-bot" / "lab.db"))
    return InventoryStore(path)


@lru_cache(maxsize=1)
def _procurement() -> ProcurementStore:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    data_dir = Path(os.environ.get("UUMA_DATA_DIR", local_app_data / "UuMA"))
    path = Path(os.environ.get("LAB_DATABASE_PATH", data_dir / "forge-lab-bot" / "lab.db"))
    return ProcurementStore(path)


@lru_cache(maxsize=1)
def _journal() -> ForgeJournalStore:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    data_dir = Path(os.environ.get("UUMA_DATA_DIR", local_app_data / "UuMA"))
    path = Path(os.environ.get("LAB_DATABASE_PATH", data_dir / "forge-lab-bot" / "lab.db"))
    return ForgeJournalStore(path)


def _wake_forge_journal_runner() -> dict[str, Any]:
    """Request one dormant Windows task run without overriding an explicit operator stop."""
    task_name = os.environ.get("FORGE_JOURNAL_TASK_NAME", "UuMA Forge Journal Runner").strip()
    if os.name != "nt":
        return {"status": "UNSUPPORTED", "requested": False, "task_name": task_name}
    try:
        completed = subprocess.run(
            ["schtasks.exe", "/Run", "/TN", task_name],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return {"status": "UNAVAILABLE", "requested": False, "task_name": task_name}
    message = f"{completed.stdout}\n{completed.stderr}".lower()
    if completed.returncode == 0:
        return {"status": "REQUESTED", "requested": True, "task_name": task_name}
    if "disabled" in message:
        status = "PAUSED"
    elif "cannot find" in message or "not exist" in message:
        status = "MISSING"
    else:
        status = "UNAVAILABLE"
    return {"status": status, "requested": False, "task_name": task_name}


def _queue_journal_write(payload: dict[str, Any]) -> dict[str, Any]:
    job = _journal().queue_write(
        payload["operation"],
        payload.get("payload", {}),
        payload["idempotency_key"],
        journal_id=payload.get("journal_id", ""),
        notion_page_id=payload.get("notion_page_id", ""),
        notion_url=payload.get("notion_url", ""),
        journal_kind=payload.get("journal_kind", "LOG"),
        title=payload.get("title", ""),
        project_system=payload.get("project_system", ""),
        entry_type=payload.get("entry_type", ""),
        max_attempts=int(payload.get("max_attempts", 3)),
        offline=bool(payload.get("offline", False)),
        actor_id=payload.get("actor_id", "forge-lab-bot"),
    )
    result = dict(job)
    result["delivery_trigger"] = (
        _wake_forge_journal_runner()
        if str(job.get("status")) == "QUEUED"
        else {"status": "NOT_NEEDED", "requested": False}
    )
    return result


@lru_cache(maxsize=1)
def _crawler_engine() -> SourcingCrawlerEngine:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    data_dir = Path(os.environ.get("UUMA_DATA_DIR", local_app_data / "UuMA"))
    profile_dir = data_dir / "chrome_profiles" / "procurement"
    config = CrawlerConfig(user_data_dir=profile_dir)
    return SourcingCrawlerEngine(config)


@mcp.tool()
def knowledge_runtime_preflight(recover: bool = True) -> dict[str, Any]:
    """Ensure this specialist's own knowledge graph is available before domain work."""
    return ensure_knowledge_graph(_agent_id(), recover=recover)


@mcp.tool()
def register_direct_run(contract_json: str, external_run_ref: str = "") -> dict[str, Any]:
    """Register safe domain work started from a direct specialist chat."""
    task = TaskContract.model_validate_json(contract_json)
    return (
        _control_plane()
        .register_direct_run(_agent_id(), task, external_run_ref=external_run_ref or None)
        .model_dump(mode="json")
    )


@mcp.tool()
def get_assignment(task_id: str) -> dict[str, Any]:
    """Read a task only when it is assigned to the current Worker."""
    task = _control_plane().require_task(task_id)
    if task["assignee"] != _agent_id():
        raise PermissionError("This task is not assigned to the current Worker.")
    return task


@mcp.tool()
def report_progress(progress_json: str) -> dict[str, str]:
    """Report structured progress and heartbeat for the current Worker's Run."""
    progress = RunProgress.model_validate_json(progress_json)
    _control_plane().report_progress(progress, actor_id=_agent_id())
    return {"run_id": progress.run_id, "status": progress.status.value}


@mcp.tool()
def block_run(progress_json: str) -> dict[str, str]:
    """Block the current Run with an explicit reason and resumable progress state."""
    progress = RunProgress.model_validate_json(progress_json)
    _control_plane().block_run(progress, actor_id=_agent_id())
    return {"run_id": progress.run_id, "status": "BLOCKED"}


@mcp.tool()
def submit_result(result_json: str) -> dict[str, str]:
    """Submit a contract-validated result for the current Worker's Run."""
    result = ResultContract.model_validate_json(result_json)
    if _agent_id() in {"scholar", "wisdom-oldman"} and result.outcome.value == "COMPLETED":
        readiness = ensure_knowledge_graph(_agent_id(), recover=False)
        if readiness.get("ready") is not True:
            raise RuntimeError("Knowledge graph unavailable; report BLOCKED or FAILED, not COMPLETED")
    event_type = _control_plane().submit_result(result, actor_id=_agent_id())
    return {"run_id": result.run_id, "event_type": event_type}


@mcp.tool()
def propose_graph_operation(operation_json: str) -> dict[str, str]:
    """Submit a graph change proposal; Workers cannot approve or apply it."""
    operation = GraphOperation.model_validate_json(operation_json)
    if operation.requested_by != _agent_id():
        raise PermissionError("Operation requester must match the Worker identity.")
    _control_plane().propose_operation(operation, actor_id=_agent_id())
    return {"operation_id": operation.operation_id, "status": "PROPOSED"}


@mcp.tool()
def brainstormer_propose_transaction(transaction_json: str) -> dict[str, Any]:
    """Propose a validated project/topic reasoning-state transaction."""
    actor = _require_brainstormer()
    transaction = StateTransaction.model_validate_json(transaction_json)
    return _brainstormer_store().propose(transaction, requested_by=actor)


@mcp.tool()
def brainstormer_commit_safe_transaction(proposal_id: str) -> dict[str, Any]:
    """Commit only assumptions, questions, checkpoints, and other review-free state."""
    return _brainstormer_store().commit_safe(proposal_id, actor_id=_require_brainstormer())


@mcp.tool()
def brainstormer_get_context(project_id: str, topic_id: str = "") -> dict[str, Any]:
    """Restore bounded structured state for one project or topic."""
    _require_brainstormer()
    return _brainstormer_store().get_context(project_id, topic_id or None)


@mcp.tool()
def brainstormer_search_topics(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Find durable topics using deterministic text relevance."""
    _require_brainstormer()
    return _brainstormer_store().search_topics(query, limit=limit)


@mcp.tool()
def eschematic_status() -> dict[str, Any]:
    """Check the eSchematic bridge and runtime paths available to forge-lab-bot."""
    _require_forge_lab_bot()
    return _eschematic().status()


@mcp.tool()
def eschematic_get_component(component_id: str) -> dict[str, Any]:
    """Read one canonical component record from the authoritative eSchematic catalog."""
    _require_forge_lab_bot()
    return _eschematic().get_component(component_id)


@mcp.tool()
def eschematic_list_components(category: str = "", limit: int = 200) -> dict[str, Any]:
    """List canonical eSchematic component records, optionally filtered by category."""
    _require_forge_lab_bot()
    return _eschematic().list_components(category, limit)


@mcp.tool()
def eschematic_normalize_bom(
    input_path: str, mapping_json: str = "", resolve_component_ids: bool = True
) -> dict[str, Any]:
    """Normalize a CSV/XLSX design BOM and optionally resolve rows to canonical component IDs."""
    _require_forge_lab_bot()
    mapping = json.loads(mapping_json) if mapping_json else None
    if mapping is not None and not isinstance(mapping, dict):
        raise ValueError("mapping_json must contain an object.")
    normalized = _eschematic().normalize_bom(input_path, mapping)
    return _eschematic().resolve_normalized_bom(normalized) if resolve_component_ids else normalized


@mcp.tool()
def eschematic_export_design_manifest(manifest_json: str) -> dict[str, Any]:
    """Release an immutable, hashed design manifest from fully resolved BOM component IDs."""
    _require_forge_lab_bot()
    payload = json.loads(manifest_json)
    return _eschematic().export_design_manifest(
        payload["design_id"],
        payload["revision_id"],
        payload["resolved_items"],
        payload.get("metadata"),
    )


@mcp.tool()
def eschematic_find_components(query: str, limit: int = 10) -> dict[str, Any]:
    """Search approved eSchematic sources for reviewable component candidates."""
    _require_forge_lab_bot()
    return _eschematic().find_components(query, limit)


@mcp.tool()
def eschematic_commit_candidate(candidate_id: str, approved: bool = False) -> dict[str, Any]:
    """Commit a reviewed candidate to eSchematic only after explicit user/engineering approval."""
    _require_forge_lab_bot()
    return _eschematic().commit_candidate(candidate_id, approved=approved)


@mcp.tool()
def eschematic_validate_circuit(circuit_ir_path: str) -> dict[str, Any]:
    """Run eSchematic structural connectivity validation against a Circuit IR file."""
    _require_forge_lab_bot()
    return _eschematic().validate_circuit(circuit_ir_path)


@mcp.tool()
def eschematic_check_electrical_rules(circuit_ir_path: str) -> dict[str, Any]:
    """Run eSchematic electrical rule checks without claiming safety certification."""
    _require_forge_lab_bot()
    return _eschematic().check_electrical_rules(circuit_ir_path)


@mcp.tool()
def eschematic_infer_circuit(prompt: str) -> dict[str, Any]:
    """Create a reviewable proposed Circuit IR from a natural-language hardware request."""
    _require_forge_lab_bot()
    return _eschematic().infer_circuit(prompt)


@mcp.tool()
def eschematic_recommend(circuit_ir_path: str) -> dict[str, Any]:
    """List traceable supporting-component recommendations without mutating the circuit."""
    _require_forge_lab_bot()
    return _eschematic().recommend(circuit_ir_path)


@mcp.tool()
def eschematic_render(
    circuit_ir_path: str, output_dir: str = "", overwrite: bool = False
) -> dict[str, Any]:
    """Render connectivity-checked PNG/SVG artifacts through eSchematic."""
    _require_forge_lab_bot()
    return _eschematic().render_circuit(circuit_ir_path, output_dir, overwrite=overwrite)


@mcp.tool()
def inventory_status() -> dict[str, Any]:
    """Return the Lab inventory database path and current event/balance counts."""
    _require_forge_lab_bot()
    store = _inventory()
    with store.connect() as connection:
        event_count = connection.execute("SELECT COUNT(*) FROM inventory_events").fetchone()[0]
        purchase_history_count = connection.execute(
            "SELECT COUNT(*) FROM purchase_history_lines"
        ).fetchone()[0]
        purchase_review_count = connection.execute(
            """
            SELECT COUNT(*) FROM purchase_history_lines
            WHERE resolution_status = 'NEEDS_COMPONENT_REVIEW'
            """
        ).fetchone()[0]
    return {
        "database_path": str(store.database_path),
        "event_count": event_count,
        "purchase_history_count": purchase_history_count,
        "purchase_review_count": purchase_review_count,
        "balances": store.balances(),
    }


@mcp.tool()
def inventory_create_location(
    name: str, parent_location_id: str = "", location_id: str = ""
) -> dict[str, Any]:
    """Create a stable physical inventory location such as cabinet, drawer, or box."""
    _require_forge_lab_bot()
    return _inventory().create_location(
        name, parent_location_id or None, location_id=location_id or None
    )


@mcp.tool()
def inventory_get_balances(component_id: str = "") -> dict[str, Any]:
    """Read event-derived inventory balances, optionally for one canonical component ID."""
    _require_forge_lab_bot()
    return {"balances": _inventory().balances(component_id or None)}


@mcp.tool()
def inventory_receive(receipt_json: str) -> dict[str, Any]:
    """Receive inspected stock into lab.db; ordered items are not stock before this event."""
    actor_id = _require_forge_lab_bot()
    payload = json.loads(receipt_json)
    return _inventory().receive(
        payload["component_id"],
        payload["quantity"],
        lot_id=payload.get("lot_id", ""),
        location_id=payload.get("location_id", "UNLOCATED"),
        display_name=payload.get("display_name", ""),
        supplier=payload.get("supplier", ""),
        offer_ref=payload.get("offer_ref", ""),
        actor_id=actor_id,
        reason=payload.get("reason", "received and inspected"),
        evidence_ref=payload.get("evidence_ref", ""),
    )


@mcp.tool()
def inventory_transition(transition_json: str) -> dict[str, Any]:
    """Record RESERVE/RELEASE/INSTALL/UNINSTALL/DAMAGE/REPAIR/CONSUME/SCRAP events."""
    actor_id = _require_forge_lab_bot()
    payload = json.loads(transition_json)
    return _inventory().transition(
        payload["event_type"],
        payload["component_id"],
        payload["quantity"],
        lot_id=payload.get("lot_id", ""),
        location_id=payload.get("location_id", "UNLOCATED"),
        build_id=payload.get("build_id"),
        source_bucket=payload.get("source_bucket"),
        actor_id=actor_id,
        reason=payload["reason"],
        evidence_ref=payload.get("evidence_ref", ""),
    )


@mcp.tool()
def inventory_adjust(adjustment_json: str) -> dict[str, Any]:
    """Record a reasoned physical-count reconciliation; never overwrite balances directly."""
    actor_id = _require_forge_lab_bot()
    payload = json.loads(adjustment_json)
    return _inventory().adjust(
        payload["component_id"],
        payload.get("bucket", "AVAILABLE"),
        payload["delta"],
        lot_id=payload.get("lot_id", ""),
        location_id=payload.get("location_id", "UNLOCATED"),
        actor_id=actor_id,
        reason=payload["reason"],
        evidence_ref=payload.get("evidence_ref", ""),
    )


@mcp.tool()
def inventory_preview_or_import_legacy_rows(rows_json: str, commit: bool = False) -> dict[str, Any]:
    """Preview normalized legacy Excel rows; commit only after mapping review and approval."""
    actor_id = _require_forge_lab_bot()
    rows = json.loads(rows_json)
    if not isinstance(rows, list):
        raise TypeError("rows_json must contain an array.")
    return _inventory().import_legacy_rows(rows, commit=commit, actor_id=actor_id)


@mcp.tool()
def inventory_preview_or_import_order_workbook(
    workbook_path: str,
    categories_json: str = "",
    component_mapping_json: str = "",
    commit: bool = False,
) -> dict[str, Any]:
    """Preview Taobao order history; commit stages evidence only and never creates stock."""
    _require_forge_lab_bot()
    categories = json.loads(categories_json) if categories_json else None
    if categories is not None and not isinstance(categories, list):
        raise ValueError("categories_json must contain an array.")
    mapping = json.loads(component_mapping_json) if component_mapping_json else None
    if mapping is not None and not isinstance(mapping, dict):
        raise ValueError("component_mapping_json must contain an object.")
    workbook = preview_order_workbook(
        workbook_path,
        categories=categories,
        component_mapping=mapping,
    )
    staged = _inventory().import_purchase_history(workbook["rows"], commit=commit)
    return {key: value for key, value in workbook.items() if key not in {"rows", "sample_rows"}} | {
        "status": staged["status"],
        "purchase_history": staged,
        "sample_rows": workbook["sample_rows"],
    }


@mcp.tool()
def inventory_list_purchase_history(
    needs_review_only: bool = True, limit: int = 100
) -> dict[str, Any]:
    """List staged order evidence, normally the rows still needing eSchematic identity review."""
    _require_forge_lab_bot()
    rows = _inventory().purchase_history(needs_review_only=needs_review_only, limit=limit)
    return {"count": len(rows), "rows": rows}


@mcp.tool()
def inventory_resolve_purchase_history_line(source_key: str, component_id: str) -> dict[str, Any]:
    """Attach a verified canonical eSchematic component ID to one staged purchase line."""
    _require_forge_lab_bot()
    component = _eschematic().get_component(component_id)
    if component.get("command_exit_code") or component.get("id") != component_id:
        raise ValueError("component_id does not exist in the configured eSchematic catalog.")
    return _inventory().resolve_purchase_history_line(source_key, component_id)


@mcp.tool()
def lab_analyze_bom(input_path: str, mapping_json: str = "") -> dict[str, Any]:
    """Normalize/resolve an eSchematic BOM, then compare it with available Lab inventory."""
    _require_forge_lab_bot()
    mapping = json.loads(mapping_json) if mapping_json else None
    resolved = _eschematic().normalize_and_resolve_bom(input_path, mapping)
    if resolved["status"] != "resolved":
        return {"status": "NEEDS_COMPONENT_REVIEW", "bom": resolved, "inventory": None}
    inventory = _inventory().check_bom_shortage(resolved["resolved_items"])
    return {"status": inventory["status"], "bom": resolved, "inventory": inventory}


@mcp.tool()
def lab_create_build(build_json: str) -> dict[str, Any]:
    """Create a physical Build tied to one eSchematic design revision/manifest."""
    _require_forge_lab_bot()
    payload = json.loads(build_json)
    return _inventory().create_build(
        payload["design_revision_id"],
        payload.get("design_manifest_hash", ""),
        payload.get("design_manifest"),
        build_id=payload.get("build_id"),
    )


@mcp.tool()
def lab_get_current_as_built(build_id: str) -> dict[str, Any]:
    """Return the current installed component state for a physical Build."""
    _require_forge_lab_bot()
    return _inventory().current_as_built(build_id)


@mcp.tool()
def lab_list_builds(status: str = "", limit: int = 100) -> dict[str, Any]:
    """List physical Builds, optionally filtered by status (OPEN, IN_PROGRESS, COMPLETED, ABANDONED)."""
    _require_forge_lab_bot()
    rows = _inventory().list_builds(status=status or None, limit=limit)
    return {"count": len(rows), "builds": rows}


@mcp.tool()
def lab_update_build_status(build_id: str, status: str) -> dict[str, Any]:
    """Update a physical Build's lifecycle status (OPEN, IN_PROGRESS, COMPLETED, ABANDONED)."""
    _require_forge_lab_bot()
    return _inventory().update_build_status(build_id, status)


@mcp.tool()
def lab_record_commissioning(record_json: str) -> dict[str, Any]:
    """Record a commissioning, bring-up, or calibration test result tied to a Build."""
    _require_forge_lab_bot()
    payload = json.loads(record_json)
    return _inventory().record_commissioning(
        payload["build_id"],
        payload["test_name"],
        payload["status"],
        operator=payload.get("operator", "forge-lab-bot"),
        metrics=payload.get("metrics"),
        notes=payload.get("notes", ""),
        evidence_ref=payload.get("evidence_ref", ""),
        record_id=payload.get("record_id"),
        occurred_at=payload.get("occurred_at"),
    )


@mcp.tool()
def lab_list_commissioning(
    build_id: str = "", status: str = "", limit: int = 100
) -> dict[str, Any]:
    """List commissioning and test logs, optionally filtered by build_id or status."""
    _require_forge_lab_bot()
    rows = _inventory().list_commissioning(
        build_id=build_id or None, status=status or None, limit=limit
    )
    return {"count": len(rows), "records": rows}


@mcp.tool()
def lab_record_worklog(worklog_json: str) -> dict[str, Any]:
    """Record a structured lab worklog entry preserving observation != hypothesis != cause."""
    _require_forge_lab_bot()
    payload = json.loads(worklog_json)
    return _inventory().record_worklog(
        payload["project_name"],
        payload["action"],
        payload["observation"],
        build_id=payload.get("build_id"),
        source_ref=payload.get("source_ref", ""),
        hypothesis=payload.get("hypothesis", ""),
        confirmed_cause=payload.get("confirmed_cause", ""),
        result=payload.get("result", ""),
        parts=payload.get("parts"),
        next_action=payload.get("next_action", ""),
        worklog_id=payload.get("worklog_id"),
        occurred_at=payload.get("occurred_at"),
    )


@mcp.tool()
def lab_list_worklogs(
    project_name: str = "", build_id: str = "", limit: int = 100
) -> dict[str, Any]:
    """List structured lab worklogs, optionally filtered by project_name or build_id."""
    _require_forge_lab_bot()
    rows = _inventory().list_worklogs(
        project_name=project_name or None, build_id=build_id or None, limit=limit
    )
    return {"count": len(rows), "worklogs": rows}


@mcp.tool()
def lab_journal_register_snapshot(snapshot_json: str) -> dict[str, Any]:
    """Reconcile one fetched Notion Forge Journal page into the durable lab.db sync ledger."""
    _require_forge_lab_bot()
    payload = json.loads(snapshot_json)
    return _journal().register_snapshot(
        payload["notion_page_id"],
        payload["notion_url"],
        payload.get("title", ""),
        payload["remote_content_hash"],
        remote_edited_at=payload.get("remote_edited_at", ""),
        journal_kind=payload.get("journal_kind", "LOG"),
        project_system=payload.get("project_system", ""),
        entry_type=payload.get("entry_type", ""),
        snapshot=payload.get("snapshot"),
        actor_id=payload.get("actor_id", "openclaw"),
    )


@mcp.tool()
def lab_journal_queue_write(write_json: str) -> dict[str, Any]:
    """Stage an idempotent Notion write; a PATCH_LOG must include its visible change notice."""
    _require_forge_lab_bot()
    payload = json.loads(write_json)
    return _queue_journal_write(payload)


@mcp.tool()
def lab_journal_capture_chat(capture_json: str) -> dict[str, Any]:
    """Capture reported real lab work locally, queue its Notion log, and wake one sync run."""
    _require_forge_lab_bot()
    payload = json.loads(capture_json)
    required = ("title", "project_system", "entry_type", "raw_note", "action", "observation")
    missing = [name for name in required if not str(payload.get(name) or "").strip()]
    if missing:
        raise ValueError(f"Chat journal capture requires: {', '.join(missing)}.")
    entry_type = str(payload["entry_type"]).strip().title()
    if entry_type not in {"Problem", "Experiment", "Repair", "Build"}:
        raise ValueError("entry_type must be Problem, Experiment, Repair, or Build.")
    identity_seed = json.dumps(
        {
            name: payload.get(name, "")
            for name in (
                "title", "project_system", "entry_type", "raw_note", "action", "observation",
                "occurred_at",
            )
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    content_digest = sha256(identity_seed.encode("utf-8")).hexdigest()
    key = str(payload.get("idempotency_key") or f"forge-chat:{content_digest}").strip()
    source_ref = str(
        payload.get("source_ref") or f"hermes-chat://content/{content_digest[:24]}"
    ).strip()
    worklog = _inventory().record_worklog(
        str(payload["project_system"]),
        str(payload["action"]),
        str(payload["observation"]),
        build_id=payload.get("build_id"),
        source_ref=source_ref,
        hypothesis=str(payload.get("hypothesis") or ""),
        confirmed_cause=str(payload.get("confirmed_cause") or ""),
        result=str(payload.get("result") or ""),
        parts=payload.get("parts"),
        next_action=str(payload.get("next_step") or ""),
        worklog_id=f"log_chat_{sha256(key.encode('utf-8')).hexdigest()[:24]}",
        occurred_at=payload.get("occurred_at"),
    )
    journal_payload = {
        "title": str(payload["title"]),
        "project_system": str(payload["project_system"]),
        "type": entry_type,
        "raw_note": str(payload["raw_note"]),
        "process": str(payload.get("process") or payload["action"]),
        "result": str(payload.get("result") or ""),
        "verification": str(payload.get("verification") or ""),
        "next_step": str(payload.get("next_step") or ""),
        "candidate_lesson": str(payload.get("candidate_lesson") or ""),
        "change_reason": "Captured from a relevant LAB_BOT conversation with source provenance.",
        "source_ref": source_ref,
        "worklog_id": worklog["worklog_id"],
    }
    job = _queue_journal_write({
        "operation": "CREATE_LOG",
        "payload": journal_payload,
        "idempotency_key": key,
        "title": str(payload["title"]),
        "project_system": str(payload["project_system"]),
        "entry_type": entry_type,
        "actor_id": "forge-lab-bot-chat",
    })
    return {"worklog": worklog, "journal_job": job}


@mcp.tool()
def lab_journal_claim_write(worker_id: str, lease_seconds: int = 120) -> dict[str, Any]:
    """Lease the next durable OpenClaw/Notion sync operation for bounded delivery."""
    _require_forge_lab_bot()
    job = _journal().claim_write(worker_id, lease_seconds=lease_seconds)
    return {"claimed": job is not None, "job": job}


@mcp.tool()
def lab_journal_finish_write(result_json: str) -> dict[str, Any]:
    """Record verified Notion delivery, retryable failure, or a visible conflict."""
    _require_forge_lab_bot()
    payload = json.loads(result_json)
    return _journal().finish_write(
        payload["sync_job_id"],
        succeeded=bool(payload.get("succeeded", False)),
        worker_id=payload["worker_id"],
        remote_page_id=payload.get("remote_page_id", ""),
        remote_url=payload.get("remote_url", ""),
        remote_edited_at=payload.get("remote_edited_at", ""),
        remote_content_hash=payload.get("remote_content_hash", ""),
        error=payload.get("error", ""),
        conflict=bool(payload.get("conflict", False)),
    )


@mcp.tool()
def lab_journal_request_resync(
    notion_page_id: str, reason: str, idempotency_key: str
) -> dict[str, Any]:
    """Queue an explicit pull/reconciliation without overwriting an unresolved conflict."""
    actor_id = _require_forge_lab_bot()
    return _journal().request_resync(
        notion_page_id, reason, idempotency_key, actor_id=actor_id
    )


@mcp.tool()
def lab_journal_sync_status(
    notion_page_id: str = "", sync_status: str = "", limit: int = 100
) -> dict[str, Any]:
    """Read Forge Journal sync state and pending notification count."""
    _require_forge_lab_bot()
    return _journal().status(
        notion_page_id=notion_page_id or None,
        sync_status=sync_status or None,
        limit=limit,
    )


@mcp.tool()
def lab_journal_list_events(journal_id: str, limit: int = 100) -> dict[str, Any]:
    """Read append-only synchronization evidence for one journal record."""
    _require_forge_lab_bot()
    events = _journal().list_events(journal_id, limit=limit)
    return {"count": len(events), "events": events}


@mcp.tool()
def lab_journal_list_notifications(status: str = "", limit: int = 100) -> dict[str, Any]:
    """Read durable queued, failed, conflict, and recovered user notices."""
    _require_forge_lab_bot()
    notices = _journal().list_notifications(status=status or None, limit=limit)
    return {"count": len(notices), "notifications": notices}


@mcp.tool()
def lab_journal_claim_notification(worker_id: str, lease_seconds: int = 120) -> dict[str, Any]:
    """Lease the next user notice for delivery through the originating Hermes route."""
    _require_forge_lab_bot()
    notice = _journal().claim_notification(worker_id, lease_seconds=lease_seconds)
    return {"claimed": notice is not None, "notification": notice}


@mcp.tool()
def lab_journal_finish_notification(result_json: str) -> dict[str, Any]:
    """Record notification delivery or schedule its bounded retry."""
    _require_forge_lab_bot()
    payload = json.loads(result_json)
    return _journal().finish_notification(
        payload["notification_id"],
        sent=bool(payload.get("sent", False)),
        worker_id=payload["worker_id"],
        error=payload.get("error", ""),
    )


@mcp.tool()
def lab_record_failure(failure_json: str) -> dict[str, Any]:
    """Record a hardware fault/failure incident with symptoms and root-cause status."""
    _require_forge_lab_bot()
    payload = json.loads(failure_json)
    return _inventory().record_failure(
        payload["symptom"],
        severity=payload.get("severity", "MEDIUM"),
        build_id=payload.get("build_id"),
        component_id=payload.get("component_id"),
        suspected_cause=payload.get("suspected_cause", ""),
        confirmed_cause=payload.get("confirmed_cause", ""),
        action_taken=payload.get("action_taken", ""),
        evidence_ref=payload.get("evidence_ref", ""),
        failure_id=payload.get("failure_id"),
        occurred_at=payload.get("occurred_at"),
    )


@mcp.tool()
def lab_list_failures(
    build_id: str = "", component_id: str = "", severity: str = "", limit: int = 100
) -> dict[str, Any]:
    """List hardware failure records, optionally filtered by build, component, or severity."""
    _require_forge_lab_bot()
    rows = _inventory().list_failures(
        build_id=build_id or None,
        component_id=component_id or None,
        severity=severity or None,
        limit=limit,
    )
    return {"count": len(rows), "failures": rows}


@mcp.tool()
def lab_propose_lesson(lesson_json: str) -> dict[str, Any]:
    """Propose a candidate engineering lesson derived from worklogs, testing, or failures."""
    _require_forge_lab_bot()
    payload = json.loads(lesson_json)
    return _inventory().propose_lesson(
        payload["statement"],
        payload["scope"],
        target_system=payload.get("target_system", "LAB_ONLY"),
        severity=payload.get("severity", "RECOMMEND"),
        confidence=float(payload.get("confidence", 0.8)),
        status=payload.get("status", "CANDIDATE"),
        evidence_refs=payload.get("evidence_refs"),
        exceptions=payload.get("exceptions", ""),
        created_by=payload.get("created_by", "forge-lab-bot"),
        lesson_id=payload.get("lesson_id"),
    )


@mcp.tool()
def lab_list_lessons(target_system: str = "", status: str = "", limit: int = 100) -> dict[str, Any]:
    """List engineering lessons, optionally filtered by target_system or status."""
    _require_forge_lab_bot()
    rows = _inventory().list_lessons(
        target_system=target_system or None, status=status or None, limit=limit
    )
    return {"count": len(rows), "lessons": rows}


@mcp.tool()
def lab_update_lesson_status(lesson_id: str, status: str, exceptions: str = "") -> dict[str, Any]:
    """Refine a candidate lesson without crossing the human/reviewer approval boundary."""
    _require_forge_lab_bot()
    if status.strip().upper() != "CANDIDATE":
        raise PermissionError(
            "LAB_BOT may only keep lessons as CANDIDATE; reviewer lifecycle decisions are external."
        )
    return _inventory().update_lesson_status(
        lesson_id, status, exceptions=exceptions if exceptions else None
    )


@mcp.tool()
def eschematic_submit_design_feedback(feedback_json: str) -> dict[str, Any]:
    """Submit a design feedback proposal to eSchematic without directly mutating design data."""
    _require_forge_lab_bot()
    payload = json.loads(feedback_json)
    return _inventory().propose_design_feedback(
        payload["design_revision_id"],
        payload["change_summary"],
        payload["rationale"],
        target_component_id=payload.get("target_component_id"),
        evidence_refs=payload.get("evidence_refs"),
        proposal_id=payload.get("proposal_id"),
    )


@mcp.tool()
def eschematic_list_design_feedback(
    design_revision_id: str = "", status: str = "", limit: int = 100
) -> dict[str, Any]:
    """List design feedback proposals submitted by forge-lab-bot to eSchematic."""
    _require_forge_lab_bot()
    rows = _inventory().list_design_feedback(
        design_revision_id=design_revision_id or None,
        status=status or None,
        limit=limit,
    )
    return {"count": len(rows), "proposals": rows}


@mcp.tool()
def procurement_create_requirement(requirement_json: str) -> dict[str, Any]:
    """Create a new sourcing requirement for a component, raw material, or consumable."""
    _require_forge_lab_bot()
    payload = json.loads(requirement_json)
    return _procurement().create_requirement(
        item_name=payload["item_name"],
        target_quantity=payload["target_quantity"],
        component_id=payload.get("component_id"),
        specs=payload.get("specs", ""),
        target_unit_price=payload.get("target_unit_price"),
        metadata=payload.get("metadata"),
        requirement_id=payload.get("requirement_id"),
    )


@mcp.tool()
def procurement_list_requirements(status: str = "", limit: int = 100) -> dict[str, Any]:
    """List sourcing requirements, optionally filtered by status (OPEN, SOURCING, ORDERED, FULFILLED, CANCELLED)."""
    _require_forge_lab_bot()
    rows = _procurement().list_requirements(status=status or None, limit=limit)
    return {"count": len(rows), "requirements": rows}


@mcp.tool()
def procurement_create_requirements_from_shortages(shortages_json: str) -> dict[str, Any]:
    """Convert BOM shortages into tracked sourcing requirements in lab.db."""
    _require_forge_lab_bot()
    shortages = json.loads(shortages_json)
    created = _procurement().create_requirements_from_shortages(shortages)
    return {"count": len(created), "requirements": created}


@mcp.tool()
def procurement_expand_terms(query: str, component_id: str = "") -> dict[str, Any]:
    """Expand part number/query into aliases, packaging keywords, and raw material alternatives."""
    _require_forge_lab_bot()
    return _procurement().lookup_or_expand_terms(query, component_id=component_id)


@mcp.tool()
def procurement_save_term_rule(rule_json: str) -> dict[str, Any]:
    """Save or update a deterministic search term expansion rule in lab.db."""
    _require_forge_lab_bot()
    payload = json.loads(rule_json)
    return _procurement().save_term_rule(
        target_name=payload["target_name"],
        aliases=payload.get("aliases", []),
        package_keywords=payload.get("package_keywords"),
        raw_materials=payload.get("raw_materials"),
        rule_id=payload.get("rule_id"),
    )


@mcp.tool()
def procurement_parse_offer_snippet(snippet_text: str) -> dict[str, Any]:
    """Parse unstructured text or share link from Taobao, 1688, LCSC, etc. into structured offer data."""
    _require_forge_lab_bot()
    return _procurement().parse_offer_snippet(snippet_text)


@mcp.tool()
def procurement_record_offers(offers_json: str) -> dict[str, Any]:
    """Record supplier offers (pricing, MOQ, shipping, shop name) for procurement evaluation."""
    _require_forge_lab_bot()
    offers = json.loads(offers_json)
    recorded = _procurement().record_offers(offers)
    return {"count": len(recorded), "offers": recorded}


@mcp.tool()
def procurement_list_offers(
    requirement_id: str = "", shop_name: str = "", limit: int = 100
) -> dict[str, Any]:
    """List supplier offers, optionally filtered by requirement_id or shop_name."""
    _require_forge_lab_bot()
    rows = _procurement().list_offers(
        requirement_id=requirement_id, shop_name=shop_name, limit=limit
    )
    return {"count": len(rows), "offers": rows}


@mcp.tool()
def procurement_evaluate_sourcing(requirement_ids_json: str) -> dict[str, Any]:
    """Evaluate multi-strategy sourcing options (Lowest Landed Cost, Single-Shop Bundle, Raw Material DIY)."""
    _require_forge_lab_bot()
    requirement_ids = json.loads(requirement_ids_json)
    return _procurement().evaluate_sourcing(requirement_ids)


@mcp.tool()
def procurement_confirm_order(order_plan_json: str) -> dict[str, Any]:
    """Confirm a procurement order plan: mark requirements as ORDERED and create purchase_lots awaiting receipt."""
    _require_forge_lab_bot()
    payload = json.loads(order_plan_json)
    return _procurement().confirm_order(payload)


@mcp.tool()
def procurement_check_crawler_status() -> dict[str, Any]:
    """Check local Chrome installation, user data profile directory, and session persistence status."""
    _require_forge_lab_bot()
    return _crawler_engine().check_environment()


@mcp.tool()
def procurement_auto_search_and_evaluate(
    query: str,
    requirement_id: str = "",
    target_quantity: float = 1.0,
    platforms: str = "taobao,1688",
    max_results_per_platform: int = 5,
) -> dict[str, Any]:
    """Automatically drive local Chrome session to search Taobao and 1688, harvest live offers, and compute 3-strategy evaluation."""
    _require_forge_lab_bot()
    platform_list = [p.strip().lower() for p in platforms.split(",") if p.strip()]
    return _crawler_engine().search_harvest_and_evaluate(
        query=query,
        requirement_id=requirement_id or None,
        target_quantity=max(target_quantity, 1.0),
        platforms=platform_list,
        max_per_platform=max_results_per_platform,
        proc_store=_procurement(),
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
