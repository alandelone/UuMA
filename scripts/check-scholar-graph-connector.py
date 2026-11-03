"""Restore only Scholar's existing SSH forwards; never restart a server or receiver."""
from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import psutil


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_services() -> dict:
    common = ["ssh", "-N", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
              "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=15",
              "-o", "ServerAliveCountMax=3", "-L"]
    return {name: {"argv": [*common, f"127.0.0.1:{port}:127.0.0.1:{port}", "ubuntu-server"],
                   "module": "ssh", "port": port}
            for name, port in (("scholar_fieldkg_tunnel", 8892),
                               ("scholar_graph_probe_tunnel", 8887))}


def check_listeners(services: dict) -> None:
    """A matching port alone is insufficient; never adopt or kill another listener."""
    expected = {item["port"]: item["argv"] for item in services.values()}
    for conn in psutil.net_connections(kind="inet"):
        if conn.status != "LISTEN" or conn.laddr.port not in expected:
            continue
        if conn.laddr.ip != "127.0.0.1" or conn.pid is None:
            raise RuntimeError("Scholar graph port has an unexpected listener")
        actual = psutil.Process(conn.pid).cmdline()
        argv = expected[conn.laddr.port]
        if (not actual or Path(actual[0]).stem.casefold() != "ssh" or actual[1:] != argv[1:]):
            raise RuntimeError("Scholar graph listener does not match its configured SSH owner")


def run_once(project: Path, connector: Path, marker: Path, *,
             config_sha256: str, launcher_sha256: str) -> dict:
    config_path = connector / "startup.json"
    launcher = project / "scripts/start-distributed-workstation.py"
    if sha(config_path) != config_sha256 or sha(launcher) != launcher_sha256:
        raise ValueError("Scholar connector configuration or launcher changed; review before recovery")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    owner = json.loads(marker.read_text(encoding="utf-8-sig"))
    if (owner.get("node_id") != "alandelone-server-001"
            or owner.get("namespace") != "ScholarFieldKG" or str(owner.get("project_id")) != "2"
            or owner.get("local_url") != "http://127.0.0.1:8892"
            or owner.get("canonical_catalog_owner") != "workstation"):
        raise ValueError("Scholar server owner marker changed; recovery is not admitted")
    services = expected_services()
    if (config.get("schema_version") != 1 or config.get("services") != services
            or Path(config["workspace"]).resolve() != project.resolve()):
        raise ValueError("Recovery is restricted to the two existing Scholar graph forwards")
    check_listeners(services)
    sys.path.insert(0, str(project / "src"))
    result = runpy.run_path(str(launcher))["start"](connector)
    check_listeners(services)
    if sha(config_path) != config_sha256 or sha(launcher) != launcher_sha256:
        raise ValueError("Scholar connector context changed during recovery")
    return {"observed_at": datetime.now(UTC).isoformat(), "services": result,
            "server_restarted": False, "gateway_restarted": False, "catalog_modified": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--connector", type=Path, required=True)
    parser.add_argument("--marker", type=Path, required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--launcher-sha256", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()
    if args.interval < 5:
        parser.error("Connector supervision requires an interval of at least five seconds")
    sys.path.insert(0, str(args.project / "src"))
    from uuma.brainstormer_lock import BrainstormerProcessLock

    with BrainstormerProcessLock(args.receipt.parent / "supervisor-owner", timeout_seconds=0.2):
        while True:
            status = check_cycle(args)
            if not args.watch:
                raise SystemExit(status)
            time.sleep(args.interval)


def check_cycle(args) -> int:
    status = 0
    try:
        result = run_once(args.project, args.connector, args.marker,
                          config_sha256=args.config_sha256, launcher_sha256=args.launcher_sha256)
    except (OSError, ValueError, RuntimeError, psutil.Error) as error:
        result = {"observed_at": datetime.now(UTC).isoformat(), "error": str(error),
                  "error_type": type(error).__name__, "recovery_completed": False}
        status = 1
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.receipt.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2), encoding="utf-8")
    temporary.replace(args.receipt)
    return status


if __name__ == "__main__":
    main()
