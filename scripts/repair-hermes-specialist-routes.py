"""Safely separate collided multiplexed specialist Telegram routes.

Run with Hermes' Python while its gateway is stopped. The old session and its
transcript remain intact; only the two specialist routing entries are reset.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chat-id", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    root = Path(os.environ.get("HERMES_HOME") or Path(os.environ["LOCALAPPDATA"]) / "hermes")
    root = root.resolve()
    if root.name == "profiles" or root.parent.name == "profiles":
        parser.error("HERMES_HOME must be the default multiplex gateway home")
    db_path = root / "state.db"
    sessions_dir = root / "sessions"
    keys = [f"agent:{profile}:telegram:dm:{args.chat_id}" for profile in
            ("brainstormer", "wisdom-oldman")]
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT session_key, entry_json FROM gateway_routing "
            "WHERE session_key IN (?, ?)", keys
        ).fetchall()
    entries = {key: json.loads(value) for key, value in rows}
    if set(entries) != set(keys):
        parser.error("Both specialist routes must exist; no changes made")
    old_ids = {entries[key]["session_id"] for key in keys}
    print(json.dumps({key: entries[key]["session_id"] for key in keys}, indent=2))
    if len(old_ids) != 1:
        print("Routes are already distinct; checking session rows.")
    if not args.apply:
        print("Stop the gateway and rerun with --apply to repair routes or missing rows.")
        return

    from gateway.status import live_gateway_pid_for_home

    live_pid = live_gateway_pid_for_home(root)
    if live_pid is not None:
        parser.error(f"Gateway PID {live_pid} is still running; stop it before repair")

    backup_root = root / "uuma-route-backups" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_root.mkdir(parents=True, exist_ok=False)
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_root / "state.db") as backup:
        source.backup(backup)
    legacy_index = sessions_dir / "sessions.json"
    if legacy_index.exists():
        shutil.copy2(legacy_index, backup_root / "sessions.json")

    from gateway.config import GatewayConfig
    from gateway.session import SessionStore

    store = SessionStore(sessions_dir, GatewayConfig(multiplex_profiles=True))
    repaired = {}
    for key in keys:
        if len(old_ids) == 1:
            entry = store.reset_session(key)
        else:
            with store._lock:
                entry = store._entry_locked(key)
        if entry is None or (len(old_ids) == 1 and entry.session_id in old_ids):
            raise RuntimeError(f"Failed to load/reset {key}; backup is at {backup_root}")
        db = store._db_for_key(key)
        if db is None:
            raise RuntimeError(f"No profile database for {key}; backup is at {backup_root}")
        if db.get_session(entry.session_id) is None:
            # The old collided ID belongs to another profile's DB. A native reset
            # tries to link it as parent, violating this profile DB's FK. Keep the
            # old ID as descriptive lineage but create an independent root row.
            old_id = next(iter(old_ids)) if len(old_ids) == 1 else None
            kwargs = store._session_create_kwargs(
                session_id=entry.session_id,
                session_key=key,
                origin=entry.origin,
                source_value=entry.platform.value if entry.platform else "unknown",
                display_name=entry.display_name,
                parent_session_id=None,
            )
            if old_id:
                kwargs["model_config"] = {"_reset_from": old_id}
            db.create_session(**kwargs)
            store._record_gateway_session_peer(
                entry.session_id, key, entry.origin, display_name=entry.display_name
            )
        if db.get_session(entry.session_id) is None:
            raise RuntimeError(f"Missing new session row for {key}; backup is at {backup_root}")
        repaired[key] = entry.session_id
    if len(set(repaired.values())) != len(keys):
        raise RuntimeError(f"New routes still collide; backup is at {backup_root}")
    print(json.dumps({"repaired": repaired, "backup": str(backup_root)}, indent=2))


if __name__ == "__main__":
    main()
