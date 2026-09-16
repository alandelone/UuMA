from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class DiagnosticBackend(str, Enum):
    AGY = "agy"
    CODEX = "codex"
    AUTO = "auto"


class RemediationStatus(str, Enum):
    PENDING_USER_APPROVAL = "PENDING_USER_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    APPLIED = "APPLIED"


class IncidentContext(BaseModel):
    incident_id: str = Field(default_factory=lambda: new_id("inc"))
    run_id: str
    task_id: str
    agent_id: str
    error_message: str
    stack_trace: str | None = None
    working_directory: str
    context_files: list[str] = Field(default_factory=list)
    recent_logs: list[str] = Field(default_factory=list)
    occurred_at: datetime = Field(default_factory=utc_now)


class DiagnosticReport(BaseModel):
    incident_id: str
    backend_used: str
    root_cause: str
    impact_analysis: str
    remediation_proposal: str
    unified_diff: str | None = None
    verification_plan: str
    target_files: list[str] = Field(default_factory=list)
    raw_output: str = ""
    duration_seconds: float = 0.0
    created_at: datetime = Field(default_factory=utc_now)


class RemediationProposal(BaseModel):
    remediation_id: str = Field(default_factory=lambda: new_id("rem"))
    incident_id: str
    run_id: str
    agent_id: str
    report: DiagnosticReport
    status: RemediationStatus = RemediationStatus.PENDING_USER_APPROVAL
    target_files: list[str] = Field(default_factory=list)
    user_approval_note: str | None = None
    approved_at: datetime | None = None
    applied_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)


@dataclass(frozen=True)
class DiagnosticSettings:
    allowed_roots: tuple[Path, ...]
    data_dir: Path
    log_dir: Path
    agy_executable: str = "agy"
    codex_executable: str = "codex"
    timeout_seconds: int = 300
    default_backend: DiagnosticBackend = DiagnosticBackend.AUTO

    @classmethod
    def from_env(cls) -> DiagnosticSettings:
        configured_roots = os.environ.get(
            "UUMA_ALLOWED_ROOTS",
            os.environ.get("GEMINI_WORKER_ALLOWED_ROOTS", ""),
        )
        if configured_roots:
            roots = tuple(
                Path(item).expanduser().resolve()
                for item in configured_roots.split(os.pathsep)
                if item.strip()
            )
        else:
            roots = (
                Path.cwd().resolve(),
                Path.home().resolve(),
            )

        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        data_dir = Path(os.environ.get("UUMA_DATA_DIR", local_app_data / "UuMA")).expanduser().resolve()
        log_dir = data_dir / "diagnostics"

        agy_env = os.environ.get("AGY_EXECUTABLE", "")
        if not agy_env:
            local_agy = local_app_data / "agy" / "bin" / "agy.exe"
            agy_env = str(local_agy) if local_agy.is_file() else "agy"

        codex_env = os.environ.get("CODEX_EXECUTABLE", "")
        if not codex_env:
            local_codex = local_app_data / "OpenAI" / "Codex" / "bin" / "codex.exe"
            codex_env = str(local_codex) if local_codex.is_file() else "codex"

        backend_str = os.environ.get("UUMA_DIAGNOSTIC_BACKEND", "auto").strip().lower()
        backend = (
            DiagnosticBackend(backend_str)
            if backend_str in {"agy", "codex", "auto"}
            else DiagnosticBackend.AUTO
        )

        return cls(
            allowed_roots=roots,
            data_dir=data_dir,
            log_dir=log_dir,
            agy_executable=agy_env,
            codex_executable=codex_env,
            timeout_seconds=int(os.environ.get("UUMA_DIAGNOSTIC_TIMEOUT_SECONDS", "300")),
            default_backend=backend,
        )


def _extract_diff(text: str) -> tuple[str | None, list[str]]:
    diff_match = re.search(r"```(?:diff|patch)?\s*\n(--- [^\n]+\n\+\+\+ [^\n]+[\s\S]*?)```", text)
    if diff_match:
        diff_body = diff_match.group(1).strip()
    else:
        raw_match = re.search(r"(--- [a-zA-Z0-9_/\\.-]+\n\+\+\+ [a-zA-Z0-9_/\\.-]+[\s\S]+)", text)
        diff_body = raw_match.group(1).strip() if raw_match else None

    target_files: list[str] = []
    if diff_body:
        for line in diff_body.splitlines():
            if line.startswith("+++ "):
                target = line[4:].strip().removeprefix("b/")
                if target and target != "/dev/null":
                    target_files.append(target)

    return diff_body, target_files


def _extract_section(text: str, heading: str, next_headings: list[str]) -> str:
    pattern = rf"(?i)(?:###?\s*|\*\*\s*){re.escape(heading)}[:\s*]*\n([\s\S]*?)(?=(?:###?\s*|\*\*\s*)(?:{'|'.join(re.escape(h) for h in next_headings)})|\Z)"
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    return ""


class DiagnosticEngine:
    def __init__(self, settings: DiagnosticSettings):
        self.settings = settings
        self.proposals_dir = self.settings.data_dir / "remediations"
        self.proposals_dir.mkdir(parents=True, exist_ok=True)

    def resolve_executable(self, backend: DiagnosticBackend) -> tuple[str, DiagnosticBackend]:
        if backend == DiagnosticBackend.AUTO:
            agy_path = shutil.which(self.settings.agy_executable)
            if agy_path:
                return agy_path, DiagnosticBackend.AGY
            codex_path = shutil.which(self.settings.codex_executable)
            if codex_path:
                return codex_path, DiagnosticBackend.CODEX
            raise FileNotFoundError(
                f"Neither Antigravity CLI ({self.settings.agy_executable}) "
                f"nor Codex CLI ({self.settings.codex_executable}) was found on PATH."
            )

        if backend == DiagnosticBackend.AGY:
            agy_path = shutil.which(self.settings.agy_executable)
            if not agy_path:
                raise FileNotFoundError(f"Antigravity CLI not found: {self.settings.agy_executable}")
            return agy_path, DiagnosticBackend.AGY

        if backend == DiagnosticBackend.CODEX:
            codex_path = shutil.which(self.settings.codex_executable)
            if not codex_path:
                raise FileNotFoundError(f"Codex CLI not found: {self.settings.codex_executable}")
            return codex_path, DiagnosticBackend.CODEX

        raise ValueError(f"Unknown diagnostic backend: {backend}")

    def build_prompt(self, incident: IncidentContext) -> str:
        sections = [
            (
                "You are an autonomous senior diagnostic engineering agent. "
                "An execution run failed in our local multi-agent system. "
                "Analyze the failure root cause, assess impact, and propose a concise, "
                "actionable remediation patch. Do NOT execute destructive commands."
            ),
            f"INCIDENT ID: {incident.incident_id}",
            f"AGENT ID: {incident.agent_id}",
            f"RUN ID: {incident.run_id}",
            f"TASK ID: {incident.task_id}",
            f"WORKING DIRECTORY: {incident.working_directory}",
            f"ERROR MESSAGE:\n{incident.error_message}",
        ]
        if incident.stack_trace:
            sections.append(f"STACK TRACE:\n{incident.stack_trace}")
        if incident.context_files:
            sections.append("RELEVANT FILES:\n" + "\n".join(f"- {f}" for f in incident.context_files))
        if incident.recent_logs:
            sections.append("RECENT LOGS:\n" + "\n".join(f"- {l}" for l in incident.recent_logs[-20:]))

        sections.append(
            "RESPONSE FORMAT REQUIREMENTS:\n"
            "Please structure your response with these exact markdown sections:\n"
            "### Root Cause\n<Concise explanation of the underlying failure>\n\n"
            "### Impact Analysis\n<Assessment of affected components, state, or data>\n\n"
            "### Remediation Proposal\n<Step-by-step description of the recommended fix>\n\n"
            "### Unified Diff\n<Standard unified git diff inside a ```diff code block if code/config changes are required, or None>\n\n"
            "### Verification Plan\n<Command or verification check to run to confirm resolution>"
        )
        return "\n\n".join(sections)

    def parse_report(
        self,
        raw_output: str,
        incident_id: str,
        backend_used: str,
        duration: float,
    ) -> DiagnosticReport:
        try:
            parsed = json.loads(raw_output)
            if isinstance(parsed, dict):
                content = parsed.get("response") or parsed.get("content") or raw_output
            else:
                content = raw_output
        except (json.JSONDecodeError, TypeError):
            content = raw_output

        diff, target_files = _extract_diff(content)
        root_cause = _extract_section(content, "Root Cause", ["Impact Analysis", "Remediation Proposal", "Unified Diff", "Verification Plan"])
        impact = _extract_section(content, "Impact Analysis", ["Remediation Proposal", "Unified Diff", "Verification Plan"])
        proposal = _extract_section(content, "Remediation Proposal", ["Unified Diff", "Verification Plan"])
        verification = _extract_section(content, "Verification Plan", ["Unified Diff", "End"])

        if not root_cause:
            root_cause = content[:400].strip()
        if not proposal:
            proposal = content.strip()
        if not verification:
            verification = "Run test suite and verify agent run restarts without error."

        return DiagnosticReport(
            incident_id=incident_id,
            backend_used=backend_used,
            root_cause=root_cause,
            impact_analysis=impact or "Local execution failure; state remains contained.",
            remediation_proposal=proposal,
            unified_diff=diff,
            target_files=target_files,
            verification_plan=verification,
            raw_output=raw_output,
            duration_seconds=duration,
        )

    def _verify_working_directory(self, cwd_str: str) -> Path:
        cwd = Path(cwd_str).expanduser().resolve()
        if not cwd.is_dir():
            raise NotADirectoryError(f"Working directory does not exist: {cwd}")
        if not any(cwd == root or cwd.is_relative_to(root) for root in self.settings.allowed_roots):
            raise PermissionError(f"Working directory {cwd} is outside allowed roots.")
        return cwd

    def run_diagnostics(
        self,
        incident: IncidentContext,
        backend: DiagnosticBackend = DiagnosticBackend.AUTO,
    ) -> DiagnosticReport:
        cwd = self._verify_working_directory(incident.working_directory)
        executable, selected_backend = self.resolve_executable(backend)
        prompt = self.build_prompt(incident)

        started_at = time.monotonic()
        if selected_backend == DiagnosticBackend.AGY:
            cmd = [
                executable,
                "-p",
                prompt,
                "--mode",
                "plan",
            ]
        else:
            cmd = [
                executable,
                "exec",
                "--sandbox",
                "read-only",
                prompt,
            ]

        try:
            process = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.settings.timeout_seconds,
                check=False,
            )
            duration = round(time.monotonic() - started_at, 3)
            raw = (process.stdout or "").strip()
            if process.returncode != 0 and not raw:
                raw = f"Diagnostic CLI error (exit {process.returncode}):\n{process.stderr.strip()}"
        except subprocess.TimeoutExpired:
            duration = round(time.monotonic() - started_at, 3)
            raw = f"Diagnostic CLI timed out after {self.settings.timeout_seconds} seconds."

        report = self.parse_report(
            raw_output=raw,
            incident_id=incident.incident_id,
            backend_used=selected_backend.value,
            duration=duration,
        )

        log_dir = self.settings.log_dir / f"{datetime.now(UTC):%Y-%m-%d}"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{incident.incident_id}.json"
        log_path.write_text(
            json.dumps(
                {
                    "incident": incident.model_dump(mode="json"),
                    "report": report.model_dump(mode="json"),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return report

    def create_proposal(
        self,
        report: DiagnosticReport,
        incident: IncidentContext,
    ) -> RemediationProposal:
        proposal = RemediationProposal(
            incident_id=incident.incident_id,
            run_id=incident.run_id,
            agent_id=incident.agent_id,
            report=report,
            target_files=report.target_files,
        )
        self.save_proposal(proposal)
        return proposal

    def save_proposal(self, proposal: RemediationProposal) -> None:
        file_path = self.proposals_dir / f"{proposal.remediation_id}.json"
        file_path.write_text(
            json.dumps(proposal.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get_proposal(self, remediation_id: str) -> RemediationProposal | None:
        file_path = self.proposals_dir / f"{remediation_id}.json"
        if not file_path.is_file():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return RemediationProposal.model_validate(data)

    def list_proposals(
        self,
        status: RemediationStatus | None = None,
        agent_id: str | None = None,
    ) -> list[RemediationProposal]:
        results: list[RemediationProposal] = []
        for path in sorted(self.proposals_dir.glob("rem_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                proposal = RemediationProposal.model_validate(data)
                if status is not None and proposal.status != status:
                    continue
                if agent_id is not None and proposal.agent_id != agent_id:
                    continue
                results.append(proposal)
            except (json.JSONDecodeError, ValueError, OSError):
                continue
        return results

    def approve_proposal(
        self,
        remediation_id: str,
        approve: bool,
        note: str = "",
    ) -> RemediationProposal:
        proposal = self.get_proposal(remediation_id)
        if proposal is None:
            raise KeyError(f"Unknown remediation proposal: {remediation_id}")
        if proposal.status != RemediationStatus.PENDING_USER_APPROVAL:
            raise ValueError(f"Proposal {remediation_id} is already in state {proposal.status}")

        proposal.status = RemediationStatus.APPROVED if approve else RemediationStatus.REJECTED
        proposal.user_approval_note = note
        proposal.approved_at = utc_now()
        self.save_proposal(proposal)
        return proposal

    def apply_remediation(
        self,
        remediation_id: str,
        working_directory: str | Path | None = None,
    ) -> dict[str, Any]:
        proposal = self.get_proposal(remediation_id)
        if proposal is None:
            raise KeyError(f"Unknown remediation proposal: {remediation_id}")
        if proposal.status != RemediationStatus.APPROVED:
            raise PermissionError(
                f"Cannot apply proposal {remediation_id}: requires explicit user approval first (current status: {proposal.status})"
            )

        diff = proposal.report.unified_diff
        if not diff:
            proposal.status = RemediationStatus.APPLIED
            proposal.applied_at = utc_now()
            self.save_proposal(proposal)
            return {
                "remediation_id": remediation_id,
                "status": "APPLIED",
                "message": "No code diff was required; remediation recommendation marked applied.",
                "target_files": [],
            }

        cwd = Path(working_directory).resolve() if working_directory else Path.cwd().resolve()
        if not any(cwd == root or cwd.is_relative_to(root) for root in self.settings.allowed_roots):
            raise PermissionError(f"Apply directory {cwd} is outside allowed roots.")

        git_exe = shutil.which("git")
        if not git_exe:
            raise FileNotFoundError("Git executable is required to apply unified diffs.")

        patch_file = self.settings.data_dir / "remediations" / f"{remediation_id}.patch"
        patch_file.write_text(diff + "\n", encoding="utf-8")

        try:
            check_proc = subprocess.run(
                [git_exe, "apply", "--check", str(patch_file)],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
            )
            if check_proc.returncode != 0:
                raise RuntimeError(
                    f"Patch check failed for {remediation_id}:\n{check_proc.stderr or check_proc.stdout}"
                )

            apply_proc = subprocess.run(
                [git_exe, "apply", str(patch_file)],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
            )
            if apply_proc.returncode != 0:
                raise RuntimeError(
                    f"Patch apply failed for {remediation_id}:\n{apply_proc.stderr or apply_proc.stdout}"
                )

            proposal.status = RemediationStatus.APPLIED
            proposal.applied_at = utc_now()
            self.save_proposal(proposal)

            return {
                "remediation_id": remediation_id,
                "status": "APPLIED",
                "target_files": proposal.target_files,
                "verification_plan": proposal.report.verification_plan,
            }
        finally:
            if patch_file.exists():
                patch_file.unlink(missing_ok=True)
