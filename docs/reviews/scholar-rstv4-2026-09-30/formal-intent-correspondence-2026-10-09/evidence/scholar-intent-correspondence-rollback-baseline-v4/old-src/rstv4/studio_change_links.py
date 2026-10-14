"""Author-assigned relationships, append-only link history and immutable edit context."""
from __future__ import annotations

import difflib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .database import transaction
from .models import new_id
from .service import NotFoundError, RevisionConflictError


def encoded(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def current_ids(conn: Any, change_id: str) -> list[str]:
    return sorted(row[0] for row in conn.execute(
        "SELECT comment_id FROM comment_changes WHERE change_id=?", (change_id,)
    ))


def record_initial(conn: Any, change_id: str, comment_ids: list[str], *, origin: str, timestamp: str) -> None:
    conn.execute("INSERT OR IGNORE INTO studio_change_link_state VALUES(?,?,?,?,?)",
                 (change_id, encoded(sorted(set(comment_ids))), origin, 0, timestamp))


def original_ids(conn: Any, operation: Any) -> set[str]:
    payload = json.loads(operation["payload_json"])
    if "comment_ids" in payload:
        return set(payload["comment_ids"])
    change = conn.execute("SELECT change_id FROM studio_changes WHERE operation_id=?",
                          (operation["operation_id"],)).fetchone()
    if change is None:
        return set()
    state = conn.execute("SELECT initial_comment_ids_json FROM studio_change_link_state WHERE change_id=?",
                         (change[0],)).fetchone()
    return set(json.loads(state[0]) if state else current_ids(conn, change[0]))


def author_lines(document: dict[str, Any]) -> list[str]:
    """Readable exact author structure, including grouping, order, sources and attachments."""
    lines = [f"标题：{document.get('title', '')}", f"摘要：{document.get('abstract', '')}"]
    for s, section in enumerate(document.get("sections", []), 1):
        lines.append(f"章节 {s}：{section.get('title', '')} · {section.get('role', '')}")
        for group in section.get("paragraph_groups", []):
            members = [str(i + 1) for i, p in enumerate(section.get("paragraphs", [])) if p["id"] in group["paragraph_ids"]]
            lines.append(f"段落组：{group.get('label', '')} · 包含段落 {', '.join(members)}")
        for p, paragraph in enumerate(section.get("paragraphs", []), 1):
            lines.append(f"段落 {s}.{p} · 目的：{paragraph.get('purpose', '')} · 写法：{paragraph.get('paradigm', '')}")
            for intent in paragraph.get("intents", []):
                lines.append(f"意图：{intent.get('label', '')}")
                for thought in intent.get("thoughts", []):
                    lines.append(f"想法：{thought.get('text', '')}")
                    lines.append(f"引用决定：{thought.get('citation_mode', '')} {encoded(thought.get('citations', []))}")
            for formula in paragraph.get("formulas", []):
                lines.append(f"公式：{formula.get('latex', '')} · {formula.get('caption', '')}")
            if paragraph.get("asset_ids"):
                lines.append(f"图表文件：{', '.join(paragraph['asset_ids'])}")
    return lines


def event_view(row: Any) -> dict[str, Any]:
    item = dict(row)
    for field in ["before_comment_ids_json", "after_comment_ids_json", "request_json"]:
        item[field[:-5]] = json.loads(item.pop(field))
    return item


def change_view(conn: Any, row: Any) -> dict[str, Any]:
    item = dict(row)
    state = conn.execute("SELECT * FROM studio_change_link_state WHERE change_id=?", (row["change_id"],)).fetchone()
    item.update(comment_ids=current_ids(conn, row["change_id"]),
                association_revision=state["link_revision"] if state else 0,
                initial_comment_ids=json.loads(state["initial_comment_ids_json"]) if state else current_ids(conn, row["change_id"]),
                association_origin=state["initial_origin"] if state else "legacy_current_links_unverified",
                association_events=[event_view(event) for event in conn.execute(
                    "SELECT * FROM studio_change_link_events WHERE change_id=? ORDER BY resulting_link_revision",
                    (row["change_id"],))])
    before, after = json.loads(row["before_json"]), json.loads(row["after_json"])
    item["author_diff"] = "\n".join(difflib.unified_diff(author_lines(before), author_lines(after),
                                   fromfile="修改前", tofile="修改后", lineterm=""))
    item["structure_changed"] = before != after
    return item


def owned_change(conn: Any, manuscript_id: str, change_id: str) -> Any:
    row = conn.execute("""SELECT c.*,o.base_revision,o.resulting_revision,o.operation_kind
                         FROM studio_changes c JOIN studio_operations o USING(operation_id)
                         WHERE c.change_id=? AND c.manuscript_id=?""", (change_id, manuscript_id)).fetchone()
    if row is None:
        raise NotFoundError("The saved change does not belong to this manuscript")
    return row


def list_changes(db_path: Path, manuscript_id: str) -> list[dict[str, Any]]:
    with transaction(db_path) as conn:
        if not conn.execute("SELECT 1 FROM manuscripts WHERE manuscript_id=?", (manuscript_id,)).fetchone():
            raise NotFoundError("Unknown manuscript")
        rows = conn.execute("""SELECT c.*,o.base_revision,o.resulting_revision,o.operation_kind
                             FROM studio_changes c JOIN studio_operations o USING(operation_id)
                             WHERE c.manuscript_id=? ORDER BY o.resulting_revision""", (manuscript_id,)).fetchall()
        return [change_view(conn, row) for row in rows]


def set_links(db_path: Path, manuscript_id: str, change_id: str, *, request_id: str,
              expected_link_revision: int, comment_ids: list[str], reverses_event_id: str | None = None) -> dict[str, Any]:
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("A stable association request id is required")
    if type(expected_link_revision) is not int or expected_link_revision < 0:
        raise ValueError("Association revision must be a nonnegative integer")
    if (not isinstance(comment_ids, list) or len(comment_ids) > 100
            or any(not isinstance(item, str) or not item for item in comment_ids)):
        raise ValueError("Select at most 100 explicit comment identifiers")
    selected = sorted(set(comment_ids))
    payload = {"manuscript_id": manuscript_id, "change_id": change_id,
               "expected_link_revision": expected_link_revision, "comment_ids": selected,
               "reverses_event_id": reverses_event_id}
    with transaction(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = owned_change(conn, manuscript_id, change_id)
        previous = conn.execute("SELECT * FROM studio_change_link_events WHERE request_id=?", (request_id,)).fetchone()
        if previous:
            if json.loads(previous["request_json"]) != payload:
                raise RevisionConflictError("Association request id already belongs to a different decision")
            return {"event": event_view(previous), "change": change_view(conn, row), "idempotent_replay": True}
        before = current_ids(conn, change_id)
        state = conn.execute("SELECT * FROM studio_change_link_state WHERE change_id=?", (change_id,)).fetchone()
        revision = state["link_revision"] if state else 0
        if revision != expected_link_revision:
            raise RevisionConflictError("The saved change associations have changed; review their current state")
        for comment_id in selected:
            comment = conn.execute("""SELECT r.manuscript_id,c.archived_at FROM review_comments c
                                      JOIN review_rounds r USING(review_round_id) WHERE c.comment_id=?""", (comment_id,)).fetchone()
            if comment is None or comment["manuscript_id"] != manuscript_id:
                raise NotFoundError("A selected comment does not belong to this manuscript")
            if comment["archived_at"] and comment_id not in before:
                raise ValueError("An archived comment cannot receive a new association")
        if reverses_event_id:
            reversed_event = conn.execute("SELECT * FROM studio_change_link_events WHERE event_id=? AND change_id=?",
                                          (reverses_event_id, change_id)).fetchone()
            if (reversed_event is None or reversed_event["resulting_link_revision"] != revision
                    or json.loads(reversed_event["after_comment_ids_json"]) != before
                    or json.loads(reversed_event["before_comment_ids_json"]) != selected):
                raise RevisionConflictError("Only the unchanged latest association decision can be reversed")
        timestamp = datetime.now(UTC).isoformat()
        if state is None:
            record_initial(conn, change_id, before, origin="legacy_capture_before_late_link", timestamp=timestamp)
        event_id = new_id("change_link_event")
        conn.execute("INSERT INTO studio_change_link_events VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (event_id, request_id, change_id, revision, revision + 1, encoded(before), encoded(selected),
                      reverses_event_id, encoded(payload), timestamp))
        conn.execute("DELETE FROM comment_changes WHERE change_id=?", (change_id,))
        conn.executemany("INSERT INTO comment_changes VALUES(?,?)", [(item, change_id) for item in selected])
        conn.execute("UPDATE studio_change_link_state SET link_revision=? WHERE change_id=?", (revision + 1, change_id))
        return {"event": event_view(conn.execute("SELECT * FROM studio_change_link_events WHERE event_id=?", (event_id,)).fetchone()),
                "change": change_view(conn, row), "idempotent_replay": False}
