"""Node transport receipts, separate from domain state and task authority."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


class NodeJournal:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS transport_receipts (
                    key TEXT PRIMARY KEY, request_digest TEXT NOT NULL,
                    value_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS transport_events (
                    sequence INTEGER PRIMARY KEY, key TEXT NOT NULL,
                    occurred_at TEXT NOT NULL, value_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS protocol_tasks (
                    task_id TEXT PRIMARY KEY, owner TEXT NOT NULL, value BLOB NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def reserve(self, key: str, request: Any, initial: dict) -> tuple[dict, bool]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM transport_receipts WHERE key=?", (key,)).fetchone()
            if row:
                if row["request_digest"] != digest(request):
                    raise ValueError("Idempotency key conflicts with its original request")
                return json.loads(row["value_json"]), False
            db.execute(
                "INSERT INTO transport_receipts VALUES (?,?,?)",
                (key, digest(request), json.dumps(initial)),
            )
            self._event(db, key, initial)
            return initial, True

    def get(self, key: str) -> dict | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT value_json FROM transport_receipts WHERE key=?", (key,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def update(self, key: str, value: dict) -> None:
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE transport_receipts SET value_json=? WHERE key=?", (json.dumps(value), key)
            )
            if cursor.rowcount != 1:
                raise KeyError(key)
            self._event(db, key, value)

    @staticmethod
    def _event(db, key: str, value: dict):
        db.execute(
            "INSERT INTO transport_events(key,occurred_at,value_json) VALUES (?,?,?)",
            (key, datetime.now(UTC).isoformat(), json.dumps(value)),
        )

    def inspect(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT key,value_json FROM transport_receipts ORDER BY key"
            ).fetchall()
        return [{"key": row[0], **json.loads(row[1])} for row in rows]
