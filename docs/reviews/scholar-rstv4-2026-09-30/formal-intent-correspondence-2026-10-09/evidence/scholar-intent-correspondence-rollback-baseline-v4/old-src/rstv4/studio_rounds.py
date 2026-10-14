"""Immutable author-selected review baselines and conservative legacy resolution."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .service import NotFoundError, RSTV4Error


def content_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def version(conn: Any, manuscript_id: str, version_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM manuscript_versions WHERE manuscript_version_id=? AND manuscript_id=?",
        (version_id, manuscript_id),
    ).fetchone()
    if row is None:
        raise NotFoundError("The reviewed version does not belong to this manuscript")
    return dict(row)


def resolve(conn: Any, round_row: Any) -> dict[str, Any]:
    result = dict(round_row)
    metadata = conn.execute(
        "SELECT * FROM studio_review_round_baselines WHERE review_round_id=?",
        (result["review_round_id"],),
    ).fetchone()
    version_id = metadata["baseline_manuscript_version_id"] if metadata else None
    origin = "explicit_round_baseline" if metadata else "legacy_unknown"
    if metadata and not version_id:
        origin = "unresolved_at_round_creation"
    # A legacy artifact's exact generation job may prove its immutable version.
    # Never substitute the current generated version or infer from file order.
    if metadata is None and result["baseline_artifact_id"]:
        artifact = conn.execute(
            "SELECT * FROM studio_artifacts WHERE artifact_id=? AND manuscript_id=? AND artifact_kind='MARKDOWN'",
            (result["baseline_artifact_id"], result["manuscript_id"]),
        ).fetchone()
        if artifact:
            candidates = [
                row
                for row in conn.execute(
                    "SELECT * FROM manuscript_versions WHERE manuscript_id=?",
                    (result["manuscript_id"],),
                )
                if json.loads(row["inputs_json"]).get("job_id") == artifact["job_id"]
            ]
            if len(candidates) == 1:
                version_id = candidates[0]["manuscript_version_id"]
                origin = "legacy_exact_artifact_job"
    result.update(
        baseline_manuscript_version_id=version_id,
        baseline_version=None,
        baseline_document_revision=None,
        baseline_available=False,
        baseline_origin=origin,
    )
    if version_id:
        original = version(conn, result["manuscript_id"], version_id)
        actual_digest = content_digest(original["content"])
        if metadata and actual_digest != metadata["content_sha256"]:
            raise RSTV4Error("The fixed review baseline content failed integrity verification")
        inputs = json.loads(original["inputs_json"])
        result.update(
            baseline_available=True,
            baseline_version=original["version"],
            baseline_document_revision=inputs.get("studio_revision"),
            baseline_content_sha256=actual_digest,
        )
    return result


def baseline_text(conn: Any, round_row: Any) -> tuple[dict[str, Any], str]:
    resolved = resolve(conn, round_row)
    if not resolved["baseline_available"]:
        raise RSTV4Error(
            "This review round has no proven fixed baseline; choose a reviewed version in a new round"
        )
    original = version(conn, resolved["manuscript_id"], resolved["baseline_manuscript_version_id"])
    return resolved, original["content"]
