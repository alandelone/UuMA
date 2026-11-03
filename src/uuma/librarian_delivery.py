"""Deliver frozen recovery-batch revisions over the device-bound SSH transport."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from .librarian_intake import IDENTITY, MAX_SESSION_REQUESTS
from .librarian_transfer import (
    DEFAULT_BYTES_PER_SECOND,
    send_manifest_over_ssh,
    send_objects_over_ssh,
    send_over_ssh,
)


def deliver_queued_batch(
    root: Path, batch_id: str, *, host: str, identity_file: Path,
    timeout_seconds: float = 14400, bytes_per_second: int = DEFAULT_BYTES_PER_SECOND,
    use_sessions: bool = False,
) -> dict[str, Any]:
    """Send all immutable revisions; mark delivered only if the queue did not change.

    Retried transfers replay older manifests in order. Server-side source grants and
    receipt checks remain authoritative. No SSH key or credential is copied to NAS.
    """
    root = Path(root).resolve(strict=True)
    db_path = root / "queue.sqlite"
    if db_path.is_symlink():
        raise ValueError("Local queue cannot be a symbolic link")
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=rw", uri=True)) as db:
        current = db.execute("SELECT manifest_json FROM batches WHERE batch_id=?", (batch_id,)).fetchone()
        if current is None:
            raise KeyError("Unknown queued batch")
        table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='batch_revisions'").fetchone()
        revisions = (db.execute("SELECT revision,manifest_json FROM batch_revisions WHERE batch_id=? "
                                "ORDER BY revision", (batch_id,)).fetchall() if table else [])
        if not revisions:
            # Legacy first revision predates the append-only revisions table.
            revisions = [(1, current[0])]
        if revisions[-1][1] != current[0]:
            raise ValueError("Frozen batch history does not match the current queue")
        manifests = []
        previous_digest = None
        for expected_revision, (revision, raw) in enumerate(revisions, 1):
            manifest = json.loads(raw)
            if revision != expected_revision or manifest.get("revision", 1) != expected_revision:
                raise ValueError("Frozen batch revision history is incomplete")
            if expected_revision > 1 and manifest.get("previous_manifest_sha256") != previous_digest:
                raise ValueError("Frozen batch predecessor does not match")
            device, source = manifest.get("device"), manifest.get("source")
            if (not isinstance(device, str) or not IDENTITY.fullmatch(device)
                    or not isinstance(source, str) or not IDENTITY.fullmatch(source)
                    or manifest.get("batch_id") != batch_id):
                raise ValueError("Frozen batch identity is invalid")
            previous_digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            manifests.append((raw, manifest))
        sent: set[tuple[str, str, str]] = set()
        for raw, manifest in manifests:
            pending_objects: list[tuple[Path, str]] = []
            for entry in manifest["entries"]:
                if entry["status"] == "UNAVAILABLE":
                    continue
                reference = entry.get("object_ref", "")
                digest = entry.get("sha256", "")
                if (entry["status"] != "CAPTURED" or not isinstance(reference, str)
                        or not re.fullmatch(r"objects/[a-f0-9]{32}/[0-9]+\.capsule", reference)
                        or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)):
                    raise ValueError("Frozen batch object reference is invalid")
                path = root / reference
                if any(part.is_symlink() for part in (path, path.parent, path.parent.parent)):
                    raise ValueError("Frozen batch object cannot contain symbolic links")
                if not path.resolve(strict=True).is_relative_to(root):
                    raise ValueError("Frozen batch object escaped the local queue")
                key = (manifest["device"], manifest["source"], digest)
                if key in sent:
                    # A successful receipt in this same delivery proves this object
                    # is already present for this device and source. Each manifest
                    # is still independently verified and committed by the receiver.
                    continue
                if use_sessions:
                    pending_objects.append((path, digest))
                    if len(pending_objects) == MAX_SESSION_REQUESTS:
                        send_objects_over_ssh(pending_objects, device=manifest["device"],
                                              source=manifest["source"], host=host,
                                              identity_file=identity_file, timeout_seconds=timeout_seconds,
                                              bytes_per_second=bytes_per_second)
                        sent.update((manifest["device"], manifest["source"], item[1])
                                    for item in pending_objects)
                        pending_objects = []
                else:
                    send_over_ssh(path, device=manifest["device"], source=manifest["source"],
                                  expected_digest=digest, host=host, identity_file=identity_file,
                                  timeout_seconds=timeout_seconds, bytes_per_second=bytes_per_second)
                    sent.add(key)
            if pending_objects:
                send_objects_over_ssh(pending_objects, device=manifest["device"],
                                      source=manifest["source"], host=host,
                                      identity_file=identity_file, timeout_seconds=timeout_seconds,
                                      bytes_per_second=bytes_per_second)
                sent.update((manifest["device"], manifest["source"], item[1])
                            for item in pending_objects)
            receipt = send_manifest_over_ssh(raw.encode("utf-8"), device=manifest["device"],
                                             source=manifest["source"], host=host,
                                             identity_file=identity_file, timeout_seconds=timeout_seconds,
                                             bytes_per_second=bytes_per_second)
        db.execute("BEGIN IMMEDIATE")
        try:
            result = db.execute("UPDATE batches SET delivery_state='DELIVERED' "
                                "WHERE batch_id=? AND manifest_json=?", (batch_id, current[0]))
            if result.rowcount != 1:
                raise ValueError("Queued batch changed during delivery; latest revision remains pending")
            db.commit()
        except BaseException:
            db.rollback()
            raise
    return receipt
