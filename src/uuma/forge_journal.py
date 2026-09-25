from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import sqlite3
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TextIO
from uuid import uuid4

JOURNAL_KINDS = {"LOG", "KNOWLEDGE_CANDIDATE"}
SYNC_STATUSES = {"LOCAL", "QUEUED", "SYNCED", "FAILED", "CONFLICT"}
SYNC_DIRECTIONS = {"PULL", "PUSH"}
SYNC_OPERATIONS = {"CREATE_LOG", "PATCH_LOG", "UPSERT_CANDIDATE", "REFRESH_PAGE"}
JOB_STATUSES = {"QUEUED", "LEASED", "SYNCED", "FAILED", "CONFLICT", "CANCELLED"}
NOTIFICATION_STATUSES = {"QUEUED", "LEASED", "SENT", "FAILED"}


class JournalSyncError(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _notion_id(value: str) -> str:
    raw = value.strip().lower()
    compact = raw.replace("-", "")
    if len(compact) == 32 and all(character in "0123456789abcdef" for character in compact):
        return compact
    return raw


class ForgeJournalStore:
    """Durable Forge Journal synchronization state stored inside Lab_Bot's lab.db."""

    def __init__(
        self,
        database_path: Path | str,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self.bootstrap()

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise JournalSyncError("The journal clock must return a timezone-aware datetime.")
        return value.astimezone(UTC)

    def _now_text(self) -> str:
        return self._now().isoformat()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def bootstrap(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS forge_journal_pages (
                    journal_id TEXT PRIMARY KEY,
                    notion_page_id TEXT UNIQUE,
                    notion_url TEXT,
                    journal_kind TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    project_system TEXT NOT NULL DEFAULT '',
                    entry_type TEXT NOT NULL DEFAULT '',
                    remote_edited_at TEXT,
                    remote_content_hash TEXT,
                    synced_remote_content_hash TEXT,
                    snapshot_json TEXT NOT NULL DEFAULT '{}',
                    sync_status TEXT NOT NULL DEFAULT 'LOCAL',
                    last_synced_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS forge_journal_sync_jobs (
                    sync_job_id TEXT PRIMARY KEY,
                    journal_id TEXT NOT NULL REFERENCES forge_journal_pages(journal_id),
                    direction TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    base_remote_content_hash TEXT,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    available_at TEXT NOT NULL,
                    lease_owner TEXT,
                    lease_expires_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS forge_journal_sync_events (
                    event_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    sync_job_id TEXT REFERENCES forge_journal_sync_jobs(sync_job_id),
                    journal_id TEXT NOT NULL REFERENCES forge_journal_pages(journal_id),
                    event_type TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    occurred_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS forge_journal_notifications (
                    notification_id TEXT PRIMARY KEY,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    journal_id TEXT NOT NULL REFERENCES forge_journal_pages(journal_id),
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'QUEUED',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    available_at TEXT NOT NULL,
                    lease_owner TEXT,
                    lease_expires_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_forge_journal_pages_status
                    ON forge_journal_pages(sync_status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_forge_journal_jobs_delivery
                    ON forge_journal_sync_jobs(status, available_at, created_at);
                CREATE INDEX IF NOT EXISTS idx_forge_journal_jobs_page
                    ON forge_journal_sync_jobs(journal_id, status);
                CREATE INDEX IF NOT EXISTS idx_forge_journal_events_page
                    ON forge_journal_sync_events(journal_id, event_sequence);
                CREATE INDEX IF NOT EXISTS idx_forge_journal_notifications_delivery
                    ON forge_journal_notifications(status, available_at, created_at);
                """
            )
            self._normalize_page_identities(connection)

    @staticmethod
    def _normalize_page_identities(connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT * FROM forge_journal_pages
            WHERE notion_page_id IS NOT NULL AND notion_page_id != ''
            ORDER BY created_at, journal_id
            """
        ).fetchall()
        grouped: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault(_notion_id(str(row["notion_page_id"])), []).append(row)
        for normalized, matches in grouped.items():
            survivor = next(
                (
                    row
                    for row in matches
                    if str(row["notion_page_id"]).strip().lower() == normalized
                ),
                matches[0],
            )
            latest = max(matches, key=lambda row: str(row["updated_at"]))
            survivor_id = str(survivor["journal_id"])
            for duplicate in matches:
                duplicate_id = str(duplicate["journal_id"])
                if duplicate_id == survivor_id:
                    continue
                connection.execute(
                    "UPDATE forge_journal_sync_jobs SET journal_id = ? WHERE journal_id = ?",
                    (survivor_id, duplicate_id),
                )
                connection.execute(
                    "UPDATE forge_journal_sync_events SET journal_id = ? WHERE journal_id = ?",
                    (survivor_id, duplicate_id),
                )
                connection.execute(
                    "UPDATE forge_journal_notifications SET journal_id = ? WHERE journal_id = ?",
                    (survivor_id, duplicate_id),
                )
                connection.execute(
                    "DELETE FROM forge_journal_pages WHERE journal_id = ?", (duplicate_id,)
                )
            connection.execute(
                """
                UPDATE forge_journal_pages
                SET notion_page_id = ?, notion_url = ?, journal_kind = ?, title = ?,
                    project_system = ?, entry_type = ?, remote_edited_at = ?,
                    remote_content_hash = ?, synced_remote_content_hash = ?,
                    snapshot_json = ?, sync_status = ?, last_synced_at = ?,
                    last_error = ?, updated_at = ?
                WHERE journal_id = ?
                """,
                (
                    normalized,
                    latest["notion_url"],
                    latest["journal_kind"],
                    latest["title"],
                    latest["project_system"],
                    latest["entry_type"],
                    latest["remote_edited_at"],
                    latest["remote_content_hash"],
                    latest["synced_remote_content_hash"],
                    latest["snapshot_json"],
                    latest["sync_status"],
                    latest["last_synced_at"],
                    latest["last_error"],
                    latest["updated_at"],
                    survivor_id,
                ),
            )

    @staticmethod
    def _validate_kind(kind: str) -> str:
        normalized = kind.strip().upper()
        if normalized not in JOURNAL_KINDS:
            raise JournalSyncError(f"Unknown journal kind: {kind}")
        return normalized

    @staticmethod
    def _validate_direction(direction: str) -> str:
        normalized = direction.strip().upper()
        if normalized not in SYNC_DIRECTIONS:
            raise JournalSyncError(f"Unknown sync direction: {direction}")
        return normalized

    @staticmethod
    def _validate_operation(operation: str) -> str:
        normalized = operation.strip().upper()
        if normalized not in SYNC_OPERATIONS:
            raise JournalSyncError(f"Unknown sync operation: {operation}")
        return normalized

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        for key in ("snapshot_json", "payload_json", "details_json"):
            if key in item:
                item[key.removesuffix("_json")] = json.loads(item.pop(key) or "{}")
        return item

    def _event(
        self,
        connection: sqlite3.Connection,
        *,
        journal_id: str,
        event_type: str,
        actor_id: str,
        sync_job_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO forge_journal_sync_events(
                event_id, sync_job_id, journal_id, event_type,
                actor_id, details_json, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _id("jevt"),
                sync_job_id,
                journal_id,
                event_type,
                actor_id.strip() or "system",
                _canonical_json(details or {}),
                self._now_text(),
            ),
        )

    def _notify(
        self,
        connection: sqlite3.Connection,
        *,
        journal_id: str,
        event_type: str,
        dedupe_key: str,
        payload: dict[str, Any],
    ) -> None:
        now = self._now_text()
        connection.execute(
            """
            INSERT OR IGNORE INTO forge_journal_notifications(
                notification_id, dedupe_key, journal_id, event_type,
                payload_json, status, available_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'QUEUED', ?, ?, ?)
            """,
            (
                _id("jnotice"),
                dedupe_key,
                journal_id,
                event_type,
                _canonical_json(payload),
                now,
                now,
                now,
            ),
        )

    def register_snapshot(
        self,
        notion_page_id: str,
        notion_url: str,
        title: str,
        remote_content_hash: str,
        *,
        remote_edited_at: str = "",
        journal_kind: str = "LOG",
        project_system: str = "",
        entry_type: str = "",
        snapshot: dict[str, Any] | None = None,
        actor_id: str = "openclaw",
    ) -> dict[str, Any]:
        page_id = _notion_id(notion_page_id)
        page_url = notion_url.strip()
        content_hash = remote_content_hash.strip()
        if not page_id or not page_url or not content_hash:
            raise JournalSyncError(
                "notion_page_id, notion_url, and remote_content_hash are required."
            )
        kind = self._validate_kind(journal_kind)
        now = self._now_text()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            page = connection.execute(
                "SELECT * FROM forge_journal_pages WHERE notion_page_id = ?", (page_id,)
            ).fetchone()
            if page is None:
                journal_id = _id("journal")
                connection.execute(
                    """
                    INSERT INTO forge_journal_pages(
                        journal_id, notion_page_id, notion_url, journal_kind,
                        title, project_system, entry_type, remote_edited_at,
                        remote_content_hash, synced_remote_content_hash,
                        snapshot_json, sync_status, last_synced_at,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SYNCED', ?, ?, ?)
                    """,
                    (
                        journal_id,
                        page_id,
                        page_url,
                        kind,
                        title.strip(),
                        project_system.strip(),
                        entry_type.strip(),
                        remote_edited_at.strip() or None,
                        content_hash,
                        content_hash,
                        _canonical_json(snapshot or {}),
                        now,
                        now,
                        now,
                    ),
                )
                self._event(
                    connection,
                    journal_id=journal_id,
                    event_type="SNAPSHOT_REGISTERED",
                    actor_id=actor_id,
                    details={"remote_content_hash": content_hash},
                )
                return {"journal_id": journal_id, "sync_status": "SYNCED", "conflict": False}

            journal_id = str(page["journal_id"])
            pending = connection.execute(
                """
                SELECT sync_job_id, base_remote_content_hash
                FROM forge_journal_sync_jobs
                WHERE journal_id = ? AND direction = 'PUSH'
                  AND status IN ('QUEUED', 'LEASED')
                ORDER BY created_at
                """,
                (journal_id,),
            ).fetchall()
            conflict_jobs = [
                row
                for row in pending
                if (row["base_remote_content_hash"] or "") != content_hash
            ]
            if conflict_jobs:
                job_ids = [str(row["sync_job_id"]) for row in conflict_jobs]
                placeholders = ",".join("?" for _ in job_ids)
                connection.execute(
                    f"""
                    UPDATE forge_journal_sync_jobs
                    SET status = 'CONFLICT', lease_owner = NULL, lease_expires_at = NULL,
                        last_error = 'Notion changed after the local write was based.',
                        updated_at = ?
                    WHERE sync_job_id IN ({placeholders})
                    """,
                    (now, *job_ids),
                )
                connection.execute(
                    """
                    UPDATE forge_journal_pages
                    SET notion_url = ?, title = ?, project_system = ?, entry_type = ?,
                        remote_edited_at = ?, remote_content_hash = ?, snapshot_json = ?,
                        sync_status = 'CONFLICT',
                        last_error = 'Concurrent Notion and local changes require review.',
                        updated_at = ?
                    WHERE journal_id = ?
                    """,
                    (
                        page_url,
                        title.strip(),
                        project_system.strip(),
                        entry_type.strip(),
                        remote_edited_at.strip() or None,
                        content_hash,
                        _canonical_json(snapshot or {}),
                        now,
                        journal_id,
                    ),
                )
                self._event(
                    connection,
                    journal_id=journal_id,
                    event_type="SYNC_CONFLICTED",
                    actor_id=actor_id,
                    details={"sync_job_ids": job_ids, "remote_content_hash": content_hash},
                )
                self._notify(
                    connection,
                    journal_id=journal_id,
                    event_type="CONFLICT",
                    dedupe_key=f"conflict:{journal_id}:{content_hash}",
                    payload={"journal_id": journal_id, "notion_page_id": page_id},
                )
                return {"journal_id": journal_id, "sync_status": "CONFLICT", "conflict": True}

            resulting_status = "QUEUED" if pending else "SYNCED"
            connection.execute(
                """
                UPDATE forge_journal_pages
                SET notion_url = ?, journal_kind = ?, title = ?, project_system = ?,
                    entry_type = ?, remote_edited_at = ?, remote_content_hash = ?,
                    synced_remote_content_hash = ?, snapshot_json = ?,
                    sync_status = ?, last_synced_at = ?, last_error = NULL,
                    updated_at = ?
                WHERE journal_id = ?
                """,
                (
                    page_url,
                    kind,
                    title.strip(),
                    project_system.strip(),
                    entry_type.strip(),
                    remote_edited_at.strip() or None,
                    content_hash,
                    content_hash,
                    _canonical_json(snapshot or {}),
                    resulting_status,
                    now,
                    now,
                    journal_id,
                ),
            )
            self._event(
                connection,
                journal_id=journal_id,
                event_type=(
                    "SNAPSHOT_REFRESHED_WITH_PENDING_WRITE"
                    if pending
                    else "SNAPSHOT_RECONCILED"
                ),
                actor_id=actor_id,
                details={"remote_content_hash": content_hash},
            )
            return {
                "journal_id": journal_id,
                "sync_status": resulting_status,
                "conflict": False,
            }

    def queue_write(
        self,
        operation: str,
        payload: dict[str, Any],
        idempotency_key: str,
        *,
        journal_id: str = "",
        notion_page_id: str = "",
        notion_url: str = "",
        journal_kind: str = "LOG",
        title: str = "",
        project_system: str = "",
        entry_type: str = "",
        max_attempts: int = 3,
        offline: bool = False,
        actor_id: str = "forge-lab-bot",
    ) -> dict[str, Any]:
        op = self._validate_operation(operation)
        if op == "REFRESH_PAGE":
            direction = "PULL"
        else:
            direction = "PUSH"
        key = idempotency_key.strip()
        if not key:
            raise JournalSyncError("idempotency_key is required for every journal sync write.")
        attempts_limit = int(max_attempts)
        if attempts_limit < 1 or attempts_limit > 10:
            raise JournalSyncError("max_attempts must be between 1 and 10.")
        if op == "PATCH_LOG":
            if not str(payload.get("change_summary") or "").strip():
                raise JournalSyncError("PATCH_LOG requires change_summary for a visible change notice.")
            if not str(payload.get("change_reason") or "").strip():
                raise JournalSyncError("PATCH_LOG requires change_reason for a visible change notice.")
        if op == "UPSERT_CANDIDATE":
            candidate_status = str(payload.get("status") or "Candidate").strip().upper()
            if candidate_status != "CANDIDATE":
                raise PermissionError("LAB_BOT may only write Candidate engineering knowledge.")

        payload_json = _canonical_json(payload)
        payload_hash = _digest(payload)
        now = self._now_text()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM forge_journal_sync_jobs WHERE idempotency_key = ?", (key,)
            ).fetchone()
            if existing is not None:
                if existing["payload_hash"] != payload_hash or existing["operation"] != op:
                    raise JournalSyncError(
                        "The idempotency key already exists with a different journal request."
                    )
                return self._row(existing)

            page = None
            if journal_id.strip():
                page = connection.execute(
                    "SELECT * FROM forge_journal_pages WHERE journal_id = ?",
                    (journal_id.strip(),),
                ).fetchone()
            elif _notion_id(notion_page_id):
                page = connection.execute(
                    "SELECT * FROM forge_journal_pages WHERE notion_page_id = ?",
                    (_notion_id(notion_page_id),),
                ).fetchone()
            if page is None:
                assigned_journal_id = journal_id.strip() or _id("journal")
                kind = self._validate_kind(journal_kind)
                connection.execute(
                    """
                    INSERT INTO forge_journal_pages(
                        journal_id, notion_page_id, notion_url, journal_kind,
                        title, project_system, entry_type, sync_status,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'LOCAL', ?, ?)
                    """,
                    (
                        assigned_journal_id,
                        _notion_id(notion_page_id) or None,
                        notion_url.strip() or None,
                        kind,
                        title.strip(),
                        project_system.strip(),
                        entry_type.strip(),
                        now,
                        now,
                    ),
                )
                page = connection.execute(
                    "SELECT * FROM forge_journal_pages WHERE journal_id = ?",
                    (assigned_journal_id,),
                ).fetchone()
            assert page is not None
            assigned_journal_id = str(page["journal_id"])
            sync_job_id = _id("jsync")
            connection.execute(
                """
                INSERT INTO forge_journal_sync_jobs(
                    sync_job_id, journal_id, direction, operation, payload_json,
                    payload_hash, base_remote_content_hash, idempotency_key,
                    status, max_attempts, available_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', ?, ?, ?, ?)
                """,
                (
                    sync_job_id,
                    assigned_journal_id,
                    direction,
                    op,
                    payload_json,
                    payload_hash,
                    page["remote_content_hash"],
                    key,
                    attempts_limit,
                    now,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE forge_journal_pages
                SET sync_status = 'QUEUED', last_error = NULL, updated_at = ?
                WHERE journal_id = ?
                """,
                (now, assigned_journal_id),
            )
            self._event(
                connection,
                journal_id=assigned_journal_id,
                sync_job_id=sync_job_id,
                event_type="WRITE_QUEUED",
                actor_id=actor_id,
                details={"operation": op, "direction": direction, "offline": bool(offline)},
            )
            if offline:
                self._notify(
                    connection,
                    journal_id=assigned_journal_id,
                    event_type="QUEUED_OFFLINE",
                    dedupe_key=f"queued:{sync_job_id}",
                    payload={"sync_job_id": sync_job_id, "operation": op},
                )
            job = connection.execute(
                "SELECT * FROM forge_journal_sync_jobs WHERE sync_job_id = ?", (sync_job_id,)
            ).fetchone()
            assert job is not None
            return self._row(job)

    def claim_write(self, worker_id: str, *, lease_seconds: int = 120) -> dict[str, Any] | None:
        worker = worker_id.strip()
        if not worker:
            raise JournalSyncError("worker_id is required to lease a sync job.")
        lease_duration = max(30, min(int(lease_seconds), 3600))
        now_dt = self._now()
        now = now_dt.isoformat()
        expires = (now_dt + timedelta(seconds=lease_duration)).isoformat()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            expired = connection.execute(
                """
                SELECT sync_job_id, journal_id, attempts, max_attempts
                FROM forge_journal_sync_jobs
                WHERE status = 'LEASED' AND lease_expires_at <= ?
                """,
                (now,),
            ).fetchall()
            for row in expired:
                terminal = int(row["attempts"]) >= int(row["max_attempts"])
                status = "FAILED" if terminal else "QUEUED"
                connection.execute(
                    """
                    UPDATE forge_journal_sync_jobs
                    SET status = ?, available_at = ?, lease_owner = NULL,
                        lease_expires_at = NULL, last_error = 'Lease expired.', updated_at = ?
                    WHERE sync_job_id = ?
                    """,
                    (status, now, now, row["sync_job_id"]),
                )
                connection.execute(
                    """
                    UPDATE forge_journal_pages
                    SET sync_status = ?, last_error = 'Sync worker lease expired.', updated_at = ?
                    WHERE journal_id = ?
                    """,
                    (status, now, row["journal_id"]),
                )
                self._event(
                    connection,
                    journal_id=str(row["journal_id"]),
                    sync_job_id=str(row["sync_job_id"]),
                    event_type="LEASE_EXPIRED",
                    actor_id="system",
                    details={"terminal": terminal},
                )
                if terminal:
                    self._notify(
                        connection,
                        journal_id=str(row["journal_id"]),
                        event_type="FAILED",
                        dedupe_key=f"failed:{row['sync_job_id']}",
                        payload={"sync_job_id": row["sync_job_id"], "reason": "Lease expired."},
                    )

            job = connection.execute(
                """
                SELECT * FROM forge_journal_sync_jobs
                WHERE status = 'QUEUED' AND available_at <= ?
                ORDER BY available_at, created_at
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if job is None:
                return None
            connection.execute(
                """
                UPDATE forge_journal_sync_jobs
                SET status = 'LEASED', attempts = attempts + 1,
                    lease_owner = ?, lease_expires_at = ?, updated_at = ?
                WHERE sync_job_id = ? AND status = 'QUEUED'
                """,
                (worker, expires, now, job["sync_job_id"]),
            )
            self._event(
                connection,
                journal_id=str(job["journal_id"]),
                sync_job_id=str(job["sync_job_id"]),
                event_type="WRITE_LEASED",
                actor_id=worker,
                details={"lease_expires_at": expires},
            )
            leased = connection.execute(
                "SELECT * FROM forge_journal_sync_jobs WHERE sync_job_id = ?",
                (job["sync_job_id"],),
            ).fetchone()
            assert leased is not None
            return self._row(leased)

    def finish_write(
        self,
        sync_job_id: str,
        *,
        succeeded: bool,
        worker_id: str,
        remote_page_id: str = "",
        remote_url: str = "",
        remote_edited_at: str = "",
        remote_content_hash: str = "",
        error: str = "",
        conflict: bool = False,
    ) -> dict[str, Any]:
        job_id = sync_job_id.strip()
        worker = worker_id.strip()
        if not job_id or not worker:
            raise JournalSyncError("sync_job_id and worker_id are required.")
        now_dt = self._now()
        now = now_dt.isoformat()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = connection.execute(
                "SELECT * FROM forge_journal_sync_jobs WHERE sync_job_id = ?", (job_id,)
            ).fetchone()
            if job is None:
                raise JournalSyncError("Unknown sync_job_id.")
            if job["status"] != "LEASED" or job["lease_owner"] != worker:
                raise JournalSyncError("The sync job is not leased by this worker.")
            journal_id = str(job["journal_id"])

            if conflict:
                message = error.strip() or "Remote state changed before the write completed."
                connection.execute(
                    """
                    UPDATE forge_journal_sync_jobs
                    SET status = 'CONFLICT', lease_owner = NULL, lease_expires_at = NULL,
                        last_error = ?, updated_at = ? WHERE sync_job_id = ?
                    """,
                    (message, now, job_id),
                )
                connection.execute(
                    """
                    UPDATE forge_journal_pages
                    SET sync_status = 'CONFLICT', last_error = ?, updated_at = ?
                    WHERE journal_id = ?
                    """,
                    (message, now, journal_id),
                )
                self._event(
                    connection,
                    journal_id=journal_id,
                    sync_job_id=job_id,
                    event_type="SYNC_CONFLICTED",
                    actor_id=worker,
                    details={"error": message},
                )
                self._notify(
                    connection,
                    journal_id=journal_id,
                    event_type="CONFLICT",
                    dedupe_key=f"conflict:{job_id}",
                    payload={"sync_job_id": job_id, "error": message},
                )
                return {"sync_job_id": job_id, "status": "CONFLICT", "retrying": False}

            if succeeded:
                if not remote_content_hash.strip():
                    raise JournalSyncError(
                        "A successful write requires remote_content_hash as reconciliation evidence."
                    )
                connection.execute(
                    """
                    UPDATE forge_journal_sync_jobs
                    SET status = 'SYNCED', lease_owner = NULL, lease_expires_at = NULL,
                        last_error = NULL, updated_at = ? WHERE sync_job_id = ?
                    """,
                    (now, job_id),
                )
                connection.execute(
                    """
                    UPDATE forge_journal_pages
                    SET notion_page_id = COALESCE(NULLIF(?, ''), notion_page_id),
                        notion_url = COALESCE(NULLIF(?, ''), notion_url),
                        remote_edited_at = COALESCE(NULLIF(?, ''), remote_edited_at),
                        remote_content_hash = ?, synced_remote_content_hash = ?,
                        sync_status = 'SYNCED', last_synced_at = ?, last_error = NULL,
                        updated_at = ?
                    WHERE journal_id = ?
                    """,
                    (
                        _notion_id(remote_page_id),
                        remote_url.strip(),
                        remote_edited_at.strip(),
                        remote_content_hash.strip(),
                        remote_content_hash.strip(),
                        now,
                        now,
                        journal_id,
                    ),
                )
                self._event(
                    connection,
                    journal_id=journal_id,
                    sync_job_id=job_id,
                    event_type="WRITE_SYNCED",
                    actor_id=worker,
                    details={"remote_content_hash": remote_content_hash.strip()},
                )
                if int(job["attempts"]) > 1:
                    self._notify(
                        connection,
                        journal_id=journal_id,
                        event_type="RECOVERED",
                        dedupe_key=f"recovered:{job_id}",
                        payload={"sync_job_id": job_id, "attempts": int(job["attempts"])},
                    )
                return {"sync_job_id": job_id, "status": "SYNCED", "retrying": False}

            message = error.strip() or "Journal sync failed without an error description."
            attempts = int(job["attempts"])
            terminal = attempts >= int(job["max_attempts"])
            status = "FAILED" if terminal else "QUEUED"
            delay_seconds = min(3600, 60 * (2 ** max(0, attempts - 1)))
            available = (now_dt + timedelta(seconds=delay_seconds)).isoformat()
            connection.execute(
                """
                UPDATE forge_journal_sync_jobs
                SET status = ?, available_at = ?, lease_owner = NULL, lease_expires_at = NULL,
                    last_error = ?, updated_at = ? WHERE sync_job_id = ?
                """,
                (status, available, message, now, job_id),
            )
            page_status = "FAILED" if terminal else "QUEUED"
            connection.execute(
                """
                UPDATE forge_journal_pages
                SET sync_status = ?, last_error = ?, updated_at = ? WHERE journal_id = ?
                """,
                (page_status, message, now, journal_id),
            )
            self._event(
                connection,
                journal_id=journal_id,
                sync_job_id=job_id,
                event_type="WRITE_FAILED" if terminal else "WRITE_RETRY_SCHEDULED",
                actor_id=worker,
                details={"error": message, "attempts": attempts, "available_at": available},
            )
            self._notify(
                connection,
                journal_id=journal_id,
                event_type="FAILED" if terminal else "QUEUED_RETRY",
                dedupe_key=f"{'failed' if terminal else 'retry'}:{job_id}:{attempts}",
                payload={"sync_job_id": job_id, "error": message, "attempts": attempts},
            )
            return {"sync_job_id": job_id, "status": status, "retrying": not terminal}

    def request_resync(
        self,
        notion_page_id: str,
        reason: str,
        idempotency_key: str,
        *,
        actor_id: str = "forge-lab-bot",
    ) -> dict[str, Any]:
        page_id = _notion_id(notion_page_id)
        if not page_id or not reason.strip():
            raise JournalSyncError("notion_page_id and reason are required for manual resync.")
        with self.connect() as connection:
            page = connection.execute(
                "SELECT * FROM forge_journal_pages WHERE notion_page_id = ?", (page_id,)
            ).fetchone()
        if page is None:
            raise JournalSyncError("The Notion page must be registered before manual resync.")
        if page["sync_status"] == "CONFLICT":
            raise JournalSyncError("A conflict requires explicit human resolution before resync.")
        return self.queue_write(
            "REFRESH_PAGE",
            {"notion_page_id": page_id, "reason": reason.strip()},
            idempotency_key,
            journal_id=str(page["journal_id"]),
            actor_id=actor_id,
        )

    def status(
        self,
        *,
        notion_page_id: str | None = None,
        sync_status: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 1000))
        clauses: list[str] = []
        params: list[Any] = []
        if notion_page_id:
            clauses.append("notion_page_id = ?")
            params.append(_notion_id(notion_page_id))
        if sync_status:
            normalized = sync_status.strip().upper()
            if normalized not in SYNC_STATUSES:
                raise JournalSyncError(f"Unknown sync status: {sync_status}")
            clauses.append("sync_status = ?")
            params.append(normalized)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(safe_limit)
        with self.connect() as connection:
            pages = connection.execute(
                f"""
                SELECT * FROM forge_journal_pages
                {where}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
            counts = connection.execute(
                """
                SELECT sync_status, COUNT(*) AS count
                FROM forge_journal_pages GROUP BY sync_status
                """
            ).fetchall()
            pending_notifications = connection.execute(
                """
                SELECT COUNT(*) AS count FROM forge_journal_notifications
                WHERE status IN ('QUEUED', 'LEASED')
                """
            ).fetchone()
        return {
            "counts": {str(row["sync_status"]): int(row["count"]) for row in counts},
            "pending_notifications": int(pending_notifications["count"]),
            "pages": [self._row(row) for row in pages],
        }

    def get_page(self, journal_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM forge_journal_pages WHERE journal_id = ?",
                (journal_id.strip(),),
            ).fetchone()
        if row is None:
            raise JournalSyncError("Unknown journal_id.")
        return self._row(row)

    def enqueue_notification(
        self,
        journal_id: str,
        event_type: str,
        dedupe_key: str,
        payload: dict[str, Any],
        *,
        actor_id: str = "forge-journal-runner",
    ) -> dict[str, Any]:
        journal = self.get_page(journal_id)
        event = event_type.strip().upper()
        key = dedupe_key.strip()
        if not event or not key:
            raise JournalSyncError("event_type and dedupe_key are required.")
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._notify(
                connection,
                journal_id=str(journal["journal_id"]),
                event_type=event,
                dedupe_key=key,
                payload=payload,
            )
            self._event(
                connection,
                journal_id=str(journal["journal_id"]),
                event_type="NOTIFICATION_QUEUED",
                actor_id=actor_id,
                details={"event_type": event, "dedupe_key": key},
            )
            row = connection.execute(
                "SELECT * FROM forge_journal_notifications WHERE dedupe_key = ?",
                (key,),
            ).fetchone()
        assert row is not None
        return self._row(row)

    def list_events(self, journal_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 1000))
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM forge_journal_sync_events
                WHERE journal_id = ?
                ORDER BY event_sequence DESC
                LIMIT ?
                """,
                (journal_id.strip(), safe_limit),
            ).fetchall()
        return [self._row(row) for row in rows]

    def list_notifications(
        self, *, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 1000))
        params: list[Any] = []
        where = ""
        if status:
            normalized = status.strip().upper()
            if normalized not in NOTIFICATION_STATUSES:
                raise JournalSyncError(f"Unknown notification status: {status}")
            where = "WHERE status = ?"
            params.append(normalized)
        params.append(safe_limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM forge_journal_notifications
                {where}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._row(row) for row in rows]

    def claim_notification(
        self, worker_id: str, *, lease_seconds: int = 120
    ) -> dict[str, Any] | None:
        worker = worker_id.strip()
        if not worker:
            raise JournalSyncError("worker_id is required to lease a notification.")
        lease_duration = max(30, min(int(lease_seconds), 3600))
        now_dt = self._now()
        now = now_dt.isoformat()
        expires = (now_dt + timedelta(seconds=lease_duration)).isoformat()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            expired = connection.execute(
                """
                SELECT notification_id, attempts, max_attempts
                FROM forge_journal_notifications
                WHERE status = 'LEASED' AND lease_expires_at <= ?
                """,
                (now,),
            ).fetchall()
            for row in expired:
                status = (
                    "FAILED" if int(row["attempts"]) >= int(row["max_attempts"]) else "QUEUED"
                )
                connection.execute(
                    """
                    UPDATE forge_journal_notifications
                    SET status = ?, available_at = ?, lease_owner = NULL,
                        lease_expires_at = NULL, last_error = 'Lease expired.', updated_at = ?
                    WHERE notification_id = ?
                    """,
                    (status, now, now, row["notification_id"]),
                )
            notice = connection.execute(
                """
                SELECT * FROM forge_journal_notifications
                WHERE status = 'QUEUED' AND available_at <= ?
                ORDER BY available_at, created_at
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if notice is None:
                return None
            connection.execute(
                """
                UPDATE forge_journal_notifications
                SET status = 'LEASED', attempts = attempts + 1,
                    lease_owner = ?, lease_expires_at = ?, updated_at = ?
                WHERE notification_id = ? AND status = 'QUEUED'
                """,
                (worker, expires, now, notice["notification_id"]),
            )
            leased = connection.execute(
                "SELECT * FROM forge_journal_notifications WHERE notification_id = ?",
                (notice["notification_id"],),
            ).fetchone()
            assert leased is not None
            return self._row(leased)

    def finish_notification(
        self,
        notification_id: str,
        *,
        sent: bool,
        worker_id: str,
        error: str = "",
    ) -> dict[str, Any]:
        notice_id = notification_id.strip()
        worker = worker_id.strip()
        if not notice_id or not worker:
            raise JournalSyncError("notification_id and worker_id are required.")
        now_dt = self._now()
        now = now_dt.isoformat()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            notice = connection.execute(
                "SELECT * FROM forge_journal_notifications WHERE notification_id = ?",
                (notice_id,),
            ).fetchone()
            if notice is None:
                raise JournalSyncError("Unknown notification_id.")
            if notice["status"] != "LEASED" or notice["lease_owner"] != worker:
                raise JournalSyncError("The notification is not leased by this worker.")
            if sent:
                connection.execute(
                    """
                    UPDATE forge_journal_notifications
                    SET status = 'SENT', lease_owner = NULL, lease_expires_at = NULL,
                        last_error = NULL, updated_at = ? WHERE notification_id = ?
                    """,
                    (now, notice_id),
                )
                return {"notification_id": notice_id, "status": "SENT", "retrying": False}

            message = error.strip() or "Notification delivery failed without an error description."
            attempts = int(notice["attempts"])
            terminal = attempts >= int(notice["max_attempts"])
            status = "FAILED" if terminal else "QUEUED"
            delay_seconds = min(3600, 60 * (2 ** max(0, attempts - 1)))
            available = (now_dt + timedelta(seconds=delay_seconds)).isoformat()
            connection.execute(
                """
                UPDATE forge_journal_notifications
                SET status = ?, available_at = ?, lease_owner = NULL, lease_expires_at = NULL,
                    last_error = ?, updated_at = ? WHERE notification_id = ?
                """,
                (status, available, message, now, notice_id),
            )
            return {"notification_id": notice_id, "status": status, "retrying": not terminal}


def main(
    argv: list[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Forge Journal durable synchronization ledger")
    parser.add_argument("--database", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    import_parser = subparsers.add_parser(
        "import-snapshots", help="Read one JSON snapshot per stdin line and reconcile it"
    )
    import_parser.add_argument("--expected-count", type=int)
    import_parser.add_argument(
        "--base64-chunks",
        action="store_true",
        help="Read short base64 chunks and use a single '.' line to terminate each snapshot",
    )
    status_parser = subparsers.add_parser("status", help="Print journal synchronization status")
    status_parser.add_argument("--sync-status", default="")
    status_parser.add_argument("--include-snapshots", action="store_true")
    args = parser.parse_args(argv)
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    store = ForgeJournalStore(args.database)

    if args.command == "status":
        result = store.status(sync_status=args.sync_status or None)
        if not args.include_snapshots:
            for page in result["pages"]:
                page.pop("snapshot", None)
        output_stream.write(json.dumps(result, ensure_ascii=True, sort_keys=True) + "\n")
        return 0

    imported = 0
    conflicts = 0
    chunk_buffer: list[str] = []
    for line_number, line in enumerate(input_stream, start=1):
        if args.base64_chunks:
            if line.strip() != ".":
                if line.strip():
                    chunk_buffer.append(line.strip())
                continue
            try:
                line = base64.b64decode("".join(chunk_buffer), validate=True).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError) as exc:
                raise JournalSyncError(
                    f"Invalid base64 snapshot ending on line {line_number}."
                ) from exc
            chunk_buffer.clear()
        elif not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise JournalSyncError(f"Invalid JSON snapshot on line {line_number}.") from exc
        snapshot = payload.get("snapshot") or {}
        content_hash = str(payload.get("remote_content_hash") or _digest(snapshot))
        result = store.register_snapshot(
            payload["notion_page_id"],
            payload["notion_url"],
            payload.get("title", ""),
            content_hash,
            remote_edited_at=payload.get("remote_edited_at", ""),
            journal_kind=payload.get("journal_kind", "LOG"),
            project_system=payload.get("project_system", ""),
            entry_type=payload.get("entry_type", ""),
            snapshot=snapshot,
            actor_id=payload.get("actor_id", "openclaw"),
        )
        imported += 1
        conflicts += int(bool(result["conflict"]))
        if args.expected_count is not None and imported >= args.expected_count:
            break
    if args.base64_chunks and chunk_buffer:
        raise JournalSyncError("The final base64 snapshot is missing its '.' terminator.")
    if args.expected_count is not None and imported != args.expected_count:
        raise JournalSyncError(
            f"Expected {args.expected_count} snapshots but imported {imported}."
        )
    output_stream.write(
        json.dumps({"imported": imported, "conflicts": conflicts}, sort_keys=True) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
