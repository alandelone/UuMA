"""Verify source-only PDF superscript/definition geometry without interpreting science."""
from __future__ import annotations

import math
import re
import unicodedata


def normalized_anchor_text(text: str) -> str:
    """A locator alias only; callers retain the exact source and native glyph text."""
    return "".join(character for character in unicodedata.normalize("NFKC", text) if not character.isspace())


def source_footnote_definitions(pdf_context: dict, target_ids: list[str]) -> dict[str, dict]:
    lines = [line for line in pdf_context["indexed_layout_lines"] if line["line_id"] in target_ids]
    if [line["line_id"] for line in lines] != target_ids or not lines:
        raise ValueError("Footnote source must retain the exact ordered target-table domain")
    indices = [i for i, line in enumerate(lines) if re.fullmatch(r"[a-z]", line["text"].strip())]
    definitions = {}
    for number, position in enumerate(indices):
        marker = lines[position]["text"].strip()
        stop = indices[number + 1] if number + 1 < len(indices) else len(lines)
        body = [line for line in lines[position + 1:stop] if line["text"].strip()]
        if marker in definitions or not body:
            raise ValueError("Actual footnote marker duplicated or complete definition missing")
        definitions[marker] = {"marker": marker, "marker_line_id": lines[position]["line_id"], "definition_lines": body}
    if not definitions:
        raise ValueError("Original table footer marker domain is empty")
    return definitions


def verify_footnote_anchor_ledger(pdf_context: dict, target_ids: list[str], ledger: dict) -> list[dict]:
    if (ledger["source_pdf"] != pdf_context["source_pdf"]
            or ledger["source_pdf_sha256"] != pdf_context["source_pdf_sha256"]
            or ledger["original_pdf_layout_path"] != pdf_context["layout_text_path"]
            or ledger["original_pdf_layout_sha256"] != pdf_context["layout_text_sha256"]
            or ledger["table_source_line_ids"] != target_ids
            or ledger["scientific_fields_generated_or_changed"] is not False
            or ledger["learner_or_expected_scientific_values_used"] is not False):
        raise ValueError("Original PDF footnote geometry lineage or source-only isolation changed")
    definitions = source_footnote_definitions(pdf_context, target_ids)
    actual_lines = {line["line_id"]: line for line in pdf_context["indexed_layout_lines"]}
    footnotes, seen = ledger["source_footnotes"], set()
    for footnote in footnotes:
        marker = footnote["marker"]
        if marker not in definitions or marker in seen:
            raise ValueError("Footnote ledger contains a foreign or duplicate actual marker")
        seen.add(marker)
        if any(footnote[key] != value for key, value in definitions[marker].items()):
            raise ValueError("Footnote ledger changed or omitted complete original definition lines")
        anchor_id = footnote["anchor_line_id"]
        if anchor_id not in target_ids or target_ids.index(anchor_id) >= target_ids.index(footnote["marker_line_id"]):
            raise ValueError("Footnote anchor must be in the actual table body before its footer")
        source_line = actual_lines[anchor_id]
        token = footnote["anchor_token"]
        matches = [key for key in target_ids if normalized_anchor_text(token) in normalized_anchor_text(actual_lines[key]["text"])]
        if (not token or matches != [anchor_id] or marker not in token
                or footnote["anchor_line_exact_text"] != source_line["text"]):
            raise ValueError("Actual PDF marker word does not uniquely match unchanged source line")
        glyph, bbox = footnote["marker_glyph"], footnote["anchor_word_bbox"]
        numeric = [glyph[key] for key in ["size", "x0", "x1", "top", "bottom"]]
        numeric += [bbox[key] for key in ["x0", "x1", "top", "bottom"]]
        numeric.append(footnote["anchor_word_body_font_size"])
        if (not all(isinstance(value, (float, int)) and math.isfinite(value) for value in numeric)
                or glyph["text"] != marker or not 0 < glyph["size"] < 0.8 * footnote["anchor_word_body_font_size"]
                or not bbox["x0"] <= glyph["x0"] < glyph["x1"] <= bbox["x1"]
                or not bbox["top"] <= glyph["top"] < glyph["bottom"] <= bbox["bottom"]):
            raise ValueError("Footnote source glyph is not a located smaller superscript within its actual word")
        footer = footnote["footer_marker_glyph"]
        if (footer["text"] != marker or abs(footer["size"] - glyph["size"]) > 0.001
                or footer["top"] <= glyph["bottom"] or ledger["actual_pdf_page"] != footnote["original_pdf_page"]):
            raise ValueError("Actual PDF footer glyph and superscript marker identity/geometry differ")
    if seen != set(definitions):
        raise ValueError("Footnote ledger omitted an actual original footer marker")
    return footnotes
