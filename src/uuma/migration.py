"""Consistent, non-destructive SQLite snapshots and source-content inventories."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


def quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def database_inventory(path: Path) -> dict:
    tables = {}
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        integrity = [row[0] for row in db.execute("PRAGMA integrity_check")]
        if integrity != ["ok"]:
            raise ValueError("Database integrity check failed")
        for table, schema in db.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall():
            columns = [row[1] for row in db.execute(f"PRAGMA table_info({quoted(table)})")]
            order = ",".join(quoted(column) for column in columns)
            hasher, count = hashlib.sha256(), 0
            for row in db.execute(f"SELECT * FROM {quoted(table)} ORDER BY {order}"):
                normalized = [
                    {"type": type(v).__name__, "value": v.hex() if isinstance(v, bytes) else v}
                    for v in row
                ]
                hasher.update(json.dumps(normalized, ensure_ascii=False).encode() + b"\n")
                count += 1
            tables[table] = {"rows": count, "sha256": hasher.hexdigest(), "schema": schema}
    return {"integrity": "ok", "tables": tables}


def backup_database(source: Path, destination: Path) -> dict:
    source, destination = source.resolve(strict=True), destination.resolve()
    if destination.exists() or source == destination:
        raise FileExistsError("A migration snapshot must use a new destination")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental overwrite, including a concurrent snapshot operation.
    with destination.open("xb"):
        pass
    with (
        sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src,
        sqlite3.connect(destination) as dst,
    ):
        src.backup(dst)
        # A snapshot is a standalone file, not a new WAL writer sharing live sidecars.
        mode = dst.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
        if mode.lower() != "delete":
            raise RuntimeError("Migration snapshot could not become a standalone database")
    return {
        "source": str(source),
        "snapshot": str(destination),
        "inventory": database_inventory(destination),
    }


def content_inventory(root: Path) -> dict:
    root = root.resolve(strict=True)
    records = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Content inventories require explicit handling of symlinks")
        if path.is_file():
            if not path.resolve().is_relative_to(root):
                raise ValueError("Content path escapes its owner directory")
            with path.open("rb") as handle:
                records[path.relative_to(root).as_posix()] = {
                    "size": path.stat().st_size,
                    "sha256": hashlib.file_digest(handle, "sha256").hexdigest(),
                }
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    command = sub.add_parser("backup")
    command.add_argument("source", type=Path)
    command.add_argument("destination", type=Path)
    command = sub.add_parser("inspect")
    command.add_argument("source", type=Path)
    args = parser.parse_args()
    result = (
        backup_database(args.source, args.destination)
        if args.action == "backup"
        else database_inventory(args.source)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
