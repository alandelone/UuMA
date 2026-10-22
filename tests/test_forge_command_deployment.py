import importlib.util
from pathlib import Path

import pytest
import yaml

SOURCE = Path(__file__).parents[1] / "scripts/deploy-forge-commands.py"
SPEC = importlib.util.spec_from_file_location("forge_command_deployment", SOURCE)
assert SPEC and SPEC.loader
DEPLOY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEPLOY)


def test_deployment_preserves_models_mcp_and_other_commands(tmp_path):
    home = tmp_path / "profiles/forge-lab-bot"
    home.mkdir(parents=True)
    original = {
        "model": {"provider": "antigravity-oauth", "default": "gemini-3.8-flash"},
        "plugins": {"enabled": ["existing"], "entries": {"existing": {"x": 7}}},
        "mcp_servers": {"uuma-worker": {"env": {"LAB_DATABASE_PATH": "existing-authority.db"}}},
        "quick_commands": {"existing": {"type": "alias", "target": "/status"}},
        "platforms": {"telegram": {"extra": {"command_menu": {
            "max_commands": 40, "priority": ["existing"],
        }}}},
    }
    before = yaml.safe_dump(original).encode()
    (home / "config.yaml").write_bytes(before)
    DEPLOY.deploy(home, tmp_path / "workspace", tmp_path / "backup")
    current = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    assert current["model"] == original["model"]
    assert current["mcp_servers"] == original["mcp_servers"]
    assert current["plugins"]["entries"]["existing"] == {"x": 7}
    assert current["quick_commands"]["existing"] == original["quick_commands"]["existing"]
    assert current["quick_commands"]["cancel"] == {"type": "alias", "target": "/stop"}
    assert current["platforms"]["telegram"]["extra"]["command_menu"]["max_commands"] == 40
    assert (tmp_path / "backup/config.before.yaml").read_bytes() == before


def test_non_forge_profile_is_rejected_before_any_write(tmp_path):
    with pytest.raises(ValueError, match="only be deployed"):
        DEPLOY.deploy(tmp_path / "yonc", tmp_path, tmp_path / "backup")
    assert not (tmp_path / "backup").exists()
