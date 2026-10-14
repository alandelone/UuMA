"""Loss-aware normalization and basic quality checks for MinerU content lists."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

REFERENCE_HEADING = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s*)?"
    r"(?:references|bibliography|works cited|literature cited)$",
    re.IGNORECASE,
)
REFERENCE_LINE = re.compile(
    r"(?m)^\s*(?:\d+(?:\.\d+)*\.?\s*)?"
    r"(?:references|bibliography|works cited|literature cited)\s*:?\s*$",
    re.IGNORECASE,
)
NUMBERED_REFERENCE = re.compile(
    r"(?=\[\d{1,4}\]\s|^\s*\d{1,4}\.\s)", re.MULTILINE
)
REFERENCE_YEAR = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b", re.IGNORECASE)
BACK_MATTER = re.compile(
    r"^(?:there are no\s+)?(?:conflicts? of interest|competing interests?|"
    r"acknowledg(?:e)?ments?|how to cite this article|"
    r"disclaimer(?:/publisher.s note)?|other websites)\b",
    re.IGNORECASE,
)
ALIGNMENT_WORD = re.compile(r"[A-Za-z]{5,}")
BRACKETED_REFERENCE = re.compile(r"^[ \t]*\[(\d{1,4})\][ \t]", re.MULTILINE)
DOTTED_REFERENCE = re.compile(r"^[ \t]*(\d{1,4})\.[ \t]", re.MULTILINE)
SOURCE_REFERENCE_HEADING = re.compile(
    r"(?im)^[ \t]*(?:references|bibliography|works cited|literature cited)[ \t]*\r?$"
)


def _page_number(item: dict[str, Any]) -> int | None:
    index = item.get("page_idx")
    if isinstance(index, int) and not isinstance(index, bool) and index >= 0:
        return index + 1
    return None


def _reference_parts(text: str) -> list[str]:
    parts = [part.strip() for part in NUMBERED_REFERENCE.split(text) if part.strip()]
    if len(parts) > 1:
        return parts
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if (
        len(lines) >= 3
        and sum(bool(REFERENCE_YEAR.search(line)) for line in lines) / len(lines) >= 0.6
        and sum(len(line) >= 40 for line in lines) / len(lines) >= 0.8
    ):
        return lines
    return parts or [text]


def _reference_words(text: str) -> set[str]:
    return {word.lower() for word in ALIGNMENT_WORD.findall(text)}


def _align_reference_pages(
    references: list[dict[str, Any]], source_pdf_path: str | Path
) -> dict[str, Any]:
    """Align entries to physical PDF pages, withholding ambiguous locations."""
    try:
        completed = subprocess.run(
            ["pdftotext", "-layout", "-enc", "UTF-8", str(source_pdf_path), "-"],
            capture_output=True,
            check=True,
            timeout=120,
        )
        pages = completed.stdout.decode("utf-8", errors="replace").split("\f")
        if pages and not pages[-1].strip():
            pages.pop()
        if not pages:
            raise ValueError("PDF has no extractable pages")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        for reference in references:
            reference["location"]["mineru_page_number"] = reference["page_number"]
            reference["page_number"] = None
        return {"method": "unavailable", "reason": type(exc).__name__,
                "aligned": 0, "ambiguous": len(references), "corrected": 0}

    page_words = [_reference_words(page) for page in pages]
    first_reference_page = min(
        (ref["page_number"] for ref in references if isinstance(ref["page_number"], int)),
        default=1,
    )
    missing_numbers: list[int] = []
    numbering_checked = False
    for pattern in (BRACKETED_REFERENCE, DOTTED_REFERENCE):
        parsed_numbers = {
            int(match.group(1)) for ref in references
            if (match := pattern.match(ref["raw_text"]))
        }
        try:
            numbered_source = subprocess.run(
                ["pdftotext", "-f", str(first_reference_page), "-enc", "UTF-8",
                 str(source_pdf_path), "-"],
                capture_output=True,
                check=True,
                timeout=120,
            ).stdout.decode("utf-8", errors="replace")
            source_heading = SOURCE_REFERENCE_HEADING.search(numbered_source)
            if source_heading:
                source_numbers = {
                    int(value) for value in pattern.findall(numbered_source[source_heading.end():])
                }
                if not source_numbers:
                    continue
                missing_numbers = sorted(source_numbers - parsed_numbers)
                numbering_checked = True
        except (OSError, subprocess.SubprocessError):
            pass
        if numbering_checked:
            break
    aligned = ambiguous = corrected = 0
    for reference in references:
        original = reference["page_number"]
        location = reference["location"]
        location["mineru_page_number"] = original
        words = _reference_words(reference["raw_text"])
        start = max(0, original - 1) if isinstance(original, int) else 0
        scores = [len(words & page) / len(words) if words else 0.0
                  for page in page_words[start:]]
        best = max(range(len(scores)), key=scores.__getitem__) if scores else None
        best_score = scores[best] if best is not None else 0.0
        second_score = sorted(scores)[-2] if len(scores) > 1 else 0.0
        if len(words) >= 4 and best_score >= 0.65 and best_score - second_score >= 0.1:
            page_number = start + best + 1
            reference["page_number"] = page_number
            location["page_alignment"] = "pdftotext_word_overlap"
            location["page_alignment_score"] = round(best_score, 3)
            aligned += 1
            corrected += page_number != original
        else:
            reference["page_number"] = None
            location["page_alignment"] = "ambiguous"
            ambiguous += 1
    return {"method": "pdftotext_word_overlap", "aligned": aligned,
            "ambiguous": ambiguous, "corrected": corrected,
            "numbering_checked": numbering_checked,
            "missing_source_numbered_references": missing_numbers}


def normalize_mineru_result(
    result: dict[str, Any], *, source_pdf_path: str | Path | None = None
) -> dict[str, Any]:
    """Keep every readable pre-reference block and locate numbered references."""
    manifest = result.get("manifest")
    if not isinstance(manifest, dict):
        raise TypeError("MinerU returned no artifact manifest")
    content_path = Path(str(manifest.get("content_list_path") or ""))
    markdown_path = Path(str(manifest.get("markdown_path") or ""))
    if not content_path.is_file() or not markdown_path.is_file():
        raise ValueError("MinerU output is missing Markdown or content list")
    if markdown_path.stat().st_size == 0:
        raise ValueError("MinerU returned empty Markdown")
    items = json.loads(content_path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise TypeError("MinerU content list is not an array")

    blocks: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    section: str | None = None
    in_references = False
    reference_heading_found = False
    readable_chars = 0
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind in {"table", "equation", "image"}:
            caption_key = "table_caption" if kind == "table" else "img_caption"
            footnote_key = "table_footnote" if kind == "table" else "img_footnote"
            captions = item.get(caption_key) or []
            footnotes = item.get(footnote_key) or []
            if isinstance(captions, str):
                captions = [captions]
            if isinstance(footnotes, str):
                footnotes = [footnotes]
            pieces = [
                *(str(value).strip() for value in captions if str(value).strip()),
                str(item.get("table_body") or item.get("text") or "").strip(),
                *(str(value).strip() for value in footnotes if str(value).strip()),
            ]
            content = "\n".join(piece for piece in pieces if piece)
            if content:
                location = {"source": "mineru_content_list", "content_index": index}
                if isinstance(item.get("page_idx"), int):
                    location["page_idx"] = item["page_idx"]
                if "bbox" in item:
                    location["bbox"] = item["bbox"]
                if isinstance(item.get("img_path"), str):
                    location["artifact_image_path"] = item["img_path"]
                blocks.append({
                    "sequence": len(blocks),
                    "page_number": _page_number(item),
                    "section": section,
                    "block_type": {
                        "table": "TABLE_HTML", "equation": "EQUATION_LATEX",
                        "image": "FIGURE_CAPTION",
                    }[kind],
                    "text": content,
                    "location": location,
                })
            continue
        if kind != "text":
            continue
        value = item.get("text")
        text = value.strip() if isinstance(value, str) else ""
        if not text:
            continue
        readable_chars += len(text)
        heading = "text_level" in item
        embedded = REFERENCE_LINE.search(text) if "\n" in text and not heading else None
        if embedded is not None:
            before = text[:embedded.start()].strip()
            after = text[embedded.end():].strip()
            if before:
                blocks.append(
                    {
                        "sequence": len(blocks),
                        "page_number": _page_number(item),
                        "section": section,
                        "block_type": "TEXT",
                        "text": before,
                        "location": {"source": "mineru_content_list", "content_index": index},
                    }
                )
            in_references = True
            reference_heading_found = True
            section = embedded.group(0).strip()
            text = after
            if not text:
                continue
        if heading:
            section = text
            if REFERENCE_HEADING.fullmatch(text.strip().rstrip(":.")):
                in_references = True
                reference_heading_found = True
                continue
            if in_references:
                in_references = False
        elif REFERENCE_HEADING.fullmatch(text.strip().rstrip(":")):
            in_references = True
            reference_heading_found = True
            section = text
            continue
        elif in_references and BACK_MATTER.match(text):
            in_references = False
            section = "Back matter"
        page = _page_number(item)
        location = {"source": "mineru_content_list", "content_index": index}
        if heading:
            location["heading_level"] = item["text_level"]
        if isinstance(item.get("page_idx"), int):
            location["page_idx"] = item["page_idx"]
        if "bbox" in item:
            location["bbox"] = item["bbox"]
        if in_references:
            for part in _reference_parts(text):
                references.append(
                    {"raw_text": part, "page_number": page, "location": location}
                )
            continue
        blocks.append(
            {
                "sequence": len(blocks),
                "page_number": page,
                "section": section,
                "block_type": "HEADING" if heading else "TEXT",
                "text": text,
                "location": location,
            }
        )

    body_chars = sum(len(block["text"]) for block in blocks)
    prose_chars = sum(len(block["text"]) for block in blocks
                      if block["block_type"] in {"TEXT", "HEADING"})
    if prose_chars < 100:
        raise ValueError("MinerU returned too little readable body text for publication")
    manifest["quality"] = {
        "raw_text_chars": readable_chars,
        "body_text_chars": body_chars,
        "prose_text_chars": prose_chars,
        "body_blocks": len(blocks),
        "table_blocks": sum(block["block_type"] == "TABLE_HTML" for block in blocks),
        "equation_blocks": sum(block["block_type"] == "EQUATION_LATEX" for block in blocks),
        "figure_caption_blocks": sum(block["block_type"] == "FIGURE_CAPTION" for block in blocks),
        "body_pages": sorted(
            {block["page_number"] for block in blocks if block["page_number"] is not None}
        ),
        "reference_heading_found": reference_heading_found,
        "reference_entries": len(references),
        "page_number_basis": "one_based_from_mineru_page_idx",
    }
    if source_pdf_path is not None:
        manifest["quality"]["reference_page_alignment"] = _align_reference_pages(
            references, source_pdf_path
        )
    result["blocks"] = blocks
    result["references"] = references
    return result
