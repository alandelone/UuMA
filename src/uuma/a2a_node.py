"""A2A 1.0 gateway with durable receipts and existing UuMA authority checks."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Protocol

from .auth import TokenRegistry
from .control_client import ControlClient, validate_endpoint
from .hermes import HermesRunClient
from .node_journal import NodeJournal
from .remote_mcp import CALLER, AgentAuthentication


class RuntimeAdapter(Protocol):
    async def start(self, key: str, task: dict) -> str: ...
    async def get(self, reference: str) -> dict: ...
    async def cancel(self, reference: str) -> dict: ...


class HermesAdapter:
    def __init__(self, client: HermesRunClient, profile: str):
        self.client, self.profile = client, profile

    async def start(self, key: str, task: dict) -> str:
        # One reserved dispatch invokes start at most once. Unknown outcomes require reconciliation.
        payload = {
            "session_id": (
                f"uuma-assigned:{task['task_id']}:{task['run_id']}:{task['epoch']}"
            ),
            "input": (
                "Execute only this assigned UuMA contract. "
                "Report progress/result using Worker MCP. "
                "Do not resume paused work or create child tasks.\n"
                + json.dumps(task, ensure_ascii=False)
            ),
            "metadata": {"uuma_dispatch_key": key},
        }
        # Profile routing is fixed by /p/<profile> in the configured runtime URL.
        result = await asyncio.to_thread(self.client.start, payload, idempotency_key=key)
        reference = result.get("run_id") or result.get("id")
        if not reference:
            raise RuntimeError("Hermes did not return an execution receipt")
        return str(reference)

    async def get(self, reference: str) -> dict:
        return await asyncio.to_thread(self.client.get, reference)

    async def cancel(self, reference: str) -> dict:
        return await asyncio.to_thread(self.client.stop, reference)


class DispatchCoordinator:
    def __init__(
        self, control, journal: NodeJournal, adapters: dict[str, RuntimeAdapter],
        execution_metadata: dict[str, dict] | None = None,
    ):
        self.control, self.journal, self.adapters = control, journal, adapters
        self.execution_metadata = execution_metadata or {}

    def authorize(self, agent_id: str, run_id: str, epoch: int) -> tuple[dict, dict]:
        run = self.control.require_run(run_id)
        task = self.control.require_task(run["task_id"])
        if (
            run["agent_id"] != agent_id
            or task["assignee"] != agent_id
            or task.get("current_run_id") != run_id
            or int(run.get("execution_epoch", 0)) != epoch
            or run["status"] not in {"PENDING", "RUNNING"}
        ):
            raise PermissionError(
                "Run is not the current authorized execution; paused Runs stay paused"
            )
        if agent_id not in self.adapters:
            raise PermissionError("Agent is not hosted by this node")
        return run, task

    async def dispatch(self, agent_id: str, run_id: str, epoch: int, a2a_id: str) -> dict:
        _run, task = await asyncio.to_thread(self.authorize, agent_id, run_id, epoch)
        key = f"dispatch:{agent_id}:{run_id}:{epoch}"
        if self.journal.get(key) is None and (
            _run["status"] != "PENDING" or _run.get("source") not in {"orchestrator", "kanban"}
        ):
            raise PermissionError("Only a pending assigned execution can start a new runtime")
        material = {
            "agent_id": agent_id,
            "task_id": _run["task_id"],
            "run_id": run_id,
            "epoch": epoch,
            "contract": task["contract"],
        }
        record, fresh = self.journal.reserve(
            key,
            material,
            {
                "phase": "DISPATCHING",
                "agent_id": agent_id,
                "run_id": run_id,
                "execution_epoch": epoch,
                "a2a_task_id": a2a_id,
                "revision": os.environ.get("UUMA_RELEASE_REVISION", "unreleased"),
                **self.execution_metadata.get(agent_id, {}),
            },
        )
        if not fresh:
            if not record.get("runtime_ref"):
                raise RuntimeError(
                    "Dispatch outcome unknown; reconcile the original request before retry"
                )
            return record
        try:
            reference = await self.adapters[agent_id].start(key, material)
        except Exception:
            self.journal.update(key, {**record, "phase": "UNCERTAIN"})
            raise
        record = {**record, "phase": "ACCEPTED", "runtime_ref": reference}
        self.journal.update(key, record)
        return record

    async def request_cancel(self, record: dict) -> dict:
        # Cancellation is requested, never represented as proof of external reversal.
        key = f"dispatch:{record['agent_id']}:{record['run_id']}:{int(record['execution_epoch'])}"
        current = self.journal.get(key) or record
        self.journal.update(key, {**current, "phase": "CANCEL_REQUESTED"})
        return await self.adapters[record["agent_id"]].cancel(record["runtime_ref"])

    async def observe(self, record: dict) -> dict:
        """Record execution and acceptance separately, without relaunching either."""
        key = f"dispatch:{record['agent_id']}:{record['run_id']}:{int(record['execution_epoch'])}"
        current = self.journal.get(key) or record
        run = await asyncio.to_thread(self.control.require_run, current["run_id"])
        observation = {
            "uuma_status": run["status"],
            "accepted": run["status"] == "COMPLETED",
            "superseded": (
                int(run.get("execution_epoch", 0)) != int(current["execution_epoch"])
                or run["status"] == "SUPERSEDED"
            ),
            "cancel_requested": current.get("phase") == "CANCEL_REQUESTED",
        }
        try:
            runtime = await self.adapters[current["agent_id"]].get(current["runtime_ref"])
        except Exception:  # noqa: BLE001 -- adapter failures must remain an unknown execution
            # A failed query is not evidence that an execution has stopped or succeeded.
            observation.update(runtime_status="unknown", runtime_reachable=False)
        else:
            observation.update(
                runtime_status=str(runtime.get("status", "unknown")).lower(),
                runtime_reachable=True,
            )
        updated = {**current, **observation}
        if updated != current:
            self.journal.update(key, updated)
        return updated


def execution_projection(record: dict) -> tuple[str, str]:
    """Return the transport state, preserving the independent review decision."""
    status, runtime = record["uuma_status"], record["runtime_status"]
    if record.get("superseded"):
        return "FAILED", "superseded_execution"
    if runtime in {"failed", "error"} or status == "FAILED":
        return "FAILED", "runtime_failed" if runtime in {"failed", "error"} else "uuma_failed"
    if status == "CANCELLED":
        return "CANCELED", "uuma_cancelled"
    if runtime in {"cancelled", "canceled"}:
        return "INPUT_REQUIRED", "runtime_cancelled_requires_reconciliation"
    if runtime == "completed" and status in {"REVIEW", "COMPLETED"}:
        return "COMPLETED", "result_pending_review" if status == "REVIEW" else "accepted"
    if status in {"REVIEW", "COMPLETED", "PAUSED", "BLOCKED"}:
        return "INPUT_REQUIRED", "runtime_requires_reconciliation"
    if runtime in {"completed", "unknown"} or record.get("cancel_requested"):
        return "INPUT_REQUIRED", "runtime_requires_reconciliation"
    return "WORKING", "executing"


def create_app(control, journal: NodeJournal, tokens: TokenRegistry, bindings: dict):
    from a2a.server.agent_execution import AgentExecutor
    from a2a.server.request_handlers.default_request_handler import LegacyRequestHandler
    from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
    from a2a.server.tasks import TaskStore, TaskUpdater
    from a2a.types.a2a_pb2 import (
        AgentCapabilities,
        AgentCard,
        AgentInterface,
        AgentSkill,
        HTTPAuthSecurityScheme,
        ListTasksResponse,
        SecurityRequirement,
        SecurityScheme,
        Task,
        TaskState,
        TaskStatus,
    )
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    adapters = {agent: binding["adapter"] for agent, binding in bindings.items()}
    execution_metadata = {
        agent: {
            **{
                key: value for key, value in binding.items()
                if key in {"node_id", "runtime_version"}
            },
            **(
                {"runtime_version_source": "configured_binding"}
                if binding.get("runtime_version") else {}
            ),
        }
        for agent, binding in bindings.items()
    }
    coordinator = DispatchCoordinator(control, journal, adapters, execution_metadata)

    class DurableTasks(TaskStore):
        def __init__(self, agent):
            self.agent = agent

        def owner(self):
            return f"{self.agent}:{CALLER.get()}"

        async def save(self, task, context):
            with journal.connect() as db:
                row = db.execute(
                    "SELECT owner FROM protocol_tasks WHERE task_id=?", (task.id,)
                ).fetchone()
                if row and row[0] != self.owner():
                    raise PermissionError("Protocol task belongs to another identity")
                db.execute(
                    "INSERT INTO protocol_tasks VALUES (?,?,?) ON CONFLICT(task_id) "
                    "DO UPDATE SET value=excluded.value",
                    (task.id, self.owner(), task.SerializeToString()),
                )

        async def get(self, task_id, context):
            with journal.connect() as db:
                row = db.execute(
                    "SELECT value FROM protocol_tasks WHERE task_id=? AND owner=?",
                    (task_id, self.owner()),
                ).fetchone()
            if not row:
                return None
            task = Task.FromString(row[0])
            from google.protobuf.json_format import MessageToDict

            metadata = MessageToDict(task.metadata)
            if metadata.get("run_id"):
                observed = await coordinator.observe(metadata)
                state, reason = execution_projection(observed)
                task.status.state = getattr(TaskState, "TASK_STATE_" + state)
                task.metadata.update({**observed, "reason": reason})
            return task

        async def list(self, params, context):
            if params.page_token:
                raise ValueError("Pagination cursor not supported by this node")
            with journal.connect() as db:
                rows = db.execute(
                    "SELECT value FROM protocol_tasks WHERE owner=? ORDER BY task_id LIMIT ?",
                    (self.owner(), min(params.page_size or 50, 100)),
                ).fetchall()
            tasks = [await self.get(Task.FromString(row[0]).id, context) for row in rows]
            if params.context_id:
                tasks = [task for task in tasks if task.context_id == params.context_id]
            return ListTasksResponse(tasks=tasks)

        async def delete(self, task_id, context):
            raise PermissionError("Transport task history is retained")

    class Executor(AgentExecutor):
        def __init__(self, agent):
            self.agent = agent

        async def execute(self, context, event_queue):
            if CALLER.get() != "orchestrator":
                raise PermissionError("Task dispatch requires Orchestrator authority")
            metadata = context.metadata
            run_id, epoch = metadata.get("uuma_run_id"), metadata.get("execution_epoch")
            if not run_id or epoch is None:
                raise ValueError("A current UuMA Run and execution epoch are required")
            record = await coordinator.dispatch(
                self.agent, str(run_id), int(epoch), context.task_id
            )
            if context.current_task is None:
                await event_queue.enqueue_event(
                    Task(
                        id=context.task_id,
                        context_id=context.context_id,
                        status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
                        history=[context.message],
                        metadata=record,
                    )
                )
            updater = TaskUpdater(event_queue, context.task_id, context.context_id)
            await updater.start_work()
            while True:
                observed = await coordinator.observe(record)
                state, reason = execution_projection(observed)
                if state != "WORKING":
                    await updater.update_status(
                        getattr(TaskState, "TASK_STATE_" + state),
                        metadata={**observed, "reason": reason},
                    )
                    return
                await asyncio.sleep(2)

        async def cancel(self, context, event_queue):
            from google.protobuf.json_format import MessageToDict

            record = MessageToDict(context.current_task.metadata)
            await asyncio.to_thread(control.request_cancel, record["run_id"])
            await coordinator.request_cancel(record)
            run = await asyncio.to_thread(control.require_run, record["run_id"])
            updater = TaskUpdater(event_queue, context.task_id, context.context_id)
            if run["status"] == "CANCELLED":
                await updater.cancel()
            else:
                await updater.requires_input()

    routes = []
    for agent, binding in bindings.items():
        card = AgentCard(
            name=agent,
            description=f"Governed UuMA agent {agent}",
            version="1.0",
            supported_interfaces=[
                AgentInterface(
                    url=validate_endpoint(binding["endpoint"]) + "/rpc",
                    protocol_binding="JSONRPC",
                    protocol_version="1.0",
                )
            ],
            capabilities=AgentCapabilities(streaming=True, push_notifications=False),
            security_schemes={
                "bearer": SecurityScheme(
                    http_auth_security_scheme=HTTPAuthSecurityScheme(scheme="bearer"),
                )
            },
            security_requirements=[SecurityRequirement(schemes={"bearer": {}})],
            default_input_modes=["text/plain"],
            default_output_modes=["text/plain"],
            skills=[
                AgentSkill(
                    id="assigned-task",
                    name="Assigned UuMA task",
                    description="Execute an existing authorized UuMA Run",
                    tags=["uuma"],
                )
            ],
        )
        handler = LegacyRequestHandler(Executor(agent), DurableTasks(agent), card)
        app = Starlette(
            routes=[
                *create_agent_card_routes(card),
                *create_jsonrpc_routes(handler, rpc_url="/rpc"),
            ]
        )
        routes.append(Mount(f"/agents/{agent}", app=app))

    async def receipts(_request):
        return JSONResponse({"agents": sorted(bindings), "receipts": journal.inspect()})

    routes.append(Route("/receipts", receipts))
    app = Starlette(routes=routes)
    app.state.coordinator = coordinator
    app.add_middleware(AgentAuthentication, tokens=tokens)
    return app


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    control = ControlClient.from_env()
    bindings = {}
    for agent, value in config["agents"].items():
        token = Path(value["runtime_token_file"]).read_text().strip()
        bindings[agent] = {
            **value,
            "adapter": HermesAdapter(
                HermesRunClient(validate_endpoint(value["runtime_url"]), token),
                agent,
            ),
        }
    app_factory = create_app
    if config.get("desktop_connector"):
        from .workstation_node import create_app as workstation_app
        app_factory = workstation_app
    app = app_factory(
        control, NodeJournal(config["journal"]), TokenRegistry(config["token_registry"]), bindings
    )
    uvicorn.run(app, host="127.0.0.1", port=config["port"])


if __name__ == "__main__":
    main()
