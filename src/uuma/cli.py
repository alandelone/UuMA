from __future__ import annotations

import argparse
import json
from pathlib import Path

from .auth import TokenRegistry
from .hermes import HermesKanbanAdapter
from .service import ControlPlane
from .settings import Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="uuma")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Initialize data, tokens, Agent definitions, and Kanban board")
    sub.add_parser("health", help="Verify the event chain and show projection counts")
    sub.add_parser("rebuild", help="Rebuild all current-state projections from events")
    sub.add_parser("reconcile", help="Import and compare Hermes Kanban task snapshots")
    ingest = sub.add_parser("ingest-spool", help="Replay locally spooled Hermes audit events")
    ingest.add_argument("--spool", type=Path, help="Override the configured audit spool directory")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = Settings.from_env()
    control_plane = ControlPlane(settings)
    if args.command == "init":
        tokens = TokenRegistry(settings.token_file()).initialize()
        created = control_plane.bootstrap()
        board = HermesKanbanAdapter(settings.hermes_executable, settings.kanban_board)
        board_result = board.initialize_board()
        print(
            json.dumps(
                {
                    "data_dir": str(settings.data_dir),
                    "tokens_created": sorted(tokens),
                    "agents_created": [agent.agent_id for agent in created],
                    "kanban": board_result.data or board_result.stdout,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    elif args.command == "health":
        print(json.dumps(control_plane.health(), indent=2))
    elif args.command == "rebuild":
        count = control_plane.events.rebuild_projections()
        print(json.dumps({"events_replayed": count, "health": control_plane.health()}, indent=2))
    elif args.command == "reconcile":
        board = HermesKanbanAdapter(settings.hermes_executable, settings.kanban_board)
        print(json.dumps({"changed_snapshots": board.reconcile(control_plane)}, indent=2))
    elif args.command == "ingest-spool":
        spool = args.spool or settings.ingest_spool_dir
        imported = duplicates = errors = 0
        for path in sorted(spool.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                profile = str(payload.get("profile") or "unknown")
                if control_plane.ingest_hermes_event(payload, profile=profile):
                    imported += 1
                else:
                    duplicates += 1
            except (OSError, ValueError, TypeError):
                errors += 1
        print(
            json.dumps(
                {
                    "spool": str(spool),
                    "imported": imported,
                    "duplicates": duplicates,
                    "errors": errors,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
