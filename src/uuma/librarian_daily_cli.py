"""Scheduled CLI for one explicitly configured daily SQLite source."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import uuid
from ctypes import wintypes
from pathlib import Path
from typing import Any

from .librarian_daily import run_daily_sqlite

FIELDS = {"schema_version", "queue", "device", "source", "database", "public_key",
          "host", "ssh_identity", "status_directory"}


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate daily configuration key")
        result[key] = value
    return result


def execute(config_path: Path) -> tuple[dict[str, Any], int]:
    """Run a trusted local configuration and append a private status receipt."""
    config_path = Path(config_path)
    if config_path.is_symlink():
        raise ValueError("Daily configuration cannot be a symbolic link")
    with config_path.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("Daily configuration exceeds its size limit")
    config = json.loads(raw, object_pairs_hook=_unique)
    if (not isinstance(config, dict) or set(config) != FIELDS
            or type(config["schema_version"]) is not int or config["schema_version"] != 1
            or any(not isinstance(config[key], str) or not config[key]
                   for key in FIELDS - {"schema_version"})):
        raise ValueError("Invalid daily configuration")
    status_directory = Path(config["status_directory"])
    if status_directory.is_symlink() or not status_directory.is_dir():
        raise ValueError("Private status directory must already exist")
    if os.name == "nt":
        # Fail closed: no normal-priority backup if Windows rejects background priority.
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.SetPriorityClass.restype = wintypes.BOOL
        if not kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x4000):
            raise OSError("Could not lower scheduled capture priority")
    try:
        result = run_daily_sqlite(
            queue=Path(config["queue"]), device=config["device"], source=config["source"],
            database=Path(config["database"]), public_key=Path(config["public_key"]),
            host=config["host"], ssh_identity=Path(config["ssh_identity"]),
        )
        success = (result["coverage"] == "COMPLETE" and result["server_intake"] == "DELIVERED"
                   and result["older_pending_before_retry"] == result["older_batches_delivered"])
        code = 0 if success else 2
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        result = {"status": "ERROR", "error_type": type(exc).__name__}
        code = 1
    receipt = status_directory / ("run-" + uuid.uuid4().hex + ".json")
    with receipt.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    return result, code


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture one configured Librarian source")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        result, code = execute(args.config)
        print(json.dumps(result, sort_keys=True))
        raise SystemExit(code)
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print(json.dumps({"status": "ERROR", "error_type": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
