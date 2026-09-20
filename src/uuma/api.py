from __future__ import annotations

import os
from typing import Annotated, Any

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .auth import TokenRegistry
from .models import (
    GraphOperation,
    ResultContract,
    RunProgress,
    RunRegistration,
    TaskContract,
    VerificationDecision,
)
from .service import (
    ConflictError,
    ContractValidationError,
    ControlPlane,
    ControlPlaneError,
    NotFoundError,
    PolicyDeniedError,
)
from .settings import Settings


class AssignRequest(BaseModel):
    agent_id: str
    user_approved: bool = False


class DirectRunRequest(BaseModel):
    task: TaskContract
    external_run_ref: str | None = None


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=4000)


class RegisterRunRequest(BaseModel):
    registration: RunRegistration
    takeover: bool = False


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    control_plane = ControlPlane(settings)
    control_plane.bootstrap()
    tokens = TokenRegistry(settings.token_file())

    app = FastAPI(title="UuMA Control Plane", version="0.1.0")
    app.state.control_plane = control_plane
    app.state.tokens = tokens

    @app.exception_handler(ControlPlaneError)
    async def control_plane_error(_request: Request, exc: ControlPlaneError) -> JSONResponse:
        status_code = {
            NotFoundError: 404,
            PolicyDeniedError: 403,
            ContractValidationError: 422,
            ConflictError: 409,
        }.get(type(exc), 400)
        return JSONResponse(
            status_code=status_code,
            content={"error": exc.__class__.__name__, "detail": str(exc)},
        )

    def require(role: str):
        def dependency(
            authorization: Annotated[str | None, Header()] = None,
            x_uuma_identity: Annotated[str | None, Header()] = None,
        ) -> str:
            if not authorization or not authorization.startswith("Bearer ") or not x_uuma_identity:
                raise HTTPException(status_code=401, detail="Missing UuMA identity or bearer token")
            token = authorization.removeprefix("Bearer ").strip()
            if not tokens.verify(x_uuma_identity, token, role):
                raise HTTPException(status_code=403, detail="Invalid UuMA identity, role, or token")
            return x_uuma_identity

        return dependency

    control_auth = require("control")
    worker_auth = require("worker")
    ingest_auth = require("ingest")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return control_plane.health()

    @app.post("/control/tasks")
    def create_task(task: TaskContract, identity: str = Depends(control_auth)) -> dict[str, Any]:
        return control_plane.create_task(task, actor_id=identity).model_dump(mode="json")

    @app.post("/control/tasks/{task_id}/approve")
    def approve_task(task_id: str, identity: str = Depends(control_auth)) -> dict[str, str]:
        control_plane.approve_task(task_id, actor_id=identity)
        return {"task_id": task_id, "status": "TODO"}

    @app.post("/control/tasks/{task_id}/route")
    def route_task(task_id: str, identity: str = Depends(control_auth)) -> dict[str, Any]:
        return control_plane.route_task(task_id, actor_id=identity).model_dump(mode="json")

    @app.post("/control/tasks/{task_id}/assign")
    def assign_task(
        task_id: str,
        body: AssignRequest,
        identity: str = Depends(control_auth),
    ) -> dict[str, str]:
        control_plane.assign_task(
            task_id,
            body.agent_id,
            actor_id=identity,
            user_approved=body.user_approved,
        )
        return {"task_id": task_id, "agent_id": body.agent_id, "status": "READY"}

    @app.get("/control/runs")
    def list_runs(
        status: str | None = None,
        agent_id: str | None = None,
        _identity: str = Depends(control_auth),
    ) -> list[dict[str, Any]]:
        return control_plane.list_runs(status=status, agent_id=agent_id)

    @app.get("/control/runs/{run_id}")
    def get_run(run_id: str, _identity: str = Depends(control_auth)) -> dict[str, Any]:
        return control_plane.require_run(run_id)

    @app.post("/control/runs")
    def register_run(
        body: RegisterRunRequest,
        identity: str = Depends(control_auth),
    ) -> dict[str, Any]:
        return control_plane.register_run(
            body.registration,
            actor_id=identity,
            takeover=body.takeover,
        ).model_dump(mode="json")

    @app.get("/control/runs/{run_id}/verification")
    def verification_context(
        run_id: str,
        _identity: str = Depends(control_auth),
    ) -> dict[str, Any]:
        return control_plane.verification_context(run_id)

    @app.post("/control/runs/{run_id}/verification")
    def verify_result(
        run_id: str,
        decision: VerificationDecision,
        identity: str = Depends(control_auth),
    ) -> dict[str, Any]:
        if run_id != decision.run_id:
            raise HTTPException(status_code=400, detail="Run ID mismatch")
        return control_plane.verify_result(decision, actor_id=identity).model_dump(mode="json")

    @app.post("/control/runs/{run_id}/cancel")
    def cancel_run(run_id: str, identity: str = Depends(control_auth)) -> dict[str, str]:
        control_plane.request_cancel(run_id, actor_id=identity)
        return {"run_id": run_id, "status": "CANCEL_REQUESTED"}

    @app.post("/control/operations")
    def propose_operation(
        operation: GraphOperation,
        identity: str = Depends(control_auth),
    ) -> dict[str, str]:
        control_plane.propose_operation(operation, actor_id=identity)
        return {"operation_id": operation.operation_id, "status": "PROPOSED"}

    @app.post("/control/operations/{operation_id}/approve")
    def approve_operation(
        operation_id: str,
        identity: str = Depends(control_auth),
    ) -> dict[str, str]:
        control_plane.approve_operation(operation_id, actor_id=identity)
        return {"operation_id": operation_id, "status": "APPROVED"}

    @app.post("/control/operations/{operation_id}/reject")
    def reject_operation(
        operation_id: str,
        body: RejectRequest,
        identity: str = Depends(control_auth),
    ) -> dict[str, str]:
        control_plane.reject_operation(operation_id, reason=body.reason, actor_id=identity)
        return {"operation_id": operation_id, "status": "REJECTED"}

    @app.post("/worker/runs/direct")
    def register_direct_run(
        body: DirectRunRequest,
        identity: str = Depends(worker_auth),
    ) -> dict[str, Any]:
        return control_plane.register_direct_run(
            identity,
            body.task,
            external_run_ref=body.external_run_ref,
        ).model_dump(mode="json")

    @app.get("/worker/tasks/{task_id}")
    def get_assignment(task_id: str, identity: str = Depends(worker_auth)) -> dict[str, Any]:
        task = control_plane.require_task(task_id)
        if task["assignee"] != identity:
            raise HTTPException(status_code=403, detail="Task is assigned to another Agent")
        return task

    @app.post("/worker/runs/{run_id}/heartbeat")
    def heartbeat(
        run_id: str,
        progress: RunProgress,
        identity: str = Depends(worker_auth),
    ) -> dict[str, str]:
        if run_id != progress.run_id:
            raise HTTPException(status_code=400, detail="Run ID mismatch")
        control_plane.report_progress(progress, actor_id=identity)
        return {"run_id": run_id, "status": progress.status.value}

    @app.post("/worker/runs/{run_id}/block")
    def block_run(
        run_id: str,
        progress: RunProgress,
        identity: str = Depends(worker_auth),
    ) -> dict[str, str]:
        if run_id != progress.run_id:
            raise HTTPException(status_code=400, detail="Run ID mismatch")
        control_plane.block_run(progress, actor_id=identity)
        return {"run_id": run_id, "status": "BLOCKED"}

    @app.post("/worker/runs/{run_id}/result")
    def submit_result(
        run_id: str,
        result: ResultContract,
        identity: str = Depends(worker_auth),
    ) -> dict[str, str]:
        if run_id != result.run_id:
            raise HTTPException(status_code=400, detail="Run ID mismatch")
        event_type = control_plane.submit_result(result, actor_id=identity)
        return {"run_id": run_id, "event_type": event_type}

    @app.post("/ingest/hermes")
    def ingest_hermes(
        payload: dict[str, Any],
        identity: str = Depends(ingest_auth),
        x_uuma_profile: Annotated[str | None, Header()] = None,
    ) -> dict[str, bool]:
        created = control_plane.ingest_hermes_event(payload, profile=x_uuma_profile or identity)
        return {"accepted": True, "duplicate": not created}

    return app


def main() -> None:
    uvicorn.run(
        "uuma.api:create_app",
        factory=True,
        host=os.environ.get("UUMA_HOST", "127.0.0.1"),
        port=int(os.environ.get("UUMA_PORT", "8766")),
    )


if __name__ == "__main__":
    main()
