from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from uuma.diagnostics import (
    DiagnosticBackend,
    DiagnosticEngine,
    DiagnosticReport,
    DiagnosticSettings,
    IncidentContext,
    RemediationStatus,
    _extract_diff,
    _extract_section,
)


@pytest.fixture
def mock_settings(tmp_path: Path) -> DiagnosticSettings:
    data_dir = tmp_path / "uuma_data"
    log_dir = data_dir / "diagnostics"
    return DiagnosticSettings(
        allowed_roots=(tmp_path,),
        data_dir=data_dir,
        log_dir=log_dir,
        agy_executable="agy",
        codex_executable="codex",
        timeout_seconds=60,
        default_backend=DiagnosticBackend.AUTO,
    )


@pytest.fixture
def sample_incident(tmp_path: Path) -> IncidentContext:
    return IncidentContext(
        run_id="run_123",
        task_id="task_456",
        agent_id="forge-lab-bot",
        error_message="ZeroDivisionError: division by zero in BOM price calculation",
        stack_trace="Traceback (most recent call last):\n  File 'calc.py', line 10, in calculate_bom\n    price = total / count\nZeroDivisionError: division by zero",
        working_directory=str(tmp_path),
        context_files=["src/calc.py"],
        recent_logs=["Step 1: Parse BOM", "Step 2: Calculate prices"],
    )


def test_diff_and_section_extraction() -> None:
    sample_output = """
### Root Cause
Division by zero occurs when the BOM part count is 0 because empty rows are not filtered.

### Impact Analysis
The BOM calculation crashes, blocking the As-Built build manifest.

### Remediation Proposal
Add a guard check before dividing by count in `calc.py`.

### Unified Diff
```diff
--- a/src/calc.py
+++ b/src/calc.py
@@ -10,1 +10,3 @@
-    price = total / count
+    if count <= 0:
+        return 0.0
+    price = total / count
```

### Verification Plan
Run `pytest tests/test_calc.py` to ensure zero items return 0.0.
"""
    diff, files = _extract_diff(sample_output)
    assert diff is not None
    assert "--- a/src/calc.py" in diff
    assert "+++ b/src/calc.py" in diff
    assert files == ["src/calc.py"]

    root_cause = _extract_section(sample_output, "Root Cause", ["Impact Analysis", "Remediation Proposal"])
    assert "Division by zero occurs" in root_cause

    impact = _extract_section(sample_output, "Impact Analysis", ["Remediation Proposal", "Unified Diff"])
    assert "BOM calculation crashes" in impact

    proposal = _extract_section(sample_output, "Remediation Proposal", ["Unified Diff", "Verification Plan"])
    assert "Add a guard check" in proposal


def test_build_prompt(mock_settings: DiagnosticSettings, sample_incident: IncidentContext) -> None:
    engine = DiagnosticEngine(mock_settings)
    prompt = engine.build_prompt(sample_incident)
    assert "INCIDENT ID: " in prompt
    assert "AGENT ID: forge-lab-bot" in prompt
    assert "ZeroDivisionError: division by zero" in prompt
    assert "src/calc.py" in prompt
    assert "### Root Cause" in prompt
    assert "### Unified Diff" in prompt


def test_resolve_executable_auto(mock_settings: DiagnosticSettings) -> None:
    engine = DiagnosticEngine(mock_settings)

    with patch("shutil.which") as mock_which:
        mock_which.side_effect = lambda cmd: "/usr/local/bin/agy" if cmd == "agy" else None
        exe, backend = engine.resolve_executable(DiagnosticBackend.AUTO)
        assert exe == "/usr/local/bin/agy"
        assert backend == DiagnosticBackend.AGY

    with patch("shutil.which") as mock_which:
        mock_which.side_effect = lambda cmd: "/usr/local/bin/codex" if cmd == "codex" else None
        exe, backend = engine.resolve_executable(DiagnosticBackend.AUTO)
        assert exe == "/usr/local/bin/codex"
        assert backend == DiagnosticBackend.CODEX

    with (
        patch("shutil.which", return_value=None),
        pytest.raises(FileNotFoundError, match="Neither Antigravity CLI"),
    ):
        engine.resolve_executable(DiagnosticBackend.AUTO)


def test_run_diagnostics_mocked_subprocess(
    mock_settings: DiagnosticSettings, sample_incident: IncidentContext
) -> None:
    engine = DiagnosticEngine(mock_settings)

    simulated_stdout = """### Root Cause
BOM empty list.

### Impact Analysis
Calc fails.

### Remediation Proposal
Check length first.

### Unified Diff
```diff
--- a/src/calc.py
+++ b/src/calc.py
@@ -1 +1,2 @@
+# guarded
```

### Verification Plan
pytest
"""
    with patch("shutil.which", return_value="/mock/agy"), patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = simulated_stdout
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        report = engine.run_diagnostics(sample_incident, backend=DiagnosticBackend.AGY)

        assert report.backend_used == "agy"
        assert "BOM empty list" in report.root_cause
        assert report.unified_diff is not None
        assert report.target_files == ["src/calc.py"]
        assert (mock_settings.log_dir).exists()


def test_remediation_lifecycle_and_approval_gate(
    mock_settings: DiagnosticSettings, sample_incident: IncidentContext, tmp_path: Path
) -> None:
    engine = DiagnosticEngine(mock_settings)

    report = DiagnosticReport(
        incident_id=sample_incident.incident_id,
        backend_used="agy",
        root_cause="Missing file",
        impact_analysis="Blocked run",
        remediation_proposal="Create missing file",
        unified_diff=None,
        target_files=[],
        verification_plan="Verify run",
    )

    proposal = engine.create_proposal(report, sample_incident)
    assert proposal.status == RemediationStatus.PENDING_USER_APPROVAL

    retrieved = engine.get_proposal(proposal.remediation_id)
    assert retrieved is not None
    assert retrieved.remediation_id == proposal.remediation_id

    # Strictly cannot apply without user approval!
    with pytest.raises(PermissionError, match="requires explicit user approval first"):
        engine.apply_remediation(proposal.remediation_id, working_directory=tmp_path)

    # Approve proposal
    approved = engine.approve_proposal(proposal.remediation_id, approve=True, note="Looks good")
    assert approved.status == RemediationStatus.APPROVED
    assert approved.user_approval_note == "Looks good"

    # Now applying succeeds
    result = engine.apply_remediation(proposal.remediation_id, working_directory=tmp_path)
    assert result["status"] == "APPLIED"

    final = engine.get_proposal(proposal.remediation_id)
    assert final.status == RemediationStatus.APPLIED


def test_apply_unified_diff_git_integration(
    mock_settings: DiagnosticSettings, sample_incident: IncidentContext, tmp_path: Path
) -> None:
    # Initialize a temporary git repository
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "UuMA Test"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@uuma.local"], cwd=tmp_path, check=True, capture_output=True)

    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    calc_file = src_dir / "calc.py"
    calc_file.write_text("def calc(a, b):\n    return a / b\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)

    patch_diff = """--- a/src/calc.py
+++ b/src/calc.py
@@ -1,2 +1,4 @@
 def calc(a, b):
+    if b == 0:
+        return 0
     return a / b
"""

    report = DiagnosticReport(
        incident_id=sample_incident.incident_id,
        backend_used="codex",
        root_cause="Zero division",
        impact_analysis="Run crash",
        remediation_proposal="Guard b == 0",
        unified_diff=patch_diff,
        target_files=["src/calc.py"],
        verification_plan="pytest",
    )

    engine = DiagnosticEngine(mock_settings)
    proposal = engine.create_proposal(report, sample_incident)

    engine.approve_proposal(proposal.remediation_id, approve=True, note="User confirmed")

    apply_result = engine.apply_remediation(proposal.remediation_id, working_directory=tmp_path)
    assert apply_result["status"] == "APPLIED"

    content = calc_file.read_text(encoding="utf-8")
    assert "if b == 0:" in content
    assert "return 0" in content


def test_mcp_control_diagnostics_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from uuma import mcp_control
    from uuma.models import ExecutionClass, RunProgress, RunRegistration, TaskContract

    db_path = tmp_path / "uuma.db"
    monkeypatch.setenv("UUMA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UUMA_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("UUMA_AGENT_ID", "orchestrator")
    monkeypatch.setenv("UUMA_ALLOWED_ROOTS", str(tmp_path))

    mcp_control._control_plane.cache_clear()
    mcp_control._diagnostic_engine.cache_clear()

    cp = mcp_control._control_plane()
    contract = cp.create_task(
        TaskContract(title="Test Task", objective="Failing objective"),
        actor_id="orchestrator",
    )
    cp.assign_task(contract.task_id, "forge-lab-bot", actor_id="orchestrator")
    run = cp.register_run(
        RunRegistration(
            task_id=contract.task_id,
            agent_id="forge-lab-bot",
            execution_class=ExecutionClass.INTERACTIVE,
            source="orchestrator",
        ),
        actor_id="orchestrator",
    )
    cp.block_run(
        RunProgress(
            run_id=run.run_id,
            task_id=contract.task_id,
            agent_id="forge-lab-bot",
            blocker="Component catalog bridge offline",
        ),
        actor_id="forge-lab-bot",
    )

    with patch.object(mcp_control._diagnostic_engine(), "run_diagnostics") as mock_diag:
        mock_diag.return_value = DiagnosticReport(
            incident_id="inc_mock_123",
            backend_used="agy",
            root_cause="Catalog socket closed",
            impact_analysis="Inventory blocked",
            remediation_proposal="Restart local catalog bridge",
            unified_diff=None,
            verification_plan="Ping catalog",
        )
        diag_res = mcp_control.diagnose_run(run.run_id, backend="agy", working_directory=str(tmp_path))
        assert diag_res["root_cause"] == "Catalog socket closed"
        assert diag_res["user_confirmation_required"] is True
        rem_id = diag_res["remediation_id"]

        fetched = mcp_control.get_remediation(rem_id)
        assert fetched["remediation_id"] == rem_id

        listed = mcp_control.list_remediations()
        assert len(listed) >= 1

        appr = mcp_control.approve_remediation(rem_id, approve=True, note="Confirmed restart")
        assert appr["status"] == "APPROVED"

        applied = mcp_control.apply_remediation(rem_id, working_directory=str(tmp_path))
        assert applied["status"] == "APPLIED"

