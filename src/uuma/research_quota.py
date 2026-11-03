"""Daily optional research ceilings, separate from cumulative reporting and provider quota."""

from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

METRICS = {
    "active_seconds": "active_seconds", "sources": "sources_used",
    "model_tokens": "model_tokens_used", "search_queries": "search_queries_used",
}


class ResearchQuota:
    def __init__(self, limits: dict[str, float] | None = None, timezone: str = "UTC"):
        self.zone = ZoneInfo(timezone)
        self.limits = dict(limits or {})
        if set(self.limits) - METRICS.keys():
            raise ValueError("Unknown daily research quota metric")
        for value in self.limits.values():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError("Daily limits must be positive finite numbers")
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Daily limits must be positive finite numbers")

    @classmethod
    def from_env(cls) -> ResearchQuota:
        limits = json.loads(os.environ.get("UUMA_RESEARCH_DAILY_LIMITS_JSON", "{}"))
        if not isinstance(limits, dict):
            raise TypeError("UUMA_RESEARCH_DAILY_LIMITS_JSON must be a JSON object")
        return cls(limits, os.environ.get("UUMA_RESEARCH_QUOTA_TIMEZONE", "UTC"))

    @staticmethod
    def delta(before: dict, after: dict) -> dict[str, float]:
        return {key: max(0, float(after.get(field, 0)) - float(before.get(field, 0)))
                for key, field in METRICS.items()}

    def snapshot(self, conn, *, now: datetime | None = None, pending: dict | None = None) -> dict:
        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError("Quota clock must include a timezone")
        start = now.astimezone(self.zone).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        usage = dict.fromkeys(METRICS, 0.0)
        # Charge positive changes once, at their recorded event time. Historical receipts stay intact.
        for row in conn.execute(
            "SELECT payload_json FROM knowledge_events WHERE aggregate_type = 'research_run' "
            "AND occurred_at >= ? AND occurred_at < ? AND event_type IN "
            "('RESEARCH_RUN_CYCLE_RECORDED','RESEARCH_RUN_UPDATED','RESEARCH_RUN_STARTED')",
            (start.astimezone(UTC).isoformat(), end.astimezone(UTC).isoformat()),
        ):
            payload = json.loads(row[0])
            after = payload.get("after", payload.get("record", {}))
            for key, value in self.delta(payload.get("before", {}), after).items():
                usage[key] += value
        for key, value in (pending or {}).items():
            if key not in METRICS or not math.isfinite(value) or value < 0:
                raise ValueError("Invalid pending research usage")
            usage[key] += value
        remaining = {k: max(0, self.limits[k] - usage[k]) if k in self.limits else None
                     for k in METRICS}
        return {
            **{k: self.limits.get(k) for k in METRICS},
            "mode": "daily" if self.limits else "provider",
            "scope": "wisdom-research", "timezone": self.zone.key,
            "period_start": start.astimezone(UTC).isoformat(),
            "reset_at": end.astimezone(UTC).isoformat(),
            "usage": usage, "remaining": remaining,
            "exhausted": any(remaining[k] == 0 for k in self.limits),
            "provider_reset_at": None,
            "usage_kind": "recorded research usage; model tokens may be estimated",
        }


def quota_delay(error: Exception) -> int | None:
    """Recognize explicit provider refusal; an unknown reset uses a bounded probe delay."""
    import re

    text = str(error)
    explicit = getattr(error, "code", None) == 429 or re.search(
        r"\b429\b|RESOURCE_EXHAUSTED|QUOTA_EXCEEDED|quota (?:exhausted|exceeded)|rate.limit",
        text, re.IGNORECASE,
    )
    if not explicit and not getattr(error, "quota_wait", False):
        return None
    delay = getattr(error, "retry_after_seconds", 1800)
    headers = getattr(error, "headers", None)
    if headers and headers.get("Retry-After"):
        from .safe_web import SafeWebFetcher
        try:
            delay = SafeWebFetcher._retry_after_seconds(headers.get("Retry-After"))
        except (TypeError, ValueError, OverflowError):
            delay = 1800
    return max(1, min(86_400, int(delay)))
