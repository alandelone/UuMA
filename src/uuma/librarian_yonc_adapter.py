"""Deterministic Source Adapter for Yonc Graph Database (yonc-graph).

Extracts projects, goals, decisions, milestones, and completed work nodes
from Yonc's SQLite graph.db into verified semantic records with primary-key evidence.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from .librarian_adapter_base import (
    AssertionStatus,
    CandidateEvidence,
    CandidateRecord,
    LibrarianDeterministicAdapter,
    MemoryCategory,
)


class YoncGraphAdapter(LibrarianDeterministicAdapter):
    """Adapter for extracting structured project graph entities from yonc-graph."""

    @property
    def source_id(self) -> str:
        return "yonc-graph"

    @property
    def default_category(self) -> MemoryCategory:
        return "Decision"

    def _open_connection(self, source_input: Any) -> tuple[sqlite3.Connection, Any]:
        """Normalize input (Path, bytes, or sqlite3.Connection) into a readable connection."""
        if isinstance(source_input, sqlite3.Connection):
            return source_input, None
        if isinstance(source_input, (str, Path)):
            conn = sqlite3.connect(f"file:{Path(source_input).as_posix()}?mode=ro", uri=True)
            return conn, None
        if isinstance(source_input, bytes):
            if not source_input.startswith(b"SQLite format 3\x00"):
                raise ValueError("Provided bytes are not a valid SQLite database")
            tmpdir = tempfile.TemporaryDirectory(prefix="yonc-graph-")
            tmp_path = Path(tmpdir.name) / "temp.db"
            tmp_path.write_bytes(source_input)
            conn = sqlite3.connect(f"file:{tmp_path.as_posix()}?mode=ro", uri=True)
            return conn, tmpdir
        raise TypeError(f"Unsupported source_input type for YoncGraphAdapter: {type(source_input)}")

    def extract(self, source_input: Any, **kwargs: Any) -> list[CandidateRecord]:
        conn, cleanup = self._open_connection(source_input)
        records: list[CandidateRecord] = []
        try:
            cur = conn.cursor()
            tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            node_table = "graph_nodes" if "graph_nodes" in tables else ("nodes" if "nodes" in tables else None)
            if node_table is None:
                return records

            # Discover available columns in nodes table
            cur.execute(f"PRAGMA table_info({node_table})")
            node_cols = {row[1] for row in cur.fetchall()}

            # Extract project context if projects table exists
            projects_map: dict[str, str] = {}
            if "projects" in tables:
                try:
                    for pid, ptitle in cur.execute("SELECT id, title FROM projects"):
                        projects_map[pid] = ptitle
                except sqlite3.OperationalError:
                    pass

            # Query columns safely
            has_superseded = "superseded_by" in node_cols
            has_done_when = "done_when" in node_cols
            has_stage = "stage" in node_cols
            has_kind = "node_kind" in node_cols

            kind_col = "node_kind" if has_kind else "'WORK'"
            stage_col = "stage" if has_stage else "'ACTIVE'"
            done_when_col = "done_when" if has_done_when else "NULL"
            super_col = "superseded_by" if has_superseded else "NULL"

            query = f"""
            SELECT id, title, description, status, {kind_col}, {stage_col},
                   {done_when_col}, {super_col}
            FROM {node_table}
            WHERE status IN ('DONE', 'CANCELLED', 'ACTIVE', 'IN_PROGRESS', 'SUPERSEDED')
               OR {kind_col} IN ('GOAL', 'DECISION', 'MILESTONE')
            """
            cur.execute(query)
            rows = cur.fetchall()

            for row in rows:
                node_id, title, desc, status, kind, stage, done_when, superseded_by = row
                title = title or f"Node {node_id}"
                desc = desc or ""

                # Determine category
                if kind in ("GOAL", "DECISION"):
                    category: MemoryCategory = "Decision"
                elif status == "DONE":
                    category = "Work & Artifacts"
                elif status == "CANCELLED":
                    category = "History"
                else:
                    category = "Knowledge"

                # Determine assertion status
                if superseded_by:
                    assertion_status: AssertionStatus = "superseded"
                elif status == "DONE":
                    assertion_status = "confirmed"
                elif status == "CANCELLED":
                    assertion_status = "historical"
                else:
                    assertion_status = "proposed"

                summary = desc[:240].strip() if desc else f"Yonc node {node_id} ({kind}) with status {status}"
                full_content_parts = [
                    f"Title: {title}",
                    f"Kind: {kind}",
                    f"Status: {status}",
                    f"Stage: {stage}",
                ]
                if desc:
                    full_content_parts.append(f"Description: {desc}")
                if done_when:
                    full_content_parts.append(f"Done Condition: {done_when}")
                if superseded_by:
                    full_content_parts.append(f"Superseded By: {superseded_by}")

                full_content = "\n".join(full_content_parts)
                exact_quote = f"Node [{node_id}] ({kind}): {title} [Status: {status}]"

                evidence = CandidateEvidence(
                    locator_type="sqlite_pk",
                    locator_value=f"{node_table}.id:{node_id}",
                    exact_quote=exact_quote,
                )

                records.append(
                    CandidateRecord(
                        record_id=f"yonc:node:{node_id}",
                        version_id=f"v1:{evidence.quote_hash[:16]}",
                        source_id=self.source_id,
                        category=category,
                        project="yonc-graph",
                        title=f"Yonc [{kind}] {title}",
                        summary=summary,
                        full_content=full_content,
                        original_status=status or "UNKNOWN",
                        original_ref=f"sqlite:yonc_graph:nodes:{node_id}",
                        assertion_status=assertion_status,
                        superseded_by=f"yonc:node:{superseded_by}" if superseded_by else None,
                        readers=["yonc", "librarian", "orchestrator"],
                        evidence=[evidence],
                        entities=["agent:yonc", "project:yonc-graph"],
                    )
                )

        finally:
            conn.close()
            if cleanup is not None:
                cleanup.cleanup()

        return records
