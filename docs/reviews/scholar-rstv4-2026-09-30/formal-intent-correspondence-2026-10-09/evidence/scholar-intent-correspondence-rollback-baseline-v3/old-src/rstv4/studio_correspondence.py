"""Explicit author-to-template references; canonical author content is never moved."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .studio_structure import paragraph_group, section_titles


def intent_index(document: dict) -> dict[str, tuple[dict, dict, dict]]:
    return {intent["id"]: (section, paragraph, intent)
            for section in document["sections"] for paragraph in section["paragraphs"]
            for intent in paragraph["intents"]}


def _references(item: dict, key: str) -> list[str]:
    refs = item.get(key, [])
    if (not isinstance(refs, list) or any(not isinstance(ref, str) or not ref for ref in refs)
            or len(refs) != len(set(refs))):
        raise ValueError(f"{key} requires distinct author block identities")
    return refs


def validate(document: dict) -> tuple[dict[str, str], dict[str, str]]:
    """One Intent destination and one explicit attachment output per original paragraph."""
    index = intent_index(document)
    paragraphs = {paragraph["id"]: (section, paragraph)
                  for section in document["sections"] for paragraph in section["paragraphs"]}
    owners: dict[str, str] = {}
    contexts: dict[str, str] = {}
    for target_id, (section, paragraph, target) in index.items():
        refs = _references(target, "author_intent_ids")
        if refs:
            source = target.get("template_source") or paragraph.get("template_source", {})
            if (section.get("placement_status") == "UNPLACED"
                    or not isinstance(source, dict)
                    or not isinstance(source.get("skeleton_id"), str)
                    or not source.get("skeleton_id")
                    or not isinstance(source.get("source_sha256"), str)
                    or not source.get("source_sha256")):
                raise ValueError("Author correspondence requires a placed fixed template Intent")
        for ref in refs:
            original = index.get(ref)
            if (original is None or original[0].get("placement_status") != "UNPLACED"
                    or not original[2].get("thoughts") or ref in owners or ref == target_id):
                raise ValueError("Original author Intent is unavailable or already corresponds")
            owners[ref] = target_id
    for target_id, (section, target) in paragraphs.items():
        for ref in _references(target, "author_context_paragraph_ids"):
            original = paragraphs.get(ref)
            if (original is None or original[0].get("placement_status") != "UNPLACED"
                    or section.get("placement_status") == "UNPLACED" or ref in contexts
                    or not any(source["id"] in owners and
                               index[owners[source["id"]]][1]["id"] == target_id
                               for source in original[1]["intents"])):
                raise ValueError("Original paragraph context needs one corresponding output position")
            contexts[ref] = target_id
    return owners, contexts


def effective_thoughts(document: dict, intent: dict) -> list[dict]:
    index = intent_index(document)
    return [*intent["thoughts"], *(thought for ref in intent.get("author_intent_ids", [])
                                 for thought in index[ref][2]["thoughts"])]


def unresolved(document: dict) -> list[dict[str, str]]:
    owners, contexts = validate(document)
    issues = []
    for section in document["sections"]:
        if section.get("placement_status") != "UNPLACED":
            continue
        if not section["paragraphs"] and not any(
            child.get("parent_section_id") == section["id"] for child in document["sections"]
        ):
            issues.append({"path": section["id"], "message": "Original author section remains unplaced"})
        for group in section.get("paragraph_groups", []):
            if not group["paragraph_ids"] or not group["label"].strip():
                issues.append({"path": group["id"], "message": "Original author group remains unresolved"})
        for paragraph in section["paragraphs"]:
            if not paragraph["intents"]:
                issues.append({"path": paragraph["id"], "message": "Original paragraph remains unplaced"})
            for intent in paragraph["intents"]:
                if intent["id"] not in owners:
                    issues.append({"path": intent["id"], "message": "Original author Intent remains unplaced"})
            if ((paragraph.get("asset_ids") or paragraph.get("formulas"))
                    and paragraph["id"] not in contexts):
                issues.append({"path": paragraph["id"],
                               "message": "Original formulas or attachments have no explicit output position"})
    return issues


def has_correspondence(document: dict) -> bool:
    return any(intent.get("author_intent_ids") for section in document["sections"]
               for paragraph in section["paragraphs"] for intent in paragraph["intents"])


def validate_origins(conn: Any, manuscript_id: str, document: dict) -> None:
    """References must use actual source-checked adopted slots in this author's history."""
    import json

    owners, _ = validate(document)
    if not owners:
        return
    frozen = {}
    for row in conn.execute(
        """SELECT operation.payload_json FROM studio_template_instances AS instance
           JOIN studio_operations AS operation
             ON operation.operation_id=json_extract(instance.adopted_json,'$.operation_id')
           WHERE instance.manuscript_id=? AND operation.manuscript_id=?
             AND operation.operation_kind='ADOPT_TEMPLATE'""", (manuscript_id, manuscript_id),
    ):
        adopted = json.loads(row["payload_json"])["document"]
        for identifier, (_, paragraph, intent) in intent_index(adopted).items():
            source = intent.get("template_source") or paragraph.get("template_source")
            if source:
                frozen.setdefault(identifier, []).append(source)
    index = intent_index(document)
    for identifier in set(owners.values()):
        _, paragraph, intent = index[identifier]
        source = intent.get("template_source") or paragraph.get("template_source")
        if source not in frozen.get(identifier, []):
            raise ValueError("Correspondence target has no matching source-checked adoption history")


def realization_document(document: dict) -> dict:
    """A reversible projection. Unresolved originals must be gated by the caller."""
    validate(document)
    if not has_correspondence(document):
        return deepcopy(document)
    result = deepcopy(document)
    result["sections"] = [section for section in result["sections"]
                          if section.get("placement_status") != "UNPLACED"]
    result["author_source_sections"] = deepcopy([
        section for section in document["sections"] if section.get("placement_status") == "UNPLACED"
    ])
    index = intent_index(document)
    paragraphs = {paragraph["id"]: paragraph for section in document["sections"]
                  for paragraph in section["paragraphs"]}
    for section in result["sections"]:
        for paragraph in section["paragraphs"]:
            author_contexts: list[dict[str, Any]] = []
            for intent in paragraph["intents"]:
                for ref in intent.get("author_intent_ids", []):
                    old_section, old_paragraph, old_intent = index[ref]
                    intent["thoughts"].extend(deepcopy(old_intent["thoughts"]))
                    author_contexts.append({
                        "author_intent_id": ref, "template_intent_id": intent["id"],
                        "source_section": {key: deepcopy(value) for key, value in old_section.items()
                                           if key not in {"paragraphs", "paragraph_groups", "block_order"}},
                        "source_section_path": section_titles(document, old_section["id"]),
                        "source_paragraph": deepcopy(old_paragraph),
                        "source_group": deepcopy(paragraph_group(old_section, old_paragraph["id"])),
                        "template_source": deepcopy(intent.get("template_source") or paragraph["template_source"]),
                    })
            if author_contexts:
                paragraph["author_contexts"] = author_contexts
            for ref in paragraph.get("author_context_paragraph_ids", []):
                source = paragraphs[ref]
                paragraph["asset_ids"] = list(dict.fromkeys([
                    *paragraph.get("asset_ids", []), *source.get("asset_ids", [])
                ]))
                if source.get("formulas"):
                    paragraph.setdefault("formulas", []).extend(deepcopy(source["formulas"]))
    return result


def release_unplaced(document: dict) -> dict:
    """Template replacement releases references back to intact original author blocks."""
    for section in document["sections"]:
        if section.get("placement_status") == "UNPLACED":
            for paragraph in section["paragraphs"]:
                paragraph.pop("author_context_paragraph_ids", None)
                for intent in paragraph["intents"]:
                    intent.pop("author_intent_ids", None)
    return document
