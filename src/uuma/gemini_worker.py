from __future__ import annotations

import json
import os
import shutil
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
        return cls(
            allowed_roots=roots,
            log_root=log_root,
            executable=os.environ.get("GEMINI_WORKER_EXECUTABLE", "gemini"),
            timeout_seconds=int(os.environ.get("GEMINI_WORKER_TIMEOUT_SECONDS", "600")),
            approval_mode=approval_mode,
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
