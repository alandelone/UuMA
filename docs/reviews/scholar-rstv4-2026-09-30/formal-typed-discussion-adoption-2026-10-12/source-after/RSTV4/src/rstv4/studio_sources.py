"""Freeze explicitly identified original sources; never infer a latest source version."""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

from .fieldkg import digest
from .research_views import parse_record, skeleton_source
from .research_workspace import WorkspaceError
from .service import RSTV4Error


def freeze_source(conn: sqlite3.Connection, evidence: dict[str, Any]) -> dict[str, Any]:
    location = evidence.get("location") or {}
    skeleton_id, unit_id = location.get("skeleton_id"), location.get("unit_id")
    if not skeleton_id and not unit_id:
        return {"available": False, "reason": "Exact original source provenance was not recorded"}
    if not isinstance(skeleton_id, str) or not isinstance(unit_id, str):
        raise RSTV4Error("Original source requires both an exact skeleton and unit identity")
    try:
        source = skeleton_source(conn, skeleton_id)
    except (WorkspaceError, ValueError) as exc:
        raise RSTV4Error("The exact original source is unavailable or changed") from exc
    unit = next((u for u in source["units"] if u["unit_id"] == unit_id), None)
    if (unit is None or source["paper_id"] != evidence.get("paper_id")
            or (evidence.get("paper_version_id") and evidence["paper_version_id"] != source["paper_version_id"])
            or (location.get("skeleton_digest") and location["skeleton_digest"] != source["content_digest"])
            or (unit and location.get("unit_digest") and location["unit_digest"] != unit["content_digest"])
            or not evidence.get("excerpt") or evidence["excerpt"] not in (unit or {}).get("raw_text", "")
            or any(key in location and location[key] != (unit or {}).get(column)
                   for key, column in [("page", "page_idx"), ("section", "section"), ("sequence", "seq_idx")])):
        raise RSTV4Error("Original evidence source identity, excerpt or location changed")
    context = {key: source[key] for key in ["paper_id", "paper_version_id", "paper_version",
                "skeleton_id", "version", "content_digest", "pdf_digest", "parsed_digest",
                "file_version_id", "parse_run_id", "units"]}
    context.update(available=True, schema_version=1, unit=unit, file_version=None, parsed_blocks=[],
                   full_text_available=False, full_text_reason="Exact original PDF file version was not recorded")
    if "source_outline" in source:
        context["source_outline"] = source["source_outline"]
    if source["file_version_id"] or source["parse_run_id"]:
        file = conn.execute("SELECT * FROM source_file_versions WHERE file_version_id=?", (source["file_version_id"],)).fetchone()
        parse = conn.execute("SELECT * FROM parse_runs WHERE parse_run_id=?", (source["parse_run_id"],)).fetchone()
        if (file is None or parse is None or file["paper_id"] != source["paper_id"]
                or parse["file_version_id"] != file["file_version_id"] or parse["status"] != "SUCCEEDED"
                or file["sha256"] != source["pdf_digest"] or file["mime_type"] != "application/pdf"):
            raise RSTV4Error("Original source file and parse versions do not match")
        context["file_version"] = {key: file[key] for key in
                                   ["file_version_id", "paper_id", "sha256", "size_bytes", "mime_type"]}
        context["parsed_blocks"] = [parse_record(dict(row)) for row in conn.execute(
            "SELECT * FROM document_blocks WHERE parse_run_id=? ORDER BY sequence,block_id",
            (source["parse_run_id"],))]
        try:
            raw = Path(file["storage_path"]).read_bytes()
            available = len(raw) == file["size_bytes"] and hashlib.sha256(raw).hexdigest() == file["sha256"]
        except OSError:
            available = False
        context["full_text_available"] = available
        context["full_text_reason"] = None if available else "Original PDF is unavailable or failed its integrity check"
    context["context_sha256"] = digest(context)
    return context


def original_pdf(conn: sqlite3.Connection, reference: dict[str, Any]) -> bytes:
    context = reference.get("source_context") or {}
    frozen = context.get("file_version")
    if not context.get("available") or not frozen:
        raise RSTV4Error("The exact original PDF source is unavailable")
    file = conn.execute("SELECT * FROM source_file_versions WHERE file_version_id=?", (frozen["file_version_id"],)).fetchone()
    if file is None or any(file[key] != value for key, value in frozen.items()):
        raise RSTV4Error("The original PDF source identity failed its integrity check")
    try:
        raw = Path(file["storage_path"]).read_bytes()
    except OSError as exc:
        raise RSTV4Error("The exact original PDF source is unavailable") from exc
    if len(raw) != frozen["size_bytes"] or hashlib.sha256(raw).hexdigest() != frozen["sha256"]:
        raise RSTV4Error("The original PDF source failed its integrity check")
    return raw


def model_source(evidence: dict[str, Any]) -> dict[str, Any]:
    """Bind the full source digest without repeating an entire paper in every model prompt."""
    context = evidence.get("source_context")
    if not context or not context.get("available"):
        return evidence
    keys = ["available", "schema_version", "context_sha256", "paper_id", "paper_version_id",
            "paper_version", "skeleton_id", "version", "file_version_id", "parse_run_id", "unit"]
    return {**evidence, "source_context": {key: context[key] for key in keys}}


def validate_references(generated: dict, frozen_evidence: dict[str, dict], ids: list[str]) -> None:
    references = generated.get("references", [])
    # Match the exact source snapshot already bound to the original validated model input.
    if len(references) != len(ids):
        raise RSTV4Error("Generated references differ from their original validated source snapshot")
    for index, (eid, reference) in enumerate(zip(ids, references, strict=True), 1):
        original = {key: value for key, value in reference.items() if key not in
                    {"citation_index", "source_snapshot_available", "reference_snapshot_source"}}
        context = original.get("source_context") or {}
        if (eid not in frozen_evidence or reference.get("citation_index") != index
                or reference.get("source_snapshot_available") is not True
                or reference.get("reference_snapshot_source") != "generation_input"
                or (context.get("available") and digest({key: value for key, value in context.items()
                    if key != "context_sha256"}) != context.get("context_sha256"))
                or model_source(original) != model_source(frozen_evidence[eid])):
            raise RSTV4Error("Generated references differ from their original validated source snapshot")
