"""UuMA State Daemon for Brainstormer Live & Shared Discussion (127.0.0.1:8772).

Serializes discussion state mutations, maintains SQLite user bindings and audit receipts,
and projects the Decision Map DAG.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from uuma.brainstormer_state import (
    BrainstormerError,
    BrainstormerStore,
    CycleDetectedError,
    RevisionConflict,
    StateTransaction,
)

logger = logging.getLogger("uuma.state_daemon")

DEFAULT_PORT = int(os.environ.get("UUMA_STATE_DAEMON_PORT", "8772"))
DEFAULT_HOST = os.environ.get("UUMA_STATE_DAEMON_HOST", "127.0.0.1")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class DatabaseManager:
    """Manages SQLite connections and schema initialization for uuma.db."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS user_bindings (
                    user_id TEXT PRIMARY KEY,
                    active_project_id TEXT NOT NULL,
                    active_topic_id TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS discussion_turns (
                    turn_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    topic_id TEXT,
                    source TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS commit_receipts (
                    commit_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    topic_id TEXT,
                    revision INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_receipts_project_rev ON commit_receipts(project_id, revision);
                CREATE INDEX IF NOT EXISTS idx_turns_project ON discussion_turns(project_id, topic_id);
                """
            )

    def get_binding(self, user_id: str) -> dict[str, Any] | None:
        with self._lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT user_id, active_project_id, active_topic_id, updated_at FROM user_bindings WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def set_binding(self, user_id: str, project_id: str, topic_id: str | None = None) -> dict[str, Any]:
        now = _now()
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_bindings (user_id, active_project_id, active_topic_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    active_project_id = excluded.active_project_id,
                    active_topic_id = excluded.active_topic_id,
                    updated_at = excluded.updated_at
                """,
                (user_id, project_id, topic_id, now),
            )
            conn.commit()
        return {"user_id": user_id, "active_project_id": project_id, "active_topic_id": topic_id, "updated_at": now}

    def record_turn(self, user_id: str, project_id: str, topic_id: str | None, source: str, text: str) -> str:
        turn_id = _id("turn")
        now = _now()
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO discussion_turns (turn_id, user_id, project_id, topic_id, source, text, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (turn_id, user_id, project_id, topic_id, source, text, now),
            )
            conn.commit()
        return turn_id

    def record_receipt(
        self, project_id: str, topic_id: str | None, revision: int, status: str, requested_by: str
    ) -> str:
        commit_id = _id("commit")
        now = _now()
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO commit_receipts (commit_id, project_id, topic_id, revision, status, requested_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (commit_id, project_id, topic_id, revision, status, requested_by, now),
            )
            conn.commit()
        return commit_id


class StateDaemon:
    """Core daemon managing project state, locks, and persistence."""

    def __init__(self, data_dir: Path | None = None) -> None:
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        self.data_dir = data_dir or Path(os.environ.get("UUMA_DATA_DIR", local / "UuMA"))
        self.store = BrainstormerStore(self.data_dir / "brainstormer")
        self.db = DatabaseManager(self.data_dir / "uuma.db")
        self._project_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._global_lock = threading.Lock()

    def get_project_lock(self, project_id: str) -> threading.Lock:
        with self._global_lock:
            return self._project_locks[project_id]


# Global Daemon instance
daemon = StateDaemon()


# --- Pydantic Schemas ---


class BindRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    topic_id: str | None = None


class CommitRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    topic_id: str | None = None
    source: str = Field(default="live", pattern=r"^(live|telegram)$")
    transaction: dict[str, Any]
    auto_approve: bool = False
    turn_text: str | None = None
    requested_by: str = "brainstormer"


class ReviewRequest(BaseModel):
    proposal_id: str = Field(min_length=1)
    project_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    approve: bool
    actor_id: str = "user"
    note: str = "User confirmed via Decision Map"
    user_id: str = "u_default"
    topic_id: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("UuMA State Daemon starting on %s:%d, data_dir=%s", DEFAULT_HOST, DEFAULT_PORT, daemon.data_dir)
    yield
    logger.info("UuMA State Daemon shutting down.")


app = FastAPI(title="UuMA State Daemon", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "uuma-state-daemon",
        "revision": 1,
        "db": str(daemon.db.db_path),
        "store": str(daemon.store.root),
    }


@app.get("/api/v1/context/{user_id}")
def get_user_context(user_id: str) -> dict[str, Any]:
    binding = daemon.db.get_binding(user_id)
    if not binding:
        return {
            "user_id": user_id,
            "project_id": None,
            "topic_id": None,
            "context": None,
            "active": False,
        }

    project_id = binding["active_project_id"]
    topic_id = binding.get("active_topic_id")

    with daemon.get_project_lock(project_id):
        try:
            context = daemon.store.get_context(project_id, topic_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to load context for project %s: %s", project_id, e)
            context = None

    return {
        "user_id": user_id,
        "project_id": project_id,
        "topic_id": topic_id,
        "context": context,
        "active": True,
        "updated_at": binding["updated_at"],
    }


@app.post("/api/v1/bind")
def bind_user(req: BindRequest) -> dict[str, Any]:
    with daemon.get_project_lock(req.project_id):
        # Validate that project can be loaded or initialized
        daemon.store.get_context(req.project_id, req.topic_id)
        binding = daemon.db.set_binding(req.user_id, req.project_id, req.topic_id)
    return {"status": "ok", "binding": binding}


@app.post("/api/v1/commit")
def commit_transaction(req: CommitRequest) -> dict[str, Any]:
    with daemon.get_project_lock(req.project_id):
        try:
            tx = StateTransaction.model_validate(req.transaction)
        except Exception as err:  # noqa: BLE001
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid transaction: {err}")

        if tx.project_id != req.project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Transaction project_id mismatch: {tx.project_id} vs {req.project_id}",
            )

        try:
            proposal = daemon.store.propose(tx, requested_by=req.requested_by)
            proposal_id = proposal["proposal_id"]

            if proposal["review_required"]:
                # Invariant: Structural modifications (project, topic, decision, supersede)
                # MUST require explicit human confirmation. Auto-approval is forbidden.
                commit_id = daemon.db.record_receipt(
                    req.project_id, req.topic_id, 0, "PENDING_REVIEW", req.requested_by
                )
                if req.turn_text:
                    daemon.db.record_turn(req.user_id, req.project_id, req.topic_id, req.source, req.turn_text)
                return {
                    "commit_id": commit_id,
                    "proposal_id": proposal_id,
                    "project_id": req.project_id,
                    "topic_id": req.topic_id,
                    "revision": None,
                    "status": "pending_review",
                    "review_required": True,
                }

            # Only safe, non-structural proposals may be committed automatically
            committed = daemon.store.commit_safe(proposal_id, actor_id=req.requested_by)
            rev = committed["project_revision"]

            commit_id = daemon.db.record_receipt(req.project_id, req.topic_id, rev, "COMMITTED", req.requested_by)
            if req.turn_text:
                daemon.db.record_turn(req.user_id, req.project_id, req.topic_id, req.source, req.turn_text)

            # Auto update active topic binding if specified
            if req.topic_id:
                daemon.db.set_binding(req.user_id, req.project_id, req.topic_id)

            return {
                "commit_id": commit_id,
                "proposal_id": proposal_id,
                "project_id": req.project_id,
                "topic_id": req.topic_id,
                "revision": rev,
                "status": "committed",
                "review_required": False,
            }
        except CycleDetectedError as cde:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(cde))
        except RevisionConflict as rc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(rc))
        except BrainstormerError as be:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(be))
        except Exception as exc:
            logger.exception("Unexpected error in commit")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@app.post("/api/v1/review")
def review_proposal(req: ReviewRequest) -> dict[str, Any]:
    with daemon.get_project_lock(req.project_id):
        try:
            reviewed = daemon.store.review(
                req.proposal_id,
                actor_id=req.actor_id,
                approve=req.approve,
                note=req.note,
            )
            status_text = "COMMITTED" if req.approve else "REJECTED"
            rev = reviewed.get("project_revision")
            commit_id = daemon.db.record_receipt(
                req.project_id, req.topic_id, rev or 0, status_text, req.actor_id
            )
            if req.topic_id and req.approve:
                daemon.db.set_binding(req.user_id, req.project_id, req.topic_id)

            return {
                "commit_id": commit_id,
                "proposal_id": req.proposal_id,
                "project_id": req.project_id,
                "topic_id": req.topic_id,
                "status": "committed" if req.approve else "rejected",
                "revision": rev,
                "reviewed_by": req.actor_id,
                "review_note": req.note,
            }
        except RevisionConflict as rc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(rc))
        except BrainstormerError as be:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(be))
        except Exception as exc:
            logger.exception("Unexpected error in review")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@app.get("/api/v1/proposals/{project_id}")
def get_project_proposals(project_id: str) -> dict[str, Any]:
    with daemon.get_project_lock(project_id):
        proposals: list[dict[str, Any]] = []
        for p_path in daemon.store.proposals.glob("*.json"):
            try:
                p_data = json.loads(p_path.read_text(encoding="utf-8"))
                if p_data.get("transaction", {}).get("project_id") == project_id:
                    proposals.append({
                        "proposal_id": p_data.get("proposal_id"),
                        "status": p_data.get("status"),
                        "created_at": p_data.get("created_at"),
                        "requested_by": p_data.get("requested_by"),
                        "review_required": p_data.get("review_required", False),
                        "rationale": p_data.get("transaction", {}).get("rationale"),
                        "operations": p_data.get("transaction", {}).get("operations", []),
                    })
            except (OSError, json.JSONDecodeError):
                logger.debug("Skipping unreadable proposal %s", p_path)
        return {"project_id": project_id, "proposals": proposals}


class ActiveQuestionRequest(BaseModel):
    project_id: str
    question_id: str
    user_id: str = "user"


@app.get("/api/v1/active-question/{project_id}")
def get_active_question(project_id: str) -> dict[str, Any]:
    with daemon.get_project_lock(project_id):
        try:
            d_map = daemon.store.get_decision_map(project_id)
            return {
                "project_id": project_id,
                "active_question_id": d_map.get("active_question_id"),
                "progression": d_map.get("progression"),
            }
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/api/v1/active-question")
def set_active_question(req: ActiveQuestionRequest) -> dict[str, Any]:
    with daemon.get_project_lock(req.project_id):
        try:
            result = daemon.store.set_active_question(
                req.project_id, req.question_id, actor_id=req.user_id
            )
            return {"status": "ok", **result}
        except BrainstormerError as be:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(be))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/api/v1/graph/{project_id}")
def get_decision_graph(project_id: str) -> dict[str, Any]:
    with daemon.get_project_lock(project_id):
        try:
            decision_map = daemon.store.get_decision_map(project_id)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project not found: {e}")

        pending_proposals: list[dict[str, Any]] = []
        for p_path in daemon.store.proposals.glob("*.json"):
            try:
                p_data = json.loads(p_path.read_text(encoding="utf-8"))
                if (
                    p_data.get("status") == "PROPOSED"
                    and p_data.get("transaction", {}).get("project_id") == project_id
                ):
                    pending_proposals.append({
                        "proposal_id": p_data.get("proposal_id"),
                        "created_at": p_data.get("created_at"),
                        "requested_by": p_data.get("requested_by"),
                        "rationale": p_data.get("transaction", {}).get("rationale"),
                        "operations": p_data.get("transaction", {}).get("operations", []),
                    })
            except (OSError, json.JSONDecodeError):
                logger.debug("Skipping unreadable proposal %s", p_path)

        return {
            **decision_map,
            "pending_proposals": pending_proposals,
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="UuMA State Daemon for Brainstormer Live")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind (default: 8772)")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
