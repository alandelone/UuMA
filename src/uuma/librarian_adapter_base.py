"""Base contracts and data models for Librarian Source Adapters.

Defines the abstract interface for deterministic and conversational adapters,
candidate record models, evidence specifications, and verification results.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

MemoryCategory = Literal["Knowledge", "Experience", "Decision", "Work & Artifacts", "History"]
AssertionStatus = Literal["proposed", "confirmed", "historical", "superseded", "rejected"]
PrivacyTier = Literal["public", "internal", "restricted", "honc_private"]


@dataclass(frozen=True)
class CandidateEvidence:
    """Traceable quote or slice anchoring a claim to a source object."""
    locator_type: str  # 'sqlite_pk' | 'jsonl_line' | 'byte_offset' | 'file_path'
    locator_value: str
    exact_quote: str
    quote_hash: str = ""

    def __post_init__(self) -> None:
        if not self.quote_hash:
            calculated = hashlib.sha256(self.exact_quote.encode("utf-8")).hexdigest()
            object.__setattr__(self, "quote_hash", calculated)


@dataclass(frozen=True)
class CandidateRecord:
    """A verified or candidate semantic record extracted from a data source."""
    record_id: str
    version_id: str
    source_id: str
    category: MemoryCategory
    project: str
    title: str
    summary: str
    full_content: str
    original_status: str
    original_ref: str
    captured_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    assertion_status: AssertionStatus = "proposed"
    superseded_by: str | None = None
    privacy_tier: PrivacyTier = "internal"
    readers: list[str] = field(default_factory=lambda: ["librarian", "orchestrator"])
    evidence: list[CandidateEvidence] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    content_sha256: str = ""
    content_bytes: int = 0

    def __post_init__(self) -> None:
        if not self.content_sha256:
            raw = self.full_content.encode("utf-8")
            object.__setattr__(self, "content_sha256", hashlib.sha256(raw).hexdigest())
            object.__setattr__(self, "content_bytes", len(raw))


class LibrarianDeterministicAdapter(ABC):
    """Abstract base class for all deterministic (zero-LLM) source adapters."""

    @property
    @abstractmethod
    def source_id(self) -> str:
        """The canonical source ID registered in REGISTERED_SOURCES."""
        ...

    @property
    @abstractmethod
    def default_category(self) -> MemoryCategory:
        """Default memory category for this source."""
        ...

    @abstractmethod
    def extract(self, source_input: Any, **kwargs: Any) -> list[CandidateRecord]:
        """Extract atomic semantic records with verifiable evidence from source data."""
        ...
