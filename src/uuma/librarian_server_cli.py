"""Private daily server source-capture entry point."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from .librarian_queue import _key_fingerprint
from .librarian_server_daily import run_sources

FIELDS = {"schema_version", "queue", "intake", "public_key", "public_fingerprint",
          "status_directory", "sources"}
SOURCE_FIELDS = {"source_id", "kind", "path", "owner_unit", "owner_env", "owner_value"}


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate server configuration key")
        result[key] = value
    return result


def execute(config_path: Path) -> tuple[dict[str, Any], int]:
    """Run only the server-owned configuration and retain one private status receipt."""
    if os.name != "posix":
        raise OSError("Server capture requires the POSIX agent host")
    config_path = Path(config_path)
    if config_path.is_symlink():
        raise ValueError("Server capture configuration cannot be a symbolic link")
    stat = config_path.stat()
    if stat.st_uid != os.geteuid() or stat.st_mode & 0o077:
        raise PermissionError("Server capture configuration must be private and owner-controlled")
    with config_path.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("Server capture configuration exceeds its size limit")
    config = json.loads(raw, object_pairs_hook=_unique)
    if (not isinstance(config, dict) or set(config) != FIELDS
            or type(config["schema_version"]) is not int or config["schema_version"] != 1
            or any(not isinstance(config[key], str) or not config[key]
                   for key in FIELDS - {"schema_version", "sources"})
            or not isinstance(config["sources"], list)):
        raise ValueError("Invalid server capture configuration")
    for spec in config["sources"]:
        if (not isinstance(spec, dict) or not SOURCE_FIELDS.issubset(spec)
                or set(spec) - SOURCE_FIELDS - {"freshness"}):
            raise ValueError("Invalid registered source configuration")
    status = Path(config["status_directory"])
    if status.is_symlink() or not status.is_dir():
        raise ValueError("Private server status directory must already exist")
    stat = status.stat()
    if stat.st_uid != os.geteuid() or stat.st_mode & 0o077:
        raise PermissionError("Server status directory must be private and owner-controlled")
    key = Path(config["public_key"])
    if key.is_symlink() or not key.is_file():
        raise ValueError("Configured server recovery public key is unavailable")
    public = key.read_bytes()
    if _key_fingerprint(public) != config["public_fingerprint"]:
        raise ValueError("Server recovery public key fingerprint changed")
    try:
        result = run_sources(config["sources"], queue=Path(config["queue"]),
                             intake=Path(config["intake"]), public_pem=public)
        result["scope"] = "registered server sources only"
        code = 0 if result["incomplete"] == 0 else 2
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        result = {"status": "ERROR", "error_type": type(exc).__name__}
        code = 1
    receipt = status / ("run-" + uuid.uuid4().hex + ".json")
    with receipt.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    return result, code


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture registered server-owned sources")
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
