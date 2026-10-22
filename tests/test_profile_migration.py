import json

import pytest
import yaml

from uuma.profile_migration import build, rewrite, without_credentials


def deployment():
    return {
        "python": "/opt/uuma/venv/bin/python",
        "identity_directory": "/opt/uuma/identities",
        "path_mappings": {r"C:\project": "/opt/uuma/source", r"C:\state": "/opt/uuma/data"},
    }


def test_profile_preserves_role_tools_secrets_and_remaps_only_paths(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    soul = "Keep these original approval rules."
    (source / "SOUL.md").write_text(soul)
    (source / "config.yaml").write_text(yaml.safe_dump({
        "model": {"provider": "existing-provider", "default": "existing-model"},
        "mcp_servers": {"uuma-worker": {
            "command": r"C:\project\.venv\python.exe", "args": ["-m", "uuma.mcp_worker"],
            "env": {"UUMA_DATA_DIR": r"C:\state", "PYTHONPATH": r"C:\project\src"},
            "include_tools": ["get_assignment", "submit_result"],
        }},
    }))
    (source / ".env").write_text('API_KEY="secret # value"\nUUMA_DATA_DIR="C:\\state"\n')
    (source / "auth.json").write_text('{"session":"workstation provider login"}')
    (source / "runtime.json").write_text(json.dumps({"data": r"C:\state\honc.db"}))
    target = tmp_path / "target"
    report = build(source, target, agent="honc", deployment=deployment())
    cfg = yaml.safe_load((target / "config.yaml").read_text())
    assert cfg["model"] == {"provider": "existing-provider", "default": "existing-model"}
    worker = cfg["mcp_servers"]["uuma-worker"]
    assert worker["include_tools"] == ["get_assignment", "submit_result"]
    assert worker["env"]["UUMA_REQUIRE_REMOTE_CONTROL"] == "1"
    assert worker["env"]["UUMA_DATA_DIR"] == "/opt/uuma/data"
    assert 'API_KEY="secret # value"' in (target / ".env").read_text()
    assert not (target / "auth.json").exists()
    assert json.loads((target / "runtime.json").read_text())["data"] == "/opt/uuma/data/honc.db"
    assert (target / "SOUL.md").read_text().startswith(soul)
    assert report["unresolved_windows_paths"] == []
    assert "secret # value" not in json.dumps(report)
    assert report["production_ready"] is False


def test_unknown_windows_dependencies_are_reported_and_not_silently_deleted(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "config.yaml").write_text(yaml.safe_dump({"mcp_servers": {
        "xhs": {"command": r"D:\desktop\python.exe", "args": [r"D:\desktop\xhs.py"]},
    }}))
    report = build(source, tmp_path / "target", agent="wisdom-oldman", deployment=deployment())
    assert "xhs" in report["mcp_names_preserved"]
    assert len(report["unresolved_windows_paths"]) == 2


def test_workstation_agents_cannot_be_moved_by_profile_builder(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        build(tmp_path, tmp_path / "other", agent="scholar", deployment=deployment())


def test_path_rewriting_respects_boundaries_and_specific_overrides():
    assert rewrite(r"C:\project-other\x", deployment()["path_mappings"]) == r"C:\project-other\x"
    assert rewrite(r"C:\project\pythonw.exe", {
        r"C:\project": "/source", r"C:\project\pythonw.exe": "/env/bin/python",
    }) == "/env/bin/python"


def test_profile_transport_redacts_secrets_but_preserves_identity_file_paths():
    required = []
    value = without_credentials({
        "env": {"NOTION_API_KEY": "private", "TELEGRAM_BOT_TOKEN": "private-bot",
                "UUMA_IDENTITY_TOKEN_FILE": "/data/identities/honc.token"},
        "headers": {"Authorization": "Bearer private-header"},
        "model": {"max_tokens": 65536},
        "url": "http://127.0.0.1/view?token=private-query",
    }, required=required)
    serialized = json.dumps(value)
    assert "private" not in serialized
    assert value["env"]["UUMA_IDENTITY_TOKEN_FILE"] == "/data/identities/honc.token"
    assert value["model"]["max_tokens"] == 65536
    assert len(required) == 4
