from __future__ import annotations

import hashlib
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .database import initialize_catalog, initialize_project

_APPROVE = re.compile(r"^APPROVE\s+([a-z0-9_]+)$", re.IGNORECASE)


def capture_user_approval(
    root: str | Path,
    *,
    profile: str,
    session_id: str,
    message_id: str,
    user_message: str,
) -> dict[str, str] | None:
    """Record an exact user approval observed at the Hermes input boundary."""
    if profile not in {"orchestrator", "scholar"}:
        return None
    match = _APPROVE.fullmatch(user_message.strip())
    if match is None:
        return None
    proposal_id = match.group(1)
    root_path = Path(root).resolve()
    catalog_path = root_path / "data" / "catalog.db"
    initialize_catalog(catalog_path)
    with closing(sqlite3.connect(catalog_path)) as connection, connection:
        connection.row_factory = sqlite3.Row
        decision = connection.execute(
            "SELECT track_id,expected_revision FROM decisions WHERE proposal_id=? AND status='PROPOSED'",
            (proposal_id,),
        ).fetchone()
        plan = connection.execute(
            "SELECT track_id,project_id,revision FROM experiment_plans WHERE proposal_id=? AND status='PROPOSED'",
            (proposal_id,),
        ).fetchone()
        review = connection.execute(
            """SELECT r.track_id,r.expected_revision FROM manuscript_scientific_review_requests r
               WHERE r.review_id=? AND NOT EXISTS(SELECT 1 FROM manuscript_scientific_review_events e WHERE e.review_id=r.review_id)""",
            (proposal_id,),
        ).fetchone()
        if decision is not None or plan is not None or review is not None:
            proposal_type = "decision" if decision is not None else "experiment_plan" if plan is not None else "manuscript_scientific_review"
            selected = decision or plan or review
            revision = int(selected["expected_revision"] if decision is not None or review is not None else selected["revision"])
            digest = hashlib.sha256(user_message.strip().encode("utf-8")).hexdigest()
            grant_id = f"grant_{uuid4().hex}"
            connection.execute(
                """INSERT OR IGNORE INTO approval_grants(
                   grant_id,proposal_id,proposal_type,track_id,project_id,proposal_revision,profile,
                   session_id,message_id,user_message_digest,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    grant_id, proposal_id, proposal_type, selected["track_id"],
                    plan["project_id"] if plan is not None else None, revision, profile, session_id,
                    message_id, digest, datetime.now(UTC).isoformat(),
                ),
            )
            connection.commit()
            return {
                "grant_id": grant_id,
                "proposal_id": proposal_id,
                "track_id": selected["track_id"],
                "proposal_type": proposal_type,
            }
    # Migration-only fallback for a pre-v3 workspace. It is not exposed by the MCP API.
    for database_path in (root_path / "projects").glob("*/research.db"):
        initialize_project(database_path)
        with closing(sqlite3.connect(database_path)) as connection, connection:
            decision = connection.execute(
                "SELECT expected_revision FROM decisions WHERE proposal_id=? AND status='PROPOSED'",
                (proposal_id,),
            ).fetchone()
            plan = connection.execute(
                "SELECT revision FROM experiment_plans WHERE proposal_id=? AND status='PROPOSED'",
                (proposal_id,),
            ).fetchone()
            if decision is None and plan is None:
                continue
            proposal_type = "decision" if decision is not None else "experiment_plan"
            revision = int((decision or plan)[0])
            digest = hashlib.sha256(user_message.strip().encode("utf-8")).hexdigest()
            grant_id = f"grant_{uuid4().hex}"
            connection.execute(
                """INSERT OR IGNORE INTO approval_grants(
                   grant_id,proposal_id,proposal_type,project_slug,proposal_revision,profile,
                   session_id,message_id,user_message_digest,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    grant_id,
                    proposal_id,
                    proposal_type,
                    database_path.parent.name,
                    revision,
                    profile,
                    session_id,
                    message_id,
                    digest,
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.commit()
            return {
                "grant_id": grant_id,
                "proposal_id": proposal_id,
                "project_slug": database_path.parent.name,
                "proposal_type": proposal_type,
            }
    return None


def consume_grant(
    connection: sqlite3.Connection,
    *,
    proposal_id: str,
    proposal_type: str,
    revision: int,
) -> sqlite3.Row:
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        """SELECT * FROM approval_grants
           WHERE proposal_id=? AND proposal_type=? AND proposal_revision=? AND consumed_at IS NULL
           ORDER BY created_at LIMIT 1""",
        (proposal_id, proposal_type, revision),
    ).fetchone()
    if row is None:
        raise PermissionError("A matching unconsumed user-message approval grant is required")
    connection.execute(
        "UPDATE approval_grants SET consumed_at=? WHERE grant_id=?",
        (datetime.now(UTC).isoformat(), row["grant_id"]),
    )
    return row
