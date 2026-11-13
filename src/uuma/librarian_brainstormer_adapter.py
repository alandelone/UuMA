"""Deterministic Source Adapter for Brainstormer State and Audits.

Ingests topics, checkpoints, questions, assumptions, and approved decisions
from Brainstormer state.json snapshots into verified semantic records.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .librarian_adapter_base import (
    AssertionStatus,
    CandidateEvidence,
    CandidateRecord,
    LibrarianDeterministicAdapter,
    MemoryCategory,
)


class BrainstormerAuditAdapter(LibrarianDeterministicAdapter):
    """Adapter for extracting structured discussion entities from Brainstormer state."""

    @property
    def source_id(self) -> str:
        return "brainstormer-structured-files"

    @property
    def default_category(self) -> MemoryCategory:
        return "Decision"

    def _load_state(self, source_input: Any) -> dict[str, Any]:
        """Normalize input (dict, str, bytes, Path) into a project state dict."""
        if isinstance(source_input, dict):
            return source_input
        if isinstance(source_input, (str, Path)):
            raw = Path(source_input).read_text(encoding="utf-8")
            return json.loads(raw)
        if isinstance(source_input, bytes):
            return json.loads(source_input.decode("utf-8"))
        raise TypeError(f"Unsupported source_input for BrainstormerAuditAdapter: {type(source_input)}")

    def extract(self, source_input: Any, **kwargs: Any) -> list[CandidateRecord]:
        state = self._load_state(source_input)
        records: list[CandidateRecord] = []

        project_id = state.get("project_id", "brainstormer")
        revision = state.get("revision", 1)
        objects = state.get("objects", {})
        if not isinstance(objects, dict):
            return records

        for obj_id, obj in objects.items():
            if not isinstance(obj, dict):
                continue

            kind = obj.get("kind", "unknown")
            status = obj.get("status", "ACTIVE")
            title = obj.get("title") or obj.get("statement") or f"Brainstormer {kind} {obj_id}"
            description = obj.get("description") or obj.get("summary") or obj.get("rationale") or ""

            # Determine category based on kind
            if kind == "decision":
                category: MemoryCategory = "Decision"
            elif kind == "checkpoint":
                category = "History"
            elif kind in ("evidence", "question"):
                category = "Knowledge"
            elif kind == "topic":
                category = "Decision"
            else:
                category = "Knowledge"

            # Determine assertion status
            if kind == "decision" and status == "APPROVED":
                assertion_status: AssertionStatus = "confirmed"
            elif status in ("SUPERSEDED", "REPLACED"):
                assertion_status = "superseded"
            elif status in ("ARCHIVED", "CLOSED"):
                assertion_status = "historical"
            elif status == "REJECTED":
                assertion_status = "rejected"
            else:
                assertion_status = "proposed"

            exact_quote = f"Brainstormer [{kind.upper()} {obj_id}]: {title} (Status: {status})"
            locator = f"objects.{obj_id}"

            evidence = CandidateEvidence(
                locator_type="json_key",
                locator_value=locator,
                exact_quote=exact_quote,
            )

            full_content_parts = [
                f"Project: {project_id} (Rev {revision})",
                f"Type: {kind}",
                f"ID: {obj_id}",
                f"Status: {status}",
                f"Title: {title}",
            ]
            if description:
                full_content_parts.append(f"Content: {description}")

            full_content = "\n".join(full_content_parts)

            records.append(
                CandidateRecord(
                    record_id=f"brainstormer:{kind}:{obj_id}",
                    version_id=f"r{revision}:{evidence.quote_hash[:16]}",
                    source_id=self.source_id,
                    category=category,
                    project=project_id,
                    title=f"Brainstormer [{kind.capitalize()}] {title}",
                    summary=description[:240].strip() if description else exact_quote,
                    full_content=full_content,
                    original_status=status,
                    original_ref=f"brainstormer:{project_id}:rev{revision}:{obj_id}",
                    assertion_status=assertion_status,
                    readers=["brainstormer", "librarian", "orchestrator"],
                    evidence=[evidence],
                    entities=["agent:brainstormer", f"project:{project_id}"],
                )
            )

        return records
