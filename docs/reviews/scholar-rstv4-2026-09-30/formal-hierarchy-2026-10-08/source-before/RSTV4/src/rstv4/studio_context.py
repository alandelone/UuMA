"""Version-bound, read-only writing context and exact author quotations."""

from __future__ import annotations

import hashlib
import re
from typing import Any


def citation_ids(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\[@([^\]]+)\]", text)))


def numbered_text(text: str, references: list[dict[str, Any]]) -> str:
    indices = {item["evidence_id"]: item["citation_index"] for item in references}
    return re.sub(
        r"\[@([^\]]+)\]",
        lambda match: f"[{indices[match[1]]}]" if match[1] in indices else match[0],
        text,
    )


def legacy_bibliography(raw: str) -> dict[str, dict[str, Any]]:
    """Read the existing compiler's braced BibTeX without substituting live metadata."""
    unescape = {
        r"\textbackslash{}": "\\", r"\&": "&", r"\%": "%", r"\$": "$",
        r"\#": "#", r"\_": "_", r"\{": "{", r"\}": "}",
        r"\textasciitilde{}": "~", r"\textasciicircum{}": "^",
    }

    def decoded(value: str) -> str:
        return re.sub(
            "|".join(re.escape(key) for key in unescape),
            lambda match: unescape[match[0]], value,
        )

    results = {}
    for entry in re.finditer(r"(?m)^@article\{([^,\n]+),\s*", raw):
        position = entry.end()
        fields = {}
        while position < len(raw):
            while position < len(raw) and raw[position] in " \r\n\t,":
                position += 1
            if position >= len(raw) or raw[position] == "}":
                break
            field = re.compile(r"(\w+)\s*=\s*\{").match(raw, position)
            if not field:
                raise ValueError("Historical bibliography has an unsupported field")
            start = position = field.end()
            depth = 1
            while position < len(raw) and depth:
                if raw[position] == "\\":
                    position += 2
                    continue
                if raw[position] == "{":
                    depth += 1
                elif raw[position] == "}":
                    depth -= 1
                position += 1
            if depth:
                raise ValueError("Historical bibliography has an incomplete field")
            fields[field[1]] = decoded(raw[start:position - 1])
        year = fields.get("year", "")
        results[entry[1]] = {
            "evidence_id": entry[1], "title": fields.get("title"),
            "authors": [fields["author"]] if fields.get("author") else [],
            "published_year": int(year) if year.isdigit() else None,
            "year_label": year, "doi": fields.get("doi"),
            "reference_snapshot_source": "verified_bib_artifact",
        }
    return results


def generated_view(
    version: dict[str, Any],
    generated: dict[str, Any] | None,
    references: list[dict[str, Any]],
) -> dict[str, Any]:
    version_id = version["manuscript_version_id"]
    blocks: list[dict[str, Any]] = []
    realizations: list[dict[str, Any]] = []

    def block(kind: str, object_id: str, text: str, label: str, **extra: Any) -> None:
        blocks.append({
            "kind": kind,
            "object_id": object_id,
            "anchor_id": f"{version_id}:{object_id}",
            "text": text,
            "display_text": numbered_text(text, references),
            "label": label,
            **extra,
        })

    if generated:
        block("title", "title", generated["title"], generated["title"])
        if generated.get("abstract"):
            block("heading", "abstract-heading", "Abstract", "Abstract")
            block("paragraph", "abstract", generated["abstract"], "Abstract")
        for section in generated["sections"]:
            block("heading", section["section_id"], section["title"], section["title"])
            for index, paragraph in enumerate(section["paragraphs"], 1):
                block(
                    "paragraph", paragraph["paragraph_id"], paragraph["text"],
                    f"{section['title']} / 段落 {index}",
                    section_id=section["section_id"], thought_ids=paragraph.get("thought_ids", []),
                    formulas=paragraph.get("formulas", []),
                    **({"group_id": paragraph["group_id"]} if paragraph.get("group_id") else {}),
                )
                if "model_call_id" in paragraph:
                    realizations.append({"paragraph_id": paragraph["paragraph_id"],
                        **{key: paragraph[key] for key in ["sentence_mappings", "sentences",
                           "sentence_positions_verified", "model_contract", "model_call_id"]
                           if key in paragraph}})
    else:
        # Legacy prose has no author-structure mapping. A position is stable only
        # inside this immutable version; never infer a current editor object.
        for index, text in enumerate(re.split(r"\n\n+", version["content"].strip())):
            if not text:
                continue
            kind = "title" if text.startswith("# ") else "heading" if text.startswith("## ") else "paragraph"
            visible = text[2:] if kind == "title" else text[3:] if kind == "heading" else text
            block(kind, f"legacy-block-{index}", visible, f"成文区块 {index + 1}")
    return {
        "manuscript_id": version["manuscript_id"],
        "generated_version_id": version_id,
        "version": version["version"],
        "content": version["content"],
        "input_revision": generated.get("input_revision") if generated else None,
        "structure_mapping_available": generated is not None,
        "blocks": blocks,
        **({"realizations": realizations} if realizations else {}),
        "references": references,
        "citation_style": generated.get("citation_style", "legacy") if generated else "legacy",
    }


def structure_object(
    document: dict[str, Any], anchor_type: str, anchor_id: str | None,
) -> tuple[str, str]:
    def paragraph_text(paragraph: dict[str, Any]) -> str:
        return "\n".join(
            thought["text"]
            for intent in paragraph["intents"]
            for thought in intent["thoughts"]
        )

    if anchor_type == "paper" and anchor_id in {None, document["manuscript_id"]}:
        return document["title"], "\n".join([
            document["title"], document.get("abstract", ""),
            *(paragraph_text(paragraph) for section in document["sections"] for paragraph in section["paragraphs"]),
        ])
    for section in document["sections"]:
        if anchor_type == "section" and anchor_id == section["id"]:
            return section["title"], "\n".join([section["title"], *(paragraph_text(item) for item in section["paragraphs"])])
        for group in section.get("paragraph_groups", []):
            if anchor_type == "paragraph_group" and anchor_id == group["id"]:
                by_id = {item["id"]: item for item in section["paragraphs"]}
                return f"{section['title']} / {group['label'] or '未定段落组'}", "\n".join(paragraph_text(by_id[item]) for item in group["paragraph_ids"])
        for paragraph in section["paragraphs"]:
            if anchor_type == "paragraph" and anchor_id == paragraph["id"]:
                return f"{section['title']} / {paragraph.get('purpose') or '段落'}", paragraph_text(paragraph)
            for intent in paragraph["intents"]:
                if anchor_type == "intent" and anchor_id == intent["id"]:
                    return intent["label"], "\n".join(item["text"] for item in intent["thoughts"])
                for thought in intent["thoughts"]:
                    if anchor_type == "thought" and anchor_id == thought["id"]:
                        return f"{intent['label']} / 思想", thought["text"]
    raise ValueError("The object does not exist in the requested manuscript revision")


def exact_quote(text: str, quote: dict[str, Any] | None) -> dict[str, Any]:
    supplied = quote or {}
    annotation = supplied.get("annotation", "")
    if not isinstance(annotation, str):
        raise TypeError("Annotation must be text")
    selected = supplied.get("text", "")
    if not isinstance(selected, str):
        raise TypeError("Quotation must be text")
    result: dict[str, Any] = {"annotation": annotation}
    if selected:
        start, end = supplied.get("start"), supplied.get("end")
        if (
            type(start) is not int or type(end) is not int
            or start < 0 or end <= start or supplied.get("offset_unit") != "utf16"
        ):
            raise ValueError("Quotation requires an exact UTF-16 start and end")
        encoded = text.encode("utf-16-le")
        if end * 2 > len(encoded):
            raise ValueError("Quotation is outside the original object")
        try:
            original = encoded[start * 2:end * 2].decode("utf-16-le")
        except UnicodeDecodeError as exc:
            raise ValueError("Quotation splits an original character") from exc
        if original != selected:
            raise ValueError("Quotation does not match the original object and version")
        result.update(text=selected, start=start, end=end, offset_unit="utf16")
    elif any(key in supplied for key in ("start", "end")):
        raise ValueError("An empty quotation cannot have a range")
    return result


def bound_quote(
    *, manuscript_id: str, anchor_type: str, anchor_id: str | None,
    anchor_revision: int, label: str, text: str, raw_text: str,
    quote: dict[str, Any] | None, generated_version_id: str | None = None,
) -> dict[str, Any]:
    return {
        **exact_quote(text, quote),
        "source": {
            "manuscript_id": manuscript_id,
            "anchor_type": anchor_type,
            "anchor_id": anchor_id,
            "anchor_revision": anchor_revision,
            "generated_version_id": generated_version_id,
            "label": label,
            "content_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        },
        "object_text": text,
        "raw_object_text": raw_text,
    }
