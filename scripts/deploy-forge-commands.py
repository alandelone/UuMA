"""Install Forge's native command plugin without changing other profile settings."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import yaml


def deploy(profile_home: Path, workspace: Path, backup: Path) -> dict:
    if profile_home.name != "forge-lab-bot":
        raise ValueError("Native Forge commands may only be deployed to forge-lab-bot.")
    source = Path(__file__).resolve().parents[1] / "integrations/hermes/uuma_forge_commands"
    backup.mkdir(parents=True, exist_ok=False)
    config_path = profile_home / "config.yaml"
    before = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    shutil.copy2(config_path, backup / "config.before.yaml")
    target = profile_home / "plugins/uuma_forge_commands"
    if target.exists():
        shutil.copytree(target, backup / "plugin.before")
    target.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "plugin.yaml"):
        shutil.copy2(source / name, target / name)
    expected = copy.deepcopy(before)
    plugins = expected.setdefault("plugins", {})
    enabled = plugins.setdefault("enabled", [])
    if "uuma_forge_commands" not in enabled:
        enabled.append("uuma_forge_commands")
    plugins["disabled"] = [x for x in plugins.get("disabled", []) if x != "uuma_forge_commands"]
    plugins.setdefault("entries", {})["uuma_forge_commands"] = {
        "mcp_allowlist": ["uuma-worker"], "settings": {"workspace_root": str(workspace.resolve())},
    }
    quick = expected.setdefault("quick_commands", {})
    for alias, destination in (("cancel", "/stop"), ("clear", "/new")):
        old = quick.get(alias)
        desired = {"type": "alias", "target": destination}
        if old is not None and old != desired:
            raise ValueError(f"Existing /{alias} quick command differs; preserve and review it.")
        quick[alias] = desired
    menu = expected.setdefault("platforms", {}).setdefault("telegram", {}).setdefault(
        "extra", {}
    ).setdefault("command_menu", {})
    priority = ["forge", "inventory", "projects", "shortages", "worklog", "model", "cancel",
                "stop", "new", "help", "status", "queue"]
    menu["priority"] = list(dict.fromkeys(priority + menu.get("priority", [])))
    menu["priority_mode"] = "prepend"
    menu.setdefault("max_commands", 24)
    payload = yaml.safe_dump(expected, allow_unicode=True, sort_keys=False)
    assert yaml.safe_load(payload) == expected
    config_path.write_text(payload, encoding="utf-8")
    assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == expected
    # Prove all changes outside these explicitly authorized configuration subtrees stayed exact.
    restored = copy.deepcopy(expected)
    for key in ("plugins", "quick_commands", "platforms"):
        if key in before:
            restored[key] = before[key]
        else:
            restored.pop(key, None)
    assert restored == before
    receipt = {"profile": str(profile_home), "backup": str(backup),
               "plugin": "uuma_forge_commands", "registered_commands": priority,
               "telegram_receiver": "Hermes forge-lab-bot", "bridge_enabled": False,
               "other_top_level_settings_preserved": True}
    (backup / "deployment.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-home", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    backup = args.backup or Path(".uuma-local") / (
        "forge-commands-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    )
    print(json.dumps(deploy(args.profile_home, args.workspace, backup), ensure_ascii=False))


if __name__ == "__main__":
    main()
