#!/usr/bin/env python3
"""Prepare a desktop node preview; never launch services, Chrome, or model requests."""

from __future__ import annotations

import argparse
import hmac
import json
import sqlite3
import sys
from pathlib import Path

from uuma.auth import TokenRegistry
from uuma.chatgpt_bridge import BridgeStore
from uuma.control_client import validate_endpoint

BRIDGE_TABLES = {
    "chatgpt_accounts", "chatgpt_routes", "chatgpt_threads", "chatgpt_requests", "chatgpt_events",
}


def inspect_bridge(database: Path) -> dict:
    if not database.is_file():
        return {"usable": False, "reason": "BRIDGE_DATABASE_MISSING"}
    try:
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
            if [row[0] for row in db.execute("PRAGMA integrity_check")] != ["ok"]:
                return {"usable": False, "reason": "BRIDGE_DATABASE_CORRUPT"}
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not BRIDGE_TABLES.issubset(tables):
                return {"usable": False, "reason": "BRIDGE_TABLES_MISSING"}
            counts = {name: db.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
                      for name in sorted(BRIDGE_TABLES)}
    except sqlite3.DatabaseError:
        return {"usable": False, "reason": "BRIDGE_DATABASE_UNREADABLE"}
    if database.resolve().name.lower() in {"uuma.db", "state.db", "wisdom.db"}:
        return {"usable": False, "reason": "BRIDGE_REQUIRES_INDEPENDENT_DATABASE", "rows": counts}
    return {"usable": True, "rows": counts}


def prepare(
    destination: Path, *, data_dir: Path, bridge_database: Path, token_registry: Path,
    identity_token_dir: Path, control_url: str, python: Path, source_root: Path,
    port: int = 8770, bridge_port: int = 8787, allow_empty_bridge: bool = False,
) -> dict:
    if destination.exists():
        raise FileExistsError("A desktop preview must use a new destination")
    if not all(1024 <= value <= 65535 for value in (port, bridge_port)) or port == bridge_port:
        raise ValueError("Desktop node and ChatGPT bridge require distinct valid ports")
    control_url = validate_endpoint(control_url)
    data_dir, token_registry = data_dir.resolve(), token_registry.resolve()
    identity_token_dir, bridge_database = identity_token_dir.resolve(), bridge_database.resolve()
    reasons = []
    try:
        if not token_registry.is_file():
            raise ValueError("missing outer registry")
        outer = TokenRegistry(token_registry).load()
        for identity in ("orchestrator", "brainstormer"):
            scoped = (identity_token_dir / (identity + ".token")).read_text(encoding="utf-8").strip()
            if not scoped or not hmac.compare_digest(scoped, outer.get(identity, "")):
                raise ValueError("mismatched scoped identity")
    except (OSError, ValueError):
        reasons.append("OUTER_NODE_AND_CONTROL_CREDENTIALS_UNAVAILABLE")
    old_tokens = data_dir / "tokens.json"
    try:
        if token_registry == old_tokens.resolve():
            raise ValueError("outer registry must be separate from existing local bridge auth")
        inner = TokenRegistry(old_tokens).load()
        if not all(inner.get(identity) for identity in ("orchestrator", "brainstormer")):
            raise ValueError("missing local bridge API credentials")
    except (OSError, ValueError):
        reasons.append("EXISTING_LOCAL_BRIDGE_API_CREDENTIALS_UNAVAILABLE")
    source_status = inspect_bridge(bridge_database)
    history_not_restored = not source_status["usable"]
    if history_not_restored and not allow_empty_bridge:
        reasons.append(source_status["reason"])
    destination.mkdir(parents=True)
    candidate = bridge_database
    if history_not_restored and allow_empty_bridge:
        candidate = destination.resolve() / "state" / "chatgpt.db"
        BridgeStore(candidate)
    receipt = {
        "kind": "workstation-desktop-preview", "services_started": False,
        "model_invoked": False, "credentials_copied": False,
        "status": "BLOCKED" if reasons else "PREPARED",
        "blockers": reasons, "source_bridge": str(bridge_database),
        "source_bridge_status": source_status, "bridge_database": str(candidate),
        "history_not_restored": history_not_restored,
        "account_routes_require_onboarding": history_not_restored,
        "outer_node_token_registry": str(token_registry),
        "control_identity_token_dir": str(identity_token_dir),
        "inner_bridge_api_token_registry": str(old_tokens),
        "browser_and_extension_data_dir": str(data_dir),
        "server_chatgpt_remote_mcp_url": f"http://127.0.0.1:{port}/mcp",
        "desktop_expiry_queue_wired": False,
        "stt_proxy_available": False,
        "offline_policy": "Block the current Run with WORKSTATION_UNAVAILABLE; do not replay a lost response",
    }

    def write(name: str, value: dict) -> None:
        with (destination / name).open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")

    if not reasons:
        config = {
            "desktop_connector": True, "port": port, "agents": {},
            "journal": str(destination.resolve() / "state" / "workstation-node.db"),
            "token_registry": str(token_registry),
        }
        common = {
            "PYTHONPATH": str(source_root.resolve() / "src"),
            "UUMA_DATA_DIR": str(data_dir), "UUMA_CHATGPT_DATABASE_PATH": str(candidate),
            "UUMA_CONTROL_URL": control_url, "UUMA_REQUIRE_REMOTE_CONTROL": "1",
            "UUMA_IDENTITY_TOKEN_DIR": str(identity_token_dir),
            "UUMA_CHATGPT_BRIDGE_URL": f"http://127.0.0.1:{bridge_port}",
        }
        node_env = {
            **common, "UUMA_AGENT_ID": "orchestrator",
            "UUMA_IDENTITY_TOKEN_FILE": str(identity_token_dir / "orchestrator.token"),
        }
        write("node-config.json", config)
        write("node-environment.json", node_env)
        write("bridge-environment.json", common)
        write("launch-preview.json", {
            "node_argv": [str(python), "-m", "uuma.a2a_node", "--config",
                          str((destination / "node-config.json").resolve())],
            "bridge_argv": [str(python), "-m", "uuma.chatgpt_cli", "--data-dir", str(data_dir),
                            "--port", str(bridge_port), "serve"],
            "requirements": [
                "Apply each environment file to its own process; do not launch automatically",
                "Check both workstation ports before launch",
                f"SSH reverse forward server 127.0.0.1:{port} to workstation 127.0.0.1:{port}",
                "Keep the existing Chrome profiles, extension pairing and local API identity registry",
                "For an empty bridge candidate, rebind existing accounts before accepting consultations",
                "Keep external side effects blocked when workstation or authoritative control is unavailable",
            ],
        })
    write("preview.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--bridge-database", type=Path, required=True)
    parser.add_argument("--token-registry", type=Path, required=True)
    parser.add_argument("--identity-token-dir", type=Path, required=True)
    parser.add_argument("--control-url", required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--bridge-port", type=int, default=8787)
    parser.add_argument("--allow-empty-bridge", action="store_true")
    result = prepare(**vars(parser.parse_args()))
    print(json.dumps({"status": result["status"], "blockers": result["blockers"]}))


if __name__ == "__main__":
    main()
