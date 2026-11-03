"""Single-server publication of verified recovery intake to a private NAS tree."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .librarian_intake import IDENTITY, _verify

GROUP_FILES = 64
GROUP_BYTES = 64 * 1024 * 1024
PUBLISH_BYTES_PER_SECOND = 4 * 1024 * 1024


def _check_io_pressure() -> None:
    """Defer background publication when configured host I/O pressure is high."""
    configured = os.environ.get("UUMA_LIBRARIAN_IO_PRESSURE_LIMIT")
    if configured is None:
        return
    limit = float(configured)
    if not 0 < limit <= 100:
        raise ValueError("Invalid publication I/O pressure limit")
    raw = Path("/proc/pressure/io").read_text(encoding="ascii")
    line = next(item for item in raw.splitlines() if item.startswith("some "))
    fields = dict(item.split("=", 1) for item in line.split()[1:])
    if float(fields["avg10"]) >= limit:
        raise BlockingIOError("Background publication deferred by I/O pressure")


def _sync_filesystem(directory: Path) -> None:
    """Durably flush a bounded group of staged files on Linux."""
    fd = os.open(directory, os.O_RDONLY)
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        syncfs = libc.syncfs
        syncfs.argtypes = [ctypes.c_int]
        syncfs.restype = ctypes.c_int
        if syncfs(fd) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
    finally:
        os.close(fd)


def _sync_directory(directory: Path) -> None:
    if os.name == "posix":
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _publish_objects(entries: list[dict[str, Any]], intake: Path, objects: Path,
                     device: str, source: str) -> None:
    """Stage and flush bounded groups, retaining the existing v1 object layout."""
    staged: list[tuple[Path, Path, int, str]] = []
    staged_digests: set[str] = set()
    staged_bytes = 0

    def commit_group() -> None:
        nonlocal staged_bytes
        if not staged:
            return
        if sys.platform.startswith("linux"):
            _sync_filesystem(objects)
        for temporary, final, size, digest in staged:
            if not _verify(temporary, size, digest):
                raise ValueError("NAS staged recovery object failed verification")
            if final.exists() or final.is_symlink():
                raise FileExistsError("Recovery object appeared during single-writer publication")
            temporary.rename(final)
        _sync_directory(objects)
        staged.clear()
        staged_digests.clear()
        staged_bytes = 0

    for entry in entries:
        if entry["status"] != "CAPTURED":
            continue
        digest, size = entry["sha256"], entry["bytes"]
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest) or type(size) is not int or size < 1:
            raise ValueError("Invalid retained recovery object")
        original = intake / device / source / digest
        if any(path.is_symlink() for path in (original, original.parent, original.parent.parent)):
            raise ValueError("Intake recovery object cannot contain symbolic links")
        if not _verify(original, size, digest):
            raise ValueError("Intake recovery object failed verification")
        final = objects / digest
        if final.is_symlink():
            raise ValueError("Recovery object cannot be a symbolic link")
        if final.exists():
            if not _verify(final, size, digest):
                raise ValueError("Existing NAS recovery object failed verification")
            continue
        if digest in staged_digests:
            continue
        if staged and staged_bytes + size > GROUP_BYTES:
            commit_group()
        if not staged:
            _check_io_pressure()
        temporary = objects / (".pending-" + uuid.uuid4().hex)
        copied = 0
        started = time.monotonic()
        with original.open("rb") as src, temporary.open("xb") as dst:
            for chunk in iter(lambda: src.read(1024 * 1024), b""):
                dst.write(chunk)
                copied += len(chunk)
                delay = copied / PUBLISH_BYTES_PER_SECOND - (time.monotonic() - started)
                if delay > 0:
                    time.sleep(delay)
            dst.flush()
            if not sys.platform.startswith("linux"):
                os.fsync(dst.fileno())
        staged.append((temporary, final, size, digest))
        staged_digests.add(digest)
        staged_bytes += size
        if len(staged) >= GROUP_FILES or staged_bytes >= GROUP_BYTES:
            commit_group()
    commit_group()


def publish_batch(intake: Path, archive: Path, batch_id: str) -> dict[str, Any]:
    """Publish all retained revisions; one local ledger serializes server writers.

    Archive is a pre-existing recovery-only NAS directory, never an MCP object tree.
    Source paths in the incoming manifest are metadata only and are never opened.
    The caller owns NAS access policy and must prevent other independent writers.
    """
    intake = Path(intake).resolve(strict=True)
    archive = Path(archive).resolve(strict=True)
    if not intake.is_dir() or not archive.is_dir() or archive == intake:
        raise ValueError("Use distinct existing private intake and recovery archive roots")
    match = re.fullmatch(
        r"librarian:([A-Za-z0-9][A-Za-z0-9_.-]{0,79}):"
        r"([A-Za-z0-9][A-Za-z0-9_.-]{0,79}):([0-9]{4}-[0-9]{2}-[0-9]{2})", batch_id,
    )
    if match is None:
        raise ValueError("Invalid recovery batch identity")
    device, source, day = match.groups()
    if not IDENTITY.fullmatch(device) or not IDENTITY.fullmatch(source):
        raise ValueError("Invalid recovery source identity")
    intake_db = intake / "recovery-intake.sqlite"
    pub_db = intake / "recovery-publication.sqlite"
    if intake_db.is_symlink() or pub_db.is_symlink():
        raise ValueError("Recovery ledgers cannot be symbolic links")
    with (closing(sqlite3.connect(intake_db.as_uri() + "?mode=ro", uri=True)) as received,
          closing(sqlite3.connect(pub_db, timeout=5)) as published):
        published.execute("""CREATE TABLE IF NOT EXISTS publications (
            batch_id TEXT NOT NULL, revision INTEGER NOT NULL, sha256 TEXT NOT NULL,
            coverage TEXT NOT NULL, published_at TEXT NOT NULL,
            PRIMARY KEY(batch_id,revision))""")
        published.execute("BEGIN IMMEDIATE")
        try:
            rows = received.execute(
                "SELECT revision,sha256,raw FROM manifest_revisions WHERE batch_id=? ORDER BY revision",
                (batch_id,),
            ).fetchall()
            if not rows:
                raise KeyError("No verified intake revisions for this batch")
            target = archive
            for component in (device, source, day):
                target = target / component
                if target.is_symlink():
                    raise ValueError("Recovery archive scope cannot contain symbolic links")
                target.mkdir(exist_ok=True)
                if not target.resolve(strict=True).is_relative_to(archive):
                    raise ValueError("Recovery archive escaped its configured root")
            objects = target / "objects"
            if objects.is_symlink():
                raise ValueError("Recovery object directory cannot be a symbolic link")
            objects.mkdir(exist_ok=True)
            previous = None
            latest: dict[str, Any] = {}
            for number, (revision, manifest_digest, raw) in enumerate(rows, 1):
                if revision != number or hashlib.sha256(raw).hexdigest() != manifest_digest:
                    raise ValueError("Intake manifest history failed verification")
                manifest = json.loads(raw)
                if (manifest.get("batch_id") != batch_id or manifest.get("revision") != revision
                        or manifest.get("previous_manifest_sha256") != previous):
                    raise ValueError("Intake manifest chain does not match")
                previous = manifest_digest
                _publish_objects(manifest["entries"], intake, objects, device, source)
                final_manifest = target / f"manifest-{manifest_digest}.json"
                if final_manifest.is_symlink():
                    raise ValueError("Recovery manifest cannot be a symbolic link")
                if final_manifest.exists():
                    if final_manifest.read_bytes() != raw:
                        raise ValueError("Retained NAS manifest is inconsistent")
                else:
                    staged = target / (".manifest-" + uuid.uuid4().hex)
                    with staged.open("xb") as stream:
                        stream.write(raw)
                        stream.flush()
                        os.fsync(stream.fileno())
                    if final_manifest.exists() or final_manifest.is_symlink():
                        raise FileExistsError("Manifest appeared during single-writer publication")
                    staged.rename(final_manifest)
                    _sync_directory(target)
                existing = published.execute(
                    "SELECT sha256 FROM publications WHERE batch_id=? AND revision=?", (batch_id, revision),
                ).fetchone()
                if existing is not None and existing[0] != manifest_digest:
                    raise ValueError("Publication history conflicts with intake")
                published.execute("INSERT OR IGNORE INTO publications VALUES (?,?,?,?,?)", (
                    batch_id, revision, manifest_digest, manifest["coverage"], datetime.now(UTC).isoformat(),
                ))
                latest = {"batch_id": batch_id, "revision": revision, "sha256": manifest_digest,
                          "coverage": manifest["coverage"], "nas_hash_verified": True}
            published.commit()
            return latest
        except BaseException:
            published.rollback()
            raise
