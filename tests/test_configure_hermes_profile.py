from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ruamel.yaml import YAML

SCRIPT = Path(__file__).parents[1] / "scripts" / "configure-hermes-profile.py"


def _configure(
    tmp_path: Path, *, role: str, initial: str = "{}\n", agent_id: str | None = None
) -> dict:
    config = tmp_path / "config.yaml"
    config.write_text(initial, encoding="utf-8")
    command = [
        sys.executable,
        str(SCRIPT),
        "--config",
        str(config),
        "--role",
        role,
        "--agent-id",
        agent_id or ("orchestrator" if role == "control" else "brainstormer"),
        "--python-exe",
        sys.executable,
        "--source-path",
        str(Path(__file__).parents[1] / "src"),
        "--data-dir",
        str(tmp_path / "data"),
        "--gemini-allowed-roots",
        str(tmp_path),
    ]
    if agent_id == "wisdom-oldman":
        command.extend(["--kag-secrets-file", str(tmp_path / ".env")])
    subprocess.run(command, check=True, capture_output=True, text=True)
    return YAML(typ="safe").load(config.read_text(encoding="utf-8"))


def test_control_profile_enables_guard_health_access_and_context_caps(tmp_path) -> None:
    config = _configure(tmp_path, role="control")

    assert "uuma_control_guard" in config["plugins"]["enabled"]
    assert config["plugins"]["entries"]["uuma_control_guard"]["mcp_allowlist"] == [
        "uuma-control"
    ]
    assert config["compression"]["threshold_tokens"] == 48_000
    assert config["compression"]["proactive_prune_tokens"] == 36_000
    assert config["compression"]["idle_compact_after_seconds"] == 1_800
    assert config["mcp_servers"]["uuma-control"]["idle_timeout_seconds"] == 0
    assert "kanban" in config["platform_toolsets"]["cli"]
    assert "kanban" in config["platform_toolsets"]["telegram"]


def test_brainstormer_profile_replaces_inherited_orchestrator_guard_permissions(tmp_path) -> None:
    config = _configure(
        tmp_path,
        role="worker",
        initial=(
            "plugins:\n"
            "  enabled: [uuma_audit, uuma_control_guard]\n"
            "  entries:\n"
            "    uuma_control_guard:\n"
            "      mcp_allowlist: [uuma-control]\n"
        ),
    )

    assert "uuma_control_guard" in config["plugins"]["enabled"]
    assert config["plugins"]["entries"]["uuma_control_guard"]["mcp_allowlist"] == [
        "uuma-worker"
    ]
    assert "uuma-control" not in config["mcp_servers"]


def test_wisdom_profile_enables_direct_run_guard(tmp_path) -> None:
    config = _configure(tmp_path, role="worker", agent_id="wisdom-oldman")
    assert "uuma_control_guard" in config["plugins"]["enabled"]
    assert config["plugins"]["entries"]["uuma_control_guard"]["mcp_allowlist"] == [
        "uuma-worker",
        "wisdom-knowledge",
    ]
    assert "uuma-control" not in config["mcp_servers"]
    knowledge = config["mcp_servers"]["wisdom-knowledge"]
    assert knowledge["env"]["UUMA_KAG_AUTO_RECOVER"] == "true"
    assert knowledge["env"]["UUMA_KAG_IDLE_SECONDS"] == "1800"
    assert knowledge["env"]["UUMA_KAG_SECRETS_FILE"] == str(tmp_path / ".env")
    assert knowledge["timeout"] == 480
    assert config["plugins"]["hook_callback_timeout"] == 450


def test_scholar_profile_enables_rst_v4_preflight(tmp_path) -> None:
    config = _configure(
        tmp_path,
        role="worker",
        agent_id="scholar",
        initial="plugins:\n  enabled: [uuma_control_guard]\n",
    )
    assert "uuma_control_guard" in config["plugins"]["enabled"]
    assert config["plugins"]["entries"]["uuma_control_guard"]["mcp_allowlist"] == [
        "uuma-worker",
        "rstv4-worker",
    ]


def test_forge_profile_enables_worker_preflight(tmp_path) -> None:
    config = _configure(tmp_path, role="worker", agent_id="forge-lab-bot")
    assert "uuma_control_guard" in config["plugins"]["enabled"]
    assert config["plugins"]["entries"]["uuma_control_guard"]["mcp_allowlist"] == [
        "uuma-worker"
    ]


def test_unknown_worker_does_not_inherit_guard(tmp_path) -> None:
    config = _configure(
        tmp_path,
        role="worker",
        agent_id="unknown-worker",
        initial="plugins:\n  enabled: [uuma_control_guard]\n",
    )
    assert "uuma_control_guard" not in config["plugins"]["enabled"]
