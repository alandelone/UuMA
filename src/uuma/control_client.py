"""Authenticated control access; remote mode never creates a local control database."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

from .models import (
    AgentDefinition,
    RouteDecision,
    RunRegistration,
    TaskContract,
    VerificationRecord,
)
from .service import (
    ConflictError,
    ContractValidationError,
    ControlPlane,
    ControlPlaneError,
    NotFoundError,
    PolicyDeniedError,
)


def validate_endpoint(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("An HTTP(S) service endpoint is required")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Service endpoint must not contain credentials, query, or fragment")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Plain HTTP is restricted to loopback SSH tunnel endpoints")
    return url.rstrip("/")


def credential() -> tuple[str, str]:
    identity = os.environ.get("UUMA_AGENT_ID", "").strip()
    token_path = os.environ.get("UUMA_IDENTITY_TOKEN_FILE", "").strip()
    token = Path(token_path).read_text(encoding="utf-8").strip() if token_path else ""
    if not identity or not token:
        raise PermissionError("Remote access requires an identity and its scoped token file")
    return identity, token


class ControlClient:
    def __init__(self, base_url: str, identity: str, token: str, *, transport=None) -> None:
        self.base_url = validate_endpoint(base_url)
        self.identity = identity
        self._token = token
        self._transport = transport

    @classmethod
    def from_env(cls) -> ControlClient:
        identity, token = credential()
        return cls(os.environ["UUMA_CONTROL_URL"], identity, token)

    def _actor(self, actor_id: str | None) -> None:
        if actor_id is not None and actor_id != self.identity:
            raise PermissionError("Actor must match the authenticated identity")

    def request(self, method: str, path: str, body: Any = None, *, extra_headers=None) -> Any:
        headers = {"Authorization": f"Bearer {self._token}", "X-Uuma-Identity": self.identity}
        if extra_headers:
            if any(key.lower() in {"authorization", "x-uuma-identity"} for key in extra_headers):
                raise PermissionError(
                    "Additional headers cannot replace the authenticated identity"
                )
            headers.update(extra_headers)
        if self._transport is not None:
            response = self._transport.request(method, path, json=body, headers=headers)
            payload = response.json()
            self._check(response.status_code, payload)
            return payload
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={**headers, "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            try:
                payload = json.load(exc)
            except (ValueError, OSError):
                payload = {"detail": "Control request rejected"}
            self._check(exc.code, payload)
            raise

    @staticmethod
    def _check(status: int, payload: Any) -> None:
        if status < 400:
            return
        error = {
            401: PolicyDeniedError,
            403: PolicyDeniedError,
            404: NotFoundError,
            409: ConflictError,
            422: ContractValidationError,
        }.get(status, ControlPlaneError)
        raise error(str(payload.get("detail", "Control request failed")))

    def create_task(self, contract, *, actor_id):
        self._actor(actor_id)
        return TaskContract.model_validate(
            self.request("POST", "/control/tasks", contract.model_dump(mode="json"))
        )

    def route_task(self, task_id, *, actor_id=None):
        self._actor(actor_id)
        return RouteDecision.model_validate(
            self.request("POST", f"/control/tasks/{quote(task_id, safe='')}/route")
        )

    def approve_task(self, task_id, *, actor_id=None):
        self._actor(actor_id)
        return self.request("POST", f"/control/tasks/{quote(task_id, safe='')}/approve")

    def assign_task(self, task_id, agent_id, *, actor_id=None, user_approved=False):
        self._actor(actor_id)
        return self.request(
            "POST",
            f"/control/tasks/{quote(task_id, safe='')}/assign",
            {"agent_id": agent_id, "user_approved": user_approved},
        )

    def register_direct_run(self, agent_id, contract, *, external_run_ref=None):
        self._actor(agent_id)
        return RunRegistration.model_validate(
            self.request(
                "POST",
                "/worker/runs/direct",
                {"task": contract.model_dump(mode="json"), "external_run_ref": external_run_ref},
            )
        )

    def register_run(self, registration, *, actor_id, takeover=False):
        self._actor(actor_id)
        return RunRegistration.model_validate(
            self.request(
                "POST",
                "/control/runs",
                {"registration": registration.model_dump(mode="json"), "takeover": takeover},
            )
        )

    def require_task(self, task_id):
        prefix = "control" if self.identity == "orchestrator" else "worker"
        return self.request("GET", f"/{prefix}/tasks/{quote(task_id, safe='')}")

    def require_run(self, run_id):
        prefix = "control" if self.identity == "orchestrator" else "worker"
        return self.request("GET", f"/{prefix}/runs/{quote(run_id, safe='')}")

    def list_runs(self, *, status=None, agent_id=None):
        if self.identity != "orchestrator":
            self._actor(agent_id)
            query = urlencode({"status": status}) if status else ""
            return self.request("GET", "/worker/runs" + ("?" + query if query else ""))
        query = urlencode({k: v for k, v in {"status": status, "agent_id": agent_id}.items() if v})
        return self.request("GET", "/control/runs" + ("?" + query if query else ""))

    def list_agents(self):
        return [AgentDefinition.model_validate(a) for a in self.request("GET", "/registry/agents")]

    def report_progress(self, progress, *, actor_id):
        self._actor(actor_id)
        return self.request(
            "POST",
            f"/worker/runs/{quote(progress.run_id, safe='')}/heartbeat",
            progress.model_dump(mode="json"),
        )

    def block_run(self, progress, *, actor_id):
        self._actor(actor_id)
        return self.request(
            "POST",
            f"/worker/runs/{quote(progress.run_id, safe='')}/block",
            progress.model_dump(mode="json"),
        )

    def submit_result(self, result, *, actor_id):
        self._actor(actor_id)
        return self.request(
            "POST",
            f"/worker/runs/{quote(result.run_id, safe='')}/result",
            result.model_dump(mode="json"),
        )["event_type"]

    def propose_operation(self, operation, *, actor_id):
        self._actor(actor_id)
        prefix = "control" if self.identity == "orchestrator" else "worker"
        return self.request("POST", f"/{prefix}/operations", operation.model_dump(mode="json"))

    def approve_operation(self, operation_id, *, actor_id):
        self._actor(actor_id)
        return self.request("POST", f"/control/operations/{quote(operation_id, safe='')}/approve")

    def request_cancel(self, run_id, *, actor_id=None):
        self._actor(actor_id)
        return self.request("POST", f"/control/runs/{quote(run_id, safe='')}/cancel")

    def verification_context(self, run_id):
        return self.request("GET", f"/control/runs/{quote(run_id, safe='')}/verification")

    def verify_result(self, decision, *, actor_id):
        self._actor(actor_id)
        return VerificationRecord.model_validate(
            self.request(
                "POST",
                f"/control/runs/{quote(decision.run_id, safe='')}/verification",
                decision.model_dump(mode="json"),
            )
        )

    def health(self):
        return self.request("GET", "/health")


def control_backend() -> ControlPlane | ControlClient:
    if os.environ.get("UUMA_CONTROL_URL", "").strip():
        return ControlClient.from_env()
    if os.environ.get("UUMA_REQUIRE_REMOTE_CONTROL") == "1":
        raise RuntimeError(
            "Remote control is required; refusing to create a local control database"
        )
    control = ControlPlane()
    control.bootstrap()
    return control
