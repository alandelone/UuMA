"""Start the operator's fixed workstation connector configuration without a console."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import time
from pathlib import Path

import psutil

from uuma.brainstormer_lock import BrainstormerProcessLock


def alive(record: dict, argv: list[str]) -> bool:
    try:
        process = psutil.Process(record["pid"])
        actual = process.cmdline()
        return (process.is_running() and bool(actual)
                and Path(actual[0]).stem.casefold() == Path(argv[0]).stem.casefold()
                and actual[1:] == argv[1:])
    except (KeyError, psutil.Error):
        return False


def listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def start(profile: Path) -> dict:
    profile = profile.resolve(strict=True)
    config = json.loads((profile / "startup.json").read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise ValueError("Unsupported workstation startup configuration")
    state_path = profile / "startup-processes.json"
    with BrainstormerProcessLock(profile):
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        result = {}
        for name, service in config["services"].items():
            argv = service["argv"]
            if alive(state.get(name, {}), argv):
                result[name] = "running"
                continue
            if service.get("port") and listening(service["port"]):
                # Never kill or replace an unexpected listener during startup.
                owners = [connection.pid for connection in psutil.net_connections(kind="inet")
                          if connection.status == "LISTEN" and connection.laddr.port == service["port"]]
                expected = service["module"]
                if not owners or not all(
                    expected in psutil.Process(pid).cmdline()
                    or expected == Path(psutil.Process(pid).cmdline()[0]).stem
                    for pid in owners
                ):
                    raise RuntimeError(f"Workstation startup port conflict: {name}")
                result[name] = "already_listening"
                continue
            environment = {**os.environ, **service.get("environment", {})}
            if service.get("environment_file"):
                environment.update(json.loads(Path(service["environment_file"]).read_text()))
            environment.update(PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
            with (profile / (name + "-startup.log")).open("ab") as log:
                process = subprocess.Popen(
                    argv, env=environment, cwd=config["workspace"], shell=False,
                    stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            state[name] = {"pid": process.pid, "argv": argv, "started_at": time.time()}
            result[name] = "started"
            temporary = state_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
            temporary.replace(state_path)
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    print(json.dumps(start(parser.parse_args().profile)))
