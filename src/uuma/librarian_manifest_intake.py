"""Private server intake for authenticated recovery-batch manifest revisions."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Any

from .librarian_intake import IDENTITY, MAX_OBJECT_BYTES, DeviceGrant, _verify

MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_ENTRIES = 100000


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate manifest key")
        result[key] = value
    return result


def receive_manifest(root: Path, grant: DeviceGrant, source: str, raw: bytes) -> dict[str, object]:
    """Commit one verified revision without granting MCP access or publishing NAS data.

    The SSH launcher must supply the already authenticated grant and private root.
    Source paths inside the manifest remain untrusted metadata and are never opened.
    """
    if (not IDENTITY.fullmatch(grant.device) or not IDENTITY.fullmatch(source)
            or source not in grant.sources or any(not IDENTITY.fullmatch(s) for s in grant.sources)):
        raise PermissionError("Device is not granted this source")
    if not 1 <= len(raw) <= MAX_MANIFEST_BYTES:
        raise ValueError("Manifest exceeds private intake limits")
    manifest = json.loads(raw, object_pairs_hook=_unique)
    if (not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int
            or manifest.get("schema_version") != 1):
        raise ValueError("Unsupported manifest")
    day = manifest.get("scheduled_date")
    if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
        raise ValueError("Invalid manifest date")
    batch_id = f"librarian:{grant.device}:{source}:{day}"
    if (manifest.get("batch_id") != batch_id or manifest.get("device") != grant.device
            or manifest.get("source") != source
            or manifest.get("capture_kind") != "encrypted_recovery_files"):
        raise PermissionError("Manifest identity does not match the authenticated source")
    revision = manifest.get("revision")
    previous = manifest.get("previous_manifest_sha256")
    if type(revision) is not int or revision < 1 or revision > 1000000:
        raise ValueError("Invalid manifest revision")
    if revision == 1:
        if previous is not None:
            raise ValueError("Initial manifest cannot have a predecessor")
    elif not isinstance(previous, str) or not re.fullmatch(r"[a-f0-9]{64}", previous):
        raise ValueError("Manifest predecessor is required")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries or len(entries) > MAX_MANIFEST_ENTRIES:
        raise ValueError("Manifest must contain source entries")
    statuses = []
    root = Path(root).resolve(strict=True)
    directory = root / grant.device / source
    if any(path.is_symlink() for path in (root / grant.device, directory)):
        raise ValueError("Intake scope cannot be a symbolic link")
    if not directory.resolve(strict=True).is_relative_to(root):
        raise ValueError("Intake scope escaped its configured root")
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("status") not in {"CAPTURED", "UNAVAILABLE"}:
            raise ValueError("Invalid manifest entry")
        statuses.append(entry["status"])
        if entry["status"] == "CAPTURED":
            digest, size = entry.get("sha256"), entry.get("bytes")
            if (not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
                    or type(size) is not int or not 0 < size <= MAX_OBJECT_BYTES
                    or entry.get("encrypted") is not True):
                raise ValueError("Invalid encrypted object reference")
            if not _verify(directory / digest, size, digest):
                raise ValueError("Intake object failed verification")
    expected = "COMPLETE" if all(status == "CAPTURED" for status in statuses) else "PARTIAL"
    if manifest.get("coverage") != expected:
        raise ValueError("Manifest coverage does not match its entries")
    digest = hashlib.sha256(raw).hexdigest()
    db_path = root / "recovery-intake.sqlite"
    if db_path.is_symlink():
        raise ValueError("Intake ledger cannot be a symbolic link")
    with closing(sqlite3.connect(db_path, timeout=5)) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS manifest_revisions (
            batch_id TEXT NOT NULL, revision INTEGER NOT NULL, sha256 TEXT NOT NULL,
            raw BLOB NOT NULL, PRIMARY KEY(batch_id,revision))""")
        db.execute("BEGIN IMMEDIATE")
        try:
            prior = db.execute("SELECT sha256 FROM manifest_revisions WHERE batch_id=? AND revision=?",
                               (batch_id, revision)).fetchone()
            if prior:
                if prior[0] != digest:
                    raise ValueError("Conflicting manifest revision")
                db.commit()
                return {"batch_id": batch_id, "revision": revision, "sha256": digest,
                        "coverage": expected, "reused": True}
            last = db.execute("SELECT revision,sha256,raw FROM manifest_revisions WHERE batch_id=? "
                              "ORDER BY revision DESC LIMIT 1", (batch_id,)).fetchone()
            if (last is None and revision != 1) or (last is not None and (
                revision != last[0] + 1 or previous != last[1]
            )):
                raise ValueError("Manifest history is incomplete or does not match")
            if last is not None:
                earlier = json.loads(last[2], object_pairs_hook=_unique)["entries"]
                if len(earlier) != len(entries):
                    raise ValueError("Manifest revision changed the original source list")
                for old, new in zip(earlier, entries, strict=True):
                    if old.get("source_path") != new.get("source_path"):
                        raise ValueError("Manifest revision changed an original source identity")
                    if old.get("status") == "CAPTURED" and old != new:
                        raise ValueError("Manifest revision altered an earlier captured entry")
            db.execute("INSERT INTO manifest_revisions VALUES (?,?,?,?)", (batch_id, revision, digest, raw))
            db.commit()
            return {"batch_id": batch_id, "revision": revision, "sha256": digest,
                    "coverage": expected, "reused": False}
        except BaseException:
            db.rollback()
            raise
