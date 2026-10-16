"""Explicit page margins, frozen realization replay and conservative layout evidence."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any


def layout_settings(document: dict[str, Any]) -> dict[str, str]:
    value = document.get("layout", {"page_margin": "standard"})
    if (not isinstance(value, dict) or set(value) != {"page_margin"}
            or value["page_margin"] not in ("standard", "narrow")):
        raise ValueError("Layout must choose the standard or narrow page margin")
    return dict(value)


def author_semantics(document: dict[str, Any]) -> dict[str, Any]:
    """Remove exactly the typed presentation field; unknown fields remain significant."""
    return {key: value for key, value in document.items() if key != "layout"}


def digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf8")).hexdigest()


def layout_replay(before: dict[str, Any], after: dict[str, Any], source: dict[str, Any],
                  input_revision: int, source_version_id: str) -> dict[str, Any]:
    """Reuse exact generated sentences/references/materials; never call a language model."""
    if author_semantics(before) != author_semantics(after):
        raise ValueError("Layout replay cannot change author text, structure, citations, relations or materials")
    old, new = layout_settings(before), layout_settings(after)
    if old == new:
        raise ValueError("Change a page margin before requesting layout replay")
    if layout_settings(source) != old:
        raise ValueError("The source generation does not freeze the original page margin")
    if type(input_revision) is not int or input_revision <= source["input_revision"]:
        raise ValueError("Layout replay requires a later author revision")
    result = deepcopy(source)
    result["input_revision"] = input_revision
    result["layout"] = new
    result["layout_replay"] = {
        "schema_version": 1, "source_generated_version_id": source_version_id,
        "source_generated_sha256": digest(source), "method": "exact-realization-recompile-v1",
    }
    return result


def same_generated_content(left: dict[str, Any], right: dict[str, Any]) -> bool:
    def fixed(view: dict[str, Any]) -> dict[str, Any]:
        return {"content": view["content"], "references": view["references"],
                "citation_style": view.get("citation_style"),
                "realizations": view.get("realizations", []),
                "blocks": [{k: v for k, v in block.items() if k != "anchor_id"}
                           for block in view["blocks"]]}
    return fixed(left) == fixed(right)


def layout_only_evidence(before: dict[str, Any], after: dict[str, Any], *,
                         baseline_document: dict[str, Any] | None,
                         target_document: dict[str, Any], baseline: dict[str, Any] | None,
                         target: dict[str, Any], old_layout: dict[str, Any] | None,
                         new_layout: dict[str, Any]) -> dict[str, Any] | None:
    """Require unchanged identities and exact text plus measured compiled PDF movement."""
    from .studio_revision_mapping import unique_paragraph

    if (baseline is None or baseline_document is None or after != target_document
            or author_semantics(before) != author_semantics(after)
            or author_semantics(baseline_document) != author_semantics(target_document)
            or layout_settings(before) == layout_settings(after)
            or layout_settings(baseline_document) == layout_settings(target_document)
            or layout_settings(baseline) != layout_settings(baseline_document)
            or layout_settings(target) != layout_settings(target_document)
            or not same_generated_content(baseline, target)
            or old_layout is None or old_layout.get("status") != "EXTRACTED"
            or new_layout.get("status") != "EXTRACTED"):
        return None
    old_blocks = {block["object_id"]: block for block in baseline["blocks"] if block["kind"] == "paragraph"}
    moved = []
    for block in target["blocks"]:
        if block["kind"] != "paragraph":
            continue
        old = old_blocks.get(block["object_id"])
        if old is None:
            return None
        original, _ = unique_paragraph(old_layout, old["display_text"])
        final, _ = unique_paragraph(new_layout, block["display_text"])
        if not original or not final:
            return None
        def positions(span: list[dict[str, Any]]) -> list[dict[str, Any]]:
            result = []
            for word in span:
                result.append({key: word[key] for key in ("page", "line", "box")})
                result.extend({key: extra[key] for key in ("page", "line", "box")}
                              for extra in word.get("extra_boxes", []))
            return result
        old_boxes, new_boxes = positions(original), positions(final)
        if old_boxes != new_boxes:
            moved.append({"paragraph_id": block["object_id"], "baseline_boxes": old_boxes,
                          "boxes": new_boxes})
    if not moved:
        return None
    first = moved[0]
    return {"status": "LAYOUT_ONLY", "change_kind": "PRESENTATION", "changed_text": "",
            "reason": "Only the explicit margin changed; exact frozen content and identities retained; actual compiled PDF boxes moved",
            "baseline_pdf_sha256": old_layout["pdf_sha256"], "baseline_boxes": first["baseline_boxes"],
            "boxes": first["boxes"], "paragraph_id": first["paragraph_id"],
            "final_page": first["boxes"][0]["page"], "final_line": first["boxes"][0]["line"],
            "final_page_end": first["boxes"][-1]["page"], "final_line_end": first["boxes"][-1]["line"],
            "moved_paragraphs": moved, "supports_scientific_text_modification": False}
