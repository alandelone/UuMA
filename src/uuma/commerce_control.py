"""Commerce extraction task and command control plane service using uuma.db."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

TASK_STATUSES = {
    "QUEUED",
    "WAITING_FOR_BROWSER",
    "RUNNING",
    "PAUSED",
    "FAILED",
    "CANCELLED",
    "COMPLETED",
}

COMMAND_ACTIONS = {"EXTRACT", "PAUSE", "RESUME", "CANCEL"}
COMMAND_STATUSES = {"PENDING", "CLAIMED", "EXECUTED", "FAILED", "CANCELLED"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _now_dt() -> datetime:
    return datetime.now(UTC)


def _default_control_db_path() -> Path:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    data_dir = Path(os.environ.get("UUMA_DATA_DIR", local_app_data / "UuMA"))
    override = os.environ.get("UUMA_CONTROL_DB_PATH")
    if override:
        return Path(override)
    # Check for repository-local .uuma-local/uuma.db if running from repo
    local_repo_db = Path.cwd() / ".uuma-local" / "uuma.db"
    if local_repo_db.exists():
        return local_repo_db
    return data_dir / "uuma.db"


class CommerceControlStore:
    def __init__(self, database_path: Path | str | None = None):
        if database_path is None:
            self.database_path = _default_control_db_path()
        else:
            self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.bootstrap()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.database_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def bootstrap(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS commerce_tasks (
                    task_id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    date_range_start TEXT,
                    date_range_end TEXT,
                    max_orders INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    active_lease_token TEXT,
                    lease_expires_at TEXT,
                    fencing_token INTEGER NOT NULL DEFAULT 0,
                    last_checkpoint_json TEXT NOT NULL DEFAULT '{}',
                    error_message TEXT
                );

                CREATE TABLE IF NOT EXISTS commerce_commands (
                    command_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES commerce_tasks(task_id),
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    claimed_by TEXT,
                    fencing_token INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_commerce_tasks_status
                    ON commerce_tasks(status);
                CREATE INDEX IF NOT EXISTS idx_commerce_commands_task
                    ON commerce_commands(task_id, status);
                """
            )

    def create_task(
        self,
        platform: str,
        account_id: str,
        *,
        date_range_start: str | None = None,
        date_range_end: str | None = None,
        max_orders: int | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        tid = task_id.strip() if task_id and task_id.strip() else f"task_{uuid.uuid4().hex}"
        now = _now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO commerce_tasks(
                    task_id, platform, account_id, status, date_range_start,
                    date_range_end, max_orders, created_at, updated_at
                ) VALUES (?, ?, ?, 'QUEUED', ?, ?, ?, ?, ?)
                """,
                (tid, platform.strip(), account_id.strip(), date_range_start, date_range_end, max_orders, now, now),
            )
            # Create the initial EXTRACT command
            cmd_id = f"cmd_{uuid.uuid4().hex}"
            payload = json.dumps(
                {
                    "platform": platform.strip(),
                    "account_id": account_id.strip(),
                    "date_range_start": date_range_start,
                    "date_range_end": date_range_end,
                    "max_orders": max_orders,
                }
            )
            conn.execute(
                """
                INSERT INTO commerce_commands(
                    command_id, task_id, action, status, payload_json, created_at, updated_at
                ) VALUES (?, ?, 'EXTRACT', 'PENDING', ?, ?, ?)
                """,
                (cmd_id, tid, payload, now, now),
            )
        return self.get_task(tid)

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM commerce_tasks WHERE task_id = ?",
                (task_id.strip(),),
            ).fetchone()
            if row is None:
                raise ValueError(f"Task '{task_id}' not found.")
            res = dict(row)
            res["last_checkpoint"] = json.loads(res.pop("last_checkpoint_json") or "{}")
            return res

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        task = self.get_task(task_id)
        # Check lease expiry: if RUNNING and lease expired, transition to WAITING_FOR_BROWSER
        if task["status"] == "RUNNING" and task.get("lease_expires_at"):
            expires_at = datetime.fromisoformat(task["lease_expires_at"])
            if _now_dt() > expires_at:
                self.update_task_status(task_id, "WAITING_FOR_BROWSER", reason="Lease expired without renewal")
                task = self.get_task(task_id)

        checkpoint = task.get("last_checkpoint", {})
        return {
            "task_id": task["task_id"],
            "platform": task["platform"],
            "account_id": task["account_id"],
            "status": task["status"],
            "fencing_token": task["fencing_token"],
            "date_range": {
                "start": task["date_range_start"],
                "end": task["date_range_end"],
            },
            "max_orders": task["max_orders"],
            "last_checkpoint": checkpoint,
            "error_message": task.get("error_message"),
            "created_at": task["created_at"],
            "updated_at": task["updated_at"],
        }

    def update_task_status(
        self,
        task_id: str,
        status: str,
        *,
        reason: str | None = None,
        lease_token: str | None = None,
        fencing_token: int | None = None,
    ) -> dict[str, Any]:
        st = status.strip().upper()
        if st not in TASK_STATUSES:
            raise ValueError(f"Invalid task status: {status}. Allowed: {TASK_STATUSES}")
        with self.connect() as conn:
            task = conn.execute(
                "SELECT fencing_token, active_lease_token FROM commerce_tasks WHERE task_id = ?",
                (task_id.strip(),),
            ).fetchone()
            if not task:
                raise ValueError(f"Task '{task_id}' not found.")
            if fencing_token is not None and task["fencing_token"] != fencing_token:
                raise PermissionError("Stale fencing token: command rejected.")
            if lease_token is not None and task["active_lease_token"] != lease_token:
                raise PermissionError("Stale or invalid lease token.")

            now = _now()
            conn.execute(
                """
                UPDATE commerce_tasks
                SET status = ?, error_message = COALESCE(?, error_message), updated_at = ?
                WHERE task_id = ?
                """,
                (st, reason, now, task_id.strip()),
            )
        return self.get_task(task_id)

    def pause_task(self, task_id: str, reason: str = "User requested pause") -> dict[str, Any]:
        task = self.get_task(task_id)
        if task["status"] in {"COMPLETED", "CANCELLED", "FAILED"}:
            raise ValueError(f"Cannot pause task in terminal status {task['status']}.")
        now = _now()
        cmd_id = f"cmd_{uuid.uuid4().hex}"
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE commerce_tasks SET status = 'PAUSED', updated_at = ? WHERE task_id = ?
                """,
                (now, task_id.strip()),
            )
            conn.execute(
                """
                INSERT INTO commerce_commands(
                    command_id, task_id, action, status, payload_json, created_at, updated_at
                ) VALUES (?, ?, 'PAUSE', 'PENDING', ?, ?, ?)
                """,
                (cmd_id, task_id.strip(), json.dumps({"reason": reason}), now, now),
            )
        return self.get_task(task_id)

    def resume_task(self, task_id: str) -> dict[str, Any]:
        task = self.get_task(task_id)
        if task["status"] != "PAUSED":
            raise ValueError(f"Cannot resume task with status {task['status']}; must be PAUSED.")
        now = _now()
        cmd_id = f"cmd_{uuid.uuid4().hex}"
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE commerce_tasks SET status = 'RUNNING', updated_at = ? WHERE task_id = ?
                """,
                (now, task_id.strip()),
            )
            conn.execute(
                """
                INSERT INTO commerce_commands(
                    command_id, task_id, action, status, payload_json, created_at, updated_at
                ) VALUES (?, ?, 'RESUME', 'PENDING', '{}', ?, ?)
                """,
                (cmd_id, task_id.strip(), now, now),
            )
        return self.get_task(task_id)

    def cancel_task(self, task_id: str, reason: str = "User cancelled") -> dict[str, Any]:
        task = self.get_task(task_id)
        if task["status"] in {"COMPLETED", "CANCELLED"}:
            return task
        now = _now()
        cmd_id = f"cmd_{uuid.uuid4().hex}"
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE commerce_tasks
                SET status = 'CANCELLED', active_lease_token = NULL, lease_expires_at = NULL,
                    error_message = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (reason, now, task_id.strip()),
            )
            conn.execute(
                """
                INSERT INTO commerce_commands(
                    command_id, task_id, action, status, payload_json, created_at, updated_at
                ) VALUES (?, ?, 'CANCEL', 'PENDING', ?, ?, ?)
                """,
                (cmd_id, task_id.strip(), json.dumps({"reason": reason}), now, now),
            )
        return self.get_task(task_id)

    def claim_command(
        self,
        worker_id: str,
        *,
        ttl_seconds: int = 60,
    ) -> dict[str, Any] | None:
        """Atomically claims the next pending command, granting a lease with an incremented fencing token."""
        now_dt = _now_dt()
        now = now_dt.isoformat()
        lease_expires = (now_dt + timedelta(seconds=ttl_seconds)).isoformat()
        lease_token = f"lease_{uuid.uuid4().hex}"

        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cmd = conn.execute(
                """
                SELECT c.*, t.fencing_token AS current_fencing
                FROM commerce_commands c
                JOIN commerce_tasks t ON c.task_id = t.task_id
                WHERE c.status = 'PENDING'
                ORDER BY c.created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if not cmd:
                return None

            new_fencing = cmd["current_fencing"] + 1
            cmd_id = cmd["command_id"]
            task_id = cmd["task_id"]

            conn.execute(
                """
                UPDATE commerce_commands
                SET status = 'CLAIMED', claimed_by = ?, fencing_token = ?, updated_at = ?
                WHERE command_id = ?
                """,
                (worker_id.strip(), new_fencing, now, cmd_id),
            )

            new_task_status = "RUNNING" if cmd["action"] in {"EXTRACT", "RESUME"} else "PAUSED" if cmd["action"] == "PAUSE" else "CANCELLED"
            conn.execute(
                """
                UPDATE commerce_tasks
                SET status = ?, fencing_token = ?, active_lease_token = ?, lease_expires_at = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (new_task_status, new_fencing, lease_token, lease_expires, now, task_id),
            )

            return {
                "command_id": cmd_id,
                "task_id": task_id,
                "action": cmd["action"],
                "payload": json.loads(cmd["payload_json"] or "{}"),
                "fencing_token": new_fencing,
                "lease_token": lease_token,
                "lease_expires_at": lease_expires,
            }

    def renew_lease(
        self,
        task_id: str,
        lease_token: str,
        fencing_token: int,
        *,
        ttl_seconds: int = 60,
    ) -> dict[str, Any]:
        now_dt = _now_dt()
        now = now_dt.isoformat()
        lease_expires = (now_dt + timedelta(seconds=ttl_seconds)).isoformat()

        with self.connect() as conn:
            task = conn.execute(
                """
                SELECT status, active_lease_token, fencing_token
                FROM commerce_tasks WHERE task_id = ?
                """,
                (task_id.strip(),),
            ).fetchone()
            if not task:
                raise ValueError(f"Task '{task_id}' not found.")
            if task["fencing_token"] != fencing_token:
                raise PermissionError(f"Stale fencing token {fencing_token} != current {task['fencing_token']}.")
            if task["active_lease_token"] != lease_token:
                raise PermissionError("Invalid or expired lease token.")
            if task["status"] in {"CANCELLED", "COMPLETED", "FAILED"}:
                raise ValueError(f"Cannot renew lease for task in terminal status {task['status']}.")

            conn.execute(
                """
                UPDATE commerce_tasks
                SET lease_expires_at = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (lease_expires, now, task_id.strip()),
            )

        return {
            "task_id": task_id,
            "lease_token": lease_token,
            "fencing_token": fencing_token,
            "lease_expires_at": lease_expires,
        }

    def report_checkpoint(
        self,
        task_id: str,
        lease_token: str,
        fencing_token: int,
        checkpoint: dict[str, Any],
        *,
        status: str | None = None,
    ) -> dict[str, Any]:
        now = _now()
        with self.connect() as conn:
            task = conn.execute(
                """
                SELECT status, active_lease_token, fencing_token, last_checkpoint_json
                FROM commerce_tasks WHERE task_id = ?
                """,
                (task_id.strip(),),
            ).fetchone()
            if not task:
                raise ValueError(f"Task '{task_id}' not found.")
            if task["fencing_token"] != fencing_token:
                raise PermissionError(f"Stale fencing token {fencing_token} != current {task['fencing_token']}.")
            if task["active_lease_token"] != lease_token:
                raise PermissionError("Invalid or expired lease token.")

            current_cp = json.loads(task["last_checkpoint_json"] or "{}")
            current_cp.update(checkpoint)
            new_cp_json = json.dumps(current_cp, ensure_ascii=False)

            new_status = status.strip().upper() if status else task["status"]
            if new_status not in TASK_STATUSES:
                raise ValueError(f"Invalid status: {new_status}")

            conn.execute(
                """
                UPDATE commerce_tasks
                SET status = ?, last_checkpoint_json = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (new_status, new_cp_json, now, task_id.strip()),
            )

        return self.get_task(task_id)
