"""Orchestrator handoff between accepted Graph Actions and UuMA task/run receipts.

Project acceptance belongs to the user in Yonc. This adapter neither starts a
model nor verifies project completion, and never holds user-review credentials.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .models import TaskContract, VerificationDecision
from .service import ConflictError, ControlPlane, PolicyDeniedError


class YoncAssignmentClient:
    def __init__(self, base_url: str, token: str) -> None:
        if not token.strip():
            raise ValueError("YONC_ORCHESTRATOR_TOKEN is required for assignment handoff.")
        self.base_url = base_url.rstrip("/")
        self.token = token

    @classmethod
    def from_env(cls) -> YoncAssignmentClient:
        return cls(
            os.getenv("YONC_API_URL", "http://127.0.0.1:8766"),
            os.getenv("YONC_ORCHESTRATOR_TOKEN", ""),
        )

    def request(self, path: str, payload: dict | None = None) -> dict:
        request = Request(
            self.base_url + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
            method="POST" if payload is not None else "GET",
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        except HTTPError as exc:
            # Do not put credentials, raw request bodies or remote pages in tool output.
            raise ConflictError(f"Yonc assignment request returned HTTP {exc.code}.") from exc


class YoncAssignmentBridge:
    def __init__(self, control: ControlPlane, client: YoncAssignmentClient) -> None:
        self.control, self.client = control, client

    def _path(self, assignment_id: str) -> str:
        return "/api/v2/assignments/" + quote(assignment_id, safe="")

    def _bind(self, detail: dict, task_id: str, run_id: str | None = None) -> dict:
        assignment = detail["assignment"]
        if assignment["uuma_task_id"] == task_id and (
            not run_id or assignment["uuma_run_id"] == run_id
        ):
            return assignment
        result = self.client.request(
            self._path(assignment["id"]) + "/binding",
            {
                "operation_id": f"bind:{task_id}:{run_id or 'ready'}",
                "expected_revision": assignment["revision"],
                "expected_graph_version": detail["graph_version"],
                "uuma_task_id": task_id,
                "uuma_run_id": run_id,
            },
        )
        return result["assignment"]

    def prepare(self, assignment_id: str) -> dict[str, Any]:
        """Create/route/assign exactly the user's accepted Action; execution starts separately."""
        detail = self.client.request(self._path(assignment_id))
        assignment = detail["assignment"]
        if assignment["state"] not in {"QUEUED", "ASSIGNED"}:
            raise ConflictError("Yonc assignment is not accepted and ready for handoff.")
        if detail.get("blocked_by"):
            raise ConflictError("Graph Action dependencies are not ready for dispatch.")
        if not any(
            row["event_type"] in {"approve", "reopen"} and row["actor"] == "user"
            for row in detail["history"]
        ):
            raise PolicyDeniedError("A persisted user allocation decision is required.")
        scope = f"yonc:{assignment['database_id']}:{assignment_id}:{assignment['dispatch_round']}"
        task = self.control.create_task(
            TaskContract(
                title=assignment["context"]["title"][:240],
                **assignment["task_contract"],
                acceptance_authority="USER",
                external_project_ref=f"yonc://{assignment['database_id']}",
                external_task_ref=f"yonc://{assignment['database_id']}/nodes/{assignment['node_id']}",
                idempotency_key=scope,
            ),
            actor_id="orchestrator",
        )
        decision = self.control.route_task(task.task_id)
        executor = assignment["executor_id"]
        if decision.denied or executor not in decision.candidates:
            raise PolicyDeniedError("Accepted executor does not satisfy the current task contract.")
        if self.control.require_task(task.task_id)["status"] == "PROPOSED":
            # This derives from the exact persisted Graph user decision, not a client boolean.
            self.control.approve_task(task.task_id, actor_id="user")
        current = self.control.require_task(task.task_id)
        if current["status"] in {"TODO", "READY"}:
            self.control.assign_task(task.task_id, executor)
        else:
            raise ConflictError(
                "UuMA execution already exists; synchronize instead of spawning again."
            )
        assignment = self._bind(detail, task.task_id)
        return {
            "task_id": task.task_id,
            "agent_id": executor,
            "status": "READY",
            "assignment": assignment,
            "execution_started": False,
        }

    def sync(self, assignment_id: str) -> dict:
        """Relay current UuMA evidence; a COMPLETED Run still awaits project user review."""
        detail = self.client.request(self._path(assignment_id))
        assignment = detail["assignment"]
        if not assignment["uuma_task_id"]:
            if assignment["state"] == "CANCELLED":
                return detail
            raise ConflictError("Assignment has no UuMA task binding.")
        task = self.control.require_task(assignment["uuma_task_id"])
        expected_ref = f"yonc://{assignment['database_id']}/nodes/{assignment['node_id']}"
        if (
            task["assignee"] != assignment["executor_id"]
            or task["contract"]["external_task_ref"] != expected_ref
        ):
            raise PolicyDeniedError("UuMA execution does not belong to this Graph assignment.")
        if assignment["state"] in {"CANCEL_REQUESTED", "CANCELLED"}:
            if assignment["state"] == "CANCELLED":
                return detail
            cancel = next(
                row
                for row in reversed(detail["history"])
                if row["event_type"] == "cancel" and row["actor"] == "user"
            )
            if not task["current_run_id"]:
                self.control.cancel_unstarted_task(
                    task["task_id"], decision_ref=cancel["operation_id"]
                )
                terminal, run_id = "CANCELLED", None
            else:
                run = self.control.require_run(task["current_run_id"])
                if run["status"] not in {"CANCELLED", "FAILED"}:
                    if run["status"] != "CANCEL_REQUESTED":
                        self.control.request_cancel(run["run_id"])
                    return detail
                terminal, run_id = run["status"], run["run_id"]
            self.client.request(
                self._path(assignment_id) + "/cancellation-receipt",
                {
                    "operation_id": f"cancel:{task['task_id']}",
                    "expected_revision": assignment["revision"],
                    "expected_graph_version": detail["graph_version"],
                    "uuma_task_id": task["task_id"],
                    "uuma_run_id": run_id,
                    "terminal_status": terminal,
                    "note": "UuMA confirmed execution is terminal",
                },
            )
            return self.client.request(self._path(assignment_id))
        if not task["current_run_id"]:
            return detail
        run = self.control.require_run(task["current_run_id"])
        if assignment["state"] == "ACCEPTED":
            delivery = next(
                row
                for row in detail["deliveries"]
                if row["id"] == assignment["accepted_delivery_id"]
            )
            review = next(
                (
                    row
                    for row in reversed(detail["reviews"])
                    if row["delivery_id"] == delivery["id"]
                    and row["reviewer_id"] == "user"
                    and row["decision"] == "accept"
                ),
                None,
            )
            if (
                not review
                or delivery["result_digest"] != run["result_digest"]
                or delivery["uuma_run_id"] != run["run_id"]
            ):
                raise ConflictError("User acceptance no longer matches the current UuMA result.")
            if run["status"] == "REVIEW":
                context = self.control.verification_context(run["run_id"])
                self.control.verify_result(
                    VerificationDecision(
                        run_id=run["run_id"],
                        task_id=task["task_id"],
                        acceptance_digest=context["acceptance_digest"],
                        result_digest=context["result_digest"],
                        approved=True,
                        note=f"Graph user review {review['id']}: {review['note']}",
                    ),
                    actor_id="user",
                )
            return detail
        self._bind(detail, task["task_id"], run["run_id"])
        detail = self.client.request(self._path(assignment_id))
        result = run["result"]
        if not result or result["outcome"] not in {"COMPLETED", "PARTIAL", "NEEDS_REVIEW"}:
            return detail
        current = next(
            (
                row
                for row in detail["deliveries"]
                if row["id"] == detail["assignment"]["current_delivery_id"]
            ),
            None,
        )
        if (
            current
            and current["result_digest"] == run["result_digest"]
            and current["uuma_run_id"] == run["run_id"]
        ):
            return detail
        references = result["artifact_refs"] or [f"uuma://runs/{run['run_id']}/result"]
        artifacts = [
            {
                "uri": ref,
                "label": ref.rsplit("/", 1)[-1] or "Run result",
                "resource_type": "uuma_artifact",
            }
            for ref in references
        ]
        assignment = detail["assignment"]
        self.client.request(
            self._path(assignment_id) + "/deliveries",
            {
                "operation_id": f"result:{run['run_id']}:{run['result_version']}",
                "expected_revision": assignment["revision"],
                "expected_graph_version": detail["graph_version"],
                "executor_id": run["agent_id"],
                "uuma_task_id": task["task_id"],
                "uuma_run_id": run["run_id"],
                "result_digest": run["result_digest"],
                "summary": result["summary"],
                "method": "\n".join(result["structured_rationale"])
                or "No separate method was reported; inspect the submitted result.",
                "artifacts": artifacts,
                "source_refs": task["contract"]["input_refs"],
                "reported_completed_at": result["completed_at"],
            },
        )
        return self.client.request(self._path(assignment_id))
