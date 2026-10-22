from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

AUTHORIZED_AGENTS = {
    "orchestrator",
    "brainstormer",
    "scholar",
    "wisdom-oldman",
    "forge-lab-bot",
}


class GeminiTask(BaseModel):
    task: str = Field(min_length=1, max_length=40_000)
    working_directory: str = Field(min_length=1)
    context: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    expected_output: str = Field(min_length=1, max_length=20_000)
    done_when: str = Field(min_length=1, max_length=20_000)

    @field_validator("context", "constraints")
    @classmethod
    def limit_list(cls, value: list[str]) -> list[str]:
        if len(value) > 100 or any(len(item) > 10_000 for item in value):
            raise ValueError("Too many or excessively long task-package entries.")
        return value


def build_prompt(package: GeminiTask) -> str:
    def section(name: str, values: list[str]) -> str:
        body = "\n".join(f"- {value}" for value in values) if values else "- None supplied"
        return f"{name}:\n{body}"

    return "\n\n".join(
        (
            (
                "You are a stateless worker. Complete only the bounded task below. "
                "Do not broaden the task, make final domain judgments, or rely on prior sessions."
            ),
            f"TASK:\n{package.task}",
            section("CONTEXT", package.context),
            f"WORKING DIRECTORY:\n{package.working_directory}",
            section("CONSTRAINTS", package.constraints),
            f"EXPECTED OUTPUT:\n{package.expected_output}",
            f"DONE WHEN:\n{package.done_when}",
            "Return a concise result and explicitly report warnings and any files created or modified.",
        )
    )


@dataclass(frozen=True)
class GeminiWorkerSettings:
    allowed_roots: tuple[Path, ...]
    log_root: Path
    executable: str = "gemini"
    timeout_seconds: int = 600
    approval_mode: str = "plan"
    backend: str = "gemini_cli"
    model: str = "gemini-3.8-flash-medium"
    reasoning_effort: str = "medium"

    @classmethod
    def from_env(cls) -> GeminiWorkerSettings:
        configured = os.environ.get("GEMINI_WORKER_ALLOWED_ROOTS", "")
        roots = tuple(
            Path(item).expanduser().resolve()
            for item in configured.split(os.pathsep)
            if item.strip()
        )
        if not roots:
            raise RuntimeError("GEMINI_WORKER_ALLOWED_ROOTS must contain at least one directory.")
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        log_root = Path(
            os.environ.get("GEMINI_WORKER_LOG_DIR", local_app_data / "UuMA" / "workers" / "gemini")
        ).expanduser()
        approval_mode = os.environ.get("GEMINI_WORKER_APPROVAL_MODE", "plan").strip()
        if approval_mode not in {"plan", "auto_edit"}:
            raise ValueError("GEMINI_WORKER_APPROVAL_MODE must be 'plan' or 'auto_edit'.")
        backend = os.environ.get("GEMINI_WORKER_BACKEND", "gemini_cli").strip()
        if backend not in {"gemini_cli", "account_pool"}:
            raise ValueError("Unsupported Gemini worker backend")
        executable = os.environ.get("GEMINI_WORKER_EXECUTABLE", "").strip()
        if backend == "account_pool" and (not executable or approval_mode != "plan"):
            raise ValueError("Account-pool worker requires an explicit wrapper and plan mode")
        return cls(
            allowed_roots=roots,
            log_root=log_root,
            executable=executable or "gemini",
            timeout_seconds=int(os.environ.get("GEMINI_WORKER_TIMEOUT_SECONDS", "600")),
            approval_mode=approval_mode,
            backend=backend,
            model=os.environ.get("GEMINI_WORKER_MODEL", "gemini-3.8-flash-medium"),
            reasoning_effort=os.environ.get("GEMINI_WORKER_REASONING_EFFORT", "medium"),
        )


class GeminiWorker:
    def __init__(self, settings: GeminiWorkerSettings):
        self.settings = settings

    def _resolve_working_directory(self, requested: str) -> Path:
        path = Path(requested).expanduser().resolve(strict=True)
        if not path.is_dir():
            raise NotADirectoryError(f"Working directory is not a directory: {path}")
        if not any(path == root or path.is_relative_to(root) for root in self.settings.allowed_roots):
            raise PermissionError("Working directory is outside GEMINI_WORKER_ALLOWED_ROOTS.")
        return path

    def _write_log(self, task_id: str, payload: dict[str, Any]) -> Path:
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        directory = self.settings.log_root / day
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{task_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def run(self, package: GeminiTask, requested_by: str) -> dict[str, Any]:
        if requested_by not in AUTHORIZED_AGENTS:
            raise PermissionError("Gemini Worker requires an authorized Hermes profile identity.")
        cwd = self._resolve_working_directory(package.working_directory)
        if self.settings.backend == "account_pool":
            return self._run_pool(package, requested_by, cwd)
        if self.settings.backend != "gemini_cli":
            raise ValueError("Unsupported worker backend; no implicit fallback")
        executable = shutil.which(self.settings.executable)
        if not executable:
            raise FileNotFoundError(f"Gemini CLI executable not found: {self.settings.executable}")

        task_id = f"gw-{datetime.now(UTC):%Y%m%d}-{uuid.uuid4().hex[:8]}"
        started_at = datetime.now(UTC)
        started_clock = time.monotonic()
        base_log: dict[str, Any] = {
            "task_id": task_id,
            "requested_by": requested_by,
            "started_at": started_at.isoformat(),
            "working_directory": str(cwd),
            "task": package.task,
            "approval_mode": self.settings.approval_mode,
        }
        try:
            process = subprocess.run(
                [
                    executable,
                    "--prompt",
                    build_prompt(package),
                    "--output-format",
                    "json",
                    "--approval-mode",
                    self.settings.approval_mode,
                ],
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.settings.timeout_seconds,
                check=False,
            )
            duration = round(time.monotonic() - started_clock, 3)
            if process.returncode != 0:
                result = {
                    "status": "error",
                    "task_id": task_id,
                    "error": (process.stderr or process.stdout).strip(),
                    "duration_seconds": duration,
                }
            else:
                try:
                    cli_result = json.loads(process.stdout)
                except json.JSONDecodeError as exc:
                    result = {
                        "status": "error",
                        "task_id": task_id,
                        "error": f"Gemini CLI returned invalid JSON: {exc}",
                        "duration_seconds": duration,
                    }
                else:
                    result = {
                        "status": "completed",
                        "task_id": task_id,
                        "result": cli_result.get("response", ""),
                        "stats": cli_result.get("stats") or cli_result.get("usage"),
                        "files_created": [],
                        "files_modified": [],
                        "warnings": [],
                        "duration_seconds": duration,
                    }
        except subprocess.TimeoutExpired:
            result = {
                "status": "error",
                "task_id": task_id,
                "error": f"Gemini CLI exceeded {self.settings.timeout_seconds} seconds.",
                "duration_seconds": round(time.monotonic() - started_clock, 3),
            }

        log_payload = {**base_log, **result, "finished_at": datetime.now(UTC).isoformat()}
        log_path = self._write_log(task_id, log_payload)
        return {**result, "log_path": str(log_path)}

    def _run_pool(self, package: GeminiTask, requested_by: str, cwd: Path) -> dict[str, Any]:
        """Run one native Antigravity plan through the reviewed account-pool wrapper.

        Directory checks retain the original working-directory boundary; they are
        not an OS filesystem sandbox. Native plan mode and terminal sandbox are
        explicit, with no permission bypass, continuation, or automatic replay.
        """
        if self.settings.approval_mode != "plan":
            raise PermissionError("Account-pool worker supports plan mode only")
        if not 1 <= self.settings.timeout_seconds <= 3600:
            raise ValueError("Worker timeout must be between 1 and 3600 seconds")
        if self.settings.reasoning_effort not in {"low", "medium", "high"}:
            raise ValueError("Unsupported worker reasoning effort")
        if not self.settings.model or self.settings.model.startswith("-"):
            raise ValueError("A concrete worker model is required")
        pool_root = os.environ.get("UUMA_AGY_POOL_ROOT", "")
        if not pool_root or not (Path(pool_root) / "pool.json").is_file():
            raise RuntimeError("The existing server account pool must be configured")
        executable = Path(self.settings.executable)
        if not executable.is_absolute() or not executable.is_file():
            raise ValueError("An explicit account-pool wrapper path is required")
        # Refuse a raw agy/gemini binary or a differently configured pool: the
        # wrapper is generated with the pinned pool release and root, then scoped
        # in this profile. Its hash is a deployment binding, not a model input.
        expected_hash = os.environ.get("GEMINI_WORKER_WRAPPER_SHA256", "")
        from hashlib import sha256

        wrapper_hash = sha256(executable.read_bytes()).hexdigest()
        if not expected_hash or wrapper_hash != expected_hash:
            raise PermissionError("Worker account-pool wrapper does not match its release binding")
        task_id = f"gw-{datetime.now(UTC):%Y%m%d}-{uuid.uuid4().hex[:8]}"
        started_at = datetime.now(UTC)
        started_clock = time.monotonic()
        command = [str(executable), "--output-format", "json", "--disable-slash-commands",
                   "--mode", "plan", "--sandbox", "--model", self.settings.model,
                   "--effort", self.settings.reasoning_effort,
                   "--print-timeout", f"{self.settings.timeout_seconds}s"]
        kwargs: dict[str, Any] = {"start_new_session": True} if os.name != "nt" else {
            "creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
        }
        result: dict[str, Any]
        process = None
        try:
            process = subprocess.Popen(
                command, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", **kwargs,
            )
            stdout, _stderr = process.communicate(
                build_prompt(package) + "\n", timeout=self.settings.timeout_seconds,
            )
            if process.returncode:
                result = {"status": "blocked" if process.returncode == 75 else "error",
                          "error": "Account-pool worker did not complete",
                          "exit_code": process.returncode}
            else:
                payload = json.loads(stdout)
                if not isinstance(payload, dict) or payload.get("is_error") or payload.get("error"):
                    raise ValueError("Provider reported an error or unsupported response envelope")
                response = payload.get("response", payload.get("result"))
                if not isinstance(response, str) or not response.strip():
                    raise ValueError("Provider returned no worker result text")
                result = {"status": "completed", "result": response,
                          "stats": payload.get("stats") or payload.get("usage"),
                          "actual_model": payload.get("model"), "files_created": [],
                          "files_modified": [], "warnings": [
                              "Plan-only result; no independent filesystem change audit performed.",
                              "Result requires the requesting Agent's review.",
                          ]}
        except subprocess.TimeoutExpired:
            if process is not None:
                self._stop_pool_process(process)
            result = {"status": "error", "error": "Account-pool worker exceeded its deadline",
                      "execution_outcome": "requires_reconciliation"}
        except (ValueError, OSError) as error:
            result = {"status": "error", "error": f"Worker response failed: {type(error).__name__}"}
        result.update(task_id=task_id, backend="account_pool", requested_model=self.settings.model,
                      reasoning_effort=self.settings.reasoning_effort,
                      duration_seconds=round(time.monotonic() - started_clock, 3))
        log = self._write_log(task_id, {
            **result, "requested_by": requested_by, "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(), "working_directory": str(cwd),
            "task": package.task, "approval_mode": "plan", "wrapper_sha256": wrapper_hash,
        })
        return {**result, "log_path": str(log)}

    @staticmethod
    def _stop_pool_process(process: subprocess.Popen) -> None:
        # Stop this owned process group, including a provider child holding an
        # account lease. Killing only the wrapper could leave inference running.
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, timeout=20, check=False)
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=10)
