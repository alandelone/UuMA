"""Narrow human-command authorization and durable receipts for topic creation."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
from pathlib import Path


def command_material(payload: dict, timestamp: str, nonce: str, user: str) -> bytes:
    return json.dumps(
        {"payload": payload, "timestamp": timestamp, "nonce": nonce, "user": user},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def sign_command(secret: bytes, payload: dict, timestamp: str, nonce: str, user: str) -> str:
    material = command_material(payload, timestamp, nonce, user)
    return hmac.new(secret, material, hashlib.sha256).hexdigest()


class CommandAuthorizer:
    def __init__(self, database: Path, secret_file: Path, allowed_users: set[str]):
        self.secret_file, self.allowed_users = secret_file, allowed_users
        valid_users = all(user.isascii() and user.isdigit() for user in allowed_users)
        if not allowed_users or not valid_users:
            raise ValueError("Topic commands require configured Telegram user IDs")
        self._secret()
        self.database = database
        with sqlite3.connect(database) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS navigation_commands (
                    nonce TEXT PRIMARY KEY, intent_digest TEXT NOT NULL,
                    telegram_user TEXT NOT NULL, signed_at INTEGER NOT NULL,
                    phase TEXT NOT NULL, result_json TEXT
                )
            """)
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS navigation_command_intents "
                "ON navigation_commands(intent_digest)"
            )

    def _secret(self) -> bytes:
        secret = self.secret_file.read_bytes().strip()
        if len(secret) < 32:
            raise ValueError("Topic command secret must contain at least 32 bytes")
        return secret

    def reserve(
        self, payload: dict, headers, *, now: float | None = None,
    ) -> tuple[str, dict | None]:
        """Authenticate one narrow intent, then reserve it before any business write."""
        user = headers.get("x-uuma-command-user", "")
        nonce = headers.get("x-uuma-command-nonce", "")
        timestamp = headers.get("x-uuma-command-timestamp", "")
        signature = headers.get("x-uuma-command-signature", "")
        if (
            payload.get("action") != "create" or user not in self.allowed_users
            or not 16 <= len(nonce) <= 128
            or not 1 <= len(timestamp) <= 12 or not timestamp.isascii()
            or not timestamp.isdigit() or len(signature) != 64
            or any(character not in "0123456789abcdef" for character in signature)
        ):
            raise PermissionError("Invalid human topic command")
        expected = sign_command(self._secret(), payload, timestamp, nonce, user)
        if not hmac.compare_digest(expected, signature):
            raise PermissionError("Invalid human topic command")
        digest = hashlib.sha256(json.dumps(
            {"payload": payload, "user": user}, sort_keys=True,
            separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest()
        with sqlite3.connect(self.database, timeout=30) as db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT intent_digest,phase,result_json FROM navigation_commands WHERE nonce=?",
                (nonce,),
            ).fetchone()
            if previous is None:
                previous = db.execute(
                    "SELECT intent_digest,phase,result_json FROM navigation_commands "
                    "WHERE intent_digest=?", (digest,),
                ).fetchone()
            if previous:
                if previous[0] != digest:
                    raise PermissionError("Topic command nonce conflicts with its original intent")
                if previous[1] != "COMPLETED":
                    raise RuntimeError("Topic command outcome is uncertain; reconcile before retry")
                # Returning an existing receipt cannot create another object, even after its TTL.
                return nonce, json.loads(previous[2])
            current = time.time() if now is None else now
            if not 0 <= current - int(timestamp) <= 300:
                raise PermissionError("Human topic command expired")
            db.execute(
                "INSERT INTO navigation_commands VALUES (?,?,?,?,?,NULL)",
                (nonce, digest, user, int(timestamp), "RESERVED"),
            )
        return nonce, None

    def complete(self, nonce: str, result: dict) -> None:
        with sqlite3.connect(self.database, timeout=30) as db:
            db.execute("PRAGMA synchronous=FULL")
            updated = db.execute(
                "UPDATE navigation_commands SET phase='COMPLETED',result_json=? "
                "WHERE nonce=? AND phase='RESERVED'",
                (json.dumps(result, ensure_ascii=False), nonce),
            )
            if updated.rowcount != 1:
                raise RuntimeError("Topic command has no current reservation")
