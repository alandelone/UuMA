"""Immutable local submission provenance and completion within Paper Stage 6."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .service import NotFoundError, RevisionConflictError, RSTV4Error
from .studio_read_views import document_revision

SCHEMA = """
CREATE TABLE IF NOT EXISTS studio_submission_bindings (
  event_id TEXT PRIMARY KEY REFERENCES submission_events(event_id),
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  operation_id TEXT UNIQUE,
  request_sha256 TEXT NOT NULL,
  snapshot_json TEXT NOT NULL,
  snapshot_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_studio_submission_bindings_owner
  ON studio_submission_bindings(manuscript_id,event_id);
"""


def encoded(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def event_record(conn: Any, row: Any) -> dict:
    event = dict(row)
    stored = conn.execute(
        "SELECT * FROM studio_submission_bindings WHERE event_id=?", (event["event_id"],)
    ).fetchone()
    if stored is None:
        return {**event, "binding": {"status": "UNBOUND"}}
    snapshot = json.loads(stored["snapshot_json"])
    if (stored["manuscript_id"] != event["manuscript_id"]
            or stored["created_at"] != event["created_at"]
            or text_digest(stored["snapshot_json"]) != stored["snapshot_sha256"]
            or snapshot["event"] != {key: event[key] for key in (
                "manuscript_id", "venue", "round", "status", "detail")}):
        raise RSTV4Error("The original submission event failed its provenance check")
    return {**event, "binding": {
        "status": "BOUND" if snapshot["generated_version"] else "UNBOUND",
        "snapshot": snapshot, "snapshot_sha256": stored["snapshot_sha256"],
    }}


def replay(conn: Any, manuscript_id: str, operation_id: str | None, request: dict) -> dict | None:
    if operation_id is None:
        return None
    if not isinstance(operation_id, str) or not 8 <= len(operation_id) <= 200:
        raise ValueError("Submission operation IDs must contain 8 to 200 characters")
    row = conn.execute(
        "SELECT * FROM studio_submission_bindings WHERE operation_id=?", (operation_id,)
    ).fetchone()
    if row is None:
        return None
    if row["manuscript_id"] != manuscript_id or row["request_sha256"] != digest(request):
        raise RevisionConflictError("This submission operation already records a different request")
    event = conn.execute("SELECT * FROM submission_events WHERE event_id=?", (row["event_id"],)).fetchone()
    if event is None:
        raise RSTV4Error("The original submission event is unavailable")
    return event_record(conn, event)


def version_snapshot(conn: Any, manuscript_id: str, version_id: str | None) -> dict | None:
    if version_id is None:
        return None  # Unbound historical metadata must never inherit a later active version.
    row = conn.execute(
        "SELECT * FROM manuscript_versions WHERE manuscript_id=? AND manuscript_version_id=?",
        (manuscript_id, version_id),
    ).fetchone()
    if row is None:
        raise NotFoundError("The submission version does not belong to this manuscript")
    inputs = json.loads(row["inputs_json"])
    job = conn.execute(
        "SELECT * FROM studio_jobs WHERE manuscript_id=? AND job_id=?",
        (manuscript_id, inputs.get("job_id")),
    ).fetchone()
    if (job is None or job["job_kind"] != "GENERATE" or job["status"] != "SUCCEEDED"
            or job["input_revision"] != inputs.get("studio_revision")):
        raise RSTV4Error("A successful generated version is required for this submission record")
    try:
        author = document_revision(conn, manuscript_id, job["input_revision"])["document"]
    except NotFoundError:
        template = {"status": "UNRECORDED"}
    else:
        sources = []

        def collect(value):
            if isinstance(value, dict):
                if value.get("template_source") is not None:
                    sources.append(value["template_source"])
                for item in value.values():
                    collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)

        collect(author)
        template = {"status": "RECORDED", "author_document_sha256": digest(author),
                    "venue": author.get("venue", ""),
                    "citation_style": author.get("citation_style") or inputs.get("generated", {}).get("citation_style"),
                    "template_sources": sources}
    return {"manuscript_version_id": row["manuscript_version_id"], "version": row["version"],
            "document_revision": inputs["studio_revision"], "job_id": job["job_id"],
            "content_sha256": text_digest(row["content"]),
            "inputs_sha256": text_digest(row["inputs_json"]), "template_manifest": template}


def version_intact(conn: Any, manuscript_id: str, frozen: dict) -> bool:
    row = conn.execute(
        "SELECT * FROM manuscript_versions WHERE manuscript_id=? AND manuscript_version_id=?",
        (manuscript_id, frozen["manuscript_version_id"]),
    ).fetchone()
    return bool(row is not None and row["version"] == frozen["version"]
                and text_digest(row["content"]) == frozen["content_sha256"]
                and text_digest(row["inputs_json"]) == frozen["inputs_sha256"])


def previous_event(conn: Any, manuscript_id: str, venue: str, round_number: int) -> dict | None:
    row = conn.execute(
        """SELECT * FROM submission_events WHERE manuscript_id=? AND venue=? AND round=?
           ORDER BY rowid DESC LIMIT 1""", (manuscript_id, venue, round_number),
    ).fetchone()
    return event_record(conn, row) if row is not None else None


def acceptance(conn: Any, manuscript_id: str, version_id: str | None,
               venue: str | None = None, round_number: int | None = None) -> dict | None:
    if not version_id:
        return None
    rows = conn.execute(
        "SELECT * FROM submission_events WHERE manuscript_id=? ORDER BY rowid DESC", (manuscript_id,)
    )
    seen = set()
    for row in rows:
        key = (row["venue"], row["round"])
        if key in seen or (venue is not None and key != (venue, round_number)):
            continue
        seen.add(key)
        if row["status"] not in {"ACCEPTED", "PUBLISHED", "ARCHIVED"}:
            continue
        event = event_record(conn, row)
        binding = event["binding"]
        if binding["status"] != "BOUND":
            continue
        snapshot = binding["snapshot"]
        frozen = snapshot["generated_version"]
        if frozen["manuscript_version_id"] != version_id or not version_intact(conn, manuscript_id, frozen):
            continue
        accepted_id = row["event_id"] if row["status"] == "ACCEPTED" else snapshot["accepted_event_id"]
        accepted = conn.execute("SELECT * FROM submission_events WHERE event_id=?", (accepted_id,)).fetchone()
        if (accepted is None or accepted["manuscript_id"] != manuscript_id
                or accepted["venue"] != row["venue"] or accepted["round"] != row["round"]
                or accepted["status"] != "ACCEPTED"):
            continue
        original = event_record(conn, accepted)["binding"]
        if (original["status"] == "BOUND" and original["snapshot"]["generated_version"] == frozen):
            return event_record(conn, accepted)
    return None


def file_snapshot(conn: Any, storage_root: Path, manuscript_id: str, asset_id: str | None) -> dict:
    row = conn.execute(
        "SELECT * FROM studio_assets WHERE manuscript_id=? AND asset_id=?", (manuscript_id, asset_id)
    ).fetchone()
    if row is None:
        raise NotFoundError("The final or proof file does not belong to this manuscript")
    path = Path(row["storage_path"]).resolve()
    if (row["asset_kind"] != "DOCUMENT" or row["status"] != "READY"
            or storage_root.resolve() not in path.parents or not path.is_file()):
        raise RSTV4Error("The final or proof file is unavailable")
    if path.stat().st_size != row["size_bytes"]:
        raise RSTV4Error("The final or proof file failed its integrity check")
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != row["sha256"]:
        raise RSTV4Error("The final or proof file failed its integrity check")
    return {"asset_id": row["asset_id"], "filename": row["filename"],
            "sha256": row["sha256"], "byte_size": row["size_bytes"], "media_type": row["media_type"]}


def freeze(conn: Any, storage_root: Path, manuscript_id: str, payload: Any, version: dict | None,
           final_asset_id: str | None, proof_asset_id: str | None, acknowledged: bool) -> dict:
    if not isinstance(acknowledged, bool):
        raise TypeError("Author confirmation must be a boolean")
    if payload.status.value != "ARCHIVED" and (final_asset_id or proof_asset_id):
        raise ValueError("Final and proof files are bound by an archive completion event")
    previous = previous_event(conn, manuscript_id, payload.venue, payload.round)
    accepted = None
    if payload.status.value in {"PUBLISHED", "ARCHIVED"}:
        accepted = acceptance(conn, manuscript_id, version["manuscript_version_id"] if version else None,
                              payload.venue, payload.round)
        if accepted is None:
            raise RSTV4Error("Record acceptance of this exact manuscript version, venue and round first")
    files = None
    if payload.status.value == "ARCHIVED":
        if not acknowledged:
            raise ValueError("The author must confirm the final proof and archive completion")
        if not previous or previous["status"] not in {"PUBLISHED", "ARCHIVED"}:
            raise RSTV4Error("Record publication of this exact venue and round before archive completion")
        if previous["binding"]["status"] != "BOUND" or previous["binding"]["snapshot"]["generated_version"] != version:
            raise RSTV4Error("The published version differs from the final version being archived")
        files = {"final": file_snapshot(conn, storage_root, manuscript_id, final_asset_id),
                 "proof": file_snapshot(conn, storage_root, manuscript_id, proof_asset_id)}
    return {"event": {"manuscript_id": manuscript_id, "venue": payload.venue,
                      "round": payload.round, "status": payload.status.value, "detail": payload.detail},
            "generated_version": version, "parent_event_id": previous["event_id"] if previous else None,
            "accepted_event_id": accepted["event_id"] if accepted else None, "files": files}


def record_binding(conn: Any, event_id: str, manuscript_id: str, operation_id: str | None,
                   request: dict, snapshot: dict, timestamp: str) -> None:
    raw = encoded(snapshot)
    conn.execute("INSERT INTO studio_submission_bindings VALUES(?,?,?,?,?,?,?)",
                 (event_id, manuscript_id, operation_id, digest(request), raw, text_digest(raw), timestamp))


def state(conn: Any, storage_root: Path, manuscript_id: str, active_version_id: str | None,
          author_revision: int, generated_is_stale: bool, needs_scientific_review: bool) -> dict:
    accepted = acceptance(conn, manuscript_id, active_version_id)
    completed = conn.execute(
        """SELECT * FROM submission_events WHERE manuscript_id=? AND status='ARCHIVED'
           ORDER BY rowid DESC LIMIT 1""", (manuscript_id,),
    ).fetchone()
    completion = None
    if completed is not None:
        bound = event_record(conn, completed)["binding"]
        if bound["status"] == "BOUND" and bound["snapshot"].get("files"):
            snapshot = bound["snapshot"]
            frozen = snapshot["generated_version"]
            completion_accepted = acceptance(
                conn, manuscript_id, frozen["manuscript_version_id"], completed["venue"], completed["round"],
            )
            status = "CURRENT" if (active_version_id == frozen["manuscript_version_id"]
                                   and author_revision == frozen["document_revision"]
                                   and not generated_is_stale and not needs_scientific_review
                                   and completion_accepted is not None
                                   and completion_accepted["event_id"] == snapshot["accepted_event_id"]
                                   and version_intact(conn, manuscript_id, frozen)) else "STALE"
            try:
                for item in snapshot["files"].values():
                    if file_snapshot(conn, storage_root, manuscript_id, item["asset_id"]) != item:
                        status = "UNAVAILABLE"
            except (RSTV4Error, OSError):
                status = "UNAVAILABLE"
            completion = {"event_id": completed["event_id"],
                          "generated_version_id": frozen["manuscript_version_id"],
                          "status": status, "files": snapshot["files"]}
    return {"accepted_event_id": accepted["event_id"] if accepted else None,
            "accepted_generated_version_id": active_version_id if accepted else None,
            "completion": completion}
