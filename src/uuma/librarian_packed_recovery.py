"""Experimental packed recovery publication, independent of the existing v1 archive.

Only authenticated intake capsules are packed. This component never decrypts them
and does not mark the existing v1 publication ledger as complete.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
import zipfile
from contextlib import closing
from pathlib import Path
from typing import Any

from .librarian_intake import IDENTITY, MAX_OBJECT_BYTES, _verify
from .librarian_publish import _check_io_pressure, _sync_directory

PACK_FILES = 256
PACK_BYTES = 16 * 1024 * 1024
TRANSFER_RATE = 4 * 1024 * 1024


def _digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _commit_file(temporary: Path, final: Path, digest: str, size: int) -> None:
    if final.is_symlink():
        raise ValueError("Packed archive destination cannot be a symbolic link")
    try:
        os.link(temporary, final)
        _sync_directory(final.parent)
    except FileExistsError:
        if final.is_symlink() or _digest(final) != (digest, size):
            raise ValueError("Existing packed archive object is inconsistent") from None
    temporary.unlink()


def _save_bytes(directory: Path, prefix: str, raw: bytes) -> tuple[str, Path]:
    _check_io_pressure()
    digest = hashlib.sha256(raw).hexdigest()
    final = directory / f"{prefix}-{digest}.json"
    fd, name = tempfile.mkstemp(prefix=".packed-metadata-", dir=directory)
    temporary = Path(name)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _commit_file(temporary, final, digest, len(raw))
    return digest, final


def _verify_pack(path: Path, objects: list[tuple[Path, str, int]]) -> None:
    with zipfile.ZipFile(path) as pack:
        if pack.namelist() != [item[1] for item in objects]:
            raise ValueError("Packed capsule listing is inconsistent")
        for _source, digest, size in objects:
            info = pack.getinfo(digest)
            if info.compress_type != zipfile.ZIP_STORED or info.file_size != size:
                raise ValueError("Packed capsule size or method changed")
            checksum = hashlib.sha256()
            with pack.open(info) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    checksum.update(chunk)
            if checksum.hexdigest() != digest:
                raise ValueError("Packed capsule failed verification")


def _write_pack(directory: Path, objects: list[tuple[Path, str, int]]) -> tuple[str, int]:
    _check_io_pressure()
    identity_raw = json.dumps([[digest, size] for _path, digest, size in objects],
                              separators=(",", ":")).encode()
    group_hash = hashlib.sha256(identity_raw).hexdigest()
    group_receipt = directory / f"group-{group_hash}.json"
    if group_receipt.is_symlink():
        raise ValueError("Packed group receipt cannot be a symbolic link")
    if group_receipt.exists():
        with group_receipt.open("rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise ValueError("Packed group receipt exceeds supported limits")
        receipt = json.loads(raw)
        if not isinstance(receipt, dict):
            raise ValueError("Packed group receipt is inconsistent")
        pack_hash, pack_size = receipt.get("pack_sha256"), receipt.get("pack_bytes")
        if (receipt.get("group_sha256") != group_hash or not isinstance(pack_hash, str)
                or not re.fullmatch(r"[a-f0-9]{64}", pack_hash) or type(pack_size) is not int or pack_size < 1):
            raise ValueError("Packed group receipt is inconsistent")
        retained = directory / f"pack-{pack_hash}.zip"
        if retained.is_symlink() or _digest(retained) != (pack_hash, pack_size):
            raise ValueError("Retained pack failed verification")
        _verify_pack(retained, objects)
        return pack_hash, pack_size
    fd, name = tempfile.mkstemp(prefix=".packed-capsules-", dir=directory)
    temporary = Path(name)
    started, sent = time.monotonic(), 0
    with os.fdopen(fd, "w+b") as output:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as pack:
            for source, digest, size in objects:
                if source.is_symlink() or not _verify(source, size, digest):
                    raise ValueError("Intake capsule failed verification")
                info = zipfile.ZipInfo(digest, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                with source.open("rb") as inp, pack.open(info, "w", force_zip64=True) as out:
                    for chunk in iter(lambda: inp.read(1024 * 1024), b""):
                        out.write(chunk)
                        sent += len(chunk)
                        delay = sent / TRANSFER_RATE - (time.monotonic() - started)
                        if delay > 0:
                            time.sleep(delay)
        output.flush()
        os.fsync(output.fileno())
    _verify_pack(temporary, objects)
    digest, size = _digest(temporary)
    _commit_file(temporary, directory / f"pack-{digest}.zip", digest, size)
    raw = json.dumps({"group_sha256": group_hash, "pack_sha256": digest, "pack_bytes": size},
                     sort_keys=True, separators=(",", ":")).encode()
    fd, name = tempfile.mkstemp(prefix=".packed-group-", dir=directory)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _commit_file(Path(name), group_receipt, hashlib.sha256(raw).hexdigest(), len(raw))
    return digest, size


def _commit_pack(target: Path, pending: list[tuple[Path, str, int]],
                 objects: dict[str, dict[str, Any]]) -> None:
    if not pending:
        return
    pack_hash, pack_size = _write_pack(target, pending)
    for _path, digest, size in pending:
        objects[digest] = {"pack_sha256": pack_hash, "pack_bytes": pack_size, "bytes": size}
    pending.clear()


def publish_packed_batch(intake: Path, archive: Path, batch_id: str) -> dict[str, Any]:
    """Publish retained revisions into a separate pack archive and ledger."""
    match = re.fullmatch(r"librarian:([A-Za-z0-9][A-Za-z0-9_.-]{0,79}):"
                         r"([A-Za-z0-9][A-Za-z0-9_.-]{0,79}):([0-9]{4}-[0-9]{2}-[0-9]{2})", batch_id)
    if not match:
        raise ValueError("Invalid recovery batch identity")
    device, source, day = match.groups()
    if not IDENTITY.fullmatch(device) or not IDENTITY.fullmatch(source):
        raise ValueError("Invalid recovery source")
    intake, archive = Path(intake).resolve(strict=True), Path(archive).resolve(strict=True)
    if not intake.is_dir() or not archive.is_dir() or intake == archive:
        raise ValueError("Expected separate existing intake and packed archive roots")
    _check_io_pressure()
    target = archive
    for component in (device, source, day):
        target = target / component
        if target.is_symlink():
            raise ValueError("Packed archive scope cannot contain a symbolic link")
        target.mkdir(exist_ok=True)
        if not target.resolve(strict=True).is_relative_to(archive):
            raise ValueError("Packed archive escaped its root")
    source_db, ledger = intake / "recovery-intake.sqlite", intake / "recovery-packed-publication.sqlite"
    if source_db.is_symlink() or ledger.is_symlink():
        raise ValueError("Recovery ledgers cannot be symbolic links")
    with (closing(sqlite3.connect(source_db.as_uri() + "?mode=ro", uri=True)) as received,
          closing(sqlite3.connect(ledger, timeout=5)) as published):
        published.execute("CREATE TABLE IF NOT EXISTS publications (batch_id TEXT NOT NULL, "
                          "revision INTEGER NOT NULL, manifest_sha256 TEXT NOT NULL, "
                          "map_sha256 TEXT NOT NULL, PRIMARY KEY(batch_id,revision))")
        published.execute("BEGIN IMMEDIATE")
        try:
            rows = received.execute("SELECT revision,sha256,raw FROM manifest_revisions WHERE batch_id=? "
                                    "ORDER BY revision", (batch_id,)).fetchall()
            if not rows:
                raise KeyError("No retained recovery revisions")
            previous = None
            result: dict[str, Any] = {}
            for number, (revision, manifest_hash, raw) in enumerate(rows, 1):
                manifest = json.loads(raw)
                if (revision != number or hashlib.sha256(raw).hexdigest() != manifest_hash
                        or manifest.get("batch_id") != batch_id or manifest.get("revision") != revision
                        or manifest.get("previous_manifest_sha256") != previous):
                    raise ValueError("Recovery manifest history failed verification")
                previous = manifest_hash
                objects: dict[str, dict[str, Any]] = {}
                pending: list[tuple[Path, str, int]] = []
                pending_bytes = 0

                for entry in manifest["entries"]:
                    if entry["status"] != "CAPTURED":
                        continue
                    digest, size = entry.get("sha256"), entry.get("bytes")
                    if (not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
                            or type(size) is not int or not 1 <= size <= MAX_OBJECT_BYTES
                            or entry.get("encrypted") is not True):
                        raise ValueError("Invalid retained recovery object")
                    existing_size = objects[digest]["bytes"] if digest in objects else next(
                        (item[2] for item in pending if item[1] == digest), None
                    )
                    if existing_size is not None:
                        if existing_size != size:
                            raise ValueError("Duplicate recovery digest has conflicting size")
                        continue
                    original = intake / device / source / digest
                    if any(path.is_symlink() for path in (original, original.parent, original.parent.parent)):
                        raise ValueError("Intake scope cannot contain symbolic links")
                    if pending and (len(pending) >= PACK_FILES or pending_bytes + size > PACK_BYTES):
                        _commit_pack(target, pending, objects)
                        pending_bytes = 0
                    pending.append((original, digest, size))
                    pending_bytes += size
                _commit_pack(target, pending, objects)
                map_raw = json.dumps({"schema_version": 1, "batch_id": batch_id, "revision": revision,
                                      "manifest_sha256": manifest_hash, "objects": objects},
                                     sort_keys=True, separators=(",", ":")).encode()
                map_hash, _ = _save_bytes(target, "pack-map", map_raw)
                actual_hash, _ = _save_bytes(target, "manifest", raw)
                if actual_hash != manifest_hash:
                    raise ValueError("Retained manifest digest changed")
                pointer = json.dumps({"schema_version": 1, "batch_id": batch_id, "revision": revision,
                                      "manifest_sha256": manifest_hash, "map_sha256": map_hash},
                                     sort_keys=True, separators=(",", ":")).encode()
                _check_io_pressure()
                fd, name = tempfile.mkstemp(prefix=".packed-receipt-", dir=target)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(pointer)
                    stream.flush()
                    os.fsync(stream.fileno())
                _commit_file(Path(name), target / f"receipt-{manifest_hash}.json",
                             hashlib.sha256(pointer).hexdigest(), len(pointer))
                old = published.execute("SELECT manifest_sha256,map_sha256 FROM publications "
                                        "WHERE batch_id=? AND revision=?", (batch_id, revision)).fetchone()
                if old is not None and old != (manifest_hash, map_hash):
                    raise ValueError("Packed publication history conflicts")
                published.execute("INSERT OR IGNORE INTO publications VALUES (?,?,?,?)",
                                  (batch_id, revision, manifest_hash, map_hash))
                result = {"batch_id": batch_id, "revision": revision, "manifest_sha256": manifest_hash,
                          "map_sha256": map_hash, "coverage": manifest["coverage"],
                          "objects": len(objects), "storage": "packed-v2"}
            published.commit()
            return result
        except BaseException:
            published.rollback()
            raise


def read_packed_receipt(directory: Path, manifest_sha256: str) -> dict[str, Any]:
    """Find a retained map from its known manifest digest without server state."""
    if not re.fullmatch(r"[a-f0-9]{64}", manifest_sha256):
        raise ValueError("Invalid manifest digest")
    path = Path(directory) / f"receipt-{manifest_sha256}.json"
    if path.is_symlink():
        raise ValueError("Recovery receipt cannot be a symbolic link")
    with path.open("rb") as stream:
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise ValueError("Recovery receipt exceeds supported limits")
    receipt = json.loads(raw)
    if (not isinstance(receipt, dict) or receipt.get("schema_version") != 1
            or receipt.get("manifest_sha256") != manifest_sha256
            or not isinstance(receipt.get("map_sha256"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", receipt["map_sha256"])):
        raise ValueError("Invalid recovery receipt")
    return receipt


def extract_packed_capsule(directory: Path, *, manifest_sha256: str, map_sha256: str,
                           object_sha256: str, destination: Path) -> None:
    """Restore one encrypted capsule, verifying manifest, map, pack and object hashes."""
    if any(not re.fullmatch(r"[a-f0-9]{64}", item) for item in
           (manifest_sha256, map_sha256, object_sha256)):
        raise ValueError("Invalid recovery digest")
    directory = Path(directory).resolve(strict=True)
    manifest_path, map_path = directory / f"manifest-{manifest_sha256}.json", directory / f"pack-map-{map_sha256}.json"
    if manifest_path.is_symlink() or map_path.is_symlink():
        raise ValueError("Recovery metadata cannot be symbolic links")
    with manifest_path.open("rb") as stream:
        raw = stream.read(64 * 1024 * 1024 + 1)
    with map_path.open("rb") as stream:
        map_raw = stream.read(64 * 1024 * 1024 + 1)
    if len(raw) > 64 * 1024 * 1024 or len(map_raw) > 64 * 1024 * 1024:
        raise ValueError("Recovery metadata exceeds supported limits")
    if hashlib.sha256(raw).hexdigest() != manifest_sha256 or hashlib.sha256(map_raw).hexdigest() != map_sha256:
        raise ValueError("Recovery metadata digest mismatch")
    manifest, mapping = json.loads(raw), json.loads(map_raw)
    if (mapping.get("manifest_sha256") != manifest_sha256 or mapping.get("batch_id") != manifest.get("batch_id")
            or mapping.get("revision") != manifest.get("revision")):
        raise ValueError("Recovery map does not match the manifest")
    entries = [e for e in manifest["entries"] if e.get("status") == "CAPTURED"
               and e.get("sha256") == object_sha256]
    item = mapping.get("objects", {}).get(object_sha256)
    if not entries or not isinstance(item, dict) or item.get("bytes") != entries[0].get("bytes"):
        raise ValueError("Requested object is not in this retained manifest")
    pack_hash, pack_size = item.get("pack_sha256"), item.get("pack_bytes")
    if not isinstance(pack_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", pack_hash) or type(pack_size) is not int:
        raise ValueError("Invalid retained pack")
    pack_path = directory / f"pack-{pack_hash}.zip"
    if pack_path.is_symlink() or _digest(pack_path) != (pack_hash, pack_size):
        raise ValueError("Recovery pack failed verification")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    fd, name = tempfile.mkstemp(prefix=".packed-restore-", dir=destination.parent)
    temporary = Path(name)
    try:
        digest, count = hashlib.sha256(), 0
        with os.fdopen(fd, "wb") as out, zipfile.ZipFile(pack_path) as pack:
            info = pack.getinfo(object_sha256)
            if info.compress_type != zipfile.ZIP_STORED or info.file_size != item["bytes"]:
                raise ValueError("Packed capsule metadata is inconsistent")
            with pack.open(info) as inp:
                for chunk in iter(lambda: inp.read(1024 * 1024), b""):
                    out.write(chunk)
                    digest.update(chunk)
                    count += len(chunk)
            out.flush()
            os.fsync(out.fileno())
        if digest.hexdigest() != object_sha256 or count != item["bytes"]:
            raise ValueError("Restored capsule failed verification")
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
