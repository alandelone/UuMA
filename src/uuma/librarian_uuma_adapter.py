"""Deterministic Source Adapter for UuMA Control Plane (uuma-control).

Extracts milestone events, mission gate transitions, task completions, and agent
lifecycle changes from uuma.db event store into verified semantic records.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from .librarian_adapter_base import (
    CandidateEvidence,
    CandidateRecord,
    LibrarianDeterministicAdapter,
    MemoryCategory,
)

HIGH_VALUE_EVENT_TYPES = {
    "stage_gate_passed": ("History", "confirmed"),
    "gate_transition": ("History", "confirmed"),
    "mission_stage_advanced": ("History", "confirmed"),
    "mission_status_updated": ("Decision", "confirmed"),
    "task_completed": ("Work & Artifacts", "confirmed"),
    "run_finished": ("Work & Artifacts", "confirmed"),
    "agent_registered": ("Knowledge", "confirmed"),
    "proposal_approved": ("Decision", "confirmed"),
}


class UuMAControlAdapter(LibrarianDeterministicAdapter):
    """Adapter for extracting control plane mission events from uuma-control."""

    @property
    def source_id(self) -> str:
        return "uuma-control"

    @property
    def default_category(self) -> MemoryCategory:
        return "Decision"

    def _open_connection(self, source_input: Any) -> tuple[sqlite3.Connection, Any]:
        """Normalize input into an SQLite connection."""
        if isinstance(source_input, sqlite3.Connection):
            return source_input, None
        if isinstance(source_input, (str, Path)):
            conn = sqlite3.connect(f"file:{Path(source_input).as_posix()}?mode=ro", uri=True)
            return conn, None
        if isinstance(source_input, bytes):
            if not source_input.startswith(b"SQLite format 3\x00"):
                raise ValueError("Provided bytes are not a valid SQLite database")
            tmpdir = tempfile.TemporaryDirectory(prefix="uuma-control-")
            tmp_path = Path(tmpdir.name) / "temp.db"
            tmp_path.write_bytes(source_input)
            conn = sqlite3.connect(f"file:{tmp_path.as_posix()}?mode=ro", uri=True)
            return conn, tmpdir
        raise TypeError(f"Unsupported source_input for UuMAControlAdapter: {type(source_input)}")

    def extract(self, source_input: Any, **kwargs: Any) -> list[CandidateRecord]:
        conn, cleanup = self._open_connection(source_input)
        records: list[CandidateRecord] = []
        try:
            cur = conn.cursor()
            tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "events" not in tables:
                return records

            query = """
            SELECT event_id, event_type, aggregate_type, aggregate_id,
                   actor_type, actor_id, occurred_at, payload_json, event_hash
            FROM events
            ORDER BY sequence DESC
            LIMIT 500
            """
            cur.execute(query)
            rows = cur.fetchall()

            for row in rows:
                (
                    event_id,
                    event_type,
                    agg_type,
                    agg_id,
                    actor_type,
                    actor_id,
                    occurred_at,
                    payload_json,
                    event_hash,
                ) = row

                # Classify event or filter high value
                cat_and_status = HIGH_VALUE_EVENT_TYPES.get(event_type)
                if cat_and_status:
                    category, assertion_status = cat_and_status
                elif "gate" in event_type or "stage" in event_type:
                    category = "History"
                    assertion_status = "confirmed"
                elif "complete" in event_type or "finish" in event_type:
                    category = "Work & Artifacts"
                    assertion_status = "confirmed"
                else:
                    category = "History"
                    assertion_status = "historical"

                # Parse payload if possible
                payload_summary = ""
                try:
                    payload = json.loads(payload_json)
                    if isinstance(payload, dict):
                        payload_summary = payload.get("summary") or payload.get("reason") or ""
                except (json.JSONDecodeError, TypeError):
                    payload_summary = ""

                title = f"UuMA [{event_type}] {agg_type}:{agg_id}"
                summary = payload_summary or f"Actor {actor_id} executed {event_type} on {agg_id}"
                exact_quote = f"Event [{event_type}]: {actor_id} -> {agg_id} at {occurred_at} ({event_hash[:16]})"

                evidence = CandidateEvidence(
                    locator_type="sqlite_pk",
                    locator_value=f"events.event_id:{event_id}",
                    exact_quote=exact_quote,
                )

                full_content_parts = [
                    f"Event ID: {event_id}",
                    f"Type: {event_type}",
                    f"Aggregate: {agg_type}:{agg_id}",
                    f"Actor: {actor_type}:{actor_id}",
                    f"Occurred At: {occurred_at}",
                    f"Event Hash: {event_hash}",
                    f"Payload: {payload_json}",
                ]
                full_content = "\n".join(full_content_parts)

                records.append(
                    CandidateRecord(
                        record_id=f"uuma:event:{event_id}",
                        version_id=f"v1:{event_hash[:16]}",
                        source_id=self.source_id,
                        category=category,
                        project="UuMA",
                        title=title,
                        summary=summary,
                        full_content=full_content,
                        original_status="COMMITTED",
                        original_ref=f"sqlite:uuma_control:events:{event_id}",
                        captured_at=occurred_at,
                        assertion_status=assertion_status,
                        readers=["hermes", "librarian", "orchestrator"],
                        evidence=[evidence],
                        entities=[f"actor:{actor_id}", f"aggregate:{agg_id}", "project:UuMA"],
                    )
                )

        finally:
            conn.close()
            if cleanup is not None:
                cleanup.cleanup()

        return records
