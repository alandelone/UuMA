"""Read-only semantic access to a published Librarian archive catalog.

The trusted collector/publisher owns catalog.json and content-addressed objects.
This module never creates directories, captures sources, or changes domain state.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, StrictStr

MAX_CATALOG_BYTES = 16 * 1024 * 1024
MAX_TEXT_BYTES = 8 * 1024 * 1024
IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}\Z")


class ArchiveModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArchiveSource(ArchiveModel):
    source_id: StrictStr
    owner_agent: StrictStr
    readers: list[StrictStr]
    capture_status: Literal["NOT_COLLECTED", "COMPLETE", "PARTIAL", "UNAVAILABLE"]
    device: StrictStr = "server"
    category_default: StrictStr = "Knowledge"
    privacy_tier: StrictStr = "internal"
    captured_at: AwareDatetime | None = None
    source_as_of: StrictStr = ""
    verification: Literal["UNVERIFIED", "HASH_VERIFIED", "RESTORE_VERIFIED"] = "UNVERIFIED"
    evidence_refs: list[StrictStr] = Field(default_factory=list)


class ArchiveRecord(ArchiveModel):
    record_id: StrictStr
    version_id: StrictStr
    source_id: StrictStr
    readers: list[StrictStr]
    project_ids: list[StrictStr] = Field(default_factory=list)
    category: StrictStr | None = None
    kind: StrictStr
    title: StrictStr
    summary: StrictStr = ""
    assertion_status: StrictStr = "proposed"
    superseded_by: StrictStr | None = None
    original_status: StrictStr
    original_ref: StrictStr
    captured_at: AwareDatetime
    is_summary: StrictBool = False
    derived_from: list[StrictStr] = Field(default_factory=list)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_bytes: int = Field(strict=True, ge=0)
    media_type: StrictStr = "text/plain"
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    entities: list[StrictStr] = Field(default_factory=list)


class ArchiveCatalog(ArchiveModel):
    schema_version: Literal[1]
    snapshot_id: StrictStr
    published_at: AwareDatetime
    sources: list[ArchiveSource]
    records: list[ArchiveRecord]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate archive catalog key")
        result[key] = value
    return result


def _identities(values: list[str]) -> None:
    if len(set(values)) != len(values) or any(not IDENTITY.fullmatch(v) for v in values):
        raise ValueError("Invalid or duplicate archive identity")


class LibrarianReader:
    def __init__(self, root: str | Path, actor_id: str) -> None:
        if not IDENTITY.fullmatch(actor_id):
            raise PermissionError("A trusted launcher must bind the Librarian reader identity")
        self.actor_id = actor_id
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("Configured archive root is not a directory")
        primary_path = self.root / "librarian_semantic_catalog.json"
        legacy_path = self.root / "catalog.json"
        path = primary_path if primary_path.exists() else legacy_path
        if not path.exists():
            raise FileNotFoundError(f"Neither {primary_path.name} nor {legacy_path.name} exists in archive root")
        if path.is_symlink():
            raise ValueError("Archive catalog must be a regular published file")
        with path.open("rb") as handle:
            raw = handle.read(MAX_CATALOG_BYTES + 1)
        if len(raw) > MAX_CATALOG_BYTES:
            raise ValueError("Archive catalog exceeds the supported reader size")
        self.catalog = ArchiveCatalog.model_validate(json.loads(raw, object_pairs_hook=_unique_object))
        _identities([self.catalog.snapshot_id])
        self.sources = {item.source_id: item for item in self.catalog.sources}
        if len(self.sources) != len(self.catalog.sources):
            raise ValueError("Duplicate archive source")
        self.records: dict[tuple[str, str], ArchiveRecord] = {}
        record_sources: dict[str, str] = {}
        for source in self.catalog.sources:
            _identities([source.source_id, source.owner_agent])
            _identities(source.readers)
            if source.verification == "RESTORE_VERIFIED" and not source.evidence_refs:
                raise ValueError("Restore verification needs an explicit evidence reference")
        for record in self.catalog.records:
            _identities([record.record_id, record.version_id])
            _identities(record.readers)
            source = self.sources.get(record.source_id)
            if source is None or not set(record.readers).issubset(source.readers):
                raise ValueError("Archive record has an invalid source or reader scope")
            if record_sources.setdefault(record.record_id, record.source_id) != record.source_id:
                raise ValueError("Archive record identity cannot change source")
            if record.is_summary and not record.derived_from:
                raise ValueError("An archived summary must retain its source references")
            key = (record.record_id, record.version_id)
            if key in self.records:
                raise ValueError("Duplicate archive record version")
            self.records[key] = record

    def _snapshot(self, expected_snapshot_id: str) -> None:
        if expected_snapshot_id and expected_snapshot_id != self.catalog.snapshot_id:
            raise ValueError("Archive snapshot changed; repeat the query")

    def _visible(self, record: ArchiveRecord) -> bool:
        return (
            self.actor_id in self.sources[record.source_id].readers
            and self.actor_id in record.readers
        )

    def _record(self, record_id: str, version_id: str) -> ArchiveRecord:
        record = self.records.get((record_id, version_id))
        if record is None or not self._visible(record):
            raise KeyError("Archived record/version unavailable for this reader")
        return record

    def _metadata(self, record: ArchiveRecord) -> dict[str, Any]:
        source = self.sources[record.source_id]
        return record.model_dump(mode="json", exclude={"readers"}) | {
            "snapshot_id": self.catalog.snapshot_id,
            "owner_agent": source.owner_agent,
            "source_as_of": source.source_as_of,
            "content_verified": False,
        }

    def list_sources(self, expected_snapshot_id: str = "") -> dict[str, Any]:
        self._snapshot(expected_snapshot_id)
        sources = []
        for source in self.catalog.sources:
            if self.actor_id not in source.readers:
                continue
            sources.append(source.model_dump(mode="json", exclude={"readers"}) | {
                "visible_record_versions": sum(
                    record.source_id == source.source_id and self._visible(record)
                    for record in self.catalog.records
                ),
            })
        return {"snapshot_id": self.catalog.snapshot_id, "sources": sources}

    def search_records(
        self, query: str = "", project_id: str = "", source_id: str = "",
        kind: str = "", limit: int = 50, offset: int = 0,
        expected_snapshot_id: str = "", latest_only: bool = False,
        category: str = "",
    ) -> dict[str, Any]:
        self._snapshot(expected_snapshot_id)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Use a limit between 1 and 100")
        if type(offset) is not int or offset < 0:
            raise ValueError("Offset must be a nonnegative integer")
        if len(query) > 2000:
            raise ValueError("Search query is too long")
        records = [record for record in self.catalog.records if self._visible(record)]
        if source_id:
            records = [record for record in records if record.source_id == source_id]
        if latest_only:
            latest: dict[str, ArchiveRecord] = {}
            for record in records:
                previous = latest.get(record.record_id)
                if previous is None or (record.captured_at, record.version_id) > (
                    previous.captured_at, previous.version_id
                ):
                    latest[record.record_id] = record
            records = list(latest.values())
        if project_id:
            records = [record for record in records if project_id in record.project_ids]
        if kind:
            records = [record for record in records if record.kind == kind]
        if category:
            records = [record for record in records if record.category == category]
        folded = query.casefold()
        records = [record for record in records if folded in (
            f"{record.record_id} {record.title} {record.kind} {record.original_status} "
            f"{record.summary} {record.category or ''}"
        ).casefold()]
        records.sort(key=lambda record: (
            record.captured_at, record.record_id, record.version_id
        ), reverse=True)
        selected = records[offset:offset + limit]
        end = offset + len(selected)
        return {
            "snapshot_id": self.catalog.snapshot_id,
            "search_scope": "archived_metadata",
            "total": len(records),
            "records": [self._metadata(record) for record in selected],
            "next_offset": end if end < len(records) else None,
        }

    def get_record(
        self, record_id: str, version_id: str, expected_snapshot_id: str = "",
    ) -> dict[str, Any]:
        self._snapshot(expected_snapshot_id)
        return self._metadata(self._record(record_id, version_id))

    def read_record(
        self, record_id: str, version_id: str, offset: int = 0, limit: int = 6000,
        expected_snapshot_id: str = "",
    ) -> dict[str, Any]:
        self._snapshot(expected_snapshot_id)
        record = self._record(record_id, version_id)
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 20000:
            raise ValueError("Use nonnegative character offset and a limit between 1 and 20000")
        if not (record.media_type.startswith("text/") or record.media_type in {
            "application/json", "application/x-ndjson", "application/jsonl",
        }):
            raise ValueError("This inline reader exposes binary records through metadata only")
        if record.content_bytes > MAX_TEXT_BYTES:
            raise ValueError("Record exceeds the inline text reader size; metadata remains available")
        path = self.root
        for part in ("objects", record.content_sha256[:2], record.content_sha256):
            path = path / part
            if path.is_symlink():
                raise ValueError("Archive object path cannot contain symlinks")
        if not path.resolve(strict=True).is_relative_to(self.root):
            raise ValueError("Archive object escaped its configured root")
        with path.open("rb") as handle:
            raw = handle.read(MAX_TEXT_BYTES + 1)
        if len(raw) != record.content_bytes or hashlib.sha256(raw).hexdigest() != record.content_sha256:
            raise ValueError("Archived content failed its recorded size or digest check")
        text = raw.decode("utf-8")
        end = min(offset + limit, len(text))
        return self._metadata(record) | {
            "content_verified": True,
            "text": text[offset:end],
            "offset": offset,
            "next_offset": end if end < len(text) else None,
            "total_characters": len(text),
        }

    def project_context(
        self, project_id: str, limit: int = 50, offset: int = 0,
        expected_snapshot_id: str = "",
    ) -> dict[str, Any]:
        if not project_id:
            raise ValueError("Select one explicit project")
        return self.search_records(
            project_id=project_id, latest_only=True, limit=limit, offset=offset,
            expected_snapshot_id=expected_snapshot_id,
        ) | {"project_id": project_id, "context_kind": "source_record_index"}

    def read_binary_chunk(
        self, record_id: str, version_id: str, offset: int = 0, limit: int = 262144,
        expected_snapshot_id: str = "",
    ) -> dict[str, Any]:
        """Return a bounded byte range only after hashing the entire authorized object."""
        self._snapshot(expected_snapshot_id)
        record = self._record(record_id, version_id)
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 1048576:
            raise ValueError("Use a nonnegative byte offset and a limit between 1 and 1048576")
        path = self.root
        for part in ("objects", record.content_sha256[:2], record.content_sha256):
            path = path / part
            if path.is_symlink():
                raise ValueError("Archive object path cannot contain symlinks")
        if not path.resolve(strict=True).is_relative_to(self.root):
            raise ValueError("Archive object escaped its configured root")
        digest = hashlib.sha256()
        selected = bytearray()
        position = 0
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1048576), b""):
                digest.update(chunk)
                left = max(offset - position, 0)
                right = min(offset + limit - position, len(chunk))
                if left < right:
                    selected.extend(chunk[left:right])
                position += len(chunk)
        if position != record.content_bytes or digest.hexdigest() != record.content_sha256:
            raise ValueError("Archived content failed its recorded size or digest check")
        end = min(offset + len(selected), position)
        return self._metadata(record) | {
            "content_verified": True, "content_base64": base64.b64encode(selected).decode("ascii"),
            "offset": offset, "next_offset": end if end < position else None,
            "total_bytes": position,
        }

    def backup_status(self, expected_snapshot_id: str = "") -> dict[str, Any]:
        return self.list_sources(expected_snapshot_id) | {
            "published_at": self.catalog.published_at.isoformat(),
            "policy": {"time": "00:00", "timezone": "Asia/Singapore", "daily_captures": 1},
            "schedule_installed_by_reader": False,
            "fresh_live_sources_checked": False,
        }
