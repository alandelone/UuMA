"""Honc Privacy Firewall and Habit Adapter for Librarian LSIP.

Enforces strict privacy boundaries for Honc life/health data:
- Personal diary entries, private reflections, and health data are classified as
  'honc_private' and restricted exclusively to the private owner tier.
- Routine habit names, reminder patterns, and scheduled cadences are extracted
  under the 'restricted' tier.
- Private diary content is NEVER published into the shared semantic catalog.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .librarian_adapter_base import (
    CandidateEvidence,
    CandidateRecord,
    LibrarianDeterministicAdapter,
    MemoryCategory,
    PrivacyTier,
)

PRIVATE_KEYWORDS = {
    "diary", "journal", "feeling", "mood", "health", "medical",
    "blood", "symptom", "doctor", "therapy", "personal", "secret",
}


@dataclass
class HoncEntry:
    entry_id: str
    category_type: str  # 'habit' | 'reminder' | 'journal' | 'body'
    title: str
    content: str
    timestamp: str


class HoncPrivacyAdapter(LibrarianDeterministicAdapter):
    """Adapter for Honc life-data sources with mandatory privacy boundary enforcement."""

    def __init__(self, source_id: str = "honc-database") -> None:
        self._source_id = source_id

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def default_category(self) -> MemoryCategory:
        return "Knowledge"

    def extract(self, source_input: Any, **kwargs: Any) -> list[CandidateRecord]:
        """Extract habits and safe patterns while quarantining private diary entries."""
        raw_items: list[dict[str, Any]] = []

        if isinstance(source_input, list):
            raw_items = source_input
        elif isinstance(source_input, Path):
            if source_input.suffix == ".json":
                raw_items = json.loads(source_input.read_text(encoding="utf-8"))
        elif isinstance(source_input, str):
            try:
                raw_items = json.loads(source_input)
            except json.JSONDecodeError:
                pass

        records: list[CandidateRecord] = []

        for item in raw_items:
            item_id = str(item.get("id") or item.get("entry_id") or "entry")
            kind = str(item.get("type") or item.get("category_type") or "journal").lower()
            title = str(item.get("title") or "Honc Entry")
            content = str(item.get("content") or item.get("text") or "")

            # Check privacy classification
            is_private = kind in ("journal", "diary", "body", "health") or any(
                kw in title.lower() or kw in content.lower() for kw in PRIVATE_KEYWORDS
            )

            if is_private:
                tier: PrivacyTier = "honc_private"
                readers = ["honc_owner"]
                # Redact sensitive body content in summary
                summary = f"[REDACTED_PRIVATE_ENTRY: {kind}]"
                full_content = "[Content quarantined by Librarian Honc Privacy Firewall]"
                category: MemoryCategory = "History"
                quote = f"Private entry {item_id} quarantined"
            else:
                tier = "restricted"
                readers = ["librarian", "orchestrator", "honc_owner"]
                summary = title
                full_content = content
                category = "Knowledge" if kind == "habit" else "Experience"
                quote = content[:100] if content else title

            evidence = CandidateEvidence(
                locator_type="honc_entry_id",
                locator_value=f"honc:{item_id}",
                exact_quote=quote,
            )

            records.append(CandidateRecord(
                record_id=f"rec_honc_{item_id}",
                version_id="v1",
                source_id=self._source_id,
                category=category,
                project="honc",
                title=f"Honc: {title}" if not is_private else f"Honc: [{kind.capitalize()} Private]",
                summary=summary,
                full_content=full_content,
                original_status="captured",
                original_ref=f"honc://entry/{item_id}",
                assertion_status="confirmed",
                privacy_tier=tier,
                readers=readers,
                evidence=[evidence],
                entities=["honc", "user"],
            ))

        return records
