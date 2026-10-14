"""Author-reviewed, version-bound Studio suggestions; never executable agent code."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import new_id
from .studio_context import exact_quote

MODEL_FORMAT = {
    "suggestions": [
        {
            "kind": "STRUCTURE | SOURCE | WORDING",
            "title": "short description",
            "rationale": "why this suggestion follows the original object",
            "changes": [
                {
                    "action": "SET_FIELD | INSERT_INTENT | INSERT_PARAGRAPH | ADD_SOURCE | REPLACE_TEXT",
                    "target_type": "paper | section | paragraph_group | paragraph | intent | thought",
                    "target_id": "an actual id from the supplied author document",
                    "field": "SET_FIELD: role/purpose/paradigm/label; REPLACE_TEXT: text/title/abstract",
                    "value": "SET_FIELD value or REPLACE_TEXT replacement",
                    "quote": {
                        "text": "REPLACE_TEXT original selection",
                        "start": 0,
                        "end": 4,
                        "offset_unit": "utf16",
                    },
                    "evidence_id": "ADD_SOURCE: a supplied source id",
                    "label": "INSERT_INTENT: a structural label, without author text",
                    "purpose": "INSERT_PARAGRAPH: structural purpose",
                    "paradigm": "INSERT_PARAGRAPH: organization pattern",
                    "intent_labels": ["INSERT_PARAGRAPH: structural labels, no author thoughts"],
                }
            ],
        }
    ],
}

FIELDS = {
    "STRUCTURE": {"section": {"role"}, "paragraph_group": {"label"}, "paragraph": {"purpose", "paradigm"}, "intent": {"label"}},
    "WORDING": {"thought": {"text"}, "paper": {"title", "abstract"}, "section": {"title"}},
}
CHANGE_FIELDS = {
    "SET_FIELD": {"field", "value"},
    "REPLACE_TEXT": {"field", "value", "quote"},
    "ADD_SOURCE": {"evidence_id"},
    "INSERT_INTENT": {"label"},
    "INSERT_PARAGRAPH": {"purpose", "paradigm", "intent_labels"},
}


def target(
    document: dict[str, Any], kind: str, object_id: str | None
) -> tuple[dict[str, Any], str]:
    if kind == "paper" and object_id in {None, document["manuscript_id"]}:
        return document, document["title"]
    for section in document["sections"]:
        if kind == "section" and section["id"] == object_id:
            return section, section["title"]
        for group in section.get("paragraph_groups", []):
            if kind == "paragraph_group" and group["id"] == object_id:
                return group, f"{section['title']} / {group['label'] or '未定段落组'}"
        for paragraph in section["paragraphs"]:
            if kind == "paragraph" and paragraph["id"] == object_id:
                return paragraph, f"{section['title']} / {paragraph.get('purpose') or '段落'}"
            for intent in paragraph["intents"]:
                if kind == "intent" and intent["id"] == object_id:
                    return intent, intent["label"] or "未定 Intent"
                for thought in intent["thoughts"]:
                    if kind == "thought" and thought["id"] == object_id:
                        return thought, f"{intent['label']} / {thought['text'][:60]}"
    raise ValueError("The suggestion target does not exist in this author revision")


def text(value: Any, name: str, *, empty: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    if len(value) > 24000 or (not empty and not value.strip()):
        raise ValueError(f"{name} is empty or too long")
    return value


def normalize(
    raw: Any,
    document: dict[str, Any] | None,
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise TypeError("Suggestions must be a list")
    if len(raw) > 50:
        raise ValueError("Too many independent suggestions in one response")
    sources = {item["evidence_id"]: item for item in evidence}
    result = []
    for proposal in raw:
        if not isinstance(proposal, dict) or proposal.get("kind") not in {
            "STRUCTURE",
            "SOURCE",
            "WORDING",
        }:
            raise ValueError("Unknown Studio suggestion category")
        if document is None:
            raise ValueError("This historical version has no proven author structure for adoption")
        kind = proposal["kind"]
        changes = proposal.get("changes")
        if not isinstance(changes, list) or not 1 <= len(changes) <= 100:
            raise ValueError("A suggestion needs explicit independent changes")
        normalized = []
        ranges: dict[tuple[str, str], list[tuple[int, int]]] = {}
        unique = set()
        for raw_change in changes:
            if not isinstance(raw_change, dict):
                raise TypeError("Suggestion changes must be objects")
            target_type = raw_change.get("target_type")
            target_id = raw_change.get("target_id")
            if not isinstance(target_type, str) or not isinstance(target_id, (str, type(None))):
                raise TypeError("Suggestion targets require a type and stable id")
            action = raw_change.get("action")
            if not isinstance(action, str) or action not in CHANGE_FIELDS:
                raise ValueError("Unknown suggestion action")
            if raw_change.keys() - ({"action", "target_type", "target_id"} | CHANGE_FIELDS[action]):
                raise ValueError("A suggestion contains undeclared author changes")
            original, label = target(document, target_type, target_id)
            if target_type == "paper":
                target_id = document["manuscript_id"]
            item = {
                "change_id": new_id("suggestion_change"),
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "target_label": label,
            }
            if kind in {"STRUCTURE", "WORDING"} and action in {"SET_FIELD", "REPLACE_TEXT"}:
                expected = "SET_FIELD" if kind == "STRUCTURE" else "REPLACE_TEXT"
                field = raw_change.get("field")
                if action != expected or field not in FIELDS[kind].get(target_type, set()):
                    raise ValueError("The suggestion cannot change this author field")
                before = text(original.get(field, ""), "Original field", empty=True)
                value = text(raw_change.get("value"), "Suggested value", empty=True)
                item.update(field=field, before=before, value=value)
                if action == "REPLACE_TEXT":
                    quote = exact_quote(before, raw_change.get("quote"))
                    if not quote.get("text"):
                        raise ValueError("Wording changes require the exact original range")
                    key = (target_id, field)
                    pairs = ranges.setdefault(key, [])
                    if any(quote["start"] < end and quote["end"] > start for start, end in pairs):
                        raise ValueError("Wording changes cannot overlap")
                    pairs.append((quote["start"], quote["end"]))
                    item["quote"] = quote
                    signature = (action, target_id, field, quote["start"], quote["end"])
                else:
                    signature = (action, target_id, field)
            elif kind == "SOURCE" and action == "ADD_SOURCE" and target_type == "thought":
                evidence_id = raw_change.get("evidence_id")
                if evidence_id not in sources:
                    raise ValueError("Source suggestions can only use supplied real Evidence")
                item.update(evidence=deepcopy(sources[evidence_id]), before=original["text"])
                signature = (action, target_id, evidence_id)
            elif kind == "STRUCTURE" and action == "INSERT_INTENT" and target_type == "paragraph":
                if raw_change.get("thoughts"):
                    raise ValueError("Structure suggestions cannot invent author thoughts")
                item.update(
                    before=[value["id"] for value in original["intents"]],
                    value={
                        "id": new_id("intent"),
                        "label": text(raw_change.get("label"), "Intent label"),
                        "thoughts": [],
                    },
                )
                signature = (action, target_id, item["value"]["label"])
            elif kind == "STRUCTURE" and action == "INSERT_PARAGRAPH" and target_type in {"section", "paragraph_group"}:
                labels = raw_change.get("intent_labels", [])
                if not isinstance(labels, list) or len(labels) > 100 or raw_change.get("thoughts"):
                    raise ValueError("Paragraph structure requires empty author slots")
                value = {
                    "id": new_id("paragraph"),
                    "purpose": text(raw_change.get("purpose", ""), "Paragraph purpose", empty=True),
                    "paradigm": text(
                        raw_change.get("paradigm", ""), "Paragraph paradigm", empty=True
                    ),
                    "intents": [
                        {
                            "id": new_id("intent"),
                            "label": text(label, "Intent label"),
                            "thoughts": [],
                        }
                        for label in labels
                    ],
                    "asset_ids": [],
                    "formulas": [],
                }
                before = original["paragraph_ids"] if target_type == "paragraph_group" else [item["id"] for item in original["paragraphs"]]
                item.update(before=deepcopy(before), value=value)
                signature = (action, target_id, value["purpose"], value["paradigm"], tuple(labels))
            else:
                raise ValueError("Suggestion action does not match its category or target")
            if signature in unique:
                raise ValueError("A suggestion contains duplicate changes")
            unique.add(signature)
            normalized.append(item)
        result.append(
            {
                "suggestion_id": new_id("suggestion"),
                "kind": kind,
                "title": text(proposal.get("title"), "Suggestion title"),
                "rationale": text(proposal.get("rationale"), "Suggestion rationale"),
                "changes": normalized,
            }
        )
    return result


def preview_change(document: dict[str, Any], change: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(change)
    try:
        current, label = target(document, change["target_type"], change["target_id"])
    except ValueError:
        return {**item, "available": False, "target_changed": True, "current_before": None}
    action = change["action"]
    if action in {"SET_FIELD", "REPLACE_TEXT"}:
        before = current.get(change["field"], "")
    elif action == "ADD_SOURCE":
        before = current["text"]
    else:
        before = current["paragraph_ids"] if change["target_type"] == "paragraph_group" else [
            value["id"]
            for value in current["intents" if action == "INSERT_INTENT" else "paragraphs"]
        ]
    item.update(
        available=True,
        current_label=label,
        current_before=deepcopy(before),
        target_changed=before != change["before"],
    )
    if action == "REPLACE_TEXT":
        try:
            exact_quote(before, change["quote"])
            encoded = before.encode("utf-16-le")
            quote = change["quote"]
            item["after_preview"] = (
                encoded[: quote["start"] * 2]
                + change["value"].encode("utf-16-le")
                + encoded[quote["end"] * 2 :]
            ).decode("utf-16-le")
        except ValueError:
            item["available"] = False
            item["range_changed"] = True
    elif action == "SET_FIELD":
        item["after_preview"] = change["value"]
    return item


def apply(
    document: dict[str, Any], changes: list[dict[str, Any]], confirmed: set[str]
) -> dict[str, Any]:
    result = deepcopy(document)
    # Validate all against the same pre-edit revision before applying any change.
    previews = [preview_change(document, change) for change in changes]
    for item in previews:
        if not item["available"]:
            raise ValueError(
                "An original target or quotation is unavailable; request a new anchored suggestion"
            )
        if item["target_changed"] and item["change_id"] not in confirmed:
            raise ValueError("The author must compare and confirm the changed target")
    ordered = sorted(changes, key=lambda item: item.get("quote", {}).get("start", -1), reverse=True)
    for item in ordered:
        current, _ = target(result, item["target_type"], item["target_id"])
        action = item["action"]
        if action == "SET_FIELD":
            current[item["field"]] = item["value"]
        elif action == "REPLACE_TEXT":
            encoded = current[item["field"]].encode("utf-16-le")
            quote = item["quote"]
            current[item["field"]] = (
                encoded[: quote["start"] * 2]
                + item["value"].encode("utf-16-le")
                + encoded[quote["end"] * 2 :]
            ).decode("utf-16-le")
        elif action == "ADD_SOURCE":
            evidence = item["evidence"]
            if not any(
                value["evidence_id"] == evidence["evidence_id"] for value in current["citations"]
            ):
                current["citations"].append(
                    {
                        "evidence_id": evidence["evidence_id"],
                        "selected": False,
                        "statement": evidence["statement"],
                        "title": evidence.get("title"),
                    }
                )
                current["citation_mode"] = "PENDING"
        elif action == "INSERT_INTENT":
            current["intents" if action == "INSERT_INTENT" else "paragraphs"].append(
                deepcopy(item["value"])
            )
        else:
            value = deepcopy(item["value"])
            if item["target_type"] == "paragraph_group":
                owner = next(section for section in result["sections"] if any(group["id"] == current["id"] for group in section.get("paragraph_groups", [])))
                current["paragraph_ids"].append(value["id"])
                owner["paragraphs"].append(value)
                paragraphs = {paragraph["id"]: paragraph for paragraph in owner["paragraphs"]}
                groups = {group["id"]: group for group in owner["paragraph_groups"]}
                owner["paragraphs"] = [paragraphs[identifier] for block_id in owner["block_order"] for identifier in (groups[block_id]["paragraph_ids"] if block_id in groups else [block_id])]
            else:
                current["paragraphs"].append(value)
                if "block_order" in current:
                    current["block_order"].append(value["id"])
    return result
