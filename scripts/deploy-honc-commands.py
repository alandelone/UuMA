"""Install honc's fixed help command; preserve all life, model and Graph settings."""

from __future__ import annotations

import argparse
import json
import shutil
from copy import deepcopy
from pathlib import Path

from ruamel.yaml import YAML

PLUGIN = "uuma_honc_commands"


def deploy(profile: Path, backup: Path) -> dict:
    if profile.name != "honc" or profile.parent.name != "profiles" or backup.exists():
        raise ValueError("Requires the honc profile and a fresh backup directory")
    config_path = profile / "config.yaml"
    yaml = YAML()
    yaml.preserve_quotes = True
    before = yaml.load(config_path.read_text(encoding="utf-8"))
    after = deepcopy(before)
    plugins = after.setdefault("plugins", {})
    enabled = plugins.setdefault("enabled", [])
    if PLUGIN not in enabled:
        enabled.append(PLUGIN)
    disabled = plugins.setdefault("disabled", [])
    if PLUGIN in disabled:
        disabled.remove(PLUGIN)
    menu = (
        after.setdefault("platforms", {})
        .setdefault("telegram", {})
        .setdefault("extra", {})
        .setdefault("command_menu", {})
    )
    menu["priority"] = list(
        dict.fromkeys(["honc", *menu.get("priority", []), "model", "new", "stop", "help", "status"])
    )
    menu["priority_mode"] = "prepend"
    menu.setdefault("max_commands", 24)
    restored = deepcopy(after)
    for key in ("plugins", "platforms"):
        if key in before:
            restored[key] = before[key]
        else:
            restored.pop(key, None)
    assert restored == before
    assert after.get("mcp_servers") == before.get("mcp_servers")
    assert after.get("model") == before.get("model")
    backup.mkdir(parents=True)
    shutil.copy2(config_path, backup / "config.before.yaml")
    target = profile / "plugins" / PLUGIN
    if target.exists():
        shutil.copytree(target, backup / PLUGIN)
    target.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parents[1] / "integrations/hermes" / PLUGIN
    for name in ("__init__.py", "plugin.yaml"):
        shutil.copy2(source / name, target / name)
    temporary = config_path.with_suffix(".honc-guide.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        yaml.dump(after, stream)
    assert yaml.load(temporary.read_text(encoding="utf-8")) == after
    temporary.replace(config_path)
    receipt = {
        "plugin": PLUGIN,
        "profile": str(profile),
        "backup": str(backup),
        "model_and_mcp_servers_unchanged": True,
        "life_records_changed": False,
    }
    (backup / "deployment.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-home", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(deploy(args.profile_home, args.backup)))
