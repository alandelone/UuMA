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
