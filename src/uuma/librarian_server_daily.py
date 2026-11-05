"""Source-scoped server capture into private recovery intake."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
from collections.abc import Callable
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .librarian_discovery import discover_page
from .librarian_intake import IDENTITY, DeviceGrant, receive_granted_object
from .librarian_manifest_intake import receive_manifest
from .librarian_queue import _key_fingerprint, capture_recovery_batch, retry_partial_batch


def owner_matches(spec: dict[str, Any]) -> bool:
    """Compare only the configured nonsecret path variable in the live owner process."""
    unit, key, expected = spec.get("owner_unit"), spec.get("owner_env"), spec.get("owner_value")
    if not all(isinstance(value, str) and value for value in (unit, key, expected)):
        return False
    if unit == "notion-sync.timer" and key == "NOTION_CACHE_PATH":
        # Notion uses a system timer and an inactive-between-runs oneshot service.
        # A timer trigger proves neither successful sync nor complete workspace access.
        path = Path(expected)
        if (spec.get("path") != expected or not path.is_absolute() or path.is_symlink()
                or not path.is_file() or path.stat().st_uid != os.geteuid()):
            return False
        timer = subprocess.run(
            ["systemctl", "show", unit, "-p", "LoadState", "-p", "ActiveState"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        fields = dict(line.split("=", 1) for line in timer.stdout.splitlines() if "=" in line)
        return timer.returncode == 0 and fields.get("LoadState") == "loaded" and fields.get("ActiveState") == "active"
    semantic_archive = (unit == "uuma-librarian-semantic.service"
                        and key == "UUMA_LIBRARIAN_ARCHIVE_ROOT"
                        and spec.get("path") == expected)
    ordinary_owner = (unit.startswith("uuma-") and unit.endswith(".service") and key in {
        "UUMA_DATA_DIR", "YONC_GRAPH_DB", "LAB_DATABASE_PATH", "HERMES_HOME",
    })
    if not (semantic_archive or ordinary_owner):
        return False
    result = subprocess.run(
        ["systemctl", "--user", "show", unit, "-p", "MainPID", "-p", "ActiveState"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if result.returncode or fields.get("ActiveState") != "active":
        return False
    try:
        pid = int(fields.get("MainPID", "0"))
        if pid <= 0:
            return False
        entries = (Path("/proc") / str(pid) / "environ").read_bytes().split(b"\0")
    except (OSError, ValueError):
        return False
    return key.encode() + b"=" + expected.encode() in entries


def _tree(path: Path) -> tuple[list[Path], frozenset[Path]]:
    """Enumerate a stable source without following links or silently excluding files."""
    from .librarian_discovery import discover

    cursor = None
    records: list[dict[str, Any]] = []
    for _ in range(100):
        try:
            page = discover_page(path, cursor=cursor, max_entries=10000)
        except ValueError as exc:
            if "restart its inventory" in str(exc) or "changed" in str(exc):
                walked = discover(path, max_files=100000, max_seconds=60)
                if any(iss.get("error_type") == "SYMLINK_NOT_FOLLOWED" for iss in walked.get("issues", [])):
                    raise ValueError("Source inventory contains inaccessible or unsupported entries") from exc
                records = walked["files"]
                cursor = None
                break
            raise
        if page["issues"]:
            raise ValueError("Source inventory contains inaccessible or unsupported entries")
        records.extend(page["files"])
        cursor = page["cursor"]
        if cursor is None:
            break
    if cursor is not None:
        raise ValueError("Source inventory is incomplete")
    paths = [path / item["relative_path"] for item in records]
    sqlite_paths = set()
    for candidate in paths:
        try:
            with candidate.open("rb") as stream:
                if stream.read(16) == b"SQLite format 3\x00":
                    sqlite_paths.add(candidate)
        except OSError:
            # Preserve inaccessible files in the explicit source list. Capture will
            # record them as unavailable, or reject a subsequently readable SQLite
            # file rather than silently copying it without an online snapshot.
            pass
    # A live WAL/SHM is represented by its owner's online SQLite snapshot. Never
    # treat separately copied sidecars as a consistent database backup.
    sidecars = {Path(str(database) + suffix) for database in sqlite_paths for suffix in ("-wal", "-shm")}
    return [candidate for candidate in paths if candidate not in sidecars], frozenset(sqlite_paths)


def run_sources(
    specs: list[dict[str, Any]], *, queue: Path, intake: Path, public_pem: bytes,
    now: datetime | None = None, verify_owner: Callable[[dict[str, Any]], bool] = owner_matches,
) -> dict[str, Any]:
    """Capture configured sources once per local date and verify server intake.

    Only explicitly registered absolute paths are scanned. This operation does not
    authorize readers, publish NAS data, or claim unregistered sources are covered.
    """
    current = now or datetime.now(ZoneInfo("Asia/Singapore"))
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("Server capture time requires a timezone")
    day = current.astimezone(ZoneInfo("Asia/Singapore")).date().isoformat()
    queue = Path(queue).resolve(strict=True)
    intake = Path(intake).resolve(strict=True)
    if (not queue.is_dir() or not intake.is_dir() or queue == intake
            or queue.is_symlink() or intake.is_symlink()):
        raise ValueError("Expected distinct existing private queue and intake roots")
    if os.name == "posix" and any(
        p.stat().st_uid != os.geteuid() or p.stat().st_mode & 0o077 for p in (queue, intake)
    ):
        raise PermissionError("Server queue and intake must be private to their owner")
    ids = [spec.get("source_id") for spec in specs]
    if (not specs or len(specs) > 500 or any(not isinstance(x, str) or not IDENTITY.fullmatch(x) for x in ids)
            or len(ids) != len(set(ids))):
        raise ValueError("Invalid or duplicate source identities")
    fingerprint = _key_fingerprint(public_pem)
    results: list[dict[str, Any]] = []
    for spec in specs:
        source_id = spec["source_id"]
        try:
            if not verify_owner(spec):
                results.append({"source": source_id, "status": "OWNER_UNVERIFIED"})
                continue
            kind, path_value = spec.get("kind"), spec.get("path")
            if kind not in {"sqlite", "file", "tree"} or not isinstance(path_value, str):
                raise ValueError("Invalid registered source")
            path = Path(path_value)
            if not path.is_absolute() or path.is_symlink():
                raise ValueError("Registered source must be an absolute non-symlink path")
            batch_id = f"librarian:server:{source_id}:{day}"
            old = None
            old_raw = None
            state = None
            database = queue / "queue.sqlite"
            if database.is_file():
                if database.is_symlink():
                    raise ValueError("Recovery queue cannot be a symbolic link")
                with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
                    row = db.execute("SELECT manifest_json,delivery_state FROM batches WHERE batch_id=?",
                                     (batch_id,)).fetchone()
                    if row:
                        old_raw, state = row
                        old = json.loads(old_raw)
            if old is not None and old["coverage"] == "COMPLETE" and state == "DELIVERED":
                if old.get("recovery_key_fingerprint", fingerprint) != fingerprint or any(
                    entry.get("key_fingerprint") != fingerprint for entry in old["entries"]
                    if entry["status"] == "CAPTURED"
                ):
                    raise ValueError("Existing daily batch uses a different recovery key")
                ledger = intake / "recovery-intake.sqlite"
                if ledger.is_symlink():
                    raise ValueError("Recovery intake ledger cannot be a symbolic link")
                if ledger.is_file():
                    with closing(sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True)) as db:
                        verified = db.execute(
                            "SELECT sha256 FROM manifest_revisions WHERE batch_id=? AND revision=?",
                            (batch_id, old.get("revision", 1)),
                        ).fetchone()
                    digest = hashlib.sha256(old_raw.encode("utf-8")).hexdigest()
                    if verified and verified[0] == digest:
                        result = {"source": source_id, "batch_id": batch_id, "coverage": "COMPLETE",
                                  "revision": old.get("revision", 1), "server_intake": "DELIVERED",
                                  "manifest_sha256": digest, "nas_publication": "NOT_CHECKED",
                                  "actual_captured_at": old["captured_at"]}
                        if spec.get("freshness") == "notion-cache":
                            result["source_freshness"] = "UNKNOWN; local cache, not a live Notion sync"
                        results.append(result)
                        continue
            if kind == "sqlite":
                files, sqlite_paths = [path], frozenset({path})
            elif kind == "file":
                files, sqlite_paths = [path], frozenset()
            else:
                files, sqlite_paths = _tree(path)
                if not files:
                    results.append({"source": source_id, "coverage": "EMPTY", "server_intake": "NOT_APPLICABLE",
                                    "nas_publication": "NOT_APPLICABLE"})
                    continue
            if old is not None and old["coverage"] == "PARTIAL":
                batch = retry_partial_batch(queue, batch_id, public_pem)
            else:
                batch = capture_recovery_batch(queue, "server", source_id, day, files, public_pem,
                                               sqlite_paths=sqlite_paths)
            with closing(sqlite3.connect(database.as_uri() + "?mode=rw", uri=True)) as db:
                rows = db.execute("SELECT revision,manifest_json FROM batch_revisions WHERE batch_id=? "
                                  "ORDER BY revision", (batch_id,)).fetchall()
                if not rows or rows[-1][1] != json.dumps(batch, sort_keys=True):
                    raise ValueError("Local server batch history is incomplete")
                grant = DeviceGrant("server", frozenset({source_id}))
                latest = None
                for _, raw in rows:
                    frozen = json.loads(raw)
                    for entry in frozen["entries"]:
                        if entry["status"] != "CAPTURED":
                            continue
                        reference = entry["object_ref"]
                        parts = Path(reference).parts
                        if (len(parts) != 3 or parts[0] != "objects" or ".." in parts
                                or any((queue.joinpath(*parts[:i])).is_symlink() for i in range(1, 4))):
                            raise ValueError("Invalid local encrypted-object reference")
                        with (queue / reference).open("rb") as stream:
                            receive_granted_object(stream, intake, grant, source_id,
                                                   entry["bytes"], entry["sha256"])
                    # An all-unavailable batch still needs a private source directory.
                    scope = intake / "server" / source_id
                    if scope.is_symlink() or scope.parent.is_symlink():
                        raise ValueError("Intake source scope cannot be a symbolic link")
                    scope.mkdir(mode=0o700, parents=True, exist_ok=True)
                    latest = receive_manifest(intake, grant, source_id, raw.encode("utf-8"))
                db.execute("BEGIN IMMEDIATE")
                changed = db.execute("UPDATE batches SET delivery_state='DELIVERED' "
                                     "WHERE batch_id=? AND manifest_json=?", (batch_id, rows[-1][1]))
                if changed.rowcount != 1:
                    db.rollback()
                    raise ValueError("Server source changed while delivering")
                db.commit()
            result = {"source": source_id, "batch_id": batch_id, "coverage": batch["coverage"],
                      "revision": batch.get("revision", 1), "server_intake": "DELIVERED",
                      "manifest_sha256": latest["sha256"] if latest else None,
                      "nas_publication": "NOT_CHECKED", "actual_captured_at": batch["captured_at"]}
            if spec.get("freshness") == "notion-cache":
                result["source_freshness"] = "UNKNOWN; local cache, not a live Notion sync"
            results.append(result)
        except (OSError, ValueError, TypeError, RuntimeError, sqlite3.Error) as exc:
            results.append({"source": source_id, "status": "FAILED", "error_type": type(exc).__name__})
    return {"date": day, "sources": results,
            "incomplete": sum(item.get("coverage") not in {"COMPLETE", "EMPTY"} for item in results)}
