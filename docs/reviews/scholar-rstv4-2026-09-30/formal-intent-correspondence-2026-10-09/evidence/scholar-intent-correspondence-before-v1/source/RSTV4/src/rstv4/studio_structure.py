"""Author-owned paragraph containers; flat legacy paragraphs remain compatible."""

from __future__ import annotations

from typing import Any


def section_levels(sections: list[dict], key: str = "id") -> dict[str, int]:
    """Explicit parent identities, never inferred from titles or rhetorical layers."""
    levels: dict[str, int] = {}
    stack: list[str] = []
    by_id = {section[key]: section for section in sections}
    for section in sections:
        identifier = section[key]
        parent = section.get("parent_section_id")
        if parent is None:
            stack = []
        else:
            if not isinstance(parent, str) or parent not in stack:
                raise ValueError("Subsection must follow its own existing parent in reading order")
            if section.get("placement_status") != by_id[parent].get("placement_status"):
                raise ValueError("A subsection must share its parent's placement status")
            stack = stack[:stack.index(parent) + 1]
        if len(stack) > 4:
            raise ValueError("Author headings support Section through Subparagraph (five levels)")
        levels[identifier] = len(stack)
        stack.append(identifier)
    return levels


def section_end(sections: list[dict], index: int) -> int:
    members = {sections[index]["id"]}
    end = index + 1
    while end < len(sections) and sections[end].get("parent_section_id") in members:
        members.add(sections[end]["id"])
        end += 1
    return end


def section_titles(document: dict, section_id: str) -> list[str]:
    by_id = {section["id"]: section for section in document["sections"]}
    result: list[str] = []
    visited: set[str] = set()
    current = by_id[section_id]
    while current:
        if current["id"] in visited:
            raise ValueError("Author section hierarchy cannot contain cycles")
        visited.add(current["id"])
        result.insert(0, current["title"])
        current = by_id.get(current.get("parent_section_id"))
    return result


def validate_argument_relations(document: dict, seen: set[str]) -> None:
    nodes = {item["id"] for section in document["sections"]
             for paragraph in section["paragraphs"]
             for item in [paragraph, *paragraph["intents"],
                          *(t for i in paragraph["intents"] for t in i["thoughts"])]}
    relations = document.get("argument_relations", [])
    if not isinstance(relations, list):
        raise TypeError("Author argument relations must be a list")
    for relation in relations:
        if not isinstance(relation, dict):
            raise TypeError("Author argument relations must be objects")
        identifier = relation.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValueError("Every author argument relation needs a unique stable id")
        seen.add(identifier)
        source, target = relation.get("source_id"), relation.get("target_id")
        if not isinstance(source, str) or not isinstance(target, str):
            raise TypeError("Author relation endpoints must be stable block ids")
        if source not in nodes or target not in nodes or source == target:
            raise ValueError("Argument relations must join distinct blocks in this manuscript")
        if not isinstance(relation.get("relation"), str) or not relation["relation"].strip():
            raise ValueError("Describe the author's argument relation")
        if not isinstance(relation.get("condition", ""), str):
            raise TypeError("Argument relation conditions must be author text")


def argument_context(document: dict, paragraph: dict) -> list[dict]:
    """Freeze both endpoints for writing; an edge never grants scientific approval."""
    if not document.get("argument_relations"):
        return []
    nodes = {}
    local = set()
    for section in document["sections"]:
        for item in section["paragraphs"]:
            text = "\n".join([item.get("purpose", ""),
                              *(t["text"] for i in item["intents"] for t in i["thoughts"])])
            entries = [(item, "paragraph", text),
                       *((i, "intent", "\n".join([i["label"], *(t["text"] for t in i["thoughts"])]))
                         for i in item["intents"]),
                       *((t, "thought", t["text"]) for i in item["intents"] for t in i["thoughts"])]
            for node, kind, text in entries:
                nodes[node["id"]] = {"id": node["id"], "kind": kind, "author_text": text}
                if item["id"] == paragraph["id"]:
                    local.add(node["id"])
    return [{**edge, "source": nodes[edge["source_id"]], "target": nodes[edge["target_id"]],
             "origin": "AUTHOR_ARGUMENT_RELATION"}
            for edge in document.get("argument_relations", [])
            if edge["source_id"] in local or edge["target_id"] in local]


def validate_groups(document: dict[str, Any], seen: set[str]) -> None:
    for section in document["sections"]:
        if "paragraph_groups" not in section and "block_order" not in section:
            continue
        groups = section.get("paragraph_groups", [])
        order = section.get("block_order")
        if not isinstance(groups, list) or not isinstance(order, list):
            raise TypeError("Paragraph groups require an explicit ordered container list")
        paragraphs = {item["id"] for item in section["paragraphs"]}
        grouped: set[str] = set()
        group_ids: set[str] = set()
        for group in groups:
            if not isinstance(group, dict):
                raise TypeError("Paragraph groups must be objects")
            group_id = group.get("id")
            if not isinstance(group_id, str) or not group_id or group_id in seen:
                raise ValueError("Every paragraph group needs a unique stable id")
            seen.add(group_id)
            group_ids.add(group_id)
            if not isinstance(group.get("label"), str):
                raise TypeError("Paragraph group labels must be author text")
            members = group.get("paragraph_ids")
            if not isinstance(members, list) or any(not isinstance(item, str) for item in members):
                raise TypeError("Paragraph group members must be stable paragraph ids")
            if (
                len(set(members)) != len(members)
                or not set(members).issubset(paragraphs)
                or grouped.intersection(members)
            ):
                raise ValueError(
                    "Paragraphs must belong to exactly one container in their own section"
                )
            grouped.update(members)
        if any(not isinstance(item, str) for item in order) or len(set(order)) != len(order):
            raise ValueError("Structure order must contain unique stable ids")
        if set(order) != group_ids | (paragraphs - grouped):
            raise ValueError("Every paragraph or group must appear once in its section order")
        by_id = {item["id"]: item for item in groups}
        flattened = [
            paragraph_id
            for identifier in order
            for paragraph_id in (
                by_id[identifier]["paragraph_ids"] if identifier in by_id else [identifier]
            )
        ]
        if flattened != [item["id"] for item in section["paragraphs"]]:
            raise ValueError("Author reading order must match the explicit container order")


def paragraph_group(section: dict[str, Any], paragraph_id: str) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in section.get("paragraph_groups", [])
            if paragraph_id in item["paragraph_ids"]
        ),
        None,
    )
