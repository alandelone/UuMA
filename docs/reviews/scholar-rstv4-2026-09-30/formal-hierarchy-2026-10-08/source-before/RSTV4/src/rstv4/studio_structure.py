"""Author-owned paragraph containers; flat legacy paragraphs remain compatible."""

from __future__ import annotations

from typing import Any


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
