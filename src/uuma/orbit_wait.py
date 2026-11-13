"""Durable, bounded scheduling for an existing external discovery request."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any


def external_wait_state(
    previous: dict[str, Any] | None,
    *,
    request_id: str,
    provider: str,
    outcome: str,
    reason: str,
    now: datetime | None = None,
    minimum_delay_seconds: int = 0,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    previous = previous or {}
    same = previous.get("request_id") == request_id and previous.get("provider") == provider
    signature = hashlib.sha256(json.dumps(
        [provider, request_id, outcome, reason], ensure_ascii=False,
    ).encode()).hexdigest()
    unchanged = same and previous.get("signature") == signature
    count = int(previous.get("unchanged_checks", 0)) + 1 if unchanged else 1
    progress_at = previous["last_progress_at"] if unchanged else now.isoformat()
    age = max(0, (now - datetime.fromisoformat(progress_at)).total_seconds())
    attention = outcome == "AUTH_REQUIRED" or age >= 300
    delay = 300 if outcome == "AUTH_REQUIRED" else (30, 60, 120, 300)[min(count - 1, 3)]
    delay = max(delay, min(86_400, max(0, int(minimum_delay_seconds))))
    return {
        "request_id": request_id, "provider": provider, "outcome": outcome,
        "reason": reason, "signature": signature, "unchanged_checks": count,
        "started_at": previous["started_at"] if same else now.isoformat(),
        "last_progress_at": progress_at, "checked_at": now.isoformat(),
        "next_check_at": (now + timedelta(seconds=delay)).isoformat(),
        "retry_after_seconds": delay,
        "status": "REQUIRES_ATTENTION" if attention else "WAITING_EXTERNAL",
    }
