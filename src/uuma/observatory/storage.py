"""Storage manager for observatory.db with FTS5 search."""
from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import ActivityEvent, SourceFreshness


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class ObservatoryStorage:
    """Manages the isolated observatory.db event cache and search index."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS activity_events (
                    event_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    hook TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    tool_name TEXT,
                    summary TEXT NOT NULL,
                    source_path TEXT,
                    raw_snippet TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_activity_agent ON activity_events(agent_id);
                CREATE INDEX IF NOT EXISTS idx_activity_captured ON activity_events(captured_at DESC);

                CREATE VIRTUAL TABLE IF NOT EXISTS activity_events_fts USING fts5(
                    event_id UNINDEXED,
                    agent_id,
                    tool_name,
                    summary,
                    raw_snippet
                );

                CREATE TABLE IF NOT EXISTS harvest_cursors (
                    source_key TEXT PRIMARY KEY,
                    last_file TEXT,
                    last_timestamp TEXT,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS source_health (
                    source_name TEXT PRIMARY KEY,
                    is_available INTEGER NOT NULL,
                    last_checked TEXT NOT NULL,
                    last_event_at TEXT,
                    error_message TEXT
                );
                """
            )

    def insert_events(self, events: list[ActivityEvent]) -> int:
        if not events:
            return 0
        inserted = 0
        with self._lock, self._connect() as conn:
            cursor = conn.cursor()
            for ev in events:
                try:
                    cursor.execute(
                        """
                        INSERT INTO activity_events
                        (event_id, agent_id, hook, captured_at, tool_name, summary, source_path, raw_snippet)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(event_id) DO UPDATE SET
                            agent_id = excluded.agent_id,
                            hook = excluded.hook,
                            captured_at = excluded.captured_at,
                            tool_name = excluded.tool_name,
                            summary = excluded.summary,
                            source_path = excluded.source_path,
                            raw_snippet = excluded.raw_snippet
                        """,
                        (
                            ev.event_id,
                            ev.agent_id,
                            ev.hook,
                            ev.captured_at,
                            ev.tool_name,
                            ev.summary,
                            ev.source_path,
                            ev.raw_snippet,
                        ),
                    )
                    inserted += 1
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO activity_events_fts
                        (rowid, event_id, agent_id, tool_name, summary, raw_snippet)
                        VALUES ((SELECT rowid FROM activity_events WHERE event_id = ?), ?, ?, ?, ?, ?)
                        """,
                        (
                            ev.event_id,
                            ev.event_id,
                            ev.agent_id,
                            ev.tool_name or "",
                            ev.summary,
                            ev.raw_snippet or "",
                        ),
                    )
                except sqlite3.Error:
                    continue
            conn.commit()
        return inserted

    def query_events(
        self,
        *,
        agent_id: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
        since: str | None = None,
    ) -> tuple[list[ActivityEvent], int]:
        with self._lock, self._connect() as conn:
            cursor = conn.cursor()
            conditions: list[str] = []
            params: list[Any] = []

            if query and query.strip():
                # FTS query
                clean_query = query.strip().replace('"', '""')
                conditions.append(
                    "e.event_id IN (SELECT event_id FROM activity_events_fts WHERE activity_events_fts MATCH ?)"
                )
                params.append(f'"{clean_query}"')

            if agent_id and agent_id.strip() and agent_id != "all":
                conditions.append("e.agent_id = ?")
                params.append(agent_id.strip())

            if since and since.strip():
                conditions.append("e.captured_at >= ?")
                params.append(since.strip())

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            # Count query
            count_sql = f"SELECT COUNT(*) FROM activity_events e {where_clause}"
            cursor.execute(count_sql, params)
            total = cursor.fetchone()[0]

            # Results query
            data_sql = f"""
                SELECT event_id, agent_id, hook, captured_at, tool_name, summary, source_path, raw_snippet
                FROM activity_events e
                {where_clause}
                ORDER BY e.captured_at DESC
                LIMIT ? OFFSET ?
            """
            cursor.execute(data_sql, (*params, limit, offset))
            rows = cursor.fetchall()

            events = [
                ActivityEvent(
                    event_id=row["event_id"],
                    agent_id=row["agent_id"],
                    hook=row["hook"],
                    captured_at=row["captured_at"],
                    tool_name=row["tool_name"],
                    summary=row["summary"],
                    source_path=row["source_path"] or "",
                    raw_snippet=row["raw_snippet"] or "",
                )
                for row in rows
            ]
            return events, total

    def update_cursor(self, source_key: str, last_file: str, last_timestamp: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO harvest_cursors (source_key, last_file, last_timestamp, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source_key) DO UPDATE SET
                    last_file=excluded.last_file,
                    last_timestamp=excluded.last_timestamp,
                    updated_at=excluded.updated_at
                """,
                (source_key, last_file, last_timestamp, _utc_now()),
            )
            conn.commit()

    def get_cursor(self, source_key: str) -> dict[str, str] | None:
        with self._lock, self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM harvest_cursors WHERE source_key = ?", (source_key,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "source_key": row["source_key"],
                "last_file": row["last_file"],
                "last_timestamp": row["last_timestamp"],
                "updated_at": row["updated_at"],
            }

    def update_source_health(self, health: SourceFreshness) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO source_health (source_name, is_available, last_checked, last_event_at, error_message)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_name) DO UPDATE SET
                    is_available=excluded.is_available,
                    last_checked=excluded.last_checked,
                    last_event_at=COALESCE(excluded.last_event_at, source_health.last_event_at),
                    error_message=excluded.error_message
                """,
                (
                    health.source_name,
                    1 if health.is_available else 0,
                    health.last_checked,
                    health.last_event_at,
                    health.error_message,
                ),
            )
            conn.commit()

    def get_all_source_health(self) -> dict[str, SourceFreshness]:
        with self._lock, self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM source_health")
            rows = cursor.fetchall()
            return {
                row["source_name"]: SourceFreshness(
                    source_name=row["source_name"],
                    is_available=bool(row["is_available"]),
                    last_checked=row["last_checked"],
                    last_event_at=row["last_event_at"],
                    error_message=row["error_message"],
                )
                for row in rows
            }

    def get_event_count(self) -> int:
        with self._lock, self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM activity_events")
            return cursor.fetchone()[0]
