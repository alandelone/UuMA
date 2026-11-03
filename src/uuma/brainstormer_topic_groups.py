"""Display metadata for legacy topic groups inferred from object topic_id values."""

from __future__ import annotations

TOPIC_GROUP_METADATA: dict[str, dict[str, str]] = {}


def topic_group_title(topic_id: str) -> str:
    metadata = TOPIC_GROUP_METADATA.get(topic_id, {})
    return metadata.get("title") or topic_id.replace("_", " ").title()
