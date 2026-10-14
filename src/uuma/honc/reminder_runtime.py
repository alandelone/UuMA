"""Persistent daily occurrences, fenced reservations and append-only send receipts.

Delivery is injected by the Hermes adapter. Neither a clock tick nor a queue
acknowledgment is treated as a user observation or a delivered notification.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import uuid4

from .life_models import (
    LOCAL_TIMEZONE,
    DailyAnchor,
    HabitDefinitionInput,
    LifeSettings,
    ObservationTime,
    ReminderOccurrence,
    ReminderRule,
    require_aware,
)
from .life_store import LifeStore, canonical
from .reminder_policy import advance_on_anchor, evaluate_reminder, plan_reminder_groups


def identity(*parts: str) -> str:
    return hashlib.sha256(canonical(parts).encode()).hexdigest()


def local_clock(day: date, clock: str) -> datetime:
    return datetime.combine(day, time.fromisoformat(clock), LOCAL_TIMEZONE)


class ReminderRuntime:
    def __init__(self, store: LifeStore, *, owner_id: str, delivery_target_id: str) -> None:
        self.store, self.owner_id, self.delivery_target_id = store, owner_id, delivery_target_id
        with store.transaction() as connection:
            for statement in (
                """CREATE TABLE IF NOT EXISTS life_occurrences (
                    instance_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, habit_id TEXT NOT NULL,
                    business_date TEXT NOT NULL, snapshot_json TEXT NOT NULL,
                    definition_json TEXT NOT NULL, habit_revision INTEGER NOT NULL,
                    slot_key TEXT NOT NULL, send_times_json TEXT NOT NULL)""",
                """CREATE INDEX IF NOT EXISTS life_occurrences_owner_date
                    ON life_occurrences(owner_id, business_date)""",
                """CREATE TABLE IF NOT EXISTS life_reminder_groups (
                    group_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
                    fence TEXT NOT NULL, state TEXT NOT NULL,
                    instance_ids_json TEXT NOT NULL, content TEXT NOT NULL,
                    created_at TEXT NOT NULL, lease_until TEXT NOT NULL,
                    native_execution_id TEXT, receipt_json TEXT)""",
                """CREATE TABLE IF NOT EXISTS life_reminder_events (
                    event_id TEXT PRIMARY KEY, group_id TEXT,
                    instance_id TEXT, event_type TEXT NOT NULL, payload_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL)""",
                """CREATE TRIGGER IF NOT EXISTS life_reminder_events_no_update
                    BEFORE UPDATE ON life_reminder_events
                    BEGIN SELECT RAISE(ABORT, 'reminder history is immutable'); END""",
                """CREATE TRIGGER IF NOT EXISTS life_reminder_events_no_delete
                    BEFORE DELETE ON life_reminder_events
                    BEGIN SELECT RAISE(ABORT, 'reminder history is immutable'); END""",
                """CREATE TABLE IF NOT EXISTS life_anchors (
                    record_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
                    source_ref TEXT NOT NULL REFERENCES life_sources(source_ref),
                    operation_id TEXT NOT NULL REFERENCES life_operations(operation_id)
                        DEFERRABLE INITIALLY DEFERRED,
                    payload_json TEXT NOT NULL, recorded_at TEXT NOT NULL)""",
                """CREATE TRIGGER IF NOT EXISTS life_anchors_no_update BEFORE UPDATE ON life_anchors
                    BEGIN SELECT RAISE(ABORT, 'anchor history is immutable'); END""",
                """CREATE TRIGGER IF NOT EXISTS life_anchors_no_delete BEFORE DELETE ON life_anchors
                    BEGIN SELECT RAISE(ABORT, 'anchor history is immutable'); END""",
            ):
                connection.execute(statement)

    @staticmethod
    def settings(connection: sqlite3.Connection, owner_id: str) -> LifeSettings:
        row = connection.execute(
            "SELECT r.payload_json FROM life_objects o JOIN life_revisions r "
            "ON o.object_id=r.object_id AND o.head_revision=r.revision "
            "WHERE o.owner_id=? AND o.kind='settings'",
            (owner_id,),
        ).fetchone()
        return LifeSettings.model_validate_json(row[0]) if row else LifeSettings()

    @staticmethod
    def event(connection, now, event_type, *, instance_id=None, group_id=None, payload=None):
        connection.execute(
            "INSERT INTO life_reminder_events VALUES (?, ?, ?, ?, ?, ?)",
            (
                uuid4().hex,
                group_id,
                instance_id,
                event_type,
                canonical(payload or {}),
                now.astimezone(UTC).isoformat(),
            ),
        )

    @staticmethod
    def save_snapshot(connection, value: ReminderOccurrence):
        connection.execute(
            "UPDATE life_occurrences SET snapshot_json=? WHERE instance_id=?",
            (value.model_dump_json(), value.instance_id),
        )

    def compile_day(self, day: date, now: datetime, connection=None) -> None:
        require_aware(now)
        if connection is None:
            with self.store.transaction() as transaction:
                self.compile_day(day, now, transaction)
            return
        settings = self.settings(connection, self.owner_id)
        rows = connection.execute(
            "SELECT o.object_id, r.revision, r.payload_json FROM life_objects o "
            "JOIN life_revisions r ON o.object_id=r.object_id AND o.head_revision=r.revision "
            "WHERE o.owner_id=? AND o.kind='habit_definition' AND r.status='active'",
            (self.owner_id,),
        ).fetchall()
        for row in rows:
            payload = json.loads(row["payload_json"])
            if not payload.get("reminder"):
                continue
            rule = ReminderRule.model_validate(payload["reminder"])
            if rule.recurrence == "weekdays" and day.weekday() not in rule.weekdays:
                continue
            for slot in rule.slots:
                due_clock = (
                    slot.fixed_time
                    or slot.start
                    or slot.fallback_time
                    or (
                        settings.wake_fallback_time
                        if slot.trigger == "wake"
                        else settings.bedtime_fallback_time
                    )
                )
                start = local_clock(day, due_clock)
                end = (
                    local_clock(day, slot.end)
                    if slot.trigger == "time_window"
                    else (start + timedelta(minutes=settings.fixed_point_grace_minutes))
                )
                if end <= start:
                    end += timedelta(days=1)
                send_times = [local_clock(day, value) for value in (slot.send_times or [due_clock])]
                send_times = [
                    value + timedelta(days=1) if value < start else value for value in send_times
                ]
                if any(value < start or value >= end for value in send_times):
                    raise ValueError(
                        "Explicit reminder times must lie within the configured occurrence window"
                    )
                item = ReminderOccurrence(
                    instance_id="instance_"
                    + identity(self.owner_id, row["object_id"], slot.key, day.isoformat()),
                    habit_id=row["object_id"],
                    owner_id=self.owner_id,
                    delivery_target_id=self.delivery_target_id,
                    business_date=day,
                    trigger=slot.trigger,
                    due_at=send_times[0],
                    window_start=start,
                    window_end=end,
                    enabled=rule.enabled,
                    reminder_limit=rule.count,
                    importance=rule.importance,
                )
                inserted = connection.execute(
                    "INSERT OR IGNORE INTO life_occurrences VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        item.instance_id,
                        self.owner_id,
                        item.habit_id,
                        day.isoformat(),
                        item.model_dump_json(),
                        canonical(payload["definition"]),
                        row["revision"],
                        slot.key,
                        canonical([value.isoformat() for value in send_times]),
                    ),
                ).rowcount
                if not inserted:
                    previous_row = connection.execute(
                        "SELECT snapshot_json FROM life_occurrences WHERE instance_id=?",
                        (item.instance_id,),
                    ).fetchone()
                    previous = ReminderOccurrence.model_validate_json(previous_row[0])
                    if (
                        previous.consumed_count == 0
                        and previous.reserved_count == 0
                        and not previous.active_claim
                        and previous.delivery_status == "NOT_SENT"
                        and now < previous.window_start
                    ):
                        connection.execute(
                            "UPDATE life_occurrences SET snapshot_json=?, definition_json=?, habit_revision=?, send_times_json=? WHERE instance_id=?",
                            (
                                item.model_dump_json(),
                                canonical(payload["definition"]),
                                row["revision"],
                                canonical([value.isoformat() for value in send_times]),
                                item.instance_id,
                            ),
                        )
        # Replay explicit real anchors, preserving earliest valid advancement and identity.
        anchors = connection.execute(
            "SELECT payload_json FROM life_anchors WHERE owner_id=? ORDER BY recorded_at",
            (self.owner_id,),
        ).fetchall()
        for row in anchors:
            payload = json.loads(row[0])
            observed = datetime.fromisoformat(payload["observed_at"])
            if observed.astimezone(LOCAL_TIMEZONE).date() == day:
                self.advance_anchor(
                    connection, payload["kind"], observed, payload["source_ref"], settings
                )

    def advance_anchor(self, connection, kind, observed_at, source_ref, settings=None):
        settings = settings or self.settings(connection, self.owner_id)
        anchor = DailyAnchor(
            owner_id=self.owner_id, kind=kind, occurred_at=observed_at, source_ref=source_ref
        )
        rows = connection.execute(
            "SELECT snapshot_json FROM life_occurrences WHERE owner_id=? AND business_date=?",
            (self.owner_id, observed_at.astimezone(LOCAL_TIMEZONE).date().isoformat()),
        ).fetchall()
        for row in rows:
            item = ReminderOccurrence.model_validate_json(row[0])
            advanced = advance_on_anchor(item, anchor, settings)
            if advanced != item:
                self.save_snapshot(connection, advanced)
                self.event(
                    connection,
                    observed_at,
                    "ANCHOR_ADVANCED",
                    instance_id=item.instance_id,
                    payload={"source_ref": source_ref, "due_at": advanced.due_at.isoformat()},
                )

    def bind_checkin(
        self,
        connection,
        *,
        habit_id,
        habit_revision,
        observation: ObservationTime,
        instance_id=None,
        allow_ambiguous=False,
    ):
        day = observation.occurred_date
        if observation.occurred_at:
            day = observation.occurred_at.astimezone(LOCAL_TIMEZONE).date()
        if instance_id:
            row = connection.execute(
                "SELECT * FROM life_occurrences WHERE instance_id=? AND owner_id=? AND habit_id=?",
                (instance_id, self.owner_id, habit_id),
            ).fetchone()
            if row is None or (day is not None and row["business_date"] != day.isoformat()):
                raise ValueError("Occurrence is not in this habit/owner/date scope")
            if row["habit_revision"] != habit_revision:
                raise ValueError("Occurrence definition changed; reload its revision")
            return instance_id
        if day is None:
            return None
        rows = connection.execute(
            "SELECT instance_id, habit_revision FROM life_occurrences WHERE owner_id=? AND habit_id=? AND business_date=?",
            (self.owner_id, habit_id, day.isoformat()),
        ).fetchall()
        if len(rows) == 1:
            if rows[0]["habit_revision"] != habit_revision:
                if allow_ambiguous:
                    return None
                raise ValueError(
                    "Occurrence uses an earlier definition; read its explicit ID, revision and unit"
                )
            return rows[0][0]
        if len(rows) > 1 and not allow_ambiguous:
            raise ValueError("More than one occurrence matches; choose the explicit occurrence")
        return None

    def target_status(self, connection, row):
        definition = HabitDefinitionInput.model_validate_json(row["definition_json"])
        facts = connection.execute(
            "SELECT r.payload_json FROM life_objects o JOIN life_revisions r "
            "ON o.object_id=r.object_id AND o.head_revision=r.revision "
            "WHERE o.owner_id=? AND o.kind='habit' AND r.status!='void' "
            "AND json_extract(r.payload_json, '$.instance_id')=?",
            (self.owner_id, row["instance_id"]),
        ).fetchall()
        values = [json.loads(value[0]) for value in facts]
        if definition.target_period == "week" and definition.target_value is not None:
            day = date.fromisoformat(row["business_date"])
            start = day - timedelta(days=day.weekday())
            end = start + timedelta(days=7)
            facts = connection.execute(
                "SELECT r.payload_json FROM life_objects o JOIN life_revisions r "
                "ON o.object_id=r.object_id AND o.head_revision=r.revision "
                "WHERE o.owner_id=? AND o.kind='habit' AND r.status!='void' "
                "AND json_extract(r.payload_json, '$.habit_id')=?",
                (self.owner_id, row["habit_id"]),
            ).fetchall()
            values = []
            for fact in facts:
                value = json.loads(fact[0])
                observed = value["time"]
                observed_day = observed.get("occurred_date")
                if observed.get("occurred_at"):
                    observed_day = (
                        datetime.fromisoformat(observed["occurred_at"])
                        .astimezone(LOCAL_TIMEZONE)
                        .date()
                        .isoformat()
                    )
                if (
                    observed_day
                    and start.isoformat() <= observed_day < end.isoformat()
                    and (
                        value.get("unit") == definition.unit
                        or (
                            definition.record_type == "count"
                            and value.get("unit") in {None, "time"}
                        )
                    )
                ):
                    values.append(value)
        completed = [value for value in values if value["outcome"] in {"completed", "partial"}]
        if definition.record_type in {"boolean", "text", "selection"}:
            return (
                "met"
                if any(value["outcome"] == "completed" for value in completed)
                else ("partial" if completed else "unknown")
            )
        quantities = [value["value"] for value in completed if value.get("value") is not None]
        if definition.target_value is None and any(
            value["outcome"] == "completed" for value in completed
        ):
            return "met"
        if definition.target_value is not None and sum(quantities) >= definition.target_value:
            return "met"
        return "partial" if completed else "unknown"

    def snapshot(self, connection, row):
        item = ReminderOccurrence.model_validate_json(row["snapshot_json"])
        current = self.store.get_object(connection, self.owner_id, item.habit_id)
        enabled = bool(current and current["status"] == "active" and item.enabled)
        if current and current["payload"].get("reminder"):
            rule = current["payload"]["reminder"]
            enabled = (
                enabled
                and rule["enabled"]
                and rule["count"] > 0
                and any(slot["key"] == row["slot_key"] for slot in rule["slots"])
            )
            item = item.model_copy(
                update={
                    "reminder_limit": min(item.reminder_limit, rule["count"]),
                    "importance": rule["importance"],
                }
            )
        return item.model_copy(
            update={"target_status": self.target_status(connection, row), "enabled": enabled}
        )

    def refresh(self, connection, now):
        rows = connection.execute(
            "SELECT * FROM life_occurrences WHERE owner_id=?", (self.owner_id,)
        ).fetchall()
        settings = self.settings(connection, self.owner_id)
        values = []
        for row in rows:
            value = self.snapshot(connection, row)
            decision = evaluate_reminder(value, now, settings)
            if decision.action in {"SUPPRESS", "EXPIRE"}:
                value = value.model_copy(
                    update={
                        "delivery_status": "SUPPRESSED"
                        if decision.action == "SUPPRESS"
                        else "EXPIRED"
                    }
                )
                # Policy suppression is re-evaluated after an explicit correction or
                # resume. Native SUPPRESSED receipts remain durably terminal above.
                if decision.action == "EXPIRE":
                    self.save_snapshot(connection, value)
            values.append(value)
        return values

    def prepare(self, now: datetime, lease_minutes: int = 5) -> list[dict[str, Any]]:
        """Atomic reservations only; a fence must be checked again at the side-effect boundary."""
        require_aware(now)
        with self.store.transaction() as connection:
            day = now.astimezone(LOCAL_TIMEZONE).date()
            self.compile_day(day - timedelta(days=1), now, connection)
            self.compile_day(day, now, connection)
            settings = self.settings(connection, self.owner_id)
            plan = plan_reminder_groups(self.refresh(connection, now), now, settings)
            prepared = []
            for group in plan.groups:
                members = [
                    next(
                        value
                        for value in self.refresh(connection, now)
                        if value.instance_id == identifier
                    )
                    for identifier in group.instance_ids
                ]
                # Include the consumed attempt number: later explicit sends share quota but need a new operation.
                group_id = "reminder_" + identity(
                    group.group_id, canonical([(v.instance_id, v.consumed_count) for v in members])
                )
                previous = connection.execute(
                    "SELECT state FROM life_reminder_groups WHERE group_id=?", (group_id,)
                ).fetchone()
                if previous and previous[0] not in {"CANCELLED", "FAILED_UNSENT"}:
                    continue
                descriptions = []
                for member in members:
                    value = self.store.get_object(connection, self.owner_id, member.habit_id)
                    definition = value["payload"]["definition"]
                    label = definition["name"]
                    if definition.get("semantic_role") == "diary":
                        label = "记录今天的日记；也可以顺便记下今天的身体状态。"
                    descriptions.append(label)
                    self.save_snapshot(
                        connection,
                        member.model_copy(
                            update={
                                "active_claim": True,
                                "reserved_count": member.reserved_count + 1,
                            }
                        ),
                    )
                content = "到习惯时间了：\n" + "\n".join(f"• {value}" for value in descriptions)
                fence = uuid4().hex
                connection.execute(
                    "INSERT INTO life_reminder_groups VALUES (?, ?, ?, 'RESERVED', ?, ?, ?, ?, NULL, NULL) "
                    "ON CONFLICT(group_id) DO UPDATE SET fence=excluded.fence, state='RESERVED', "
                    "instance_ids_json=excluded.instance_ids_json, content=excluded.content, "
                    "created_at=excluded.created_at, lease_until=excluded.lease_until, native_execution_id=NULL, receipt_json=NULL",
                    (
                        group_id,
                        self.owner_id,
                        fence,
                        canonical(group.instance_ids),
                        content,
                        now.astimezone(UTC).isoformat(),
                        (now + timedelta(minutes=lease_minutes)).astimezone(UTC).isoformat(),
                    ),
                )
                self.event(connection, now, "RESERVED", group_id=group_id, payload={"fence": fence})
                prepared.append({"group_id": group_id, "fence": fence, "content": content})
            return prepared

    def dispatch(
        self,
        group_id: str,
        fence: str,
        now: datetime,
        deliver: Callable[[dict[str, Any]], dict[str, Any]],
        allocate: Callable[[dict[str, Any]], str] | None = None,
    ) -> dict[str, Any]:
        """Check the fence and completion while holding the writer boundary, then hand off once.

        Keep the external handoff bounded. Other life writes cannot commit between
        this final eligibility check and the handoff. An uncertain handoff stays reserved.
        """
        require_aware(now)
        with self.store.transaction() as connection:
            group = connection.execute(
                "SELECT * FROM life_reminder_groups WHERE group_id=? AND owner_id=?",
                (group_id, self.owner_id),
            ).fetchone()
            if group is None or group["fence"] != fence or group["state"] != "RESERVED":
                return {"state": "STALE_FENCE", "sent": False}
            if now >= datetime.fromisoformat(group["lease_until"]):
                self.cancel_group(connection, group, now, "LEASE_EXPIRED")
                return {"state": "CANCELLED", "sent": False}
            settings = self.settings(connection, self.owner_id)
            for identifier in json.loads(group["instance_ids_json"]):
                row = connection.execute(
                    "SELECT * FROM life_occurrences WHERE instance_id=?", (identifier,)
                ).fetchone()
                value = self.snapshot(connection, row)
                # Ignore this group's reservation only for the final eligibility check.
                check = value.model_copy(
                    update={"active_claim": False, "reserved_count": value.reserved_count - 1}
                )
                if evaluate_reminder(check, now, settings).action != "ELIGIBLE":
                    self.cancel_group(connection, group, now, "ELIGIBILITY_CHANGED")
                    return {"state": "CANCELLED", "sent": False}
            # Persist an in-flight marker BEFORE external effects. Crash after this commit
            # is uncertain and can never hand off the group again without its original receipt.
            native_id = allocate(dict(group)) if allocate else None
            connection.execute(
                "UPDATE life_reminder_groups SET state='SENDING', native_execution_id=? WHERE group_id=?",
                (native_id, group_id),
            )
            self.event(connection, now, "SENDING", group_id=group_id)
            for identifier in json.loads(group["instance_ids_json"]):
                row = connection.execute(
                    "SELECT snapshot_json FROM life_occurrences WHERE instance_id=?", (identifier,)
                ).fetchone()
                value = ReminderOccurrence.model_validate_json(row[0])
                self.save_snapshot(
                    connection, value.model_copy(update={"delivery_status": "SENDING"})
                )
        # The second boundary forbids completed-before-send and stale takeover effects.
        with self.store.transaction() as connection:
            group = connection.execute(
                "SELECT * FROM life_reminder_groups WHERE group_id=?", (group_id,)
            ).fetchone()
            if group["fence"] != fence or group["state"] != "SENDING":
                return {"state": "STALE_FENCE", "sent": False}
            for identifier in json.loads(group["instance_ids_json"]):
                row = connection.execute(
                    "SELECT * FROM life_occurrences WHERE instance_id=?", (identifier,)
                ).fetchone()
                value = self.snapshot(connection, row)
                final_check = value.model_copy(
                    update={
                        "delivery_status": "NOT_SENT",
                        "active_claim": False,
                        "reserved_count": max(0, value.reserved_count - 1),
                    }
                )
                if evaluate_reminder(final_check, now, settings).action != "ELIGIBLE":
                    self.cancel_group(connection, group, now, "COMPLETED_BEFORE_HANDOFF")
                    return {"state": "CANCELLED", "sent": False}
            try:
                receipt = deliver(dict(group))
            except Exception as error:  # noqa: BLE001 -- any lost handoff acknowledgment must stay uncertain
                receipt = {"state": "DELIVERY_UNKNOWN", "error_type": type(error).__name__}
            if receipt.get("state") not in {
                "DELIVERED",
                "QUEUED",
                "DELIVERY_UNKNOWN",
                "FAILED_UNSENT",
                "SUPPRESSED",
            }:
                receipt = {"state": "DELIVERY_UNKNOWN", "invalid_receipt": True}
            self.apply_receipt(connection, group, now, receipt)
            return receipt

    def cancel_group(self, connection, group, now, reason):
        connection.execute(
            "UPDATE life_reminder_groups SET state='CANCELLED' WHERE group_id=?",
            (group["group_id"],),
        )
        self.event(
            connection, now, "CANCELLED", group_id=group["group_id"], payload={"reason": reason}
        )
        for identifier in json.loads(group["instance_ids_json"]):
            row = connection.execute(
                "SELECT * FROM life_occurrences WHERE instance_id=?", (identifier,)
            ).fetchone()
            value = self.snapshot(connection, row)
            self.save_snapshot(
                connection,
                value.model_copy(
                    update={
                        "active_claim": False,
                        "reserved_count": max(0, value.reserved_count - 1),
                        "delivery_status": "NOT_SENT",
                    }
                ),
            )

    def apply_receipt(self, connection, group, now, receipt):
        state = receipt["state"]
        connection.execute(
            "UPDATE life_reminder_groups SET state=?, native_execution_id=?, receipt_json=? WHERE group_id=?",
            (
                state,
                receipt.get("native_execution_id") or group["native_execution_id"],
                canonical(receipt),
                group["group_id"],
            ),
        )
        self.event(connection, now, state, group_id=group["group_id"], payload=receipt)
        for identifier in json.loads(group["instance_ids_json"]):
            row = connection.execute(
                "SELECT * FROM life_occurrences WHERE instance_id=?", (identifier,)
            ).fetchone()
            value = self.snapshot(connection, row)
            if state == "DELIVERED":
                used = value.consumed_count + 1
                send_times = [datetime.fromisoformat(t) for t in json.loads(row["send_times_json"])]
                more = used < value.reminder_limit and used < len(send_times)
                update = {
                    "consumed_count": used,
                    "reserved_count": max(0, value.reserved_count - 1),
                    "active_claim": False,
                    "delivery_status": "NOT_SENT" if more else "DELIVERED",
                }
                if more:
                    update["due_at"] = send_times[used]
                    update["window_start"] = send_times[used]
                self.save_snapshot(connection, value.model_copy(update=update))
            elif state in {"FAILED_UNSENT", "SUPPRESSED"}:
                self.save_snapshot(
                    connection,
                    value.model_copy(
                        update={
                            "reserved_count": max(0, value.reserved_count - 1),
                            "active_claim": False,
                            "delivery_status": "SUPPRESSED" if state == "SUPPRESSED" else "FAILED",
                            "failure_proven_unsent": state == "FAILED_UNSENT",
                        }
                    ),
                )
            else:
                self.save_snapshot(
                    connection,
                    value.model_copy(update={"delivery_status": state, "active_claim": False}),
                )

    def reconcile(self, now: datetime, lookup: Callable[[str], dict[str, Any] | None]) -> None:
        with self.store.transaction() as connection:
            groups = connection.execute(
                "SELECT * FROM life_reminder_groups WHERE owner_id=? AND state IN ('SENDING','QUEUED','DELIVERY_UNKNOWN','RESERVED')",
                (self.owner_id,),
            ).fetchall()
            for group in groups:
                if group["state"] == "RESERVED":
                    if now >= datetime.fromisoformat(group["lease_until"]):
                        self.cancel_group(connection, group, now, "RECOVER_UNUSED_RESERVATION")
                    continue
                receipt = (
                    lookup(group["native_execution_id"]) if group["native_execution_id"] else None
                )
                if receipt and receipt.get("state") in {"DELIVERED", "FAILED_UNSENT", "SUPPRESSED"}:
                    self.apply_receipt(connection, group, now, receipt)
                elif group["state"] == "SENDING":
                    self.apply_receipt(connection, group, now, {"state": "DELIVERY_UNKNOWN"})

    def list_occurrences(self, day: date) -> list[dict[str, Any]]:
        with self.store.ledger.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM life_occurrences WHERE owner_id=? AND business_date=? ORDER BY slot_key",
                (self.owner_id, day.isoformat()),
            ).fetchall()
            return [
                {
                    **self.snapshot(connection, row).model_dump(mode="json"),
                    "habit_revision": row["habit_revision"],
                    "slot_key": row["slot_key"],
                    "definition_snapshot": {
                        key: json.loads(row["definition_json"])[key]
                        for key in ("record_type", "unit", "target_value", "target_period")
                    },
                }
                for row in rows
            ]
