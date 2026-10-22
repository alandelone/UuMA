"""Install Wisdom-Oldman's read-only command plugin with a raw rollback backup."""

from __future__ import annotations

import argparse
import json
import shutil
from copy import deepcopy
from pathlib import Path

import yaml


def deploy(profile: Path, backup: Path) -> dict:
    if profile.name != "wisdom-oldman" or backup.exists():
        raise ValueError("Requires Wisdom-Oldman profile and a fresh backup")
    config_path = profile / "config.yaml"
    before = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    after = deepcopy(before)
    name = "uuma_wisdom_commands"
    plugins = after.setdefault("plugins", {})
    plugins["enabled"] = list(dict.fromkeys([*plugins.get("enabled", []), name]))
    plugins["disabled"] = [item for item in plugins.get("disabled", []) if item != name]
    plugins.setdefault("entries", {})[name] = {"mcp_allowlist": ["wisdom-knowledge"]}
    menu = (
        after.setdefault("platforms", {})
        .setdefault("telegram", {})
        .setdefault("extra", {})
        .setdefault("command_menu", {})
    )
    menu["priority"] = list(
        dict.fromkeys(
            [
                "progress",
                "topics",
                "wisdom",
                *menu.get("priority", []),
                "model",
                "new",
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
    temporary = config_path.with_suffix(".progress.tmp")
    temporary.write_text(
        yaml.safe_dump(after, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    assert yaml.safe_load(temporary.read_text(encoding="utf-8")) == after
    temporary.replace(config_path)
    result = {
        "profile": str(profile),
        "plugin": name,
        "read_only": True,
        "model_and_mcp_servers_unchanged": before.get("model") == after.get("model")
        and before.get("mcp_servers") == after.get("mcp_servers"),
    }
    (backup / "deployment.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-home", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(deploy(args.profile_home, args.backup)))
