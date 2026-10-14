"""Deterministic R1-R4 reminder decisions, without persistence or notification effects."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import ConfigDict

from ..models import StrictModel
from .life_models import (
    LOCAL_TIMEZONE,
    DailyAnchor,
    LifeSettings,
    ReminderOccurrence,
    require_aware,
)


class ReminderDecision(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    instance_id: str
    action: Literal[
        "ELIGIBLE",
        "WAIT",
        "SUPPRESS",
        "EXPIRE",
        "QUOTA_EXHAUSTED",
        "IN_FLIGHT",
        "ALREADY_HANDLED",
        "LOOKUP_RECEIPT",
    ]
    reason: str


class ReminderGroup(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    group_id: str
    owner_id: str
    delivery_target_id: str
    due_at: datetime
    instance_ids: tuple[str, ...]


class ReminderPlan(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decisions: tuple[ReminderDecision, ...]
    groups: tuple[ReminderGroup, ...]


def evaluate_reminder(
    occurrence: ReminderOccurrence,
    now: datetime,
    settings: LifeSettings | None = None,
) -> ReminderDecision:
    """Return a decision only; ELIGIBLE still requires a service-side atomic claim."""
    require_aware(now, "evaluation time")
    policy = settings or LifeSettings()

    def decision(action: str, reason: str) -> ReminderDecision:
        return ReminderDecision(instance_id=occurrence.instance_id, action=action, reason=reason)

    if occurrence.delivery_status == "DELIVERED":
        return decision("ALREADY_HANDLED", "DELIVERY_CONFIRMED")
    if occurrence.delivery_status == "DELIVERY_UNKNOWN":
        return decision("LOOKUP_RECEIPT", "DELIVERY_UNCERTAIN")
    if occurrence.delivery_status == "FAILED" and not occurrence.failure_proven_unsent:
        return decision("LOOKUP_RECEIPT", "NO_PROOF_OF_UNSENT_EFFECT")
    if occurrence.active_claim or occurrence.delivery_status in {"QUEUED", "SENDING"}:
        return decision("IN_FLIGHT", "EXISTING_CLAIM_OR_ATTEMPT")
    if occurrence.delivery_status in {"EXPIRED", "SUPPRESSED"}:
        return decision("ALREADY_HANDLED", "TERMINAL_OCCURRENCE")
    if not occurrence.enabled or occurrence.reminder_limit == 0:
        return decision("SUPPRESS", "REMINDERS_DISABLED")
    if policy.suppress_when_complete and occurrence.target_status == "met":
        return decision("SUPPRESS", "TARGET_MET")
    if now < max(occurrence.window_start, occurrence.due_at):
        return decision("WAIT", "WINDOW_NOT_STARTED")
    if now >= occurrence.window_end:
        return decision("EXPIRE", "WINDOW_ENDED")
    if occurrence.consumed_count + occurrence.reserved_count >= occurrence.reminder_limit:
        return decision("QUOTA_EXHAUSTED", "INSTANCE_QUOTA_USED_OR_RESERVED")
    return decision("ELIGIBLE", "WITHIN_WINDOW_AND_QUOTA")


def plan_reminder_groups(
    occurrences: list[ReminderOccurrence],
    now: datetime,
    settings: LifeSettings | None = None,
) -> ReminderPlan:
    """Group simultaneous candidates; do not reserve quota or report a delivered message."""
    policy = settings or LifeSettings()
    identities = [item.instance_id for item in occurrences]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate instance in reminder planning input")
    decisions = tuple(evaluate_reminder(item, now, policy) for item in occurrences)
    eligible = {item.instance_id for item in decisions if item.action == "ELIGIBLE"}
    buckets: dict[tuple[str, ...], list[ReminderOccurrence]] = {}
    for item in occurrences:
        if item.instance_id not in eligible:
            continue
        key = (item.owner_id, item.delivery_target_id, item.due_at.astimezone(UTC).isoformat())
        if not policy.group_simultaneous:
            key += (item.instance_id,)
        buckets.setdefault(key, []).append(item)
    priority = {"high": 0, "normal": 1, "low": 2}
    groups = []
    for key in sorted(buckets):
        members = sorted(
            buckets[key],
            key=lambda item: (priority[item.importance], item.habit_id, item.instance_id),
        )
        digest = hashlib.sha256(json.dumps(key, separators=(",", ":")).encode()).hexdigest()
        groups.append(
            ReminderGroup(
                group_id=f"reminder_group_{digest}",
                owner_id=members[0].owner_id,
                delivery_target_id=members[0].delivery_target_id,
                due_at=members[0].due_at.astimezone(UTC),
                instance_ids=tuple(item.instance_id for item in members),
            )
        )
    return ReminderPlan(decisions=decisions, groups=tuple(groups))


def advance_on_anchor(
    occurrence: ReminderOccurrence,
    anchor: DailyAnchor,
    settings: LifeSettings | None = None,
) -> ReminderOccurrence:
    """Advance a same-day pending instance; identity and consumed quota stay unchanged.

    This accepts an internal semantic anchor, not raw natural language. The input
    adapter must verify that the source is an explicit current user report.
    """
    if anchor.owner_id != occurrence.owner_id:
        raise ValueError("anchor owner differs from occurrence owner")
    policy = settings or LifeSettings()
    matching_wake = (
        occurrence.trigger == "wake"
        and anchor.kind in {"wake", "day_start"}
        and policy.advance_explicit_wake_or_day_start
    )
    matching_bedtime = (
        occurrence.trigger == "bedtime"
        and anchor.kind == "bedtime"
        and policy.advance_explicit_bedtime
    )
    if not (matching_wake or matching_bedtime):
        return occurrence
    if anchor.occurred_at.astimezone(LOCAL_TIMEZONE).date() != occurrence.business_date:
        return occurrence
    if anchor.occurred_at >= occurrence.due_at:
        return occurrence
    if occurrence.delivery_status not in {"NOT_SENT", "FAILED"}:
        return occurrence
    if occurrence.delivery_status == "FAILED" and not occurrence.failure_proven_unsent:
        return occurrence
    if occurrence.active_claim or occurrence.reserved_count or occurrence.consumed_count:
        return occurrence
    values = occurrence.model_dump()
    values.update(
        due_at=anchor.occurred_at,
        window_start=anchor.occurred_at,
        window_end=anchor.occurred_at + timedelta(minutes=policy.fixed_point_grace_minutes),
        fallback_due_at=occurrence.fallback_due_at or occurrence.due_at,
    )
    return ReminderOccurrence.model_validate(values)
