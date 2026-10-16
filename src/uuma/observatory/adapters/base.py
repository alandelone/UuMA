"""Abstract base class for Observatory Source Adapters."""
from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from ..models import ObservatoryItem, SessionRecord, SourceFreshness


class ObservatorySourceAdapter(ABC):
    """Abstract contract for an agent's read-only data source adapter."""

    agent_id: str
    display_name: str
    role: str
    source_name: str

    def safe_sqlite_connect(self, db_path: Path | str) -> sqlite3.Connection | None:
        """Create a guaranteed read-only, non-locking SQLite connection."""
        p = Path(db_path)
        if not p.exists():
            return None
        try:
            uri = f"{p.resolve().as_uri()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=5.0)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error:
            return None

    @abstractmethod
    def probe_health(self) -> SourceFreshness:
        """Probe the reachability and freshness of this agent's underlying source."""

    @abstractmethod
    def list_items(self, limit: int = 10, offset: int = 0) -> list[ObservatoryItem]:
        """List active items, projects, topics, or tasks for this agent."""

    @abstractmethod
    def get_item(self, item_id: str) -> ObservatoryItem | None:
        """Fetch deep details for a specific item."""

    def get_sessions(self, item_id: str) -> list[SessionRecord]:
        """Fetch associated conversation sessions or return empty if not applicable."""
        return []
