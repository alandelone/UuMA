import json
from unittest.mock import Mock

import pytest

from uuma import librarian_worker as worker


def test_identity_and_remote_authority_are_required(monkeypatch):
    monkeypatch.setenv("UUMA_AGENT_ID", "honc")
    with pytest.raises(PermissionError):
        worker.client()
    monkeypatch.setenv("UUMA_AGENT_ID", "librarian")
    monkeypatch.delenv("UUMA_IDENTITY_TOKEN_FILE", raising=False)
    with pytest.raises(PermissionError):
        worker.client()


def test_stale_assignment_and_cross_agent_progress_rejected(monkeypatch):
    control = Mock()
    monkeypatch.setattr(worker, "client", lambda: control)
    control.require_task.return_value = {
        "assignee": "librarian", "current_run_id": "r", "execution_epoch": 2,
    }
    control.require_run.return_value = {
        "agent_id": "librarian", "task_id": "t", "status": "RUNNING", "execution_epoch": 2,
    }
    with pytest.raises(PermissionError):
        worker.get_assignment("t", "r", 1)
    assert worker.get_assignment("t", "r", 2)["runtime_binding"]["authorized"]
    with pytest.raises(PermissionError):
        worker.report_progress(json.dumps({"run_id": "r", "task_id": "t", "agent_id": "honc"}))
    control.report_progress.assert_not_called()


def test_direct_mutation_is_rejected_before_registration(monkeypatch):
    control = Mock()
    monkeypatch.setattr(worker, "client", lambda: control)
    with pytest.raises(PermissionError):
        worker.register_direct_run(json.dumps({
            "title": "Restore", "objective": "Replace files", "risk_level": "REVERSIBLE",
        }))
    control.register_direct_run.assert_not_called()


def test_no_domain_or_approval_tools_are_exposed():
    import asyncio

    tools = asyncio.run(worker.mcp.list_tools())
    assert {tool.name for tool in tools} == {
        "worker_intake_status", "register_direct_run", "get_assignment",
        "report_progress", "block_run", "submit_result",
    }
