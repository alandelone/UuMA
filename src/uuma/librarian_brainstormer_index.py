"""Derive a minimal provenance-preserving index from an owner snapshot.

This index never represents a topic, checkpoint or proposal as a decision. The
original Brainstormer state and conversation remain separate recovery sources.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from typing import Any

IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}\Z")
TOPIC_STATUSES = {"ACTIVE", "PAUSED", "ARCHIVED", "CLOSED"}


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate source state key")
        result[key] = value
    return result


def topic_index(snapshot: bytes, *, project_id: str, topic_id: str,
                captured_at: datetime, readers: list[str]) -> dict[str, Any]:
    """Create a non-original, non-secret structural index for one existing topic.

    The caller must obtain an owner-consistent snapshot and establish reader grants.
    The index includes only IDs, normalized statuses, counts and source revision;
    arbitrary source titles, prompt text, credentials and tool output are excluded.
    """
    if (not isinstance(project_id, str) or not IDENTITY.fullmatch(project_id)
            or not isinstance(topic_id, str) or not IDENTITY.fullmatch(topic_id)
            or len("brainstormer-topic-index:" + topic_id) > 160
            or not isinstance(readers, list) or not readers or len(set(readers)) != len(readers)
            or any(not isinstance(reader, str) or not IDENTITY.fullmatch(reader) for reader in readers)):
        raise ValueError("Invalid project, topic or explicit reader identities")
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("Capture time must have an explicit timezone")
    state = json.loads(snapshot, object_pairs_hook=_unique)
    if (not isinstance(state, dict) or state.get("project_id") != project_id
            or type(state.get("revision")) is not int or state["revision"] < 1
            or not isinstance(state.get("objects"), dict)):
        raise ValueError("Expected existing project state with a real revision")
    objects = state["objects"]
    topic = objects.get(topic_id)
    if not isinstance(topic, dict) or topic.get("id") != topic_id or topic.get("kind") != "topic":
        raise ValueError("The selected topic is not present in the source snapshot")
    status = topic.get("status")
    if status not in TOPIC_STATUSES:
        raise ValueError("Topic status is not recognized by the index adapter")
    updated_at = state.get("updated_at")
    if updated_at is not None:
        if not isinstance(updated_at, str):
            raise TypeError("Source update time must be an ISO timestamp")
        try:
            datetime.fromisoformat(updated_at)
        except ValueError:
            raise ValueError("Source update time must be an ISO timestamp") from None
    allowed_kinds = {"topic", "question", "assumption", "evidence", "checkpoint", "decision"}
    selected = [obj for obj in objects.values() if isinstance(obj, dict)
                and (obj.get("id") == topic_id or obj.get("topic_id") == topic_id)]
    counts = Counter(obj.get("kind") for obj in selected if obj.get("kind") in allowed_kinds)
    body = {
        "record_type": "brainstormer-topic-structural-index",
        "project_id": project_id, "topic_id": topic_id, "source_revision": state["revision"],
        "topic_status": status, "object_counts": {name: counts[name] for name in sorted(allowed_kinds)},
        "note": "Counts do not imply that a proposal or decision was accepted.",
    }
    content = json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(content).hexdigest()
    source_digest = hashlib.sha256(snapshot).hexdigest()
    source_ref = f"brainstormer:project:{project_id}:revision:{state['revision']}"
    record = {
        "record_id": "brainstormer-topic-index:" + topic_id,
        "version_id": "r" + str(state["revision"]) + ":" + source_digest[:24],
        "source_id": "brainstormer-index", "readers": readers, "project_ids": [project_id],
        "kind": "structural-index", "title": "Brainstormer topic structural index",
        "original_status": status, "original_ref": source_ref,
        "captured_at": captured_at.isoformat(), "is_summary": True,
        "derived_from": [source_ref], "content_sha256": digest,
        "content_bytes": len(content), "media_type": "application/json",
    }
    return {"record": record, "content": content, "source_sha256": source_digest,
            "source_updated_at": updated_at}
