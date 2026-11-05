import subprocess
import sys
from pathlib import Path

from ruamel.yaml import YAML

from integrations.hermes.uuma_control_guard import _DIRECT_SPECIALISTS, _DOMAIN_PREFLIGHT


def test_librarian_profile_has_only_scoped_servers_and_guard(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("mcp_servers:\n  inherited:\n    command: other\n", encoding="utf-8")
    script = Path(__file__).parents[1] / "scripts/configure-hermes-profile.py"
    command = [sys.executable, str(script), "--config", str(config), "--role", "worker",
               "--agent-id", "librarian", "--python-exe", sys.executable, "--source-path", str(tmp_path),
               "--data-dir", str(tmp_path / "data"), "--gemini-allowed-roots", str(tmp_path),
               "--control-url", "http://127.0.0.1:8765", "--librarian-mcp-url", "http://127.0.0.1:8788",
               "--identity-token-file", str(tmp_path / "identity.token")]
    subprocess.run(command, check=True, capture_output=True, text=True)
    value = YAML(typ="safe").load(config.read_text(encoding="utf-8"))
    assert set(value["mcp_servers"]) == {"uuma-worker", "uuma-librarian-read"}
    assert value["plugins"]["entries"]["uuma_control_guard"]["mcp_allowlist"] == [
        "uuma-worker", "uuma-librarian-read",
    ]
    read = value["mcp_servers"]["uuma-librarian-read"]
    assert read["args"] == ["-m", "uuma.mcp_librarian"]
    assert read["env"]["UUMA_REMOTE_MCP_URL"] == "http://127.0.0.1:8788"
    assert read["env"]["UUMA_IDENTITY_TOKEN_FILE"] == str(tmp_path / "identity.token")
    assert read["env"]["UUMA_REQUIRE_REMOTE_CONTROL"] == "1"
    assert set(value["mcp_servers"]["uuma-worker"]["tools"]["include"]) == {
        "register_direct_run", "get_assignment", "report_progress", "block_run", "submit_result",
    }
    assert "librarian" in _DIRECT_SPECIALISTS
    assert _DOMAIN_PREFLIGHT["librarian"] == ("uuma-librarian-read", "librarian_get_backup_status")


def test_librarian_profile_rejects_non_loopback_before_mutation(tmp_path):
    config = tmp_path / "config.yaml"
    before = "mcp_servers: {}\n"
    config.write_text(before, encoding="utf-8")
    script = Path(__file__).parents[1] / "scripts/configure-hermes-profile.py"
    result = subprocess.run([sys.executable, str(script), "--config", str(config), "--role", "worker",
                             "--agent-id", "librarian", "--python-exe", sys.executable,
                             "--source-path", str(tmp_path), "--data-dir", str(tmp_path),
                             "--gemini-allowed-roots", str(tmp_path), "--control-url", "http://127.0.0.1:8765",
                             "--librarian-mcp-url", "http://outside.example:8788",
                             "--identity-token-file", str(tmp_path / "identity.token")],
                            capture_output=True, text=True, check=False)
    assert result.returncode != 0 and config.read_text(encoding="utf-8") == before
    assert not config.with_suffix(".yaml.uuma-backup").exists()


def test_librarian_assigned_preflight_checks_authority_then_reads_catalog(monkeypatch):
    from collections import OrderedDict

    from integrations.hermes import uuma_control_guard as guard

    calls = []

    class Context:
        def call_mcp(self, server, tool, arguments, **_kwargs):
            calls.append((server, tool, arguments))
            if tool == "get_assignment":
                return {"ok": True, "result": {
                    "task_id": "task", "runtime_binding": {
                        "run_id": "run", "execution_epoch": 1,
                        "agent_id": "librarian", "authorized": True,
                    },
                    "contract": {"output_schema": {
                        "properties": {"error": {"type": "string"}},
                    }},
                }}
            assert (server, tool, arguments) == (
                "uuma-librarian-read", "librarian_get_backup_status", {},
            )
            return {"ok": True, "result": {"catalog_version": "test-catalog", "sources": []}}

    monkeypatch.setattr(guard, "_profile", lambda: "librarian")
    monkeypatch.setattr(guard, "_CONTEXT", Context())
    monkeypatch.setattr(guard, "_SESSIONS", OrderedDict())
    monkeypatch.delenv("HERMES_KANBAN_TASK", raising=False)
    result = guard._health_context(
        session_id="uuma-assigned:task:run:1", user_message="Read recorded source coverage",
    )
    assert [tool for _, tool, _ in calls] == ["get_assignment", "librarian_get_backup_status"]
    assert guard._SESSIONS["uuma-assigned:task:run:1"].domain_checked is True
    assert "test-catalog" in result["context"]


def test_schema_error_fields_do_not_hide_actual_runtime_errors():
    from integrations.hermes import uuma_control_guard as guard

    schema = {"properties": {"error": {"type": "string"}}}
    assert not guard._contains_error({"ok": True, "result": {"output_schema": schema}})
    assert guard._contains_error({"ok": True, "result": {
        "output_schema": schema, "error": "Execution expired",
    }})
    assert guard._contains_error({"ok": False, "result": {"output_schema": schema}})
