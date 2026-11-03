"""Consistent SQLite snapshots for Librarian capture; no production scheduling."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path


def snapshot_sqlite(
    source: Path, destination: Path, *, timeout_seconds: float = 60,
) -> dict[str, object]:
    """Create a checked, non-overwriting snapshot of an existing SQLite owner.

    The destination parent must already exist. A failed snapshot is never published.
    """
    if not 0 < timeout_seconds <= 300:
        raise ValueError("Snapshot timeout must be positive and at most 300 seconds")
    deadline = time.monotonic() + timeout_seconds

    def progress(status: int, remaining: int, total: int) -> None:
        if time.monotonic() >= deadline:
            raise TimeoutError("Consistent snapshot exceeded its capture deadline")

    source = Path(source).resolve(strict=True)
    destination = Path(destination)
    if not source.is_file():
        raise ValueError("Source must be an existing SQLite file")
    parent = destination.parent.resolve(strict=True)
    destination = parent / destination.name
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    fd, name = tempfile.mkstemp(prefix=".librarian-snapshot-", suffix=".tmp", dir=parent)
    os.close(fd)
    temporary = Path(name)
    try:
        with (
            closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as origin,
            closing(sqlite3.connect(temporary)) as target,
        ):
            origin.backup(target, pages=256, progress=progress, sleep=0.05)
            check = target.execute("PRAGMA quick_check").fetchall()
            if check != [("ok",)]:
                raise ValueError("Snapshot failed SQLite quick_check")
            schema_version = target.execute("PRAGMA user_version").fetchone()[0]
        digest = hashlib.sha256()
        size = 0
        with temporary.open("r+b") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        return {"sha256": digest.hexdigest(), "bytes": size, "sqlite_user_version": schema_version,
                "quick_check": "ok"}
    finally:
        temporary.unlink(missing_ok=True)
