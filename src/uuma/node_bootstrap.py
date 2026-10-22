"""Create a fresh control baseline in a new directory without importing old tasks."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from .auth import TokenRegistry
from .deployment_admission import set_admission
from .node_journal import digest
from .service import ControlPlane
from .settings import Settings


def initialize(directory: Path, *, node: str, authorization: str) -> dict:
    if node not in {"server", "workstation"} or not authorization.strip():
        raise ValueError("A node and the human's fresh-baseline authorization are required")
    directory = directory.expanduser().resolve()
    # Exclusive creation: this command cannot reset an existing database or directory.
    directory.mkdir(parents=True, exist_ok=False)
    if os.name != "nt":
        directory.chmod(0o700)
    settings = replace(
        Settings.from_env(),
        data_dir=directory,
        database_path=directory / "uuma.db",
        artifact_dir=directory / "artifacts",
        ingest_spool_dir=directory / "spool" / "hermes",
        knowledge_data_dir=directory / "knowledge-not-migrated",
        honc_data_dir=directory / "honc-not-migrated",
    )
    control = ControlPlane(settings)
    control.bootstrap()
    agents = sorted(agent.agent_id for agent in control.list_agents())
    baseline_id = "fresh-control:" + digest({"node": node, "authorization": authorization})
    set_admission(control, agents, baseline_id, True)
    control.events.append(
        event_type="CONTROL_BASELINE_STARTED",
        aggregate_type="control",
        aggregate_id=node,
        actor_type="user",
        actor_id="user",
        payload={
            "authorization": authorization,
            "old_control_history_imported": False,
            "knowledge_and_domain_data_reset": False,
            "intake": "paused_pending_cutover",
            "baseline_id": baseline_id,
        },
    )
    tokens = TokenRegistry(settings.token_file()).initialize()
    settings.token_file().chmod(0o600)
    identities = directory / "identities"
    identities.mkdir(mode=0o700)
    for identity, token in tokens.items():
        path = identities / (identity + ".token")
        with path.open("x", encoding="utf-8") as handle:
            handle.write(token + "\n")
        path.chmod(0o600)
    with control.events.connect() as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    chain = control.events.verify_chain()[0]
    if integrity != "ok" or not chain or tasks or runs:
        raise RuntimeError("Fresh baseline validation failed; directory retained for inspection")
    receipt = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "node": node,
        "baseline_id": baseline_id,
        "authorization": authorization,
        "agents": agents,
        "task_count": tasks,
        "run_count": runs,
        "integrity": integrity,
        "event_chain_valid": chain,
        "intake": "paused_pending_cutover",
        "production_active": False,
    }
    (directory / "baseline-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--node", choices=["server", "workstation"], required=True)
    parser.add_argument("--authorization", required=True)
    args = parser.parse_args()
    print(json.dumps(initialize(args.directory, node=args.node, authorization=args.authorization)))


if __name__ == "__main__":
    main()
