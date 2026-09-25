"""Durable, identity-scoped ChatGPT consultation queue in the control database."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

PERMISSIONS = {
    "orchestrator": {"chat", "search", "deep_research"},
    "brainstormer": {"chat", "search", "deep_research"},
    "wisdom-oldman": {"chat", "search", "deep_research"},
    "forge-lab-bot": {"search"},
}
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
ACTIVE = {"PREFLIGHT", "SENDING", "RUNNING"}


class Consultation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=1, max_length=200)
    project: str = Field(default="general", min_length=1, max_length=200)
    thread: str = Field(default="main", min_length=1, max_length=100)
    mode: str = "chat"
    prompt: str = Field(min_length=1, max_length=48000)
    idempotency_key: str = Field(min_length=1, max_length=200)
    sites: list[str] = Field(default_factory=list, max_length=20)
    account: str | None = None
    parent_id: str | None = None


def conversation_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.netloc != "chatgpt.com"
            or not re.fullmatch(r"/c/[a-zA-Z0-9-]+", parsed.path)
            or parsed.query or parsed.fragment):
        raise ValueError("Use a private https://chatgpt.com/c/... conversation URL.")
    return value


class BridgeStore:
    def __init__(self, database: Path):
        self.database = database
        database.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS chatgpt_accounts (
                    alias TEXT PRIMARY KEY, identity TEXT NOT NULL, workspace TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'AUTH_REQUIRED',
                    capabilities TEXT NOT NULL DEFAULT '[]', verified_at REAL,
                    action TEXT, error TEXT, chrome_profile TEXT,
                    confirmed_capabilities TEXT NOT NULL DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS chatgpt_routes (
                    agent TEXT PRIMARY KEY, account TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chatgpt_threads (
                    account TEXT NOT NULL, agent TEXT NOT NULL, project TEXT NOT NULL,
                    thread TEXT NOT NULL, url TEXT NOT NULL,
                    PRIMARY KEY(account, agent, project, thread), UNIQUE(account, url)
                );
                CREATE TABLE IF NOT EXISTS chatgpt_requests (
                    id TEXT PRIMARY KEY, agent TEXT NOT NULL, account TEXT NOT NULL,
                    run_id TEXT NOT NULL, project TEXT NOT NULL, thread TEXT NOT NULL,
                    mode TEXT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL,
                    idem TEXT NOT NULL, status TEXT NOT NULL, url TEXT,
                    result TEXT, error TEXT, created REAL NOT NULL, updated REAL NOT NULL,
                    submitted REAL, UNIQUE(agent, idem)
                );
                CREATE INDEX IF NOT EXISTS chatgpt_queue ON chatgpt_requests(status, created);
                CREATE TABLE IF NOT EXISTS chatgpt_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT NOT NULL,
                    actor TEXT NOT NULL, kind TEXT NOT NULL, at REAL NOT NULL, detail TEXT NOT NULL
                );
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(chatgpt_accounts)")}
            if "chrome_profile" not in columns:
                db.execute("ALTER TABLE chatgpt_accounts ADD COLUMN chrome_profile TEXT")
            if "confirmed_capabilities" not in columns:
                db.execute(
                    "ALTER TABLE chatgpt_accounts ADD COLUMN confirmed_capabilities "
                    "TEXT NOT NULL DEFAULT '[]'"
                )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def event(db, subject: str, actor: str, kind: str, detail: dict | None = None):
        db.execute("INSERT INTO chatgpt_events(subject,actor,kind,at,detail) VALUES(?,?,?,?,?)",
                   (subject, actor, kind, time.time(), json.dumps(detail or {})))

    @staticmethod
    def authorize(agent: str, mode: str | None = None):
        if agent not in PERMISSIONS or (mode and mode not in PERMISSIONS[agent]):
            raise PermissionError("This identity is not allowed to use this bridge capability.")

    @staticmethod
    def require_run(db, agent: str, run_id: str):
        row = db.execute("""SELECT r.agent_id,r.status,t.current_run_id,t.status AS task_status
            FROM runs r JOIN tasks t ON t.task_id=r.task_id WHERE r.run_id=?""",
                         (run_id,)).fetchone()
        if (not row or row["agent_id"] != agent or row["current_run_id"] != run_id
                or row["status"] not in {"PENDING", "RUNNING", "PAUSED", "BLOCKED"}
                or row["task_status"] in {"COMPLETED", "CANCELLED"}):
            raise PermissionError("A current, nonterminal UuMA run owned by this agent is required.")

    def add_account(self, alias: str, identity: str, workspace: str):
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", alias):
            raise ValueError("Account alias must contain lowercase letters, digits or hyphens.")
        if not identity.strip() or not workspace.strip():
            raise ValueError("Expected account email and workspace are required.")
        with self.connect() as db:
            db.execute("INSERT INTO chatgpt_accounts(alias,identity,workspace) VALUES(?,?,?)",
                       (alias, identity.strip().casefold(), workspace.strip()))
            for agent in PERMISSIONS:
                db.execute("INSERT OR IGNORE INTO chatgpt_routes VALUES(?,?)", (agent, alias))
            self.event(db, alias, "human", "ACCOUNT_ADDED")

    def accounts(self) -> list[dict]:
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM chatgpt_accounts ORDER BY alias")]

    def account_action(self, alias: str, action: str):
        if action not in {"open", "verify", "enable", "disable"}:
            raise ValueError("Unknown account action.")
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM chatgpt_accounts WHERE alias=?", (alias,)).fetchone():
                raise ValueError("Unknown account.")
            if action in {"enable", "disable"}:
                db.execute("UPDATE chatgpt_accounts SET enabled=?,status=? WHERE alias=?",
                           (action == "enable", "AUTH_REQUIRED" if action == "enable"
                            else "ACCOUNT_DISABLED", alias))
            else:
                db.execute("UPDATE chatgpt_accounts SET action=? WHERE alias=?", (action, alias))
            self.event(db, alias, "human", "ACCOUNT_" + action.upper())

    def account_state(self, alias: str, status: str, capabilities: list[str] | None = None):
        with self.connect() as db:
            if capabilities is not None:
                row = db.execute(
                    "SELECT confirmed_capabilities FROM chatgpt_accounts WHERE alias=?",
                    (alias,),
                ).fetchone()
                confirmed = json.loads(row["confirmed_capabilities"]) if row else []
                capabilities = sorted(set(capabilities) | set(confirmed))
            db.execute("""UPDATE chatgpt_accounts SET status=?,action=NULL,error=?,
                capabilities=COALESCE(?,capabilities),verified_at=? WHERE alias=?""",
                       (status, None if status == "READY" else status,
                        json.dumps(capabilities) if capabilities is not None else None,
                        time.time() if status == "READY" else None, alias))
            self.event(db, alias, "browser", status)

    def confirm_capability(self, alias: str, capability: str, enabled: bool):
        if capability != "deep_research":
            raise ValueError("Only Deep Research supports user confirmation.")
        with self.connect() as db:
            row = db.execute(
                "SELECT capabilities,confirmed_capabilities FROM chatgpt_accounts WHERE alias=?",
                (alias,),
            ).fetchone()
            if not row:
                raise ValueError("Unknown account.")
            confirmed = set(json.loads(row["confirmed_capabilities"]))
            capabilities = set(json.loads(row["capabilities"]))
            if enabled:
                confirmed.add(capability)
                capabilities.add(capability)
            else:
                confirmed.discard(capability)
                capabilities.discard(capability)
            db.execute(
                "UPDATE chatgpt_accounts SET confirmed_capabilities=?,capabilities=? WHERE alias=?",
                (json.dumps(sorted(confirmed)), json.dumps(sorted(capabilities)), alias),
            )
            self.event(
                db,
                alias,
                "human",
                "CAPABILITY_CONFIRMED" if enabled else "CAPABILITY_UNCONFIRMED",
                {"capability": capability},
            )

    def configure_browser(self, alias: str, chrome_profile: str | None):
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM chatgpt_accounts WHERE alias=?", (alias,)).fetchone():
                raise ValueError("Unknown account.")
            db.execute(
                "UPDATE chatgpt_accounts SET chrome_profile=?,status='AUTH_REQUIRED' WHERE alias=?",
                (chrome_profile or None, alias),
            )
            self.event(
                db,
                alias,
                "human",
                "BROWSER_CONFIGURED",
                {"chrome_profile": chrome_profile or "dedicated"},
            )

    def bind(self, agent: str, account: str):
        self.authorize(agent)
        with self.connect() as db:
            if not account:
                db.execute("DELETE FROM chatgpt_routes WHERE agent=?", (agent,))
                self.event(db, agent, "human", "ROUTE_UNBOUND")
                return
            if not db.execute("SELECT 1 FROM chatgpt_accounts WHERE alias=?", (account,)).fetchone():
                raise ValueError("Unknown account.")
            db.execute("INSERT OR REPLACE INTO chatgpt_routes VALUES(?,?)", (agent, account))
            self.event(db, agent, "human", "ROUTE_BOUND", {"account": account})

    def routes(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM chatgpt_routes")]

    def bind_thread(self, account: str, agent: str, project: str, thread: str, url: str):
        self.authorize(agent)
        conversation_url(url)
        with self.connect() as db:
            if db.execute("""SELECT 1 FROM chatgpt_requests WHERE account=? AND agent=?
                AND project=? AND thread=? AND status NOT IN ('COMPLETED','FAILED','CANCELLED')""",
                          (account, agent, project, thread)).fetchone():
                raise ValueError("Finish or cancel pending requests before rebinding a thread.")
            db.execute(
                """INSERT INTO chatgpt_threads VALUES(?,?,?,?,?)
                ON CONFLICT(account,agent,project,thread) DO UPDATE SET url=excluded.url""",
                (account, agent, project, thread, url),
            )
            self.event(db, agent, "human", "THREAD_BOUND", {"account": account})

    def threads(self, agent: str):
        self.authorize(agent)
        with self.connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM chatgpt_threads WHERE agent=?", (agent,))]

    @staticmethod
    def decode(row) -> dict[str, Any]:
        value = dict(row)
        for key in ("payload", "result"):
            value[key] = json.loads(value[key]) if value.get(key) else None
        return value

    def request(self, agent: str, body: Consultation):
        self.authorize(agent, body.mode)
        payload = body.model_dump()
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.connect() as db:
            old = db.execute("SELECT * FROM chatgpt_requests WHERE agent=? AND idem=?",
                             (agent, body.idempotency_key)).fetchone()
            if old:
                if old["digest"] != digest:
                    raise ValueError("Idempotency key already used with a different request.")
                return self.decode(old)
            self.require_run(db, agent, body.run_id)
            route = db.execute("SELECT account FROM chatgpt_routes WHERE agent=?", (agent,)).fetchone()
            if not route:
                raise ValueError("No account binding. Complete bridge onboarding first.")
            account = body.account or route["account"]
            # Temporary overrides are limited to the human's current approved binding.
            if account != route["account"]:
                raise PermissionError("Rebind the agent in the human dashboard before switching.")
            acc = db.execute("SELECT * FROM chatgpt_accounts WHERE alias=?", (account,)).fetchone()
            if not acc or not acc["enabled"]:
                raise ValueError("ACCOUNT_DISABLED")
            if body.parent_id:
                parent = db.execute("SELECT * FROM chatgpt_requests WHERE id=?",
                                    (body.parent_id,)).fetchone()
                if (not parent or parent["agent"] != agent or parent["account"] != account
                        or parent["project"] != body.project or parent["thread"] != body.thread
                        or parent["status"] not in {"COMPLETED", "AWAITING_INPUT"}):
                    raise PermissionError("Continuation must belong to the same agent and thread.")
                if parent["status"] == "AWAITING_INPUT":
                    db.execute("UPDATE chatgpt_requests SET status='COMPLETED',updated=? WHERE id=?",
                               (time.time(), body.parent_id))
                    self.event(db, body.parent_id, agent, "CLARIFICATION_SUPPLIED")
            if db.execute("""SELECT 1 FROM chatgpt_requests WHERE account=? AND agent=?
                AND project=? AND thread=? AND status NOT IN ('COMPLETED','FAILED','CANCELLED')""",
                          (account, agent, body.project, body.thread)).fetchone():
                raise ValueError("This conversation already has an unfinished request.")
            rid, now = "cgpt_" + uuid.uuid4().hex, time.time()
            db.execute("""INSERT INTO chatgpt_requests
                (id,agent,account,run_id,project,thread,mode,payload,digest,idem,status,created,updated)
                VALUES(?,?,?,?,?,?,?,?,?,?,'QUEUED',?,?)""",
                       (rid, agent, account, body.run_id, body.project, body.thread, body.mode,
                        json.dumps(payload), digest, body.idempotency_key, now, now))
            self.event(db, rid, agent, "QUEUED", {"run_id": body.run_id, "mode": body.mode})
            return self.decode(db.execute("SELECT * FROM chatgpt_requests WHERE id=?", (rid,)).fetchone())

    def get(self, agent: str, rid: str):
        self.authorize(agent)
        with self.connect() as db:
            row = db.execute("SELECT * FROM chatgpt_requests WHERE id=? AND agent=?",
                             (rid, agent)).fetchone()
            if not row:
                raise PermissionError("Request not available to this identity.")
            return self.decode(row)

    def recent(self):
        with self.connect() as db:
            return [self.decode(r) for r in db.execute(
                "SELECT * FROM chatgpt_requests ORDER BY created DESC LIMIT 100")]

    def transition(self, rid: str, status: str, *, expected: set[str],
                   error: str | None = None, result: dict | None = None, url: str | None = None):
        with self.connect() as db:
            row = db.execute("SELECT * FROM chatgpt_requests WHERE id=?", (rid,)).fetchone()
            if not row or row["status"] not in expected:
                return False
            db.execute("""UPDATE chatgpt_requests SET status=?,error=?,result=COALESCE(?,result),
                url=COALESCE(?,url),updated=?,submitted=CASE WHEN ?='SENDING'
                THEN COALESCE(submitted,?) ELSE submitted END WHERE id=?""",
                       (status, error, json.dumps(result) if result is not None else None,
                        url, time.time(), status, time.time(), rid))
            self.event(db, rid, "bridge", status, {"error": error} if error else {})
            return True

    def cancel(self, agent: str, rid: str):
        self.get(agent, rid)
        self.transition(rid, "CANCELLED", expected=ACTIVE | {
            "QUEUED", "NEEDS_REVIEW", "PAUSED", "AWAITING_INPUT"})
        return self.get(agent, rid)

    def resume(self, rid: str):
        """Human may resume observation, never authorize blind resubmission."""
        with self.connect() as db:
            row = db.execute("SELECT * FROM chatgpt_requests WHERE id=?", (rid,)).fetchone()
            if not row or row["status"] not in {"PAUSED", "NEEDS_REVIEW"}:
                raise ValueError("Only paused or uncertain requests can resume.")
            status = "RUNNING" if row["submitted"] else "QUEUED"
            db.execute("UPDATE chatgpt_requests SET status=?,updated=?,error=NULL WHERE id=?",
                       (status, time.time(), rid))
            self.event(db, rid, "human", "OBSERVATION_RESUMED")

    def recover(self):
        with self.connect() as db:
            db.execute("UPDATE chatgpt_requests SET status='QUEUED' WHERE status='PREFLIGHT'")
            for row in db.execute("SELECT id FROM chatgpt_requests WHERE status='SENDING'").fetchall():
                db.execute("UPDATE chatgpt_requests SET status='NEEDS_REVIEW',error=? WHERE id=?",
                           ("Submission interrupted; inspect the conversation before resuming.", row[0]))
                self.event(db, row[0], "bridge", "RECOVERY_NEEDS_REVIEW")

    def runnable(self):
        with self.connect() as db:
            return [self.decode(r) for r in db.execute("""SELECT r.* FROM chatgpt_requests r
                JOIN chatgpt_accounts a ON r.account=a.alias
                WHERE r.status='RUNNING' AND a.enabled=1 ORDER BY r.created""")]

    def claim(self):
        with self.connect() as db:
            row = db.execute("""SELECT r.* FROM chatgpt_requests r
                JOIN chatgpt_accounts a ON r.account=a.alias
                WHERE r.status='QUEUED' AND a.enabled=1 AND a.status='READY'
                AND NOT EXISTS (SELECT 1 FROM chatgpt_requests busy
                    WHERE busy.account=r.account AND busy.status IN
                    ('PREFLIGHT','SENDING','RUNNING','PAUSED','NEEDS_REVIEW','AWAITING_INPUT'))
                ORDER BY r.created LIMIT 1""").fetchone()
            if not row:
                return None
            try:
                self.require_run(db, row["agent"], row["run_id"])
            except PermissionError:
                db.execute("UPDATE chatgpt_requests SET status='CANCELLED',error=? WHERE id=?",
                           ("Originating UuMA run is no longer active.", row["id"]))
                self.event(db, row["id"], "bridge", "RUN_INACTIVE")
                return None
            db.execute("UPDATE chatgpt_requests SET status='PREFLIGHT',updated=? WHERE id=?",
                       (time.time(), row["id"]))
            self.event(db, row["id"], "bridge", "PREFLIGHT")
            return self.decode(row)

    def thread_url(self, request: dict):
        with self.connect() as db:
            row = db.execute("""SELECT url FROM chatgpt_threads
                WHERE account=? AND agent=? AND project=? AND thread=?""",
                             tuple(request[k] for k in ("account", "agent", "project", "thread")))
            found = row.fetchone()
            return found[0] if found else None

    def remember_thread(self, request: dict, url: str):
        conversation_url(url)
        with self.connect() as db:
            db.execute("INSERT INTO chatgpt_threads VALUES(?,?,?,?,?) ON CONFLICT "
                       "(account,agent,project,thread) DO UPDATE SET url=excluded.url",
                       (*[request[k] for k in ("account", "agent", "project", "thread")], url))
            db.execute("UPDATE chatgpt_requests SET url=? WHERE id=?", (url, request["id"]))
