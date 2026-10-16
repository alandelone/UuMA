"""Conservative author-change realization and final compiled PDF text-line evidence."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .studio_context import numbered_text
from .studio_layout import layout_only_evidence


def tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text)
    # TeX renders a word-internal ASCII apostrophe as U+2019. Preserve all
    # other punctuation, primes and word boundaries when locating exact prose.
    normalized = re.sub(r"(?<=\w)\u2019(?=\w)", "'", normalized)
    return re.findall(r"\w+|[^\w\s]", normalized)


def extract_layout(pdf: Path, layout_path: Path) -> dict[str, Any]:
    pdf_sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    command = shutil.which("pdftotext")
    if not command:
        return {"pdf_sha256": pdf_sha, "status": "TOOL_UNAVAILABLE", "tokens": [], "lines": []}
    try:
        result = subprocess.run([command, "-bbox-layout", "-enc", "UTF-8", str(pdf), str(layout_path)],
                                capture_output=True, timeout=30, check=False)
        if result.returncode:
            return {"pdf_sha256": pdf_sha, "status": "EXTRACTION_FAILED", "tokens": [], "lines": []}
        root = ET.parse(layout_path).getroot()
        lines, stream = [], []
        for page_index, page in enumerate(root.iter("{http://www.w3.org/1999/xhtml}page"), 1):
            page_lines = []
            for element in page.iter("{http://www.w3.org/1999/xhtml}line"):
                words = [{"text": word.text or "", "box": [float(word.get(k, "0")) for k in ["xMin", "yMin", "xMax", "yMax"]]}
                         for word in element.findall("{http://www.w3.org/1999/xhtml}word")]
                if words:
                    page_lines.append({"y": float(element.get("yMin", "0")), "words": words})
            grouped = []
            for line in sorted(page_lines, key=lambda item: item["y"]):
                if grouped and abs(grouped[-1]["y"] - line["y"]) <= 1:
                    grouped[-1]["words"].extend(line["words"])
                else:
                    grouped.append(line)
            for line_index, line in enumerate(grouped, 1):
                words = sorted(line["words"], key=lambda item: item["box"][0])
                lines.append({"page": page_index, "line": line_index, "text": " ".join(w["text"] for w in words),
                              "words": words})
                for word in words:
                    stream.extend({"token": token, "page": page_index, "line": line_index, "box": word["box"]}
                                  for token in tokens(word["text"]))
        return {"pdf_sha256": pdf_sha, "layout_sha256": hashlib.sha256(layout_path.read_bytes()).hexdigest(),
                "status": "EXTRACTED" if stream else "NO_EXTRACTABLE_TEXT", "tokens": stream, "lines": lines,
                "line_number_kind": "visible_text_line_from_top_of_physical_page", "method": "pdftotext-bbox-layout-v1"}
    except (OSError, subprocess.TimeoutExpired, ET.ParseError, ValueError) as exc:
        return {"pdf_sha256": pdf_sha, "status": "EXTRACTION_FAILED", "error_type": type(exc).__name__, "tokens": [], "lines": []}


def unique_paragraph(layout: dict[str, Any], text: str) -> tuple[list[dict[str, Any]], str]:
    needle = tokens(text)
    stream = layout["tokens"]
    if not needle or layout["status"] != "EXTRACTED":
        return [], layout["status"]
    variants = [stream]
    dehyphenated = []
    index = 0
    while index < len(stream):
        if (index + 2 < len(stream) and stream[index]["token"].isalnum()
                and stream[index + 1]["token"] == "-" and stream[index + 2]["token"].isalnum()
                and stream[index]["page"] == stream[index + 2]["page"]
                and stream[index]["line"] + 1 == stream[index + 2]["line"]):
            dehyphenated.append({**stream[index], "token": stream[index]["token"] + stream[index + 2]["token"],
                                 "extra_boxes": [stream[index + 1], stream[index + 2]]})
            index += 3
        else:
            dehyphenated.append(stream[index])
            index += 1
    variants.append(dehyphenated)
    matches = {}
    for variant in variants:
        for start in range(max(0, len(variant) - len(needle) + 1)):
            matched = variant[start:start + len(needle)]
            if [item["token"] for item in matched] == needle:
                key = tuple((item["page"], item["line"], tuple(item["box"])) for item in matched)
                matches[key] = matched
    if len(matches) != 1:
        return [], "AMBIGUOUS_PDF_TEXT" if matches else "PDF_TEXT_NOT_FOUND"
    return next(iter(matches.values())), "UNIQUE_FULL_PARAGRAPH"


def thoughts(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {thought["id"]: {"paragraph_id": paragraph["id"], "thought": thought}
            for section in document.get("sections", []) for paragraph in section.get("paragraphs", [])
            for intent in paragraph.get("intents", []) for thought in intent.get("thoughts", [])}


def frozen_origins(document: dict[str, Any], target: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Original author-bank context, never the current editor or a projected template slot."""
    if document.get("manuscript_id") != target["manuscript_id"]:
        raise ValueError("Frozen author origins belong to another manuscript")
    result: dict[str, list[dict[str, Any]]] = {}
    for section in document.get("sections", []):
        for paragraph in section.get("paragraphs", []):
            for intent in paragraph.get("intents", []):
                original = [{"thought_id": t["id"], "text": t["text"]}
                            for t in intent.get("thoughts", [])]
                for thought in intent.get("thoughts", []):
                    result.setdefault(thought["id"], []).append({
                        "manuscript_id": target["manuscript_id"],
                        "generated_version_id": target["generated_version_id"],
                        "generated_version_number": target["version"],
                        "input_revision": target["input_revision"],
                        "section_id": section["id"], "section_title": section["title"],
                        "paragraph_id": paragraph["id"],
                        "paragraph_purpose": paragraph.get("purpose", ""),
                        "intent_id": intent["id"], "intent_label": intent["label"],
                        "thought_id": thought["id"], "thought_text": thought["text"],
                        "intent_thoughts": original,
                    })
    return result


def compare_sentence(sentence: str, original: dict[str, Any] | None,
                     original_text: str) -> str:
    """Compare recorded full sentences; citation identity never proves prose changed."""
    if not original or not original.get("sentence_positions_verified"):
        return ("GENERATED_TEXT_CHANGED" if sentence and not original_text else
                "EXACT_BASELINE_TEXT_RETAINED" if sentence and sentence in original_text
                else "BASELINE_SENTENCE_COMPARISON_UNKNOWN")
    previous = [item["text"] for item in original["sentences"]]
    if sentence in previous:
        return "EXACT_BASELINE_TEXT_RETAINED"

    def prose(text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[ \t]*\[@[^\]]+\]", "", text)).strip()

    if prose(sentence) and any(prose(sentence) == prose(text) for text in previous):
        return "CITATION_ONLY"
    return "GENERATED_TEXT_CHANGED"


def write_mapping(path: Path, comments: list[dict[str, Any]], *, target: dict[str, Any],
                  baseline: dict[str, Any] | None, target_document: dict[str, Any],
                  baseline_document: dict[str, Any] | None, pdf: Path,
                  baseline_pdf: Path | None = None) -> dict[str, Any]:
    layout = extract_layout(pdf, path.parent / "final-compiled-layout.xhtml")
    old_layout = (extract_layout(baseline_pdf, path.parent / "baseline-compiled-layout.xhtml")
                  if baseline_pdf is not None else None)
    final_thoughts = thoughts(target_document)
    baseline_thoughts = thoughts(baseline_document) if baseline_document is not None else None
    blocks = {b["object_id"]: b for b in target["blocks"] if b["kind"] == "paragraph"}
    original_blocks = {b["object_id"]: b for b in baseline["blocks"] if b["kind"] == "paragraph"} if baseline else {}
    realizations = {item["paragraph_id"]: item for item in target.get("realizations", [])}
    original_realizations = {item["paragraph_id"]: item for item in baseline.get("realizations", [])} if baseline else {}
    origins = frozen_origins(target_document, target)
    rows = []
    for comment in comments:
        for change in comment.get("changes", []):
            before, after = thoughts(json.loads(change["before_json"])), thoughts(json.loads(change["after_json"]))
            changed = sorted(set(before) | set(after))
            changed = [identifier for identifier in changed if before.get(identifier) != after.get(identifier)]
            base = {"comment_id": comment["comment_id"], "change_id": change["change_id"],
                    "generated_version_id": target["generated_version_id"],
                    "baseline_version_id": baseline["generated_version_id"] if baseline else None,
                    "final_pdf_sha256": layout["pdf_sha256"], "final_line": None, "final_page": None,
                    "final_line_end": None, "final_page_end": None, "line_number_kind": layout.get("line_number_kind"),
                    "changed_text": "", "thought_id": None, "paragraph_id": None,
                    "sentence_index": None, "boxes": []}
            if not changed:
                presentation = layout_only_evidence(
                    json.loads(change["before_json"]), json.loads(change["after_json"]),
                    baseline_document=baseline_document, target_document=target_document,
                    baseline=baseline, target=target, old_layout=old_layout, new_layout=layout)
                rows.append({**base, **(presentation or {"status": "STRUCTURE_OR_SOURCE_CHANGE_UNMAPPED",
                    "reason": "No proven pure layout change or changed thought can be attributed to generated output"})})
            for identifier in changed:
                entry = {**base, "thought_id": identifier}
                expected, current = after.get(identifier), final_thoughts.get(identifier)
                if expected != current:
                    rows.append({**entry, "status": "SUPERSEDED_OR_REVERSED", "reason": "This edit's after-state does not equal the fixed generated input"})
                    continue
                if expected is None:
                    rows.append({**entry, "status": "REMOVED_FROM_AUTHOR_STRUCTURE", "reason": "Deleted author thought has no final text location"})
                    continue
                paragraph_id = expected["paragraph_id"]
                entry["paragraph_id"] = paragraph_id
                block, realization = blocks.get(paragraph_id), realizations.get(paragraph_id)
                if baseline_thoughts is None:
                    rows.append({**entry, "status": "BASELINE_INPUT_UNKNOWN", "reason": "No proven original author input for this round"})
                    continue
                if baseline_thoughts.get(identifier) == current:
                    rows.append({**entry, "status": "NO_AUTHOR_CHANGE_FROM_BASELINE", "reason": "Fixed baseline and target author thought are identical"})
                    continue
                if not block or not realization or not realization.get("sentence_positions_verified"):
                    rows.append({**entry, "status": "SENTENCE_MAPPING_UNKNOWN", "reason": "Exact sentence text and complete author mapping were not recorded"})
                    continue
                matched, match_status = unique_paragraph(layout, block["display_text"])
                spans = []
                cursor = 0
                for sentence in realization["sentences"]:
                    length = len(tokens(numbered_text(sentence["text"], target["references"])))
                    spans.append(matched[cursor:cursor + length] if matched else [])
                    cursor += length
                if matched and cursor != len(matched):
                    matched, match_status = [], "SENTENCE_TOKEN_MAPPING_MISMATCH"
                original_text = original_blocks.get(paragraph_id, {}).get("text", "")
                for mapping in realization["sentence_mappings"]:
                    if identifier not in mapping["thought_ids"]:
                        continue
                    sentence_index = mapping["sentence"]
                    sentence = realization["sentences"][sentence_index]["text"]
                    span = spans[sentence_index] if matched else []
                    locations = []
                    for word in span:
                        locations.append({"page": word["page"], "line": word["line"], "box": word["box"]})
                        locations.extend({"page": extra["page"], "line": extra["line"], "box": extra["box"]} for extra in word.get("extra_boxes", []))
                    # Text comparison is an observation, not a semantic claim or author approval.
                    status = compare_sentence(sentence, original_realizations.get(paragraph_id), original_text)
                    rows.append({**entry, "changed_text": sentence, "sentence_index": sentence_index,
                        "status": status if span else "FINAL_LOCATION_UNKNOWN", "text_comparison": status,
                        "change_kind": "CITATION" if status == "CITATION_ONLY" else "TEXT",
                        "supports_scientific_text_modification": bool(span) and status == "GENERATED_TEXT_CHANGED",
                        "reason": match_status, "boxes": locations,
                        "final_page": locations[0]["page"] if locations else None,
                        "final_line": locations[0]["line"] if locations else None,
                        "final_page_end": locations[-1]["page"] if locations else None,
                        "final_line_end": locations[-1]["line"] if locations else None})
    for row in rows:
        row["origins"] = origins.get(row["thought_id"], [])
    columns = ["comment_id", "change_id", "final_line", "final_page", "changed_text", "thought_id", "paragraph_id",
               "sentence_index", "final_line_end", "final_page_end", "status", "text_comparison", "reason",
               "line_number_kind", "generated_version_id", "baseline_version_id", "final_pdf_sha256",
               "change_kind", "baseline_pdf_sha256", "supports_scientific_text_modification"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    report = {"method": "author-to-recorded-sentence-to-final-pdf-v1", "scientific_acceptance": False,
              "automatic_response_approval": False, "pdf": {key: value for key, value in layout.items() if key != "tokens"},
              "rows": rows}
    (path.parent / "change-realization-map.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"rows": len(rows), "changed_text_rows_with_final_location": sum(row["status"] == "GENERATED_TEXT_CHANGED" for row in rows),
            "retained_text_rows_with_final_location": sum(row["status"] == "EXACT_BASELINE_TEXT_RETAINED" for row in rows),
            "layout_only_rows": sum(row["status"] == "LAYOUT_ONLY" for row in rows),
            "citation_only_rows": sum(row["status"] == "CITATION_ONLY" for row in rows),
            "unknown_or_unattributed_rows": sum(row["status"] not in {"GENERATED_TEXT_CHANGED", "EXACT_BASELINE_TEXT_RETAINED", "LAYOUT_ONLY", "CITATION_ONLY"} for row in rows),
            "line_number_kind": layout.get("line_number_kind"), "pdf_sha256": layout["pdf_sha256"],
            "layout_status": layout["status"], "semantic_or_response_claims_approved": False}
