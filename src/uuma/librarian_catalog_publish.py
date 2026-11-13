"""Publish explicitly classified archive records, separately from recovery storage.

This owner-side operation is not an MCP tool. The operator supplies the source
file locations and an explicit set of record versions cleared for retrieval.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from .librarian_read import MAX_CATALOG_BYTES, LibrarianReader

if os.name == "posix":
    import fcntl

CHUNK = 1024 * 1024


def _digest(path: Path) -> tuple[str, int]:
    result = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            result.update(chunk)
            size += len(chunk)
    return result.hexdigest(), size


def _private_directory(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Archive directory must exist and must not be a symlink")
    info = path.stat()
    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise PermissionError("Archive directory must be private and owner-controlled")


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _regular_source(path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Object source must be an absolute path without symlinks")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Object source must be a regular file")
    return path


def _copy_object(source: Path, destination: Path, expected_hash: str, expected_size: int) -> None:
    source = _regular_source(source)
    before = source.stat()
    digest = hashlib.sha256()
    copied = 0
    fd, name = tempfile.mkstemp(prefix=".object-", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as out, source.open("rb") as inp:
            for chunk in iter(lambda: inp.read(CHUNK), b""):
                out.write(chunk)
                digest.update(chunk)
                copied += len(chunk)
            out.flush()
            os.fsync(out.fileno())
        after = source.stat()
        if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                or copied != expected_size or digest.hexdigest() != expected_hash):
            raise ValueError("Object source changed or failed its declared digest")
        try:
            os.link(name, destination)
            _fsync_directory(destination.parent)
        except FileExistsError:
            if destination.is_symlink() or _digest(destination) != (expected_hash, expected_size):
                raise ValueError("Existing archive object failed integrity verification") from None
    finally:
        Path(name).unlink(missing_ok=True)


def publish_catalog(
    root: Path, catalog: dict[str, Any], *, approved_versions: frozenset[tuple[str, str]],
    object_sources: dict[str, Path], expected_current_sha256: str | None,
) -> dict[str, Any]:
    """Publish a verified, append-only catalog from explicit retrieval approvals.

    ``approved_versions`` and ``object_sources`` are trusted server configuration,
    never parameters exposed to an agent. They must cover every catalog version.
    No credential classification or access decision is inferred from a filename,
    project association, or recovery manifest. Existing record versions cannot be
    removed or changed, except that their readers may be narrowed. Current catalog
    publication is atomic and prior catalog snapshots retain their original bytes.
    """
    if os.name != "posix":
        raise OSError("Archive publication requires a POSIX server")
    root = Path(root)
    if not root.is_absolute():
        raise ValueError("Archive root must be absolute")
    _private_directory(root)
    if not isinstance(catalog, dict):
        raise TypeError("Archive catalog must be an object")
    raw = json.dumps(catalog, sort_keys=True, ensure_ascii=False).encode("utf-8")
    if not 1 <= len(raw) <= MAX_CATALOG_BYTES:
        raise ValueError("Archive catalog exceeds the supported reader size")
    lock = root / ".catalog-publication.lock"
    if lock.is_symlink():
        raise ValueError("Archive publication lock cannot be a symlink")
    lock_fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix=".validate-", dir=root) as temporary:
            stage = Path(temporary)
            (stage / "catalog.json").write_bytes(raw)
            candidate = LibrarianReader(stage, "librarian")
        if set(candidate.records) != set(approved_versions):
            raise PermissionError("Every published version requires explicit retrieval classification")
        current_path = root / "catalog.json"
        primary_path = root / "librarian_semantic_catalog.json"
        if current_path.is_symlink() or primary_path.is_symlink():
            raise ValueError("Current archive catalog cannot be a symlink")
        old_raw = primary_path.read_bytes() if primary_path.exists() else (
            current_path.read_bytes() if current_path.exists() else None
        )
        if (hashlib.sha256(old_raw).hexdigest() if old_raw is not None else None) != expected_current_sha256:
            raise ValueError("Current archive catalog changed since the prepared publication")
        if old_raw is not None:
            old = LibrarianReader(root, "librarian")
            if any(key not in candidate.records
                   or candidate.records[key].model_dump(exclude={"readers"}) != record.model_dump(exclude={"readers"})
                   or not set(candidate.records[key].readers).issubset(record.readers)
                   for key, record in old.records.items()):
                raise ValueError("Published record history cannot be removed or rewritten")
            if not set(old.sources).issubset(candidate.sources):
                raise ValueError("Published source history cannot be removed")
            if any(candidate.sources[key].owner_agent != source.owner_agent for key, source in old.sources.items()):
                raise ValueError("Published source owner cannot be rewritten")
            if old.catalog.snapshot_id == candidate.catalog.snapshot_id and old_raw != raw:
                raise ValueError("Catalog snapshot identity cannot be reused for different contents")
        objects = root / "objects"
        objects.mkdir(mode=0o700, exist_ok=True)
        _private_directory(objects)
        for record in candidate.catalog.records:
            parent = objects / record.content_sha256[:2]
            parent.mkdir(mode=0o700, exist_ok=True)
            _private_directory(parent)
            destination = parent / record.content_sha256
            if destination.exists() or destination.is_symlink():
                if destination.is_symlink() or _digest(destination) != (record.content_sha256, record.content_bytes):
                    raise ValueError("Existing archive object failed integrity verification")
                continue
            source = object_sources.get(record.content_sha256)
            if source is None:
                raise ValueError("A new catalog object has no approved source")
            _copy_object(source, destination, record.content_sha256, record.content_bytes)
        snapshots = root / "catalogs"
        snapshots.mkdir(mode=0o700, exist_ok=True)
        _private_directory(snapshots)
        snapshot = snapshots / (candidate.catalog.snapshot_id + ".json")
        if snapshot.is_symlink():
            raise ValueError("Catalog snapshot cannot be a symlink")
        try:
            with snapshot.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            _fsync_directory(snapshots)
        except FileExistsError:
            if snapshot.read_bytes() != raw:
                raise ValueError("Catalog snapshot identity already contains different bytes") from None
        # Recheck external writers immediately before publication. Advisory locking
        # coordinates this component's writers, not unrelated filesystem writers.
        if current_path.is_symlink() or (current_path.read_bytes() if current_path.exists() else None) != old_raw:
            raise ValueError("Current archive catalog changed during publication")
        fd, name = tempfile.mkstemp(prefix=".catalog-", dir=root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, current_path)
            # Maintain primary catalog file (librarian_semantic_catalog.json)
            fd2, name2 = tempfile.mkstemp(prefix=".catalog-", dir=root)
            try:
                with os.fdopen(fd2, "wb") as stream2:
                    stream2.write(raw)
                    stream2.flush()
                    os.fsync(stream2.fileno())
                os.replace(name2, primary_path)
            finally:
                Path(name2).unlink(missing_ok=True)
            _fsync_directory(root)
        finally:
            Path(name).unlink(missing_ok=True)
        return {"snapshot_id": candidate.catalog.snapshot_id, "catalog_sha256": hashlib.sha256(raw).hexdigest(),
                "record_versions": len(candidate.records), "catalog_bytes": len(raw)}
    finally:
        os.close(lock_fd)
