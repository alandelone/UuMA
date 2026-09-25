"""Cookie-free command broker for the optional UuMA Chrome extension."""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path


class ExtensionUnavailable(RuntimeError):
    pass


class ExtensionBroker:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Condition()
        self.queues = defaultdict(deque)
        self.results = {}
        self.last_seen = {}
        self.pairs = self._load()

    def _load(self) -> dict[str, str]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.pairs, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def pair(self, alias: str) -> str:
        token = secrets.token_urlsafe(32)
        with self.lock:
            self.pairs[alias] = self._digest(token)
            self.last_seen.pop(alias, None)
            self._save()
        return token

    def authenticate(self, alias: str, token: str) -> None:
        expected = self.pairs.get(alias)
        if not expected or not secrets.compare_digest(expected, self._digest(token)):
            raise PermissionError("Invalid extension pairing")

    def is_paired(self, alias: str) -> bool:
        return alias in self.pairs

    def connected(self, alias: str) -> bool:
        return time.monotonic() - self.last_seen.get(alias, 0) < 45

    def poll(self, alias: str, token: str, timeout: float = 20) -> dict | None:
        self.authenticate(alias, token)
        deadline = time.monotonic() + timeout
        with self.lock:
            self.last_seen[alias] = time.monotonic()
            while not self.queues[alias]:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self.lock.wait(remaining)
                self.last_seen[alias] = time.monotonic()
            return self.queues[alias].popleft()

    def complete(self, alias: str, token: str, command_id: str, result: dict) -> None:
        self.authenticate(alias, token)
        with self.lock:
            self.last_seen[alias] = time.monotonic()
            self.results[command_id] = result
            self.lock.notify_all()

    def call(self, alias: str, action: str, payload: dict | None = None,
             timeout: float = 30) -> dict:
        if not self.is_paired(alias):
            raise ExtensionUnavailable("EXTENSION_CONNECTION_REQUIRED")
        command_id = uuid.uuid4().hex
        command = {"id": command_id, "action": action, "payload": payload or {}}
        deadline = time.monotonic() + timeout
        with self.lock:
            self.queues[alias].append(command)
            self.lock.notify_all()
            while command_id not in self.results:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ExtensionUnavailable("EXTENSION_UNAVAILABLE")
                self.lock.wait(remaining)
            result = self.results.pop(command_id)
        if not result.get("ok"):
            raise ExtensionUnavailable(result.get("error") or "EXTENSION_COMMAND_FAILED")
        return result.get("value") or {}
