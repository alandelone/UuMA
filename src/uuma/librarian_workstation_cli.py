"""Private scheduled CLI for registered workstation recovery sources."""

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

from .librarian_queue import _key_fingerprint
from .librarian_workstation_daily import run_sources

FIELDS = {"schema_version", "queue", "device", "public_key", "public_fingerprint", "host",
          "ssh_identity", "status_directory", "sources"}


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate workstation configuration key")
        result[key] = value
    return result


def execute(config_path: Path) -> tuple[dict[str, Any], int]:
    config_path = Path(config_path)
    if config_path.is_symlink():
        raise ValueError("Workstation configuration cannot be a symbolic link")
    with config_path.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("Workstation configuration exceeds its size limit")
    config = json.loads(raw, object_pairs_hook=_unique)
    if (not isinstance(config, dict) or set(config) not in (FIELDS, FIELDS | {"transfer_sessions"})
            or type(config["schema_version"]) is not int or config["schema_version"] != 1
            or any(not isinstance(config[key], str) or not config[key]
                   for key in FIELDS - {"schema_version", "sources"})
            or not isinstance(config["sources"], list)
            or type(config.get("transfer_sessions", False)) is not bool):
        raise ValueError("Invalid workstation capture configuration")
    for spec in config["sources"]:
        if not isinstance(spec, dict) or set(spec) != {"source_id", "kind", "path"}:
            raise ValueError("Invalid registered workstation source")
    status = Path(config["status_directory"])
    if status.is_symlink() or not status.is_dir():
        raise ValueError("Private workstation status directory must already exist")
    public_path = Path(config["public_key"])
    if public_path.is_symlink() or not public_path.is_file():
        raise ValueError("Configured recovery public key is unavailable")
    public = public_path.read_bytes()
    if _key_fingerprint(public) != config["public_fingerprint"]:
        raise ValueError("Workstation recovery public key fingerprint changed")
    if os.name == "nt":
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.SetPriorityClass.restype = wintypes.BOOL
        if not kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x4000):
            raise OSError("Could not lower workstation capture priority")
    receipt = status / ("run-" + uuid.uuid4().hex + ".jsonl")
    with receipt.open("x", encoding="utf-8") as stream:
        def record(value: dict[str, Any]) -> None:
            stream.write(json.dumps(value, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

        try:
            result = run_sources(config["sources"], queue=Path(config["queue"]), public_pem=public,
                                 device=config["device"], host=config["host"],
                                 ssh_identity=Path(config["ssh_identity"]), on_result=record,
                                 use_sessions=config.get("transfer_sessions", False))
            result["scope"] = "registered workstation sources only"
            record({"summary": result})
            return result, 0 if result["incomplete"] == 0 else 2
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            result = {"status": "ERROR", "error_type": type(exc).__name__}
            record(result)
            return result, 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture registered workstation sources")
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
