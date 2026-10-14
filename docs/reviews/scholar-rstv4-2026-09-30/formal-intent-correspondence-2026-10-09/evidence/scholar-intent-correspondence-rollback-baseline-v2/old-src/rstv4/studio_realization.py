"""Validate model realization without inventing prose, mappings or source identifiers."""
from __future__ import annotations

import re
from typing import Any

from .service import RSTV4Error

OUTPUT_SCHEMA = {
    "paragraph": "one nonempty string containing the entire paragraph",
    "sentences": "array of exact consecutive sentence strings covering paragraph; no omitted text",
    "sentence_mappings": [{"sentence": "zero-based integer index in sentences",
                           "thought_ids": "nonempty array of supplied stable author thought ids"}],
    "requirements": "One mapping per sentence; every author thought must appear; no invented ids.",
}


def validate(response: dict[str, Any], thought_ids: set[str], evidence_ids: set[str]) -> dict[str, Any]:
    text = response.get("paragraph") or response.get("text")
    if not isinstance(text, str) or not text.strip():
        raise RSTV4Error("Paragraph realization requires nonempty paragraph text")
    text = text.strip()
    if not set(re.findall(r"\[@([^\]]+)\]", text)).issubset(evidence_ids):
        raise RSTV4Error("Generator introduced an unselected citation")
    mappings = response.get("sentence_mappings")
    if not isinstance(mappings, list):
        raise RSTV4Error("Paragraph realization sentence_mappings must be an array of objects")
    mapped: set[str] = set()
    indices: set[int] = set()
    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise RSTV4Error("Paragraph realization sentence_mappings must contain objects")
        index = mapping.get("sentence")
        if type(index) is not int or index < 0 or index in indices:
            raise RSTV4Error("Paragraph realization sentence indices must be unique nonnegative integers")
        ids = mapping.get("thought_ids")
        if not isinstance(ids, list) or not ids or any(not isinstance(item, str) for item in ids):
            raise RSTV4Error("Paragraph realization thought_ids must be a nonempty array of strings")
        indices.add(index)
        mapped.update(ids)
    if mapped != thought_ids:
        raise RSTV4Error(
            f"Paragraph realization mapping mismatch: missing={sorted(thought_ids-mapped)}, "
            f"unknown={sorted(mapped-thought_ids)}"
        )
    sentences = response.get("sentences")
    positions = []
    if sentences is not None:
        if (not isinstance(sentences, list) or not sentences
                or any(not isinstance(item, str) or not item.strip() for item in sentences)):
            raise RSTV4Error("Paragraph realization sentences must be a nonempty array of strings")
        cursor = 0
        for sentence in sentences:
            sentence = sentence.strip()
            start = text.find(sentence, cursor)
            if start < 0 or text[cursor:start].strip():
                raise RSTV4Error("Paragraph realization sentences must exactly cover the paragraph in order")
            positions.append({"text": sentence, "start": start, "end": start + len(sentence),
                              "offset_unit": "unicode_codepoint"})
            cursor = start + len(sentence)
        if text[cursor:].strip() or indices != set(range(len(sentences))):
            raise RSTV4Error("Paragraph realization must map every actual sentence exactly once")
    # Old stored integrations did not return sentence text. Keep their mappings, explicitly
    # report unavailable positions, and never manufacture sentence boundaries or offsets.
    return {"text": text, "sentence_mappings": mappings, "sentences": positions,
            "sentence_positions_verified": sentences is not None}
