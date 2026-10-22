"""Prepare an isolated, API-only Brainstormer pilot; never start a bot receiver.

Run with the pinned Hermes Python on the target node. Inputs must be credential-free
profile candidates and a consistent content snapshot. The final profile is untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
from pathlib import Path

import yaml

READ_TOOLS = {
    "get_assignment", "report_progress", "block_run", "submit_result",
    "brainstormer_search_topics", "brainstormer_get_context",
    "brainstormer_get_decision_map", "brainstormer_calculate_capacity",
}
PLUGINS = ("uuma_audit", "uuma_observability", "uuma_control_guard",
           "uuma_brainstormer_commands")


def inventory(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlink input is not supported: {path.name}")
        if not path.is_file():
            continue
        if path.name in {".env", "auth.json"} or "token" in path.name.lower():
            raise ValueError(f"Credential-like input is not allowed: {path.name}")
        if "__pycache__" in path.parts:
            continue
        result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def private_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(text)
    path.chmod(0o600)


def prepare(profile: Path, content: Path, plugins: Path, destination: Path,
            *, port: int = 8772) -> dict:
    if not 1024 <= port <= 65535:
        raise ValueError("Invalid internal API port")
    for path in (profile, content, plugins):
        if not path.is_dir():
            raise ValueError(f"Missing input directory: {path}")
    # Validate every source before writing a candidate or generating credentials.
    before = inventory(profile)
    content_hashes = inventory(content)
    overlays = {name: inventory(plugins / name) for name in PLUGINS}
    if any(not value for value in overlays.values()):
        raise ValueError("All four approved UuMA plugin overlays are required")
    if destination.exists():
        raise ValueError("Pilot destination already exists; never overwrite a runtime")
    if any(destination.resolve().is_relative_to(p.resolve()) for p in (profile, content, plugins)):
        raise ValueError("Pilot destination must be outside the input directories")
    original = yaml.safe_load((profile / "config.yaml").read_text(encoding="utf-8"))
    if "plugins/antigravity-oauth/__init__.py" not in before:
        raise ValueError("The reviewed account-pool provider plugin is required")
    worker = original["mcp_servers"]["uuma-worker"]
    original_tools = worker["tools"]["include"]
    if not READ_TOOLS.issubset(original_tools):
        raise ValueError("Profile tool contract changed; review the pilot allowlist")
    environment = worker["env"]
    if (environment.get("UUMA_REQUIRE_REMOTE_CONTROL") != "1"
            or not environment.get("UUMA_IDENTITY_TOKEN_FILE")
            or environment.get("UUMA_CONTROL_URL") != "http://127.0.0.1:8765"):
        raise ValueError("Pilot requires authenticated node-local authoritative control")
    destination.mkdir(parents=True, mode=0o700)
    home = destination / "home"
    target = home / "profiles" / "brainstormer"
    # Copy files from the validated inventory only: never sessions, cron, or .env.
    allowed = {"config.yaml", "SOUL.md", "AGENTS.md", "provider-pool-binding.json"}
    copied = {}
    for relative, digest in before.items():
        path = Path(relative)
        if relative not in allowed and path.parts[0] not in {"skills", "plugins"}:
            continue
        out = target / path
        out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(profile / path, out)
        copied[relative] = digest
    for name, files in overlays.items():
        for relative in files:
            out = target / "plugins" / name / relative
            out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(plugins / name / relative, out)
    data = destination / "data"
    for relative in content_hashes:
        out = data / "brainstormer" / relative
        out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(content / relative, out)
    config = original
    config["mcp_servers"] = {"uuma-worker": worker}
    worker["env"]["UUMA_DATA_DIR"] = str(data)
    worker["tools"]["include"] = sorted(READ_TOOLS)
    config["platforms"] = {"telegram": {"enabled": False},
                           "api_server": {"enabled": False}}
    config["platform_toolsets"] = {"api_server": []}
    config["stt"] = {"enabled": False}
    config["memory"] = {"memory_enabled": False, "user_profile_enabled": False}
    config["agent"]["max_turns"] = 12
    config["gateway"] = {"api_server": {"max_concurrent_runs": 2}}
    config["security"] = {**config.get("security", {}), "allow_lazy_installs": False}
    (target / "config.yaml").write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    root_config = {
        "model": config["model"], "agent": {"max_turns": 1},
        "gateway": {"multiplex_profiles": True, "max_concurrent_sessions": 2,
                    "api_server": {"max_concurrent_runs": 2}},
        "platforms": {"telegram": {"enabled": False},
                      "api_server": {"enabled": True, "host": "127.0.0.1", "port": port}},
        "platform_toolsets": {"api_server": []}, "mcp_servers": {},
        "memory": {"memory_enabled": False, "user_profile_enabled": False},
        "security": {"allow_lazy_installs": False},
    }
    # Hermes resolves the gateway's default provider during startup, before a
    # named-profile request exists. Register the same reviewed transport there.
    for relative in copied:
        if relative.startswith("plugins/antigravity-oauth/"):
            out = home / relative
            out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(profile / relative, out)
    (home / "config.yaml").write_text(yaml.safe_dump(root_config), encoding="utf-8")
    for name, directory in (("gateway", home), ("brainstormer", target)):
        token = secrets.token_urlsafe(36)
        private_write(destination / "identities" / f"{name}.token", token + "\n")
        private_write(directory / ".env", f"API_SERVER_KEY={token}\n")
    receipt = {
        "schema_version": 1, "kind": "isolated-read-only-pilot", "production_active": False,
        "telegram_enabled": False, "model_invoked": False, "port": port,
        "profile_source": str(profile), "profile_files": copied,
        "plugin_overlays": overlays, "content_files": content_hashes,
        "read_tools": sorted(READ_TOOLS),
        "deferred_dependencies": ["gemini-worker", "notion_kb", "chatgpt-bridge", "telegram"],
        "home": str(home), "data": str(data),
    }
    if (target / "SOUL.md").read_bytes() != (profile / "SOUL.md").read_bytes():
        raise AssertionError("Agent role changed during pilot preparation")
    (destination / "preparation.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    if inventory(profile) != before:
        raise AssertionError("Source profile changed during preparation")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("profile", "content", "plugins", "destination"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8772)
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(prepare(**vars(args))))
