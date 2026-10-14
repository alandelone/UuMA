from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ruamel.yaml import YAML

from uuma.auth import TOKEN_ROLES
from uuma.colleague_directory import ROLE_GUIDANCE
from uuma.policy import RiskLevel, default_agents
from uuma.specialist_skills import SPECIALIST_SKILL_ALLOWLISTS

SCRIPT = Path(__file__).parents[1] / "scripts" / "configure-hermes-profile.py"


def test_honc_profile_configuration_via_script(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "mcp_servers:\n"
        "  inherited-tool:\n"
        "    command: custom\n"
        "plugins:\n"
        "  enabled: [uuma_audit]\n",
        encoding="utf-8",
    )
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--config",
        str(config_file),
        "--role",
        "worker",
        "--agent-id",
        "honc",
        "--python-exe",
        sys.executable,
        "--source-path",
        str(Path(__file__).parents[1] / "src"),
        "--data-dir",
        str(tmp_path / "data"),
        "--gemini-allowed-roots",
        str(tmp_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    loaded = YAML(typ="safe").load(config_file.read_text(encoding="utf-8"))

    # Guard plugin
    assert "uuma_control_guard" in loaded["plugins"]["enabled"]
    assert loaded["plugins"]["entries"]["uuma_control_guard"]["mcp_allowlist"] == [
        "uuma-worker",
        "honc-execution",
    ]

    # Only worker and honc-execution servers allowed
    assert set(loaded["mcp_servers"].keys()) == {"uuma-worker", "honc-execution"}
    honc_exec = loaded["mcp_servers"]["honc-execution"]
    assert honc_exec["args"] == ["-m", "uuma.honc.mcp"]

    # Worker tools restricted
    worker_tools = loaded["mcp_servers"]["uuma-worker"]["tools"]["include"]
    assert set(worker_tools) == {
        "register_direct_run",
        "get_assignment",
        "report_progress",
        "block_run",
        "submit_result",
    }
    assert loaded["tools"]["tool_search"]["enabled"] == "off"


def test_honc_in_control_guard_and_preflight() -> None:
    from integrations.hermes.uuma_control_guard import (
        _DIRECT_SPECIALISTS,
        _DOMAIN_PREFLIGHT,
    )

    assert "honc" in _DIRECT_SPECIALISTS
    assert _DOMAIN_PREFLIGHT.get("honc") == ("honc-execution", "honc_status")


def test_honc_auth_and_policy() -> None:
    # Auth token role
    assert TOKEN_ROLES.get("honc") == "worker"

    # Policy agent specification
    agents = default_agents()
    honc_policy = next((a for a in agents if a.agent_id == "honc"), None)
    assert honc_policy is not None
    assert honc_policy.maximum_risk == RiskLevel.REVERSIBLE
    expected_capabilities = {
        "daily_execution",
        "tracing",
        "focus",
        "checkin",
        "habit_tracking",
    }
    assert expected_capabilities.issubset(honc_policy.capabilities)


def test_honc_specialist_skills_and_files() -> None:
    skills = SPECIALIST_SKILL_ALLOWLISTS.get("honc")
    assert skills is not None
    assert "honc-daily-execution" in skills
    assert "honc-tracing" in skills
    assert "honc-focus" in skills
    assert "honc-checkin" in skills

    # Verify actual SKILL.md and SOUL.md files exist
    repo_root = Path(__file__).parents[1]
    soul_file = repo_root / "profiles" / "honc" / "SOUL.md"
    assert soul_file.is_file()
    assert "日常执行与追踪管家" in soul_file.read_text(encoding="utf-8")

    for s in skills:
        skill_doc = repo_root / "profiles" / "honc" / "skills" / s / "SKILL.md"
        assert skill_doc.is_file()
        assert len(skill_doc.read_text(encoding="utf-8").strip()) > 50


def test_honc_colleague_directory_guidance() -> None:
    guidance = ROLE_GUIDANCE.get("honc")
    assert guidance is not None
    assert "日常執行與追蹤管家" in guidance["role"]
    assert any("ACTION" in w for w in guidance["suitable_work"])

