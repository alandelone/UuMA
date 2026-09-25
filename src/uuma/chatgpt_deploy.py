"""Incremental bridge-only profile installation with a restorable manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from ruamel.yaml import YAML

from .chatgpt_bridge import PERMISSIONS, BridgeStore


def digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def configure(config: dict, agent: str, python: str, source: str, data: str,
              enabled: bool = True, url: str = "http://127.0.0.1:8787"):
    servers = config.setdefault("mcp_servers", {})
    guard = config.setdefault("plugins", {}).setdefault("entries", {}).setdefault(
        "uuma_control_guard", {}
    )
    allowlist = guard.setdefault("mcp_allowlist", [])
    if enabled and agent in PERMISSIONS:
        servers["chatgpt-bridge"] = {
            "command": python, "args": ["-m", "uuma.mcp_chatgpt"],
            "env": {"PYTHONPATH": source, "UUMA_DATA_DIR": data, "UUMA_AGENT_ID": agent,
                    "UUMA_CHATGPT_BRIDGE_URL": url},
            "timeout": 30, "connect_timeout": 30, "idle_timeout_seconds": 0,
        }
        if "chatgpt-bridge" not in allowlist:
            allowlist.append("chatgpt-bridge")
    else:
        servers.pop("chatgpt-bridge", None)
        guard["mcp_allowlist"] = [name for name in allowlist if name != "chatgpt-bridge"]


def deploy(project: Path, data: Path, hermes: Path, *, port: int = 8787):
    profiles = {"orchestrator": hermes}
    profiles.update({a: hermes / "profiles" / a for a in PERMISSIONS if a != "orchestrator"})
    profiles.update(
        {
            agent: hermes / "profiles" / agent
            for agent in ("scholar", "yonc")
            if (hermes / "profiles" / agent / "config.yaml").is_file()
        }
    )
    for home in profiles.values():
        if not (home / "config.yaml").is_file():
            raise ValueError(f"Missing Hermes profile: {home}")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup = data / "backups" / ("chatgpt-bridge-" + stamp)
    backup.mkdir(parents=True)
    if (data / "uuma.db").exists():
        with sqlite3.connect(data / "uuma.db") as source, sqlite3.connect(backup / "uuma.db") as dest:
            source.backup(dest)
    manifest = {
        "created": stamp,
        "files": [],
        "data_dir": str(data),
        "hermes_home": str(hermes),
    }
    yaml = YAML()
    yaml.preserve_quotes = True
    skill = project / "profiles" / "shared" / "chatgpt-consultation" / "SKILL.md"
    for agent, home in profiles.items():
        targets = [home / "config.yaml", home / "skills" / "chatgpt-consultation" / "SKILL.md"]
        records = []
        for target in targets:
            saved = backup / agent / target.relative_to(home)
            existed = target.exists()
            if existed:
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
            record = {
                "target": str(target),
                "backup": str(saved),
                "existed": existed,
                "original_sha256": digest(saved),
            }
            manifest["files"].append(record)
            records.append(record)
        config_path = home / "config.yaml"
        config = yaml.load(config_path.read_text(encoding="utf-8")) or {}
        configure(config, agent, sys.executable, str(project / "src"), str(data),
                  url=f"http://127.0.0.1:{port}")
        with config_path.open("w", encoding="utf-8") as handle:
            yaml.dump(config, handle)
        target_skill = targets[1]
        if agent in PERMISSIONS:
            target_skill.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(skill, target_skill)
        elif target_skill.is_file():
            target_skill.unlink()
        for record in records:
            record["deployed_sha256"] = digest(Path(record["target"]))
    BridgeStore(data / "uuma.db")
    path = backup / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def rollback(manifest_path: Path):
    manifest_path = manifest_path.resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    backup_root = manifest_path.parent.resolve()
    hermes = Path(payload["hermes_home"]).resolve()
    yaml = YAML()
    yaml.preserve_quotes = True
    for record in payload["files"]:
        target = Path(record["target"]).resolve()
        backup = Path(record["backup"]).resolve()
        if hermes not in target.parents or target.name not in {"config.yaml", "SKILL.md"}:
            raise ValueError(f"Unsafe rollback target: {target}")
        if backup_root not in backup.parents:
            raise ValueError(f"Unsafe rollback source: {backup}")
        if target.name == "config.yaml":
            if not backup.is_file() or not target.is_file():
                raise ValueError(f"Missing profile configuration for rollback: {target}")
            if digest(target) == record.get("deployed_sha256"):
                shutil.copy2(backup, target)
                continue
            original = yaml.load(backup.read_text(encoding="utf-8")) or {}
            current = yaml.load(target.read_text(encoding="utf-8")) or {}
            original_servers = original.get("mcp_servers", {})
            current_servers = current.setdefault("mcp_servers", {})
            if "chatgpt-bridge" in original_servers:
                current_servers["chatgpt-bridge"] = original_servers["chatgpt-bridge"]
            else:
                current_servers.pop("chatgpt-bridge", None)
            original_allow = (
                original.get("plugins", {}).get("entries", {})
                .get("uuma_control_guard", {}).get("mcp_allowlist", [])
            )
            current_guard = current.setdefault("plugins", {}).setdefault("entries", {}).setdefault(
                "uuma_control_guard", {}
            )
            current_allow = current_guard.setdefault("mcp_allowlist", [])
            if "chatgpt-bridge" in original_allow and "chatgpt-bridge" not in current_allow:
                current_allow.append("chatgpt-bridge")
            if "chatgpt-bridge" not in original_allow:
                current_guard["mcp_allowlist"] = [
                    name for name in current_allow if name != "chatgpt-bridge"
                ]
            with target.open("w", encoding="utf-8") as handle:
                yaml.dump(current, handle)
        elif digest(target) == record.get("deployed_sha256"):
            if record["existed"]:
                if not backup.is_file():
                    raise ValueError(f"Missing rollback source: {backup}")
                shutil.copy2(backup, target)
            elif target.is_file():
                target.unlink()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--hermes-home", type=Path)
    parser.add_argument("--rollback-manifest", type=Path)
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    if args.rollback_manifest:
        rollback(args.rollback_manifest)
        return
    if not args.project or not args.data_dir or not args.hermes_home:
        parser.error("--project, --data-dir and --hermes-home are required for deployment")
    print(deploy(args.project.resolve(), args.data_dir.resolve(), args.hermes_home.resolve(),
                 port=args.port))


if __name__ == "__main__":
    main()
