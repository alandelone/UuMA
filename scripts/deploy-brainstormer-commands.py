"""Install only Brainstormer navigation; preserve model, routing and other plugins."""

from __future__ import annotations

import argparse
import json
import shutil
from copy import deepcopy
from pathlib import Path

import yaml
from dotenv import dotenv_values


def deploy(profile: Path, backup: Path) -> dict:
    if profile.name != "brainstormer" or backup.exists():
        raise ValueError("Requires Brainstormer profile and a fresh backup directory")
    root = profile.parents[1]
    settings = dotenv_values(root / ".env")
    owners = str(settings.get("TELEGRAM_ALLOWED_USERS", "")).split(",")
    if len(owners) != 1 or not owners[0].strip().isdigit():
        raise ValueError("An explicit single Telegram owner is required")
    owner = owners[0].strip()
    config_path = profile / "config.yaml"
    before = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    after = deepcopy(before)
    name = "uuma_brainstormer_commands"
    plugins = after.setdefault("plugins", {})
    plugins["enabled"] = list(dict.fromkeys([*plugins.get("enabled", []), name]))
    plugins["disabled"] = [x for x in plugins.get("disabled", []) if x != name]
    plugins.setdefault("entries", {})[name] = {
        "settings": {"owner_id": owner, "chat_id": owner, "state_user_id": "telegram:" + owner}
    }
    menu = (
        after.setdefault("platforms", {})
        .setdefault("telegram", {})
        .setdefault("extra", {})
        .setdefault("command_menu", {})
    )
    menu["priority"] = list(
        dict.fromkeys(
            [
                "topics",
                "brainstorm",
                *menu.get("priority", []),
                "model",
                "new",
                "stop",
                "help",
                "status",
            ]
        )
    )
    menu["priority_mode"] = "prepend"
    menu.setdefault("max_commands", 24)
    unchanged = deepcopy(after)
    for key in ("plugins", "platforms"):
        if key in before:
            unchanged[key] = before[key]
        else:
            unchanged.pop(key, None)
    assert unchanged == before
    backup.mkdir(parents=True)
    shutil.copy2(config_path, backup / "config.before.yaml")
    target = profile / "plugins" / name
    if target.exists():
        shutil.copytree(target, backup / name)
    target.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parents[1] / "integrations/hermes" / name
    for filename in ("__init__.py", "plugin.yaml"):
        shutil.copy2(source / filename, target / filename)
    temporary = config_path.with_suffix(".navigation.tmp")
    temporary.write_text(
        yaml.safe_dump(after, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    assert yaml.safe_load(temporary.read_text(encoding="utf-8")) == after
    temporary.replace(config_path)
    receipt = {
        "profile": str(profile),
        "plugin": name,
        "backup": str(backup),
        "model_and_servers_unchanged": after.get("model") == before.get("model")
        and after.get("mcp_servers") == before.get("mcp_servers"),
    }
    (backup / "deployment.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-home", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(deploy(args.profile_home, args.backup)))
