from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_uuma_control_guard import PLUGIN

from uuma import mcp_worker


@pytest.fixture(autouse=True)
def isolated_guard(monkeypatch):
    PLUGIN._SESSIONS.clear()
    PLUGIN._CONTEXT = None
    monkeypatch.setattr(PLUGIN, "_profile", lambda: "brainstormer")
    yield
    PLUGIN._SESSIONS.clear()
    PLUGIN._CONTEXT = None


def test_assigned_runtime_uses_original_run_without_registering_another():
    context = Mock()
    context.call_mcp.side_effect = [
        {"ok": True, "result": {"task_id": "task", "runtime_binding": {
            "authorized": True, "run_id": "run", "execution_epoch": 1, "agent_id": "brainstormer",
        }}},
        {"ok": True, "result": []},
    ]
    PLUGIN._CONTEXT = context
    guidance = PLUGIN._health_context(
        session_id="uuma-assigned:task:run:1", turn_id="one", user_message="Compare options",
    )
    assert '"run_id": "run"' in guidance["context"]
    assert PLUGIN._state("uuma-assigned:task:run:1").direct_run_id == "run"
    assert all(call.args[1] != "register_direct_run" for call in context.call_mcp.call_args_list)


def test_invalid_or_unavailable_assignment_blocks_domain_tools_and_direct_fallback():
    PLUGIN._CONTEXT = Mock()
    PLUGIN._CONTEXT.call_mcp.return_value = {"ok": False}
    session = {"session_id": "uuma-assigned:task:run:1"}
    assert "authorization failed" in PLUGIN._health_context(**session)["context"]
    assert PLUGIN._pre_tool_call("mcp__uuma_worker__submit_result", {}, **session)["action"] == "block"
    assert PLUGIN._pre_tool_call(
        "mcp__uuma_worker__register_direct_run", {}, **session,
    )["action"] == "block"


@pytest.mark.parametrize("status,epoch,current", [
    ("PAUSED", 1, "run"), ("RUNNING", 2, "run"), ("RUNNING", 1, "new-run"),
])
def test_worker_binding_rejects_paused_and_superseded_executions(monkeypatch, status, epoch, current):
    control = SimpleNamespace(
        require_task=lambda task_id: {"assignee": "brainstormer", "current_run_id": current,
                                      "execution_epoch": epoch},
        require_run=lambda run_id: {"task_id": "task", "agent_id": "brainstormer",
                                    "execution_epoch": epoch, "status": status},
    )
    monkeypatch.setattr(mcp_worker, "_control_plane", lambda: control)
    monkeypatch.setattr(mcp_worker, "_agent_id", lambda: "brainstormer")
    with pytest.raises(PermissionError, match="stale, paused"):
        mcp_worker.get_assignment("task", "run", 1)


def test_forge_native_paths_keep_traversal_and_case_boundaries(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("FORGE_LAB_PROJECT_ROOTS", str(root))
    assert PLUGIN._is_allowed_forge_file_path(str(root / "design.md"))
    assert not PLUGIN._is_allowed_forge_file_path(str(root / "../outside.md"))
    if PLUGIN.os.name != "nt":
        assert not PLUGIN._is_allowed_forge_file_path("C:/Windows/System32/cmd.exe")
        assert not PLUGIN._is_allowed_forge_file_path(str(tmp_path / "PROJECT/design.md"))
