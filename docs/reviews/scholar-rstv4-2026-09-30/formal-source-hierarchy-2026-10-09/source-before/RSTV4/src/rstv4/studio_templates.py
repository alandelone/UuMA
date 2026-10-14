"""Source-bound empty structures. Replacement never guesses where author text belongs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import new_id
from .research_views import skeleton_source
from .service import NotFoundError
from .source_review import evidence_is_available, source_is_available
from .studio_structure import section_end


def template_preview(conn: Any, manuscript_id: str, skeleton_id: str) -> dict:
    source = skeleton_source(conn, skeleton_id)
    scope = conn.execute(
        """SELECT m.track_id,t.field_id FROM manuscripts m
           JOIN research_tracks t USING(track_id) WHERE m.manuscript_id=?""",
        (manuscript_id,),
    ).fetchone()
    if scope is None:
        raise NotFoundError("Unknown template manuscript")
    evidence = conn.execute(
        """SELECT * FROM evidence WHERE paper_id=? AND (track_id=? OR field_id=?)
           AND (paper_version_id=? OR paper_version_id IS NULL)""",
        (source["paper_id"], scope["track_id"], scope["field_id"], source["paper_version_id"]),
    ).fetchall()
    if not source_is_available(conn, source["paper_version_id"]) or not any(
        evidence_is_available(conn, dict(row)) for row in evidence
    ):
        raise ValueError("Template source is unavailable in this manuscript scope")
    sections: list[dict] = []
    for unit in source["units"]:
        # Flat legacy Skeleton units do not prove Subsection or Group boundaries.
        title = unit.get("section") or "未定章节"
        if not sections or sections[-1]["title"] != title:
            sections.append({"title": title, "paragraphs": []})
        if not isinstance(unit.get("layer3"), dict) or not isinstance(unit.get("layer2"), dict):
            raise TypeError("Template layers must be explicit structural objects")
        label = unit["layer3"].get("intent")
        label = label if isinstance(label, str) and label != "UNKNOWN" else ""
        sections[-1]["paragraphs"].append({
            "unit_id": unit["unit_id"], "intent": label,
            "role": unit.get("layer4") or "", "logic": unit.get("layer2") or {},
        })
    if not sections:
        raise ValueError("Template source has no structural units")
    return {"skeleton_id": skeleton_id, "skeleton_version": source["version"],
            "paper_id": source["paper_id"], "paper_version": source["paper_version"],
            "title": source["title"], "source_sha256": source["context_sha256"],
            "sections": sections, "author_text_copied": False}


def empty_sections(preview: dict, selected: list[str]) -> list[dict]:
    known = {p["unit_id"] for s in preview["sections"] for p in s["paragraphs"]}
    if not selected or len(set(selected)) != len(selected) or not set(selected) <= known:
        raise ValueError("Select distinct structural units from this exact template")
    result = []
    for section in preview["sections"]:
        units = [p for p in section["paragraphs"] if p["unit_id"] in selected]
        if not units:
            continue
        roles = {p["role"] for p in units}
        result.append({
            "id": new_id("section"), "title": section["title"],
            "role": roles.pop() if len(roles) == 1 else "", "paragraphs": [
                {"id": new_id("paragraph"), "purpose": "", "paradigm": "",
                 "logical_relation": (p["logic"].get("discourse_relation")
                                      if isinstance(p["logic"].get("discourse_relation"), str)
                                      else ""),
                 "asset_ids": [], "formulas": [], "logic": deepcopy(p["logic"]),
                 "template_source": {"skeleton_id": preview["skeleton_id"],
                                     "unit_id": p["unit_id"],
                                     "source_sha256": preview["source_sha256"]},
                 "intents": [{"id": new_id("intent"), "label": p["intent"], "thoughts": []}]}
                for p in units],
        })
    return result


def apply_structure(document: dict, sections: list[dict], scope_type: str,
                    scope_id: str | None, mode: str) -> dict:
    result = deepcopy(document)
    if scope_type == "paper":
        if scope_id not in {None, document["manuscript_id"]}:
            raise ValueError("Template target belongs to another manuscript")
        if mode == "REPLACE":
            for section in result["sections"]:
                section["placement_status"] = "UNPLACED"
            result["sections"] = sections + result["sections"]
        else:
            result["sections"].extend(sections)
        return result
    for index, section in enumerate(result["sections"]):
        if section.get("placement_status") == "UNPLACED":
            continue
        if scope_type == "section" and section["id"] == scope_id:
            end = section_end(result["sections"], index)
            parent = section.get("parent_section_id")
            if parent:
                for added in sections:
                    added["parent_section_id"] = parent
            if mode == "REPLACE":
                old = result["sections"][index:end]
                del result["sections"][index:end]
                for item in old:
                    item["placement_status"] = "UNPLACED"
                if parent:
                    old[0]["unplaced_parent_section_id"] = old[0].pop("parent_section_id")
                result["sections"][index:index] = sections
                result["sections"].extend(old)
            else:
                result["sections"][end:end] = sections
            return result
        for position, paragraph in enumerate(section["paragraphs"]):
            if scope_type == "paragraph" and paragraph["id"] == scope_id:
                added = [p for s in sections for p in s["paragraphs"]]
                identifiers = [p["id"] for p in added]
                offset = position if mode == "REPLACE" else position + 1
                if mode == "REPLACE":
                    section["paragraphs"].pop(position)
                    result["sections"].append(_unplaced([paragraph]))
                section["paragraphs"][offset:offset] = added
                for group in section.get("paragraph_groups", []):
                    if scope_id in group["paragraph_ids"]:
                        spot = group["paragraph_ids"].index(scope_id)
                        if mode == "REPLACE":
                            group["paragraph_ids"][spot:spot + 1] = identifiers
                        else:
                            group["paragraph_ids"][spot + 1:spot + 1] = identifiers
                        break
                else:
                    if "block_order" in section:
                        spot = section["block_order"].index(scope_id)
                        if mode == "REPLACE":
                            section["block_order"][spot:spot + 1] = identifiers
                        else:
                            section["block_order"][spot + 1:spot + 1] = identifiers
                return result
            for spot, intent in enumerate(paragraph["intents"]):
                if scope_type == "intent" and intent["id"] == scope_id:
                    added = [i for s in sections for p in s["paragraphs"] for i in p["intents"]]
                    offset = spot if mode == "REPLACE" else spot + 1
                    if mode == "REPLACE":
                        paragraph["intents"].pop(spot)
                        holder = {"id": new_id("paragraph"), "purpose": "", "paradigm": "",
                                  "asset_ids": [], "formulas": [], "intents": [intent]}
                        result["sections"].append(_unplaced([holder]))
                    paragraph["intents"][offset:offset] = added
                    return result
    raise ValueError("Choose an existing author structure outside the unplaced area")


def _unplaced(paragraphs: list[dict]) -> dict:
    return {"id": new_id("section"), "title": "待安置的原内容", "role": "",
            "placement_status": "UNPLACED", "paragraphs": paragraphs}
