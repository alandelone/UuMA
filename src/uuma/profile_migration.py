"""Render separate Linux profile candidates while preserving live role and tool policy."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
from pathlib import Path

import yaml

SERVER_AGENTS = {"brainstormer", "yonc", "honc", "wisdom-oldman", "forge-lab-bot"}
WINDOWS_PATH = re.compile(r"^[A-Za-z]:[/\\]")
NODE_BEGIN = "<!-- uuma-node-placement:start -->"
NODE_END = "<!-- uuma-node-placement:end -->"


def without_credentials(value, path="", required=None):
    """Prepare config for transport before separate server secret provisioning."""
    required = required if required is not None else []
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            field = f"{path}.{key}".strip(".")
            normalized = str(key).casefold()
            secret = (
                normalized in {"token", "password", "secret", "authorization", "cookie",
                               "access_token", "refresh_token", "api_key", "client_secret"}
                or normalized.endswith(("_key", "_token", "_secret", "_password"))
            )
            if secret and child:
                required.append(field)
                result[key] = "${SERVER_SECRET_REQUIRED}"
            else:
                result[key] = without_credentials(child, field, required)
        return result
    if isinstance(value, list):
        return [without_credentials(child, f"{path}[{index}]", required)
                for index, child in enumerate(value)]
    if isinstance(value, str) and re.search(
        r"[?&](?:token|key|api_key|secret)=", value, re.IGNORECASE
    ):
        required.append(path)
        return re.sub(r"([?&](?:token|key|api_key|secret)=)[^&#]*",
                      r"\1SERVER_SECRET_REQUIRED", value, flags=re.IGNORECASE)
    return value


def rewrite(value, mappings: dict[str, str]):
    if isinstance(value, dict):
        return {
            key: ":".join(rewrite(part, mappings) for part in item.split(";"))
            if key == "GEMINI_WORKER_ALLOWED_ROOTS" and isinstance(item, str)
            else rewrite(item, mappings)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [rewrite(item, mappings) for item in value]
    if not isinstance(value, str) or not WINDOWS_PATH.match(value):
        return value
    normalized = re.sub(r"/+", "/", value.replace("\\", "/"))
    for old, new in sorted(mappings.items(), key=lambda pair: len(pair[0]), reverse=True):
        old = re.sub(r"/+", "/", old.replace("\\", "/")).rstrip("/")
        if normalized.casefold() == old.casefold():
            return new.rstrip("/")
        if normalized.casefold().startswith(old.casefold() + "/"):
            return new.rstrip("/") + normalized[len(old):]
    return value


def unresolved_paths(value, path="") -> list[str]:
    if isinstance(value, dict):
        return [item for key, child in value.items()
                for item in unresolved_paths(child, f"{path}.{key}".strip("."))]
    if isinstance(value, list):
        return [item for index, child in enumerate(value)
                for item in unresolved_paths(child, f"{path}[{index}]" )]
    return [path] if isinstance(value, str) and WINDOWS_PATH.match(value) else []


def build(source: Path, destination: Path, *, agent: str, deployment: dict) -> dict:
    if agent not in SERVER_AGENTS:
        raise ValueError("Workstation profiles are outside the five-Agent migration scope")
    source, destination = source.resolve(), destination.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("Profile candidates must be separate from their source baseline")
    if destination.exists():
        raise FileExistsError("Profile candidate already exists")
    original = yaml.safe_load((source / "config.yaml").read_text(encoding="utf-8-sig"))
    config = rewrite(copy.deepcopy(original), deployment["path_mappings"])
    required_services = []
    for name, server in config.get("mcp_servers", {}).items():
        old_server = original["mcp_servers"][name]
        if name in deployment.get("desktop_mcp", {}):
            # Transport changes cannot expand or discard the original tool filters.
            transport = deployment["desktop_mcp"][name]
            for key in transport:
                if key not in {"command", "args", "url", "env", "headers"}:
                    raise ValueError("Desktop routing may only change MCP transport settings")
            for key in ["command", "args", "url", "env", "headers"]:
                server.pop(key, None)
            server.update(copy.deepcopy(transport))
            required_services.append(name)
        args = old_server.get("args", [])
        if len(args) >= 2 and args[0] == "-m" and args[1].startswith("uuma."):
            if name not in deployment.get("desktop_mcp", {}):
                server["command"] = deployment["python"]
            environment = server.setdefault("env", {})
            environment.update({
                "UUMA_AGENT_ID": agent,
                "UUMA_CONTROL_URL": "http://127.0.0.1:8765",
                "UUMA_REQUIRE_REMOTE_CONTROL": "1",
                "UUMA_IDENTITY_TOKEN_FILE": f"{deployment['identity_directory']}/{agent}.token",
            })
        # Filters and descriptive policy belong to the role, not the transport.
        for key in ["include_tools", "exclude_tools", "tools", "enabled"]:
            if server.get(key) != old_server.get(key):
                raise ValueError(f"Migration unexpectedly changed the {name} tool policy")
    unresolved = unresolved_paths(config)
    destination.mkdir(parents=True)
    file_hashes = {}
    for path in source.rglob("*"):
        if not path.is_file() or any(
            part in {"__pycache__", ".git", ".pytest_cache", "node_modules"}
            for part in path.parts
        ):
            continue
        relative = path.relative_to(source)
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError("Profile baselines cannot contain external symlinks")
        # Provider sessions need independent server authorization. Browser state stays local.
        if relative.as_posix() in {"config.yaml", ".env", "auth.json"}:
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        if path.suffix == ".json":
            value = rewrite(json.loads(path.read_text(encoding="utf-8-sig")),
                            deployment["path_mappings"])
            unresolved.extend(unresolved_paths(value, relative.as_posix()))
            target.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        file_hashes[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    (destination / "config.yaml").write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    env_source = source / ".env"
    if env_source.exists():
        lines = []
        for line in env_source.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                candidate = value.strip().strip('"').strip("'")
                if WINDOWS_PATH.match(candidate):
                    mapped = rewrite(candidate, deployment["path_mappings"])
                    line = key + "=" + mapped
            lines.append(line)
        overrides = {
            "UUMA_AGENT_ID": agent, "UUMA_CONTROL_URL": "http://127.0.0.1:8765",
            "UUMA_REQUIRE_REMOTE_CONTROL": "1",
            "UUMA_IDENTITY_TOKEN_FILE": f"{deployment['identity_directory']}/{agent}.token",
        }
        lines = [line for line in lines if line.split("=", 1)[0] not in overrides]
        lines.extend(key + "=" + value for key, value in overrides.items())
        unresolved.extend(unresolved_paths({
            line.split("=", 1)[0]: line.split("=", 1)[1].strip().strip('"').strip("'")
            for line in lines
            if "=" in line and not line.lstrip().startswith("#")
        }, ".env"))
        env_target = destination / ".env"
        env_target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        env_target.chmod(0o600)
    soul = destination / "SOUL.md"
    if soul.exists():
        body = soul.read_text(encoding="utf-8-sig")
        if NODE_BEGIN in body or NODE_END in body:
            raise ValueError("Existing node-placement instructions require explicit reconciliation")
        body += (
            f"\n\n{NODE_BEGIN}\n## Runtime placement\n\n"
            f"This {agent} profile runs on alandelone-server-001 (Linux). "
            "Its role, approvals and tool restrictions above remain authoritative. "
            "Use the configured service paths and MCP tools for server work. "
            "Browser logins and Windows actions belong to the workstation connector. "
            "When it is offline, report a desktop dependency and wait; do not simulate success "
            "or create a replacement local control database.\n"
            f"{NODE_END}\n"
        )
        soul.write_text(body, encoding="utf-8")
    report = {
        "agent_id": agent, "node": "server", "source_file_hashes": file_hashes,
        "mcp_names_preserved": sorted(config.get("mcp_servers", {})),
        "desktop_services_required": required_services,
        "unresolved_windows_paths": sorted(set(unresolved)),
        "provider_authorization_required": True,
        "production_ready": False, "messaging_receiver_started": False,
    }
    (destination / "migration-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--agent", choices=sorted(SERVER_AGENTS), required=True)
    parser.add_argument("--deployment", type=Path, required=True)
    args = parser.parse_args()
    report = build(args.source, args.destination, agent=args.agent, deployment=json.loads(
        args.deployment.read_text(encoding="utf-8")
    ))
    # No credential values are part of this public report.
    print(json.dumps(report))


if __name__ == "__main__":
    main()
