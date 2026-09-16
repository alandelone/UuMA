from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import TaskContract
from .service import ControlPlane


class HermesError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    data: Any
    stdout: str


class HermesKanbanAdapter:
    """Upgrade-safe adapter around Hermes' supported JSON CLI."""

    def __init__(self, executable: str | Path, board: str = "uuma-control") -> None:
        self.executable = str(executable)
        self.board = board

    def initialize_board(self) -> CommandResult:
        listed = self._run_global("boards", "list", "--json", json_expected=True)
        boards = listed.data if isinstance(listed.data, list) else []
        existing = next((board for board in boards if board.get("slug") == self.board), None)
        if existing is not None:
            return CommandResult(listed.command, existing, listed.stdout)
        self._run_global(
            "boards",
            "create",
            self.board,
            "--name",
            "UuMA Control",
            "--description",
            "Durable Hermes execution projection for the UuMA control plane.",
        )
        refreshed = self._run_global("boards", "list", "--json", json_expected=True)
        boards = refreshed.data if isinstance(refreshed.data, list) else []
        created = next((board for board in boards if board.get("slug") == self.board), None)
        if created is None:
            raise HermesError(f"Hermes did not report the newly created board {self.board!r}")
        return CommandResult(refreshed.command, created, refreshed.stdout)

    def create_task(self, task: TaskContract, assignee: str) -> dict[str, Any]:
        body = {
            "uuma_task_id": task.task_id,
            "objective": task.objective,
            "required_capabilities": sorted(task.required_capabilities),
            "risk_level": task.risk_level.value,
            "execution_class": task.execution_class.value,
            "output_schema": task.output_schema,
            "acceptance_checks": task.acceptance_checks,
            "external_project_ref": task.external_project_ref,
            "external_task_ref": task.external_task_ref,
        }
        args = [
            "create",
            task.title,
            "--body",
            json.dumps(body, ensure_ascii=False, separators=(",", ":")),
            "--assignee",
            assignee,
            "--idempotency-key",
            task.idempotency_key or f"uuma:{task.task_id}",
            "--max-retries",
            "3",
            "--created-by",
            "uuma-runtime",
            "--json",
        ]
        return self._run(*args, json_expected=True).data

    def list_tasks(self) -> list[dict[str, Any]]:
        data = self._run("list", "--json", json_expected=True).data
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("tasks", "items", "results"):
                if isinstance(data.get(key), list):
                    return data[key]
        raise HermesError("Unexpected Hermes Kanban list response")

    def show_task(self, task_id: str) -> dict[str, Any]:
        data = self._run("show", task_id, "--json", json_expected=True).data
        if not isinstance(data, dict):
            raise HermesError("Unexpected Hermes Kanban show response")
        return data

    def list_runs(self, task_id: str) -> list[dict[str, Any]]:
        data = self._run("runs", task_id, "--json", json_expected=True).data
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("runs"), list):
            return data["runs"]
        raise HermesError("Unexpected Hermes Kanban runs response")

    def heartbeat(self, task_id: str, note: str) -> None:
        self._run("heartbeat", task_id, "--note", note)

    def block(self, task_id: str, reason: str) -> None:
        self._run("block", task_id, reason)

    def reconcile(self, control_plane: ControlPlane) -> int:
        changed = 0
        for task in self.list_tasks():
            external_id = str(task.get("id") or task.get("task_id") or "")
            if not external_id:
                continue
            if control_plane.record_external_snapshot(
                source="hermes-kanban",
                external_id=external_id,
                snapshot=task,
            ):
                changed += 1
        return changed

    def _run(self, *args: str, json_expected: bool = False) -> CommandResult:
        return self._run_command(
            [self.executable, "kanban", "--board", self.board, *args],
            json_expected=json_expected,
        )

    def _run_global(self, *args: str, json_expected: bool = False) -> CommandResult:
        return self._run_command(
            [self.executable, "kanban", *args],
            json_expected=json_expected,
        )

    @staticmethod
    def _run_command(command: list[str], *, json_expected: bool = False) -> CommandResult:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode != 0:
            raise HermesError(
                f"Hermes command failed ({completed.returncode}): {completed.stderr.strip()}"
            )
        stdout = completed.stdout.strip()
        if not json_expected:
            return CommandResult(command, None, stdout)
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise HermesError(f"Hermes did not return valid JSON: {stdout[:500]}") from exc
        return CommandResult(command, data, stdout)


class HermesRunClient:
    """Client for Hermes' asynchronous, interruptible `/v1/runs` API."""

    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/runs", payload)

    def get(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/runs/{run_id}")

    def stop(self, run_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/runs/{run_id}/stop", {})

    def approve(self, run_id: str, choice: str, *, resolve_all: bool = False) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/runs/{run_id}/approval",
            {"choice": choice, "resolve_all": resolve_all},
        )

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise HermesError(f"Hermes Run API request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise HermesError("Hermes Run API returned a non-object response")
        return payload
