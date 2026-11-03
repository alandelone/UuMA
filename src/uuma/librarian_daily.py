"""Daily workstation recovery capture for an explicitly configured SQLite source."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .librarian_delivery import deliver_queued_batch
from .librarian_intake import IDENTITY
from .librarian_queue import capture_recovery_batch, retry_partial_batch


def run_daily_sqlite(
    *, queue: Path, device: str, source: str, database: Path, public_key: Path,
    host: str, ssh_identity: Path, now: datetime | None = None,
) -> dict[str, Any]:
    """Capture one dated SQLite source then deliver its retained revisions.

    When a previous attempt on the same local date is partial, retry unavailable
    entries as an append-only revision. A failed delivery leaves the queue pending.
    The result describes server intake, never NAS publication or full-device coverage.
    """
    if not IDENTITY.fullmatch(device) or not IDENTITY.fullmatch(source):
        raise ValueError("Invalid configured device or source")
    current = now or datetime.now(ZoneInfo("Asia/Singapore"))
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("Capture time must have an explicit timezone")
    day = current.astimezone(ZoneInfo("Asia/Singapore")).date().isoformat()
    batch_id = f"librarian:{device}:{source}:{day}"
    prefix = f"librarian:{device}:{source}:"
    queue = Path(queue)
    key = Path(public_key)
    if key.is_symlink() or not key.is_file():
        raise ValueError("Configured recovery public key is unavailable")
    public = key.read_bytes()
    existing = None
    previous_days: list[date] = []
    db_path = queue / "queue.sqlite"
    if db_path.is_symlink():
        raise ValueError("Local queue cannot be a symbolic link")
    if db_path.exists():
        with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            row = db.execute("SELECT manifest_json FROM batches WHERE batch_id=?", (batch_id,)).fetchone()
            existing = json.loads(row[0]) if row else None
            for (known_id,) in db.execute("SELECT batch_id FROM batches"):
                if known_id.startswith(prefix):
                    try:
                        known_day = date.fromisoformat(known_id.removeprefix(prefix))
                    except ValueError:
                        continue
                    if known_day < date.fromisoformat(day):
                        previous_days.append(known_day)
    if existing is not None and existing["coverage"] == "PARTIAL":
        batch = retry_partial_batch(queue, batch_id, public)
    else:
        batch = capture_recovery_batch(queue, device, source, day, [Path(database)], public,
                                       sqlite_paths=frozenset({Path(database)}))
    result: dict[str, Any] = {"batch_id": batch_id, "revision": batch.get("revision", 1),
                              "coverage": batch["coverage"], "server_intake": "PENDING",
                              "nas_publication": "NOT_CHECKED", "actual_captured_at": batch["captured_at"]}
    previous_day = max(previous_days) if previous_days else None
    missed_count = max(0, (date.fromisoformat(day) - previous_day).days - 1) if previous_day else 0
    result["missed_dates_count"] = missed_count
    result["missed_dates_sample"] = [
        (previous_day + timedelta(days=i)).isoformat() for i in range(1, min(missed_count, 31) + 1)
    ] if previous_day else []
    try:
        receipt = deliver_queued_batch(queue, batch_id, host=host, identity_file=ssh_identity)
        result["server_intake"] = "DELIVERED"
        result["server_manifest_sha256"] = receipt["sha256"]
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        result["delivery_error_type"] = type(exc).__name__
    # Old pending batches are transferred using their original identity, not recaptured.
    with closing(sqlite3.connect((queue / "queue.sqlite").resolve().as_uri() + "?mode=ro", uri=True)) as db:
        older = sorted(known_id for (known_id,) in db.execute(
            "SELECT batch_id FROM batches WHERE delivery_state='PENDING'"
        ) if known_id.startswith(prefix) and known_id != batch_id)
    delivered_old = 0
    for pending in older[:10]:
        try:
            deliver_queued_batch(queue, pending, host=host, identity_file=ssh_identity)
            delivered_old += 1
        except (OSError, ValueError, RuntimeError, sqlite3.Error):
            break
    result["older_pending_before_retry"] = len(older)
    result["older_batches_delivered"] = delivered_old
    return result
