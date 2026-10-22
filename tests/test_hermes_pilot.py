"""Isolation contracts for the server pilot; no real model or Telegram calls."""

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

spec = importlib.util.spec_from_file_location(
    "hermes_pilot", Path(__file__).parents[1] / "scripts" / "prepare-hermes-pilot.py"
)
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


@pytest.fixture
def inputs(tmp_path):
    profile, content, plugins = (tmp_path / name for name in ("profile", "content", "plugins"))
    for path in (profile, content, plugins):
        path.mkdir()
    config = {
        "model": {"provider": "antigravity-oauth", "default": "example"},
        "agent": {"max_turns": 150},
        "mcp_servers": {"uuma-worker": {
            "command": "/pinned/python", "args": ["-m", "uuma.mcp_worker"],
            "env": {"UUMA_REQUIRE_REMOTE_CONTROL": "1",
                    "UUMA_CONTROL_URL": "http://127.0.0.1:8765",
                    "UUMA_IDENTITY_TOKEN_FILE": "/private/brainstormer.token"},
            "tools": {"include": sorted(pilot.READ_TOOLS | {"register_direct_run", "write"})},
        }, "gemini-worker": {"command": "/not-ready"}},
    }
    (profile / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    (profile / "SOUL.md").write_text("Original role 原有角色", encoding="utf-8")
    provider = profile / "plugins" / "antigravity-oauth"
    provider.mkdir(parents=True)
    (provider / "__init__.py").write_text("# reviewed provider\n", encoding="utf-8")
    # These runtime files must never be copied into a fresh pilot.
    (profile / "state.db").write_bytes(b"do not copy session state")
    (profile / "cron").mkdir()
    (profile / "cron" / "jobs.json").write_text("[]", encoding="utf-8")
    (content / "projects").mkdir()
    (content / "projects" / "topic.json").write_text('{"topic":"a"}', encoding="utf-8")
    for name in pilot.PLUGINS:
        path = plugins / name
        path.mkdir()
        (path / "__init__.py").write_text("# approved overlay\n", encoding="utf-8")
    return profile, content, plugins, tmp_path / "pilot"


def test_isolated_profile_preserves_role_and_source(inputs):
    before = pilot.inventory(inputs[0])
    result = pilot.prepare(*inputs)
    target = inputs[3] / "home" / "profiles" / "brainstormer"
    assert (target / "SOUL.md").read_bytes() == (inputs[0] / "SOUL.md").read_bytes()
    assert pilot.inventory(inputs[0]) == before
    assert not (target / "state.db").exists()
    assert not (target / "cron").exists()
    assert not (inputs[3] / "data" / "uuma.db").exists()
    assert result["telegram_enabled"] is False
    assert result["production_active"] is False
    assert result["model_invoked"] is False
    config = yaml.safe_load((target / "config.yaml").read_text(encoding="utf-8"))
    assert list(config["mcp_servers"]) == ["uuma-worker"]
    worker = config["mcp_servers"]["uuma-worker"]
    assert set(worker["tools"]["include"]) == pilot.READ_TOOLS
    assert worker["env"]["UUMA_DATA_DIR"] == str(inputs[3] / "data")
    assert config["platforms"]["telegram"]["enabled"] is False
    assert config["platforms"]["api_server"]["enabled"] is False
    assert config["platform_toolsets"]["api_server"] == []
    assert config["security"]["allow_lazy_installs"] is False
    root_config = yaml.safe_load((inputs[3] / "home" / "config.yaml").read_text())
    assert root_config["security"]["allow_lazy_installs"] is False
    assert (inputs[3] / "home/plugins/antigravity-oauth/__init__.py").is_file()
    assert (inputs[3] / "data" / "brainstormer" / "projects" / "topic.json").is_file()
    assert "gemini-worker" in result["deferred_dependencies"]


def test_distinct_private_runtime_keys_never_enter_receipt(inputs):
    pilot.prepare(*inputs)
    root = inputs[3]
    a = (root / "identities" / "gateway.token").read_text().strip()
    b = (root / "identities" / "brainstormer.token").read_text().strip()
    assert a != b and min(len(a), len(b)) >= 32
    receipt = (root / "preparation.json").read_text()
    assert a not in receipt and b not in receipt
    assert json.loads(receipt)["kind"] == "isolated-read-only-pilot"


@pytest.mark.parametrize("filename", [".env", "auth.json", "oauth-token"])
def test_reject_credentials_before_writing(inputs, filename):
    (inputs[0] / filename).write_text("secret", encoding="utf-8")
    with pytest.raises(ValueError, match="Credential"):
        pilot.prepare(*inputs)
    assert not inputs[3].exists()


def test_refuses_overwrite_and_missing_remote_control(inputs):
    config_file = inputs[0] / "config.yaml"
    original = config_file.read_text(encoding="utf-8")
    config = yaml.safe_load(original)
    config["mcp_servers"]["uuma-worker"]["env"]["UUMA_REQUIRE_REMOTE_CONTROL"] = "0"
    config_file.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="authoritative control"):
        pilot.prepare(*inputs)
    assert not inputs[3].exists()
    config_file.write_text(original, encoding="utf-8")
    pilot.prepare(*inputs)
    with pytest.raises(ValueError, match="already exists"):
        pilot.prepare(*inputs)
