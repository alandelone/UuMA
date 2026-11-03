"""Workstation recovery capture for explicitly registered local sources."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .librarian_delivery import deliver_queued_batch
from .librarian_intake import IDENTITY
from .librarian_manifest_intake import MAX_MANIFEST_BYTES
from .librarian_queue import _key_fingerprint, capture_recovery_batch, retry_partial_batch
from .librarian_server_daily import _tree
from .librarian_transfer import DEFAULT_BYTES_PER_SECOND


def run_sources(
    specs: list[dict[str, str]], *, queue: Path, public_pem: bytes, device: str,
    host: str, ssh_identity: Path, now: datetime | None = None,
    on_result: Callable[[dict[str, Any]], None] | None = None,
    use_sessions: bool = False,
) -> dict[str, Any]:
    """Capture explicit local sources and send encrypted recovery batches to intake.

    Paths and source names are selected by trusted local configuration. All contents
    remain recovery-only; this function never grants semantic MCP read access.
    """
    if not IDENTITY.fullmatch(device):
        raise ValueError("Invalid workstation identity")
    ids = [spec.get("source_id") for spec in specs]
    if (not specs or len(specs) > 500 or any(not isinstance(x, str) or not IDENTITY.fullmatch(x) for x in ids)
            or len(ids) != len(set(ids))):
        raise ValueError("Invalid or duplicate workstation source identities")
    fingerprint = _key_fingerprint(public_pem)
    current = now or datetime.now(ZoneInfo("Asia/Singapore"))
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("Workstation capture time requires a timezone")
    day = current.astimezone(ZoneInfo("Asia/Singapore")).date().isoformat()
    queue = Path(queue).resolve(strict=True)
    if not queue.is_dir():
        raise ValueError("Private workstation queue must already exist")
    database = queue / "queue.sqlite"
    if database.is_symlink():
        raise ValueError("Workstation queue cannot be a symbolic link")
    results: list[dict[str, Any]] = []
    historical: dict[str, list[date]] = {source: [] for source in ids}
    if database.is_file():
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
            for (known_id,) in db.execute("SELECT batch_id FROM batches"):
                for source in ids:
                    prefix = f"librarian:{device}:{source}:"
                    if known_id.startswith(prefix):
                        try:
                            known_day = date.fromisoformat(known_id.removeprefix(prefix))
                        except ValueError:
                            continue
                        if known_day < date.fromisoformat(day):
                            historical[source].append(known_day)
                        break

    def emit(result: dict[str, Any]) -> None:
        source = result["source"]
        last = max(historical[source]) if historical[source] else None
        missed = max(0, (date.fromisoformat(day) - last).days - 1) if last else None
        result["previous_capture_date"] = last.isoformat() if last else None
        result["missed_dates_count"] = missed
        result["missed_dates_sample"] = [
            (last + timedelta(days=i)).isoformat() for i in range(1, min(missed, 31) + 1)
        ] if last and missed is not None else []
        results.append(result)
        if on_result is not None:
            on_result(result)

    for spec in specs:
        source = spec["source_id"]
        batch_id = f"librarian:{device}:{source}:{day}"
        try:
            kind, path_value = spec.get("kind"), spec.get("path")
            if kind not in {"sqlite", "file", "tree"} or not isinstance(path_value, str):
                raise ValueError("Invalid registered workstation source")
            path = Path(path_value)
            if not path.is_absolute() or path.is_symlink():
                raise ValueError("Registered source must be an absolute non-symlink path")
            old = None
            old_raw = None
            state = None
            if database.is_file():
                with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
                    row = db.execute("SELECT manifest_json,delivery_state FROM batches WHERE batch_id=?",
                                     (batch_id,)).fetchone()
                    if row:
                        old_raw, state = row
                        old = json.loads(old_raw)
            if old is not None and (old.get("recovery_key_fingerprint", fingerprint) != fingerprint or any(
                entry.get("key_fingerprint") != fingerprint for entry in old["entries"]
                if entry["status"] == "CAPTURED"
            )):
                raise ValueError("Existing batch uses a different recovery key")
            if old is not None and old["coverage"] == "COMPLETE" and state == "DELIVERED":
                emit({"source": source, "batch_id": batch_id, "coverage": "COMPLETE",
                      "revision": old.get("revision", 1), "server_intake": "DELIVERED",
                      "nas_publication": "NOT_CHECKED", "actual_captured_at": old["captured_at"],
                      "manifest_sha256": hashlib.sha256(old_raw.encode("utf-8")).hexdigest(),
                      "intake_checked_live": False})
                continue
            if old is not None and old["coverage"] == "PARTIAL":
                # Retry the original source list, rather than allowing a changing tree
                # to prevent recovery of its already-recorded unavailable entries.
                append_paths = frozenset(
                    Path(entry["source_path"]) for entry in old["entries"]
                    if source in {"codex-sessions", "codex-archived"}
                    and entry["status"] == "UNAVAILABLE"
                    and Path(entry["source_path"]).suffix.casefold() == ".jsonl"
                )
                batch = retry_partial_batch(queue, batch_id, public_pem,
                                            bytes_per_second=DEFAULT_BYTES_PER_SECOND,
                                            append_only_paths=append_paths)
            elif kind == "sqlite":
                files, sqlite_paths = [path], frozenset({path})
            elif kind == "file":
                files, sqlite_paths = [path], frozenset()
            else:
                files, sqlite_paths = _tree(path)
                if not files:
                    emit({"source": source, "coverage": "EMPTY", "server_intake": "NOT_APPLICABLE",
                          "nas_publication": "NOT_APPLICABLE"})
                    continue
            if old is None or old["coverage"] != "PARTIAL":
                append_paths = frozenset(
                    item for item in files if source in {"codex-sessions", "codex-archived"}
                    and item.suffix.casefold() == ".jsonl"
                )
                batch = capture_recovery_batch(queue, device, source, day, files, public_pem,
                                               sqlite_paths=sqlite_paths,
                                               bytes_per_second=DEFAULT_BYTES_PER_SECOND,
                                               append_only_paths=append_paths)
            if len(json.dumps(batch, sort_keys=True).encode("utf-8")) > MAX_MANIFEST_BYTES:
                emit({"source": source, "batch_id": batch_id, "coverage": batch["coverage"],
                      "server_intake": "PENDING", "status": "MANIFEST_TOO_LARGE"})
                continue
            result = {"source": source, "batch_id": batch_id, "coverage": batch["coverage"],
                      "revision": batch.get("revision", 1), "server_intake": "PENDING",
                      "nas_publication": "NOT_CHECKED", "actual_captured_at": batch["captured_at"]}
            try:
                receipt = deliver_queued_batch(queue, batch_id, host=host, identity_file=ssh_identity,
                                               use_sessions=use_sessions)
                result["server_intake"] = "DELIVERED"
                result["manifest_sha256"] = receipt["sha256"]
                result["intake_checked_live"] = True
            except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
                result["delivery_error_type"] = type(exc).__name__
            emit(result)
        except (OSError, ValueError, TypeError, RuntimeError, sqlite3.Error) as exc:
            emit({"source": source, "status": "FAILED", "error_type": type(exc).__name__})
    older: list[str] = []
    if database.is_file():
        prefixes = tuple(f"librarian:{device}:{source}:" for source in ids)
        today = {f"librarian:{device}:{source}:{day}" for source in ids}
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
            for (batch,) in db.execute("SELECT batch_id FROM batches WHERE delivery_state='PENDING'"):
                if not batch.startswith(prefixes) or batch in today:
                    continue
                try:
                    batch_day = date.fromisoformat(batch.rsplit(":", 1)[-1])
                except ValueError:
                    continue
                if batch_day < date.fromisoformat(day):
                    older.append(batch)
        older.sort()
    delivered_old = 0
    for batch in older[:10]:
        try:
            deliver_queued_batch(queue, batch, host=host, identity_file=ssh_identity,
                                 use_sessions=use_sessions)
            delivered_old += 1
        except (OSError, ValueError, RuntimeError, sqlite3.Error):
            break
    incomplete = sum(item.get("coverage") not in {"COMPLETE", "EMPTY"}
                     or item.get("server_intake") not in {"DELIVERED", "NOT_APPLICABLE"}
                     for item in results)
    return {"date": day, "sources": results, "older_pending_before_retry": len(older),
            "older_batches_delivered": delivered_old,
            "incomplete": incomplete + max(0, len(older) - delivered_old)}
