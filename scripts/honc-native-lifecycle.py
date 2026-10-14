"""Run under the installed Hermes interpreter and selected honc home."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.executable).resolve().parents[2]))

from cron.jobs import create_job, load_jobs, pause_job, resume_job
from hermes_cli.profiles import get_active_profile_name

action, runtime_path = sys.argv[1], Path(sys.argv[2])
config = json.loads(runtime_path.read_text(encoding="utf-8"))
assert get_active_profile_name() == "honc"
if action == "verify":
    saved_stdout = sys.stdout
    sys.stdout = sys.stderr
    import yaml
    from hermes_cli.plugins import discover_plugins, get_plugin_manager, invoke_hook
    from model_tools import get_tool_definitions
    from tools.mcp_tool_discovery import discover_mcp_tools

    discover_plugins(force=True)
    loaded = [
        value
        for value in get_plugin_manager()._plugins.values()
        if value.manifest.name == "honc_life"
    ]
    assert len(loaded) == 1 and loaded[0].enabled
    role = yaml.safe_load(
        (Path(config["profile_home"]) / "config.yaml").read_text(encoding="utf-8")
    )
    assert set(role["mcp_servers"]) == {"uuma-worker", "honc-execution"}
    expected = {
        "mcp__honc_execution__" + name
        for name in role["mcp_servers"]["honc-execution"]["tools"]["include"]
    }
    discovered = set(discover_mcp_tools())
    actual = {name for name in discovered if name.startswith("mcp__honc_execution__")}
    assert actual == expected and len(actual) == 19, {
        "missing": sorted(expected - actual),
        "extra": sorted(actual - expected),
        "discovered": sorted(discovered),
    }
    assert "mcp__honc_execution__honc_check_habit" not in discovered
    platforms = role.get("platform_toolsets", {})
    checks = {}
    for platform in ("cli", "telegram"):
        toolsets = list(platforms[platform]) + ["uuma-worker", "honc-execution"]
        definitions = get_tool_definitions(enabled_toolsets=toolsets, quiet_mode=True)
        names = {value.get("function", value).get("name") for value in definitions}
        forbidden = {
            "terminal",
            "execute_code",
            "delegate_task",
            "cronjob",
            "write_file",
            "patch_file",
        }
        assert not names.intersection(forbidden), names.intersection(forbidden)
        assert expected.issubset(names), expected - names
        checks[platform] = sorted(names)
    assert any(
        value.get("action") == "block"
        for value in invoke_hook("pre_tool_call", tool_name="skill_manage", args={})
    )
    print(
        json.dumps(
            {
                "profile": "honc",
                "life_plugin_loaded": True,
                "honc_tools": 19,
                "worker_tools": len(discovered - actual),
                "platform_tools": checks,
                "skill_manage_policy": "Hermes skills bundle includes schema; honc host hook blocks execution",
            }
        ),
        file=saved_stdout,
    )
    sys.exit(0)
identifier = config.get("scheduler_job_id")
name = "honc-life-semantic-tick-v1"
existing = [job for job in load_jobs() if job["name"] == name]
if identifier:
    existing = [job for job in existing if job["id"] == identifier]
    if len(existing) != 1:
        raise ValueError("Saved native honc job could not be verified")
if len(existing) > 1:
    raise ValueError("Duplicate native honc jobs; no automatic re-creation")
if action == "prepare":
    if existing:
        job = pause_job(existing[0]["id"], reason="honc life deployment verification")
    else:
        job = create_job(
            None,
            "1m",
            name=name,
            script=str(Path(config["profile_home"]) / "scripts/honc-life-tick.py"),
            no_agent=True,
            deliver="local",
            failure_deliver="local",
            attach_to_session=False,
            paused=True,
            paused_reason="honc life deployment verification",
        )
elif action == "activate":
    if len(existing) != 1:
        raise ValueError("No prepared native honc job")
    job = resume_job(existing[0]["id"])
elif action == "pause":
    job = pause_job(identifier, reason="honc life rollback")
elif action == "status":
    job = existing[0] if len(existing) == 1 else None
else:
    raise ValueError("Unknown native lifecycle action")
assert job is not None
assert job["no_agent"] and job["deliver"] == "local" and job["attach_to_session"] is False
print(
    json.dumps(
        {
            key: job.get(key)
            for key in (
                "id",
                "name",
                "enabled",
                "state",
                "script",
                "next_run_at",
                "last_status",
                "last_error",
            )
        }
    )
)
