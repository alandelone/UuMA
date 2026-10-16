"""Read historical origins from exact recorded input without rewriting a check."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .service import NotFoundError, RSTV4Error
from .studio_read_views import document_revision, generated_version
from .studio_response_checks import digest
from .studio_revision_mapping import frozen_origins


def read_origins(conn: Any, storage_root: Path, manuscript_id: str, comment_id: str,
                 check_id: str, evidence_id: str) -> dict[str, Any]:
    check = conn.execute(
        """SELECT sc.* FROM studio_response_checks sc
           JOIN review_comments c ON c.comment_id=sc.comment_id
           JOIN review_rounds r ON r.review_round_id=c.review_round_id
           WHERE sc.manuscript_id=? AND sc.comment_id=? AND sc.check_id=? AND r.manuscript_id=?""",
        (manuscript_id, comment_id, check_id, manuscript_id),
    ).fetchone()
    if check is None:
        raise NotFoundError("The historical check does not belong to this manuscript and comment")
    envelope = {"check_id": check_id, "evidence_id": evidence_id,
                "original_context_sha256": check["context_sha256"], "origins": []}

    def unavailable(reason: str, *, ambiguous: bool = False) -> dict[str, Any]:
        return {**envelope, "status": "AMBIGUOUS" if ambiguous else "UNAVAILABLE", "reason": reason}

    try:
        context = json.loads(check["context_json"])
        request = json.loads(check["request_json"])
    except (ValueError, TypeError):
        return unavailable("ORIGINAL_CONTEXT_INTEGRITY_FAILED")
    if not isinstance(context, dict) or not isinstance(request, dict):
        return unavailable("ORIGINAL_CONTEXT_INTEGRITY_FAILED")
    state = context.get("state", {})
    if (not isinstance(state, dict) or context.get("context_sha256") != check["context_sha256"]
            or digest({k: v for k, v in context.items() if k != "context_sha256"}) != check["context_sha256"]
            or digest(state) != check["state_sha256"]
            or request.get("context_sha256") != check["context_sha256"]
            or request.get("manuscript_id") != manuscript_id or request.get("comment_id") != comment_id
            or request.get("request_id") != check["request_id"] or request.get("outcome") != check["outcome"]
            or state.get("manuscript_id") != manuscript_id or state.get("comment_id") != comment_id):
        return unavailable("ORIGINAL_CONTEXT_INTEGRITY_FAILED")
    recorded = context.get("evidence")
    if not isinstance(recorded, list) or any(not isinstance(item, dict) for item in recorded):
        return unavailable("RECORDED_EVIDENCE_UNAVAILABLE")
    rows = [row for row in recorded if row.get("evidence_id") == evidence_id]
    if not rows:
        raise NotFoundError("The evidence does not belong to this historical check")
    if len(rows) != 1:
        return unavailable("AMBIGUOUS_RECORDED_EVIDENCE", ambiguous=True)
    row = rows[0]
    version_id, revision = state.get("generated_version_id"), state.get("generated_input_revision")
    if (not version_id or version_id != check["generated_version_id"]
            or row.get("generated_version_id") != version_id or type(revision) is not int
            or state.get("current_author_revision") != revision
            or not state.get("generated_record_sha256") or not state.get("current_author_document_sha256")):
        return unavailable("MISSING_FIXED_SOURCE_IDENTITY")
    record = conn.execute("""SELECT content,inputs_json FROM manuscript_versions
                             WHERE manuscript_id=? AND manuscript_version_id=?""",
                          (manuscript_id, version_id)).fetchone()
    if record is None or digest(dict(record)) != state["generated_record_sha256"]:
        return unavailable("FROZEN_RECORD_MISMATCH")
    if hashlib.sha256(record["content"].encode("utf-8")).hexdigest() != context.get("target_text_sha256"):
        return unavailable("FROZEN_TEXT_MISMATCH")
    try:
        target = generated_version(conn, storage_root, manuscript_id, version_id)
        original = document_revision(conn, manuscript_id, revision, include_serialized_sha=True)
    except (RSTV4Error, ValueError, OSError):
        return unavailable("ORIGINAL_PROVENANCE_UNAVAILABLE")
    if (target["input_revision"] != revision or target["version"] != context.get("target_version_number")
            or original["document_sha256"] != state["current_author_document_sha256"]):
        return unavailable("FROZEN_AUTHOR_INPUT_MISMATCH")
    thought_id, sentence_index = row.get("thought_id"), row.get("sentence_index")
    realizations = [item for item in target.get("realizations", [])
                    if item["paragraph_id"] == row.get("paragraph_id")]
    if (not thought_id or type(sentence_index) is not int or len(realizations) != 1
            or not realizations[0].get("sentence_positions_verified")):
        return unavailable("RECORDED_REALIZATION_UNAVAILABLE")
    realization = realizations[0]
    mappings = [item for item in realization["sentence_mappings"] if item["sentence"] == sentence_index]
    if (len(mappings) != 1 or thought_id not in mappings[0]["thought_ids"]
            or not 0 <= sentence_index < len(realization["sentences"])
            or realization["sentences"][sentence_index]["text"] != row.get("changed_text")):
        return unavailable("RECORDED_REALIZATION_MISMATCH")
    origins = frozen_origins(original["document"], target).get(thought_id, [])
    if len(origins) != 1:
        return unavailable("AMBIGUOUS_ORIGINAL_THOUGHT" if origins else "ORIGINAL_THOUGHT_UNAVAILABLE",
                           ambiguous=bool(origins))
    if row.get("origins") and row["origins"] != origins:
        return unavailable("STORED_ORIGIN_MISMATCH")
    return {**envelope, "status": "STORED_SNAPSHOT" if row.get("origins") else "RECONSTRUCTED_FROM_FIXED_INPUT",
            "source": {"manuscript_id": manuscript_id, "generated_version_id": version_id,
                       "generated_version_number": target["version"], "input_revision": revision,
                       "generated_record_sha256": state["generated_record_sha256"],
                       "author_document_sha256": original["document_sha256"]}, "origins": origins}
