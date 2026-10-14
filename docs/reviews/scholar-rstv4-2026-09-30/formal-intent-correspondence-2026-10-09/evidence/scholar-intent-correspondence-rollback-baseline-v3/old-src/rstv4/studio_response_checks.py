"""Explicit author review of fixed reply assertions, never scientific auto-approval."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from .models import new_id
from .service import NotFoundError, RevisionConflictError, RSTV4Error
from .studio_rounds import resolve


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def response_revision(conn: Any, comment_id: str) -> int:
    row = conn.execute("SELECT revision FROM studio_comment_response_state WHERE comment_id=?", (comment_id,)).fetchone()
    return row[0] if row else 0


def advance(conn: Any, comment_id: str) -> None:
    conn.execute("""INSERT INTO studio_comment_response_state VALUES(?,1)
                    ON CONFLICT(comment_id) DO UPDATE SET revision=revision+1""", (comment_id,))


def content_digest(row: Any, revision: int = 0) -> str:
    return digest({"response_revision": revision, **{key: row[key] for key in
                   ["comment_id", "edited_text", "author_decision", "response_text"]}})


def state(conn: Any, manuscript_id: str, comment_id: str) -> dict[str, Any]:
    row = conn.execute(
        """SELECT c.*, r.manuscript_id FROM review_comments c JOIN review_rounds r
           ON r.review_round_id=c.review_round_id WHERE c.comment_id=? AND r.manuscript_id=?""",
        (comment_id, manuscript_id),
    ).fetchone()
    if row is None:
        raise NotFoundError("The review comment does not belong to this manuscript")
    document = conn.execute("SELECT * FROM studio_documents WHERE manuscript_id=?", (manuscript_id,)).fetchone()
    if document is None:
        raise NotFoundError("Unknown Studio manuscript")
    round_row = conn.execute("SELECT * FROM review_rounds WHERE review_round_id=?", (row["review_round_id"],)).fetchone()
    fixed_round = resolve(conn, round_row)
    changes = [dict(item) for item in conn.execute(
        """SELECT c.change_id,c.manuscript_id,c.before_json,c.after_json,
                  COALESCE(s.link_revision,0) AS link_revision FROM studio_changes c
           JOIN comment_changes l ON l.change_id=c.change_id
           LEFT JOIN studio_change_link_state s ON s.change_id=c.change_id
           WHERE l.comment_id=? ORDER BY c.change_id""", (comment_id,),
    )]
    if any(item["manuscript_id"] != manuscript_id for item in changes):
        raise RSTV4Error("The comment contains an invalid cross-manuscript change association")
    generated = conn.execute("SELECT content,inputs_json FROM manuscript_versions WHERE manuscript_version_id=? AND manuscript_id=?",
                             (document["active_generated_version_id"], manuscript_id)).fetchone()
    return {
        "manuscript_id": manuscript_id, "comment_id": comment_id,
        "review_round_id": row["review_round_id"], "round_number": fixed_round["round_number"],
        "baseline_manuscript_version_id": fixed_round["baseline_manuscript_version_id"],
        "baseline_content_sha256": fixed_round.get("baseline_content_sha256"),
        "edited_text": row["edited_text"], "author_decision": row["author_decision"],
        "response_text": row["response_text"], "archived_at": row["archived_at"],
        "response_revision": response_revision(conn, comment_id),
        "current_author_revision": document["revision"],
        "current_author_document_sha256": hashlib.sha256(document["document_json"].encode()).hexdigest(),
        "generated_version_id": document["active_generated_version_id"],
        "generated_input_revision": document["last_generated_revision"],
        "generated_record_sha256": digest(dict(generated)) if generated else None,
        "linked_changes": [{"change_id": item["change_id"], "link_revision": item["link_revision"],
                            "before_sha256": hashlib.sha256(item["before_json"].encode()).hexdigest(),
                            "after_sha256": hashlib.sha256(item["after_json"].encode()).hexdigest()} for item in changes],
    }


def status(conn: Any, manuscript_id: str, row: Any) -> dict[str, Any]:
    latest = conn.execute(
        "SELECT * FROM studio_response_checks WHERE comment_id=? ORDER BY rowid DESC LIMIT 1",
        (row["comment_id"],),
    ).fetchone()
    if latest is None:
        return {"status": "LEGACY_UNVERIFIED" if row["status"] == "RESOLVED" else "NOT_REVIEWED"}
    current = state(conn, manuscript_id, row["comment_id"])
    return {"status": "CURRENT" if latest["state_sha256"] == digest(current) else "STALE",
            "check_id": latest["check_id"], "checked_at": latest["created_at"],
            "outcome": latest["outcome"], "generated_version_id": latest["generated_version_id"],
            "context_sha256": latest["context_sha256"], "scientific_acceptance": False}


def history(conn: Any, comment_id: str) -> list[dict[str, Any]]:
    return [{**{key: value for key, value in dict(row).items() if not key.endswith("_json")},
             "request": json.loads(row["request_json"]), "context": json.loads(row["context_json"])}
            for row in conn.execute("SELECT * FROM studio_response_checks WHERE comment_id=? ORDER BY rowid", (comment_id,))]


def validate_claims(context: dict[str, Any], outcome: str, claims: list[dict[str, Any]],
                    acknowledged_all_assertions: bool) -> None:
    current = context["state"]
    if acknowledged_all_assertions is not True:
        raise ValueError("The author must explicitly review every modification assertion in the complete reply")
    if current["archived_at"]:
        raise RevisionConflictError("Restore this archived comment before reviewing its reply")
    if not current["response_text"] or not current["response_text"].strip():
        raise ValueError("Save a nonempty reply before confirming it")
    if not current["author_decision"] or not current["author_decision"].strip():
        raise ValueError("Save the author's decision and reason before confirming the reply")
    if not current["generated_version_id"] or current["current_author_revision"] != current["generated_input_revision"]:
        raise RevisionConflictError("Generate the current author revision before confirming the final reply")
    if outcome == "EXPLAINED_NO_CHANGE":
        if claims:
            raise ValueError("A no-change explanation cannot contain modification assertions")
        return
    if outcome != "MODIFIED":
        raise ValueError("Unknown author reply-review outcome")
    if not claims:
        raise ValueError("Select each modification assertion and its actual final-manuscript change")
    if not context["baseline_to_target_diff"]:
        raise ValueError("The final manuscript has no text difference from the fixed reviewed baseline")
    evidence = {row["evidence_id"]: row for row in context["evidence"]}
    raw_reply = current["response_text"].encode("utf-16-le")
    occupied = []
    for claim in claims:
        start, end, text = claim.get("start"), claim.get("end"), claim.get("text")
        if (type(start) is not int or type(end) is not int or start < 0 or end <= start
                or end * 2 > len(raw_reply) or not isinstance(text, str) or not text.strip()
                or claim.get("offset_unit") != "utf16"):
            raise ValueError("A modification assertion requires an exact UTF-16 reply selection")
        try:
            selected = raw_reply[start * 2:end * 2].decode("utf-16-le")
        except UnicodeDecodeError as exc:
            raise ValueError("The reply selection splits a Unicode character") from exc
        if selected != text or any(start < other_end and end > other_start for other_start, other_end in occupied):
            raise ValueError("Modification assertions must match the saved reply and must not overlap")
        occupied.append((start, end))
        selected_ids = claim.get("evidence_ids")
        if not isinstance(selected_ids, list) or not selected_ids or any(not isinstance(identifier, str) for identifier in selected_ids):
            raise ValueError("Each assertion must cite one or more actual change records")
        if len(set(selected_ids)) != len(selected_ids):
            raise ValueError("Duplicate assertion evidence is not allowed")
        for identifier in selected_ids:
            row = evidence.get(identifier)
            if (row is None or row["status"] != "GENERATED_TEXT_CHANGED" or not row.get("boxes")
                    or row.get("final_page") is None or row.get("final_line") is None):
                raise ValueError("Retained, superseded, unknown or unrelated changes cannot prove an assertion was implemented")


def record(conn: Any, manuscript_id: str, comment_id: str, context: dict[str, Any],
           request: dict[str, Any]) -> dict[str, Any]:
    previous = conn.execute("SELECT * FROM studio_response_checks WHERE request_id=?", (request["request_id"],)).fetchone()
    request_json = canonical({"manuscript_id": manuscript_id, "comment_id": comment_id, **request})
    if previous:
        if previous["request_json"] != request_json:
            raise RevisionConflictError("This reply-review request ID already records a different decision")
        return {"check_id": previous["check_id"], "idempotent_replay": True}
    if request["context_sha256"] != context["context_sha256"]:
        raise RevisionConflictError("Reply, manuscript version or change associations changed; reopen the review")
    validate_claims(context, request["outcome"], request["claims"], request["acknowledged_all_assertions"])
    if digest(state(conn, manuscript_id, comment_id)) != context["state_sha256"]:
        raise RevisionConflictError("Reply context changed while it was being reviewed")
    check_id = new_id("response_check")
    conn.execute(
        "INSERT INTO studio_response_checks VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (check_id, request["request_id"], manuscript_id, comment_id, context["state"]["generated_version_id"],
         context["state_sha256"], context["context_sha256"], request["outcome"], request_json,
         canonical({key: value for key, value in context.items() if key not in {"history", "verification"}}), datetime.now(UTC).isoformat()),
    )
    conn.execute("UPDATE review_comments SET status='RESOLVED',updated_at=? WHERE comment_id=?",
                 (datetime.now(UTC).isoformat(), comment_id))
    return {"check_id": check_id, "idempotent_replay": False}
