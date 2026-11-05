"""Derive non-secret, structural indices from ChatGPT bridge state database.

This adapter indexes routes, account statuses, and thread request counts for the
Librarian semantic catalog. Raw prompt payloads, credentials, and conversation text
are strictly excluded to preserve privacy boundaries.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}\Z")


def _validate_readers(readers: list[str]) -> list[str]:
    if (
        not isinstance(readers, list)
        or not readers
        or len(set(readers)) != len(readers)
        or any(not isinstance(r, str) or not IDENTITY.fullmatch(r) for r in readers)
    ):
        raise ValueError("Invalid explicit reader identities")
    return readers


def _connect_ro_bytes(db_bytes: bytes) -> tuple[sqlite3.Connection, tempfile.TemporaryDirectory[str]]:
    if not db_bytes.startswith(b"SQLite format 3\x00"):
        raise ValueError("Provided bytes are not a valid SQLite format 3 database")
    tmpdir = tempfile.TemporaryDirectory(prefix="chatgpt-index-")
    db_file = Path(tmpdir.name) / "temp.db"
    db_file.write_bytes(db_bytes)
    conn = sqlite3.connect(f"file:{db_file.as_posix()}?mode=ro", uri=True)
    return conn, tmpdir


def chatgpt_bridge_summary_index(
    db_bytes: bytes,
    *,
    readers: list[str],
    captured_at: datetime,
) -> dict[str, Any]:
    """Create a structural summary record for the entire ChatGPT bridge state.

    Extracts account statuses, active routes, thread counts, and request counts by status.
    Excludes all raw payloads, tokens, credentials, and message content.
    """
    readers = _validate_readers(readers)
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("Capture time must have an explicit timezone")

    conn, tmpdir = _connect_ro_bytes(db_bytes)
    try:
        # Check expected tables
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        expected = {"chatgpt_accounts", "chatgpt_routes", "chatgpt_threads", "chatgpt_requests"}
        if not expected.issubset(tables):
            missing = expected - tables
            raise ValueError(f"Database missing expected ChatGPT bridge tables: {missing}")

        # Account counts by status
        acc_rows = conn.execute("SELECT status, count(*) FROM chatgpt_accounts GROUP BY status").fetchall()
        accounts_by_status = {r[0]: r[1] for r in acc_rows if r[0] is not None}

        # Routes count
        routes_count = conn.execute("SELECT count(*) FROM chatgpt_routes").fetchone()[0]

        # Threads count
        threads_count = conn.execute("SELECT count(*) FROM chatgpt_threads").fetchone()[0]

        # Request counts by status
        req_rows = conn.execute("SELECT status, count(*) FROM chatgpt_requests GROUP BY status").fetchall()
        requests_by_status = {r[0]: r[1] for r in req_rows if r[0] is not None}

        source_digest = hashlib.sha256(db_bytes).hexdigest()
        body = {
            "record_type": "chatgpt-bridge-structural-index",
            "accounts_by_status": accounts_by_status,
            "routes_count": routes_count,
            "threads_count": threads_count,
            "requests_by_status": requests_by_status,
            "source_sha256": source_digest,
            "note": "Derived from authoritative ChatGPT bridge state database without private payloads.",
        }
        content = json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        source_ref = f"workstation:chatgpt-bridge-state:sha256:{source_digest[:32]}"

        record = {
            "record_id": "chatgpt-bridge-summary",
            "version_id": f"v1:{source_digest[:24]}",
            "source_id": "chatgpt-bridge-state",
            "readers": readers,
            "project_ids": ["chatgpt-bridge"],
            "kind": "structural-index",
            "title": "ChatGPT bridge overall structural index",
            "original_status": "ACTIVE" if routes_count > 0 else "IDLE",
            "original_ref": source_ref,
            "captured_at": captured_at.isoformat(),
            "is_summary": True,
            "derived_from": [source_ref],
            "content_sha256": digest,
            "content_bytes": len(content),
            "media_type": "application/json",
        }
        return {"record": record, "content": content, "source_sha256": source_digest}
    finally:
        conn.close()
        tmpdir.cleanup()


def chatgpt_thread_indices(
    db_bytes: bytes,
    *,
    readers: list[str],
    captured_at: datetime,
) -> list[dict[str, Any]]:
    """Derive non-secret thread-level structural records for each conversation thread.

    Includes agent, account, project, thread ID, and request counts by status.
    Excludes prompt payloads, responses, and authorization headers.
    """
    readers = _validate_readers(readers)
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("Capture time must have an explicit timezone")

    conn, tmpdir = _connect_ro_bytes(db_bytes)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "chatgpt_threads" not in tables or "chatgpt_requests" not in tables:
            raise ValueError("Database missing chatgpt_threads or chatgpt_requests table")

        threads = conn.execute("SELECT account, agent, project, thread FROM chatgpt_threads").fetchall()
        source_digest = hashlib.sha256(db_bytes).hexdigest()
        results: list[dict[str, Any]] = []

        for account, agent, project, thread_id in threads:
            if not thread_id:
                continue

            # Count requests for this thread by status
            reqs = conn.execute(
                "SELECT status FROM chatgpt_requests "
                "WHERE account=? AND agent=? AND project=? AND thread=?",
                (account, agent, project, thread_id),
            ).fetchall()
            status_counts = Counter(r[0] for r in reqs if r[0] is not None)

            binding = json.dumps(
                [account, agent, project, thread_id], ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            binding_digest = hashlib.sha256(binding).hexdigest()
            rec_id = f"chatgpt-thread:{binding_digest}"

            body = {
                "record_type": "chatgpt-thread-structural-index",
                "thread_id": str(thread_id),
                "agent": str(agent or "unknown"),
                "account_alias": str(account or "unknown"),
                "project": str(project or "default"),
                "request_counts": dict(status_counts),
                "total_requests": len(reqs),
                "note": "Derived from thread requests without conversation text or model tokens.",
            }
            content = json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
            digest = hashlib.sha256(content).hexdigest()
            source_ref = f"workstation:chatgpt-thread:{binding_digest}"

            record = {
                "record_id": rec_id,
                "version_id": f"t:{source_digest}:{binding_digest}",
                "source_id": "chatgpt-bridge-state",
                "readers": readers,
                "project_ids": [str(project or "default")],
                "kind": "thread-index",
                "title": f"ChatGPT thread index: {agent} / {project}",
                "original_status": "ACTIVE" if len(reqs) > 0 else "IDLE",
                "original_ref": source_ref,
                "captured_at": captured_at.isoformat(),
                "is_summary": True,
                "derived_from": [source_ref],
                "content_sha256": digest,
                "content_bytes": len(content),
                "media_type": "application/json",
            }
            results.append({"record": record, "content": content, "source_sha256": source_digest})

        return results
    finally:
        conn.close()
        tmpdir.cleanup()
