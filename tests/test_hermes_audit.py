from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import Mock

PLUGIN_PATH = Path(__file__).parents[1] / "integrations" / "hermes" / "uuma_audit" / "__init__.py"
SPEC = importlib.util.spec_from_file_location("uuma_audit_test_plugin", PLUGIN_PATH)
assert SPEC and SPEC.loader
PLUGIN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PLUGIN)


def test_multiplexed_home_identifies_specialist(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "default")
    monkeypatch.setitem(
        sys.modules,
        "hermes_constants",
        types.SimpleNamespace(
            get_hermes_home_override=lambda: "C:/Users/user/hermes/profiles/brainstormer"
        ),
    )
    assert PLUGIN._profile() == "brainstormer"


def test_trusted_profile_forwards_exact_research_approval(monkeypatch) -> None:
    run = Mock()
    monkeypatch.setattr(PLUGIN.subprocess, "run", run)
    monkeypatch.setenv("HERMES_PROFILE", "scholar")
    monkeypatch.setenv("RSTV4_ROOT", "C:/research")
    monkeypatch.setenv("RSTV4_PYTHON", "C:/research/.venv/python.exe")

    PLUGIN._capture_research_approval(
        "pre_llm_call",
        {
            "session_id": "session-7",
            "message_id": "message-9",
            "user_message": "APPROVE proposal_123",
        },
    )

    run.assert_called_once()
    call = run.call_args
    assert call.args[0][-8:] == [
        "--root",
        "C:/research",
        "--profile",
        "scholar",
        "--session-id",
        "session-7",
        "--message-id",
        "message-9",
    ]
    assert call.kwargs["input"] == "APPROVE proposal_123"
    assert call.kwargs["check"] is False
    assert call.kwargs["timeout"] == 5


def test_approval_capture_rejects_untrusted_profile_and_extra_text(monkeypatch) -> None:
    run = Mock()
    monkeypatch.setattr(PLUGIN.subprocess, "run", run)
    monkeypatch.setenv("RSTV4_ROOT", "C:/research")
    monkeypatch.setenv("RSTV4_PYTHON", "C:/research/.venv/python.exe")

    monkeypatch.setenv("HERMES_PROFILE", "brainstormer")
    PLUGIN._capture_research_approval("pre_llm_call", {"user_message": "APPROVE proposal_123"})

    monkeypatch.setenv("HERMES_PROFILE", "orchestrator")
    PLUGIN._capture_research_approval(
        "pre_llm_call", {"user_message": "Please APPROVE proposal_123 now"}
    )

    run.assert_not_called()


def test_approval_capture_failure_does_not_block_audit_event(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "scholar")
    monkeypatch.setenv("UUMA_AUDIT_SPOOL", str(tmp_path))
    monkeypatch.setattr(
        PLUGIN,
        "_capture_research_approval",
        Mock(side_effect=RuntimeError("RSTV4 unavailable")),
    )

    PLUGIN._callback("pre_llm_call")(
        session_id="session-8",
        user_message="APPROVE proposal_456",
    )

    events = list(tmp_path.glob("*.json"))
    assert len(events) == 1
