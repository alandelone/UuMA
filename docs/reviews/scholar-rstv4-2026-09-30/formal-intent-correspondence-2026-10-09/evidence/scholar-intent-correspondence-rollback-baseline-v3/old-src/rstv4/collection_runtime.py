"""Durable Collection resource policy and independently observed worker presence."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS collection_budget_events (
  event_id TEXT PRIMARY KEY,
  collection_id TEXT NOT NULL REFERENCES collections(collection_id),
  request_id TEXT NOT NULL UNIQUE,
  request_json TEXT NOT NULL,
  limits_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS collection_runtime_state (
  collection_id TEXT PRIMARY KEY REFERENCES collections(collection_id),
  active_seconds REAL NOT NULL DEFAULT 0,
  active_since TEXT,
  stop_reason_json TEXT,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS acquisition_worker_presence (
  worker_id TEXT PRIMARY KEY,
  instance_id TEXT NOT NULL,
  role TEXT NOT NULL,
  hostname TEXT NOT NULL,
  process_id INTEGER NOT NULL,
  state TEXT NOT NULL,
  job_id TEXT,
  started_at TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS collection_reference_frontier (
  collection_id TEXT NOT NULL REFERENCES collections(collection_id),
  reference_entry_id TEXT NOT NULL REFERENCES reference_entries(reference_entry_id),
  state TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(collection_id,reference_entry_id)
);
CREATE TABLE IF NOT EXISTS collection_candidate_frontier (
  collection_id TEXT NOT NULL REFERENCES collections(collection_id),
  paper_id TEXT NOT NULL REFERENCES papers(paper_id),
  state TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(collection_id,paper_id)
);
"""


class CollectionBudgetExceeded(ValueError):
    """The budget stop has been persisted; input files and frontier remain intact."""


def now() -> datetime:
    return datetime.now(UTC)


def encoded(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_key(prefix: str, value: Any) -> str:
    return prefix + "_" + hashlib.sha256(encoded(value).encode()).hexdigest()[:32]


def current_limits(conn: sqlite3.Connection, collection_id: str) -> dict | None:
    row = conn.execute(
        "SELECT limits_json FROM collection_budget_events WHERE collection_id=? "
        "ORDER BY rowid DESC LIMIT 1", (collection_id,),
    ).fetchone()
    return json.loads(row[0]) if row else None


def initialize_policy(conn: sqlite3.Connection, collection_id: str, request_id: str,
                      limits: dict | None, timestamp: str) -> None:
    if limits is None:
        return
    conn.execute("INSERT INTO collection_runtime_state VALUES(?,0,?,NULL,?)",
                 (collection_id, timestamp, timestamp))
    result = {"collection_id": collection_id, "limits": limits, "revision": 1}
    conn.execute("INSERT INTO collection_budget_events VALUES(?,?,?,?,?,?,?)",
                 (stable_key("budget", request_id), collection_id, "initial:" + request_id,
                  encoded({"collection_id": collection_id, "limits": limits}), encoded(limits),
                  encoded(result), timestamp))


def elapsed(conn: sqlite3.Connection, collection_id: str, observed: datetime) -> float:
    row = conn.execute("SELECT active_seconds,active_since FROM collection_runtime_state "
                       "WHERE collection_id=?", (collection_id,)).fetchone()
    if row is None:
        return 0.0
    additional = max(0.0, (observed - datetime.fromisoformat(row[1])).total_seconds()) if row[1] else 0.0
    return float(row[0]) + additional


def usage(conn: sqlite3.Connection, collection_id: str, observed: datetime | None = None) -> dict:
    observed = observed or now()
    papers = conn.execute("SELECT COUNT(*) FROM collection_memberships WHERE collection_id=?",
                          (collection_id,)).fetchone()[0]
    attempts = conn.execute("SELECT COUNT(*) FROM acquisition_attempts a JOIN acquisition_jobs j "
                            "ON j.job_id=a.job_id WHERE j.collection_id=?", (collection_id,)).fetchone()[0]
    size = conn.execute(
        "SELECT COALESCE(SUM(size_bytes),0) FROM (SELECT f.sha256,MAX(f.size_bytes) AS size_bytes "
        "FROM source_file_versions f JOIN collection_memberships m ON m.paper_id=f.paper_id "
        "WHERE m.collection_id=? GROUP BY f.sha256)", (collection_id,),
    ).fetchone()[0]
    state = conn.execute("SELECT stop_reason_json FROM collection_runtime_state WHERE collection_id=?",
                         (collection_id,)).fetchone()
    return {"papers": papers, "registered_pdf_bytes": size, "task_attempts": attempts,
            "active_seconds": elapsed(conn, collection_id, observed),
            "stop_reason": json.loads(state[0]) if state and state[0] else None,
            "observed_at": observed.isoformat()}


def transition(conn: sqlite3.Connection, collection_id: str, active: bool,
               observed: datetime | None = None, reason: dict | None = None) -> None:
    if current_limits(conn, collection_id) is None:
        return
    observed = observed or now()
    total = elapsed(conn, collection_id, observed)
    conn.execute(
        "INSERT INTO collection_runtime_state VALUES(?,?,?,?,?) "
        "ON CONFLICT(collection_id) DO UPDATE SET active_seconds=excluded.active_seconds,"
        "active_since=excluded.active_since,stop_reason_json=excluded.stop_reason_json,"
        "updated_at=excluded.updated_at",
        (collection_id, total, observed.isoformat() if active else None,
         encoded(reason) if reason else None, observed.isoformat()),
    )


def pause_for_budget(conn: sqlite3.Connection, collection_id: str, reason: dict) -> None:
    observed = now()
    owner = conn.execute("SELECT status FROM collections WHERE collection_id=?", (collection_id,)).fetchone()
    if owner and owner[0] == "ACTIVE":
        conn.execute("UPDATE collections SET status='PAUSED',revision=revision+1,updated_at=? "
                     "WHERE collection_id=?", (observed.isoformat(), collection_id))
    transition(conn, collection_id, False, observed, reason)


def dispatch_stop(conn: sqlite3.Connection, collection_id: str) -> dict | None:
    limits = current_limits(conn, collection_id)
    if limits is None:
        return None
    measured = usage(conn, collection_id)
    for dimension in ("papers", "registered_pdf_bytes"):
        limit = limits.get("max_" + dimension)
        if limit is not None and measured[dimension] > limit:
            return {"kind": "BUDGET_EXHAUSTED", "dimension": dimension,
                    "limit": limit, "observed": measured[dimension]}
    for dimension in ("task_attempts", "active_seconds"):
        limit = limits.get("max_" + dimension)
        if limit is not None and measured[dimension] >= limit:
            return {"kind": "BUDGET_EXHAUSTED", "dimension": dimension,
                    "limit": limit, "observed": measured[dimension]}
    return None


def can_add_paper(conn: sqlite3.Connection, collection_id: str, paper_id: str | None) -> bool:
    if paper_id and conn.execute("SELECT 1 FROM collection_memberships WHERE collection_id=? AND paper_id=?",
                                 (collection_id, paper_id)).fetchone():
        return True
    limits = current_limits(conn, collection_id)
    if limits is None or limits.get("max_papers") is None:
        return True
    count = conn.execute("SELECT COUNT(*) FROM collection_memberships WHERE collection_id=?",
                         (collection_id,)).fetchone()[0]
    if count < limits["max_papers"]:
        return True
    pause_for_budget(conn, collection_id, {"kind": "BUDGET_EXHAUSTED", "dimension": "papers",
                                          "limit": limits["max_papers"], "observed": count})
    return False


def file_capacity(conn: sqlite3.Connection, collection_id: str, file_sha: str, size: int) -> bool:
    limits = current_limits(conn, collection_id)
    if limits is None or limits.get("max_registered_pdf_bytes") is None:
        return True
    already = conn.execute(
        "SELECT 1 FROM source_file_versions f JOIN collection_memberships m ON m.paper_id=f.paper_id "
        "WHERE m.collection_id=? AND f.sha256=?", (collection_id, file_sha),
    ).fetchone()
    total = usage(conn, collection_id)["registered_pdf_bytes"] + (0 if already else size)
    if total <= limits["max_registered_pdf_bytes"]:
        return True
    pause_for_budget(conn, collection_id, {"kind": "BUDGET_EXHAUSTED", "dimension": "registered_pdf_bytes",
                                          "limit": limits["max_registered_pdf_bytes"], "observed": total})
    return False


def worker_rows(conn: sqlite3.Connection, observed: datetime | None = None) -> list[dict]:
    observed = observed or now()
    rows = []
    for row in conn.execute("SELECT * FROM acquisition_worker_presence ORDER BY role,worker_id"):
        item = dict(row)
        item["recent_heartbeat"] = datetime.fromisoformat(item["expires_at"]) > observed
        item["observation"] = "STOPPED" if item["state"] == "STOPPED" else (
            "RECENT_HEARTBEAT" if item["recent_heartbeat"] else "HEARTBEAT_EXPIRED")
        rows.append(item)
    return rows
