"""Immutable source headings from explicit parser levels, never model/title inference."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .fieldkg import digest

SCHEMA = """
CREATE TABLE IF NOT EXISTS skeleton_source_outlines (
  skeleton_id TEXT PRIMARY KEY REFERENCES paper_skeletons(skeleton_id),
  parse_run_id TEXT NOT NULL REFERENCES parse_runs(parse_run_id),
  outline_json TEXT NOT NULL,
  content_digest TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


def build_source_outline(
    conn: sqlite3.Connection, parse_run_id: str, units: list[dict[str, Any]],
) -> dict | None:
    blocks = [dict(row) for row in conn.execute(
        "SELECT * FROM document_blocks WHERE parse_run_id=? ORDER BY sequence", (parse_run_id,),
    )]
    headings = [block for block in blocks if block["block_type"] == "HEADING"]
    if not any("heading_level" in json.loads(b["location_json"]) for b in headings):
        return None  # Legacy parses retain their exact flat source identity.
    parse = conn.execute(
        "SELECT file_version_id FROM parse_runs WHERE parse_run_id=? AND status='SUCCEEDED'",
        (parse_run_id,),
    ).fetchone()
    if parse is None:
        raise ValueError("Source outline requires a completed parse")
    sections: list[dict] = []
    stack: list[dict] = []
    membership: dict[str, str | None] = {}
    for block in blocks:
        if block["block_type"] == "HEADING":
            location = json.loads(block["location_json"])
            level = location.get("heading_level")
            if type(level) is not int or not 1 <= level <= 5:
                raise ValueError("Source headings require explicit integer levels from one to five")
            if level > len(stack) + 1:
                raise ValueError("Source heading level skips its explicit parent")
            stack = stack[:level - 1]
            section = {
                "source_section_id": block["block_id"],
                "parent_source_section_id": stack[-1]["source_section_id"] if stack else None,
                "title": block["text"], "depth": level - 1,
                "source_path": [s["title"] for s in stack] + [block["text"]],
                "heading_location": location, "page_number": block["page_number"],
                "heading_content_digest": block["content_digest"],
            }
            sections.append(section)
            stack.append(section)
        membership[block["block_id"]] = stack[-1]["source_section_id"] if stack else None
    by_id = {block["block_id"]: block for block in blocks}
    assignments = []
    previous = -1
    for index, unit in enumerate(units):
        block = by_id.get(unit.get("block_id"))
        if block is None or block["sequence"] <= previous:
            raise ValueError("Outline units must use distinct source blocks in their parse reading order")
        if (unit["raw_text"] != block["text"]
                or unit.get("page_number") != block["page_number"]
                or unit.get("section") != block["section"]):
            raise ValueError("Outline unit text and location must match its exact parse block")
        previous = block["sequence"]
        assignments.append({"seq_idx": index, "block_id": block["block_id"],
                            "source_section_id": membership[block["block_id"]],
                            "block_content_digest": block["content_digest"]})
    if any(item["source_section_id"] is None for item in assignments):
        # Preserve pre-heading content as explicitly unsectioned, without guessing a parent.
        identifier = f"unsectioned:{parse_run_id}"
        sections.insert(0, {"source_section_id": identifier, "parent_source_section_id": None,
                            "title": "未标注章节", "depth": 0, "source_path": [],
                            "heading_location": None, "page_number": None,
                            "heading_content_digest": None})
        for item in assignments:
            if item["source_section_id"] is None:
                item["source_section_id"] = identifier
    return {"schema_version": 1, "parse_run_id": parse_run_id,
            "file_version_id": parse["file_version_id"],
            "sections": sections, "unit_assignments": assignments}


def read_source_outline(conn: sqlite3.Connection, source: dict) -> dict | None:
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                        "AND name='skeleton_source_outlines'").fetchone():
        return None  # Read-only compatibility with a catalog predating this additive table.
    row = conn.execute("SELECT * FROM skeleton_source_outlines WHERE skeleton_id=?",
                       (source["skeleton_id"],)).fetchone()
    if row is None:
        return None
    try:
        outline = json.loads(row["outline_json"])
        if (digest(outline) != row["content_digest"]
                or row["parse_run_id"] != source["parse_run_id"]
                or outline["parse_run_id"] != source["parse_run_id"]
                or outline["file_version_id"] != source["file_version_id"]):
            raise ValueError("Source outline identity or digest changed")
        assignments = outline["unit_assignments"]
        if len(assignments) != len(source["units"]):
            raise ValueError("Source outline unit coverage changed")
        units = []
        for index, (unit, assignment) in enumerate(zip(source["units"], assignments, strict=True)):
            if unit["seq_idx"] != index or assignment["seq_idx"] != index:
                raise ValueError("Source outline unit order changed")
            # The historical catalog column is named page_idx; native publication stores
            # the parser's one-based page_number in it. Keep that schema/data untouched.
            units.append({**unit, "block_id": assignment["block_id"],
                          "page_number": unit["page_idx"]})
        if build_source_outline(conn, row["parse_run_id"], units) != outline:
            raise ValueError("Source outline no longer matches its original parse")
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Source outline is malformed") from exc
    return outline
