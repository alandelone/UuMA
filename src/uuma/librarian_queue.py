"""Local durable recovery-capture queue. No network, scheduler, or source mutation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import uuid
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from .librarian_append_snapshot import snapshot_append_only_jsonl
from .librarian_crypto import seal
from .librarian_snapshot import snapshot_sqlite

IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")


def _key_fingerprint(public_pem: bytes) -> str:
    public = serialization.load_pem_public_key(public_pem)
    if not isinstance(public, rsa.RSAPublicKey) or public.key_size < 3072:
        raise ValueError("Recovery public key must be RSA with at least 3072 bits")
    return hashlib.sha256(public.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo,
    )).hexdigest()


def _capture_source(
    root: Path, original: Path, directory: Path, index: int, public_pem: bytes, method: str,
    bytes_per_second: int | None,
) -> dict[str, object]:
    if original.is_symlink() or not original.is_file():
        raise ValueError("Source is absent or is a symbolic link")
    output = directory / f"{index}.capsule"
    metadata: dict[str, object] = {"capture_method": method}
    if method == "sqlite_online":
        # Temporary plaintext is confined to this private local queue; it is never sent
        # to intake. The unique staging directory is removed after encryption.
        with tempfile.TemporaryDirectory(prefix=".sqlite-snapshot-", dir=root) as staged:
            snapshot = Path(staged) / "snapshot.sqlite"
            proof = snapshot_sqlite(original, snapshot)
            metadata.update(seal(snapshot, output, public_pem, bytes_per_second=bytes_per_second))
            metadata["snapshot_sha256"] = proof["sha256"]
            metadata["sqlite_user_version"] = proof["sqlite_user_version"]
    elif method == "append_only_jsonl":
        with tempfile.TemporaryDirectory(prefix=".jsonl-snapshot-", dir=root) as staged:
            snapshot = Path(staged) / "snapshot.jsonl"
            metadata.update(snapshot_append_only_jsonl(original, snapshot,
                                                        bytes_per_second=bytes_per_second))
            metadata.update(seal(snapshot, output, public_pem, bytes_per_second=bytes_per_second))
    elif method == "stable_file":
        before = original.stat()
        with original.open("rb") as stream:
            if stream.read(16) == b"SQLite format 3\x00":
                raise ValueError("SQLite sources require an online snapshot")
        metadata.update(seal(original, output, public_pem, bytes_per_second=bytes_per_second))
        after = original.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (
            after.st_size, after.st_mtime_ns, after.st_ino
        ):
            raise ValueError("Source changed while being captured")
    else:
        raise ValueError("Unknown capture method")
    metadata.update(object_ref=output.relative_to(root).as_posix(), status="CAPTURED",
                    actual_captured_at=datetime.now(UTC).isoformat())
    return metadata


def capture_recovery_batch(
    root: Path, device: str, source: str, scheduled_date: str,
    files: list[Path], public_pem: bytes, *, sqlite_paths: frozenset[Path] = frozenset(),
    bytes_per_second: int | None = None, append_only_paths: frozenset[Path] = frozenset(),
) -> dict[str, object]:
    """Freeze one encrypted batch per source/date from trusted explicit file paths.

    Explicit SQLite paths use the online backup API; a database passed as a regular
    file fails closed. Partial captures remain immutable evidence and are retried
    only through an explicit append-only revision.
    """
    if not IDENTITY.fullmatch(device) or not IDENTITY.fullmatch(source):
        raise ValueError("Invalid source/device identity")
    if date.fromisoformat(scheduled_date).isoformat() != scheduled_date:
        raise ValueError("Invalid scheduled date")
    if not files:
        raise ValueError("An explicit nonempty source file list is required")
    sqlite_set = {str(Path(path).absolute()) for path in sqlite_paths}
    append_set = {str(Path(path).absolute()) for path in append_only_paths}
    if not sqlite_set.issubset({str(Path(path).absolute()) for path in files}):
        raise ValueError("Every SQLite source must belong to the explicit source list")
    if (not append_set.issubset({str(Path(path).absolute()) for path in files})
            or sqlite_set & append_set or any(Path(path).suffix.casefold() != ".jsonl" for path in append_set)):
        raise ValueError("Append-only histories must be explicitly listed JSONL sources")
    fingerprint = _key_fingerprint(public_pem)
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    batch_id = f"librarian:{device}:{source}:{scheduled_date}"
    with closing(sqlite3.connect(root / "queue.sqlite", timeout=5)) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS batches (
            batch_id TEXT PRIMARY KEY, manifest_json TEXT NOT NULL,
            delivery_state TEXT NOT NULL DEFAULT 'PENDING')""")
        db.execute("""CREATE TABLE IF NOT EXISTS batch_revisions (
            batch_id TEXT NOT NULL, revision INTEGER NOT NULL, manifest_json TEXT NOT NULL,
            PRIMARY KEY(batch_id,revision))""")
        db.execute("BEGIN IMMEDIATE")
        try:
            prior = db.execute(
                "SELECT manifest_json FROM batches WHERE batch_id=?", (batch_id,),
            ).fetchone()
            if prior:
                saved = json.loads(prior[0])
                if saved.get("recovery_key_fingerprint", fingerprint) != fingerprint:
                    raise ValueError("Daily batch cannot change its recovery key")
                db.commit()
                return saved
            attempt = uuid.uuid4().hex
            directory = root / "objects" / attempt
            directory.mkdir(parents=True, exist_ok=False)
            entries = []
            seen = set()
            for index, file in enumerate(files):
                original = Path(file).absolute()
                if str(original) in seen:
                    raise ValueError("Duplicate source file")
                seen.add(str(original))
                method = ("sqlite_online" if str(original) in sqlite_set else "append_only_jsonl"
                          if str(original) in append_set else "stable_file")
                entry: dict[str, object] = {"source_path": str(original), "capture_method": method}
                try:
                    entry.update(_capture_source(root, original, directory, index, public_pem, method,
                                                 bytes_per_second))
                except (OSError, ValueError, sqlite3.Error) as exc:
                    entry.update(status="UNAVAILABLE", error_type=type(exc).__name__)
                entries.append(entry)
            manifest = {
                "schema_version": 1, "batch_id": batch_id, "device": device,
                "source": source, "scheduled_date": scheduled_date,
                "captured_at": datetime.now(UTC).isoformat(),
                "revision": 1, "previous_manifest_sha256": None,
                "recovery_key_fingerprint": fingerprint,
                "coverage": "COMPLETE" if all(
                    item["status"] == "CAPTURED" for item in entries
                ) else "PARTIAL",
                "capture_kind": "encrypted_recovery_files", "entries": entries,
            }
            encoded = json.dumps(manifest, sort_keys=True)
            db.execute("INSERT INTO batches(batch_id,manifest_json) VALUES (?,?)", (batch_id, encoded))
            db.execute("INSERT INTO batch_revisions VALUES (?,?,?)", (batch_id, 1, encoded))
            db.commit()
            return manifest
        except BaseException:
            db.rollback()
            raise


def retry_partial_batch(
    root: Path, batch_id: str, public_pem: bytes, *, bytes_per_second: int | None = None,
    append_only_paths: frozenset[Path] = frozenset(),
) -> dict[str, object]:
    """Append one revision retrying unavailable files of an existing dated batch.

    Previously captured entries are retained byte-for-byte. The newly captured time
    is recorded on each retried entry, never presented as the scheduled midnight.
    """
    root = Path(root).resolve(strict=True)
    with closing(sqlite3.connect((root / "queue.sqlite").as_uri() + "?mode=rw", uri=True)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS batch_revisions (
                batch_id TEXT NOT NULL, revision INTEGER NOT NULL, manifest_json TEXT NOT NULL,
                PRIMARY KEY(batch_id,revision))""")
            row = db.execute("SELECT manifest_json FROM batches WHERE batch_id=?", (batch_id,)).fetchone()
            if row is None:
                raise KeyError("Unknown queued batch")
            previous_json = row[0]
            previous = json.loads(previous_json)
            append_set = {str(Path(path).absolute()) for path in append_only_paths}
            unavailable = {str(Path(item["source_path"]).absolute()) for item in previous["entries"]
                           if item["status"] == "UNAVAILABLE"}
            if (not append_set.issubset(unavailable)
                    or any(Path(path).suffix.casefold() != ".jsonl" for path in append_set)):
                raise ValueError("Only unavailable JSONL histories can use the append-only retry")
            db.execute("INSERT OR IGNORE INTO batch_revisions VALUES (?,?,?)", (
                batch_id, previous.get("revision", 1), previous_json,
            ))
            if previous["coverage"] == "COMPLETE":
                db.commit()
                return previous
            fingerprint = _key_fingerprint(public_pem)
            if previous.get("recovery_key_fingerprint", fingerprint) != fingerprint or any(
                item.get("key_fingerprint") != fingerprint for item in previous["entries"]
                if item["status"] == "CAPTURED"
            ):
                raise ValueError("Partial batch cannot change its recovery key")
            revision = previous.get("revision", 1) + 1
            directory = root / "objects" / uuid.uuid4().hex
            directory.mkdir(parents=True, exist_ok=False)
            entries = []
            for index, prior in enumerate(previous["entries"]):
                if prior["status"] == "CAPTURED":
                    entries.append(prior)
                    continue
                original = Path(prior["source_path"])
                method = ("append_only_jsonl" if str(original.absolute()) in append_set
                          else prior.get("capture_method", "stable_file"))
                if method == "stable_file":
                    try:
                        with original.open("rb") as stream:
                            if stream.read(16) == b"SQLite format 3\x00":
                                method = "sqlite_online"
                    except OSError:
                        # The ordinary capture path records the remaining failure.
                        pass
                entry = {"source_path": str(original), "capture_method": method,
                         "retried_at": datetime.now(UTC).isoformat()}
                try:
                    entry.update(_capture_source(root, original, directory, index, public_pem, method,
                                                 bytes_per_second))
                except (OSError, ValueError, sqlite3.Error) as exc:
                    entry.update(status="UNAVAILABLE", error_type=type(exc).__name__)
                entries.append(entry)
            manifest = dict(previous)
            manifest.update(
                revision=revision,
                previous_manifest_sha256=hashlib.sha256(previous_json.encode("utf-8")).hexdigest(),
                revised_at=datetime.now(UTC).isoformat(), entries=entries,
                coverage="COMPLETE" if all(item["status"] == "CAPTURED" for item in entries)
                else "PARTIAL",
            )
            encoded = json.dumps(manifest, sort_keys=True)
            db.execute("INSERT INTO batch_revisions VALUES (?,?,?)", (batch_id, revision, encoded))
            db.execute("UPDATE batches SET manifest_json=?,delivery_state='PENDING' WHERE batch_id=?",
                       (encoded, batch_id))
            db.commit()
            return manifest
        except BaseException:
            db.rollback()
            raise


def deliver_recovery_batch(root: Path, batch_id: str, destination: Path) -> dict[str, object]:
    """Deliver a frozen batch to a trusted recovery-only destination, then record a receipt.

    Caller serializes publication through this queue. Credentials are never decrypted.
    This function must not target the ordinary agent-readable archive object tree.
    """
    root = Path(root).resolve(strict=True)
    destination = Path(destination).resolve(strict=True)
    with closing(sqlite3.connect((root / "queue.sqlite").as_uri() + "?mode=rw", uri=True)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute(
                "SELECT manifest_json FROM batches WHERE batch_id=?", (batch_id,),
            ).fetchone()
            if row is None:
                raise KeyError("Unknown queued batch")
            manifest = json.loads(row[0])
            directory = destination / hashlib.sha256(batch_id.encode()).hexdigest()
            if directory.is_symlink():
                raise ValueError("Delivery directory cannot be a symbolic link")
            directory.mkdir(exist_ok=True)
            for item in manifest["entries"]:
                if item["status"] != "CAPTURED":
                    continue
                reference = item["object_ref"]
                if not re.fullmatch(r"objects/[a-f0-9]{32}/[0-9]+\.capsule", reference):
                    raise ValueError("Invalid queued object reference")
                source = root / reference
                if any(part.is_symlink() for part in [source, source.parent, source.parent.parent]):
                    raise ValueError("Queued object cannot contain symbolic links")
                digest = item["sha256"]
                if not re.fullmatch(r"[a-f0-9]{64}", digest):
                    raise ValueError("Invalid queued object digest")
                final = directory / digest
                if final.is_symlink():
                    raise ValueError("Delivered object cannot be a symbolic link")
                # Validate either a retained object or the newly staged full transfer.
                staged = directory / (".pending-" + uuid.uuid4().hex)
                candidate = final if final.exists() else staged
                hasher = hashlib.sha256()
                size = 0
                if candidate == staged:
                    with source.open("rb") as inp, staged.open("xb") as out:
                        for chunk in iter(lambda: inp.read(1024 * 1024), b""):
                            out.write(chunk)
                        out.flush()
                        os.fsync(out.fileno())
                with candidate.open("rb") as inp:
                    for chunk in iter(lambda: inp.read(1024 * 1024), b""):
                        hasher.update(chunk)
                        size += len(chunk)
                if size != item["bytes"] or hasher.hexdigest() != digest:
                    raise ValueError("Delivered recovery object failed verification")
                if candidate == staged:
                    # All publishers for this batch are serialized by the local queue transaction.
                    if final.exists():
                        raise FileExistsError("Recovery object appeared during publication")
                    staged.rename(final)
            encoded = row[0].encode("utf-8")
            final_manifest = directory / "manifest.json"
            if final_manifest.is_symlink():
                raise ValueError("Delivered manifest cannot be a symbolic link")
            if final_manifest.exists() and final_manifest.read_bytes() != encoded:
                # Preserve the original manifest and each subsequent immutable revision.
                final_manifest = directory / ("manifest-" + hashlib.sha256(encoded).hexdigest() + ".json")
                if final_manifest.is_symlink():
                    raise ValueError("Delivered manifest cannot be a symbolic link")
            if final_manifest.exists():
                if final_manifest.read_bytes() != encoded:
                    raise ValueError("Published batch revision differs from frozen queue")
            else:
                staged_manifest = directory / (".manifest-" + uuid.uuid4().hex)
                with staged_manifest.open("xb") as out:
                    out.write(encoded)
                    out.flush()
                    os.fsync(out.fileno())
                staged_manifest.rename(final_manifest)
            db.execute("UPDATE batches SET delivery_state='DELIVERED' WHERE batch_id=?", (batch_id,))
            db.commit()
            return {"batch_id": batch_id, "delivery_state": "DELIVERED",
                    "coverage": manifest["coverage"], "manifest_sha256": hashlib.sha256(
                        encoded,
                    ).hexdigest()}
        except BaseException:
            db.rollback()
            raise
