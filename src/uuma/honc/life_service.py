"""Semantic life operations with server-bound identity and durable receipts.

The inbound adapter must authenticate an actual user message before calling
receive_user_message, then bind that source to a request-scoped service. Those
two methods are internal adapter APIs, never model tools. This implementation
has no Hermes registration, scheduler, delivery, diagnosis or follow-up side effects.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import ValidationError

from ..models import StrictModel
from .life_history import history
from .life_models import (
    LOCAL_TIMEZONE,
    AnchorRecordRequest,
    BodyRecordRequest,
    DiaryRecordRequest,
    HabitCheckinEntry,
    HabitCheckinRequest,
    HabitConfigureRequest,
    HabitDefinitionInput,
    LifeSettings,
    ObservationTime,
    RecordCorrectionRequest,
    RecordReference,
    ReminderRule,
    SettingsUpdateRequest,
    ToolError,
    ToolResult,
    require_aware,
    validate_reminder_schedule,
)
from .life_store import LifeStore, canonical
from .reminder_runtime import ReminderRuntime

OPERATIONS = frozenset(
    {
        "configure_habit",
        "update_settings",
        "record_habit",
        "record_body",
        "save_diary",
        "correct_record",
        "record_anchor",
    }
)


class LifeRejected(Exception):
    def __init__(self, code: str, message: str, status: str = "NEEDS_INPUT") -> None:
        super().__init__(message)
        self.code, self.status = code, status


def rejected(code: str, message: str, status: str = "NEEDS_INPUT") -> ToolResult:
    return ToolResult(
        ok=False,
        status=status,
        effect_state="none",
        next_action="RELOAD_OBJECT" if status == "CONFLICT" else "ASK_USER",
        errors=[ToolError(code=code, message=message)],
    )


class LifeService:
    def __init__(
        self,
        store: LifeStore,
        *,
        owner_id: str,
        profile: str,
        session_id: str,
        source_ref: str | None = None,
        clock: Callable[[], datetime] | None = None,
        reminders: ReminderRuntime | None = None,
    ) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                owner_id,
                profile,
                session_id,
            )
        ):
            raise ValueError("backend owner, profile and session are required")
        self.store = store
        self.owner_id, self.profile, self.session_id = owner_id, profile, session_id
        self.source_ref = source_ref
        self.clock = clock or (lambda: datetime.now(UTC))
        self.reminders = reminders

    def receive_user_message(
        self,
        *,
        adapter_id: str,
        source_event_id: str,
        raw_content: str,
        received_at: datetime,
        granted_operations: tuple[str, ...] = (),
        source_origin: str = "user_message",
    ) -> dict[str, Any]:
        """Trusted adapter only: replay identity is the actual transport event ID.

        Grants are closed by default. They represent verified user-authorized
        effects, not grants parsed from tool arguments or quoted/assistant text.
        One grant provides one atomic operation per domain in this message.
        """
        require_aware(received_at, "received_at")
        if source_origin not in {"user_message", "configuration_import"}:
            raise ValueError("Unsupported trusted source origin")
        if source_origin == "configuration_import" and set(granted_operations) - {
            "configure_habit",
            "update_settings",
        }:
            raise ValueError("Configuration imports cannot authorize personal observations")
        if not adapter_id.strip() or not source_event_id.strip() or not raw_content.strip():
            raise ValueError("real adapter, transport event and user text are required")
        grants = sorted(set(granted_operations))
        if set(grants) - OPERATIONS:
            raise ValueError("unsupported life operation grant")
        with self.store.transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM life_sources WHERE owner_id = ? AND profile = ? "
                "AND adapter_id = ? AND source_event_id = ?",
                (self.owner_id, self.profile, adapter_id, source_event_id),
            ).fetchone()
            if existing:
                if (
                    existing["raw_content"] != raw_content
                    or existing["received_at"] != received_at.astimezone(UTC).isoformat()
                    or existing["session_id"] != self.session_id
                    or existing["grants_json"] != canonical(grants)
                    or existing["source_origin"] != source_origin
                ):
                    raise ValueError(
                        "transport event identity reused with different source content"
                    )
                source_ref = existing["source_ref"]
            else:
                source_ref = f"source_{uuid4().hex}"
                connection.execute(
                    "INSERT INTO life_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        source_ref,
                        self.owner_id,
                        self.profile,
                        self.session_id,
                        adapter_id,
                        source_event_id,
                        raw_content,
                        received_at.astimezone(UTC).isoformat(),
                        canonical(grants),
                        source_origin,
                    ),
                )
                for operation in grants:
                    connection.execute(
                        "INSERT INTO life_requests VALUES (?, ?, ?)",
                        (f"request_{uuid4().hex}", source_ref, operation),
                    )
            rows = connection.execute(
                "SELECT request_ref, operation_name FROM life_requests WHERE source_ref = ?",
                (source_ref,),
            ).fetchall()
            return {
                "source_ref": source_ref,
                "request_refs": {row["operation_name"]: row["request_ref"] for row in rows},
            }

    def bind_source(self, source_ref: str) -> LifeService:
        """Trusted adapter only: a separate instance avoids shared mutable message context."""
        return LifeService(
            self.store,
            owner_id=self.owner_id,
            profile=self.profile,
            session_id=self.session_id,
            source_ref=source_ref,
            clock=self.clock,
            reminders=self.reminders,
        )

    def _settings_id(self) -> str:
        return f"settings_{uuid5(NAMESPACE_URL, 'honc-life-settings:' + self.owner_id).hex}"

    def _settings(self, connection: sqlite3.Connection) -> tuple[LifeSettings, int]:
        value = self.store.get_object(connection, self.owner_id, self._settings_id())
        if value is None:
            return LifeSettings(), 0
        return LifeSettings.model_validate(value["payload"]), value["revision"]

    def _require_object(
        self,
        connection: sqlite3.Connection,
        object_id: str,
        kind: str | None = None,
    ) -> dict[str, Any]:
        value = self.store.get_object(connection, self.owner_id, object_id)
        if value is None or (kind is not None and value["kind"] != kind):
            raise LifeRejected(
                "OBJECT_NOT_FOUND", "No matching object in this owner scope", "NOT_FOUND"
            )
        return value

    @staticmethod
    def _validate_schedule(rule: ReminderRule, settings: LifeSettings) -> None:
        try:
            validate_reminder_schedule(rule, settings)
        except ValueError as error:
            raise LifeRejected("INVALID_REMINDER_SCHEDULE", str(error)) from error

    @staticmethod
    def _check_quote(source: sqlite3.Row, quote: str) -> None:
        if quote not in source["raw_content"]:
            raise LifeRejected(
                "SOURCE_QUOTE_MISMATCH", "Source quote must occur in the bound user text"
            )

    def _write(
        self,
        request: StrictModel,
        operation_name: str,
        writer: Callable[
            [sqlite3.Connection, sqlite3.Row, str, str], tuple[list[RecordReference], dict]
        ],
    ) -> ToolResult:
        digest = hashlib.sha256(
            canonical(
                request.model_dump(mode="json", exclude_unset=True, exclude={"request_ref"})
            ).encode()
        ).hexdigest()
        operation_id = f"operation_{uuid4().hex}"
        try:
            with self.store.transaction() as connection:
                source = connection.execute(
                    "SELECT s.*, q.operation_name FROM life_requests q "
                    "JOIN life_sources s ON s.source_ref = q.source_ref "
                    "WHERE q.request_ref = ? AND s.owner_id = ? AND s.profile = ? "
                    "AND s.session_id = ? AND s.source_ref = ?",
                    (
                        request.request_ref,
                        self.owner_id,
                        self.profile,
                        self.session_id,
                        self.source_ref,
                    ),
                ).fetchone()
                if source is None or source["operation_name"] != operation_name:
                    raise LifeRejected(
                        "UNBOUND_REQUEST",
                        "A current message grant for this operation is required",
                        "FAILED",
                    )
                prior = connection.execute(
                    "SELECT * FROM life_operations WHERE request_ref = ?",
                    (request.request_ref,),
                ).fetchone()
                if prior:
                    if prior["payload_digest"] != digest:
                        raise LifeRejected(
                            "REQUEST_CONTENT_CONFLICT",
                            "This request already committed different content",
                            "CONFLICT",
                        )
                    result = ToolResult.model_validate_json(prior["result_json"])
                    return result.model_copy(update={"status": "ALREADY_APPLIED"})
                quote = getattr(request, "source_quote", None)
                if quote is not None:
                    if operation_name == "save_diary":
                        settings, _ = self._settings(connection)
                        if not settings.allow_synthesized_diary:
                            self._check_quote(source, quote)
                    else:
                        self._check_quote(source, quote)
                now = require_aware(self.clock(), "server clock").astimezone(UTC).isoformat()
                records, data = writer(connection, source, operation_id, now)
                result = ToolResult(
                    ok=True,
                    status="APPLIED",
                    effect_state="committed",
                    operation_id=operation_id,
                    records=records,
                    data=data,
                    receipt_refs={"source_ref": source["source_ref"], "operation": operation_id},
                )
                connection.execute(
                    "INSERT INTO life_operations VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        operation_id,
                        request.request_ref,
                        self.owner_id,
                        digest,
                        result.model_dump_json(),
                        now,
                    ),
                )
            return result
        except LifeRejected as error:
            return rejected(error.code, str(error), error.status)
        except ValidationError as error:
            return rejected("INVALID_FIELDS", str(error))
        except sqlite3.Error:
            # Never invent a saved record or assume a missing acknowledgment means unsent.
            return ToolResult(
                ok=False,
                status="UNKNOWN",
                effect_state="unknown",
                operation_id=operation_id,
                receipt_refs={"request_ref": request.request_ref},
                next_action="READ_OPERATION",
                retry_policy="lookup_only",
                errors=[
                    ToolError(
                        code="STORAGE_OUTCOME_UNKNOWN",
                        message="Read the persisted operation receipt before retrying",
                    )
                ],
            )

    def _append(
        self,
        connection: sqlite3.Connection,
        source: sqlite3.Row,
        operation_id: str,
        now: str,
        *,
        kind: str,
        payload: dict[str, Any],
        object_id: str | None = None,
        expected_revision: int = 0,
        status: str = "recorded",
    ) -> RecordReference:
        object_id = object_id or f"{kind}_{uuid4().hex}"
        revision = self.store.append_revision(
            connection,
            owner_id=self.owner_id,
            object_id=object_id,
            kind=kind,
            expected_revision=expected_revision,
            source_ref=source["source_ref"],
            operation_id=operation_id,
            status=status,
            payload=payload,
            recorded_at=now,
        )
        time = ObservationTime.model_validate(payload.get("time", {}))
        return RecordReference(
            id=object_id,
            kind="habit" if kind == "habit_definition" else kind,
            revision=revision,
            occurred_at=time.occurred_at,
            occurred_date=time.occurred_date,
            precision=time.precision,
        )

    def configure_habit(self, request: HabitConfigureRequest) -> ToolResult:
        def writer(connection, source, operation_id, now):
            if request.action == "create":
                rows = connection.execute(
                    "SELECT o.object_id, r.payload_json FROM life_objects o JOIN life_revisions r "
                    "ON r.object_id=o.object_id AND r.revision=o.head_revision "
                    "WHERE o.owner_id=? AND o.kind='habit_definition' AND r.status!='retired'",
                    (self.owner_id,),
                ).fetchall()
                if any(
                    json.loads(row["payload_json"])["definition"]["name"].casefold()
                    == request.definition.name.casefold()
                    for row in rows
                ):
                    raise LifeRejected(
                        "DUPLICATE_HABIT_NAME", "Review the existing habit before creating another"
                    )
                settings, _ = self._settings(connection)
                reminder = None
                if request.reminder is not None:
                    reminder = request.reminder.model_dump(mode="json")
                    if "count" not in request.reminder.model_fields_set:
                        reminder["count"] = settings.default_reminder_count
                    if "importance" not in request.reminder.model_fields_set:
                        reminder["importance"] = settings.default_importance
                    reminder = ReminderRule.model_validate(reminder).model_dump(mode="json")
                    self._validate_schedule(ReminderRule.model_validate(reminder), settings)
                # Adding a definition does not implicitly enable a new proactive schedule.
                payload = {
                    "definition": request.definition.model_dump(mode="json"),
                    "reminder": reminder,
                    "reminder_defaults": {
                        "count": settings.default_reminder_count,
                        "importance": settings.default_importance,
                    },
                }
                record = self._append(
                    connection,
                    source,
                    operation_id,
                    now,
                    kind="habit_definition",
                    payload=payload,
                    status="active",
                )
                return [record], {"habit_id": record.id, "state": "active", **payload}
            current = self._require_object(connection, request.habit_id, "habit_definition")
            if current["revision"] != request.expected_revision:
                raise LifeRejected(
                    "STALE_REVISION", "Reload the current habit revision", "CONFLICT"
                )
            if current["status"] == "retired":
                raise LifeRejected("HABIT_RETIRED", "A retired habit is preserved as history")
            payload = current["payload"]
            status = current["status"]
            if request.action == "update":
                if request.definition_patch:
                    payload["definition"] = HabitDefinitionInput.model_validate(
                        {**payload["definition"], **request.definition_patch}
                    ).model_dump(mode="json")
                if request.reminder_patch:
                    payload["reminder"] = ReminderRule.model_validate(
                        {**(payload["reminder"] or {}), **request.reminder_patch}
                    ).model_dump(mode="json")
            else:
                status = {"pause": "paused", "resume": "active", "retire": "retired"}[
                    request.action
                ]
            if request.action == "update" and payload.get("reminder"):
                settings, _ = self._settings(connection)
                self._validate_schedule(ReminderRule.model_validate(payload["reminder"]), settings)
            record = self._append(
                connection,
                source,
                operation_id,
                now,
                kind="habit_definition",
                payload=payload,
                object_id=request.habit_id,
                expected_revision=request.expected_revision,
                status=status,
            )
            return [record], {"habit_id": record.id, "state": status, **payload}

        return self._write(request, "configure_habit", writer)

    def update_settings(self, request: SettingsUpdateRequest) -> ToolResult:
        def writer(connection, source, operation_id, now):
            settings, revision = self._settings(connection)
            if revision != request.expected_revision:
                raise LifeRejected(
                    "STALE_REVISION", "Reload the current settings revision", "CONFLICT"
                )
            forbidden = {
                "revision",
                "timezone",
                "body_followup_enabled",
                "nightly_unchecked_habit_chase_enabled",
                "importance_does_not_change_count",
            }
            if set(request.patch) & forbidden:
                raise LifeRejected(
                    "SETTING_NOT_EDITABLE",
                    "Identity and behavioral boundaries are not editable settings",
                )
            replacement = LifeSettings.model_validate(
                {
                    **settings.model_dump(mode="json"),
                    **request.patch,
                    "revision": revision + 1,
                }
            ).model_dump(mode="json")
            rules = connection.execute(
                "SELECT r.payload_json FROM life_objects o JOIN life_revisions r "
                "ON o.object_id=r.object_id AND o.head_revision=r.revision "
                "WHERE o.owner_id=? AND o.kind='habit_definition' AND r.status!='retired'",
                (self.owner_id,),
            ).fetchall()
            for row in rules:
                reminder = json.loads(row[0]).get("reminder")
                if reminder:
                    self._validate_schedule(
                        ReminderRule.model_validate(reminder),
                        LifeSettings.model_validate(replacement),
                    )
            record = self._append(
                connection,
                source,
                operation_id,
                now,
                kind="settings",
                object_id=self._settings_id(),
                expected_revision=revision,
                payload=replacement,
            )
            return [record], {"settings": replacement}

        return self._write(request, "update_settings", writer)

    def _validate_checkin(self, connection, entry: HabitCheckinEntry) -> dict[str, Any]:
        current = self._require_object(connection, entry.habit_id, "habit_definition")
        definition = HabitDefinitionInput.model_validate(current["payload"]["definition"])
        if entry.habit_revision != current["revision"]:
            frozen = None
            if self.reminders is not None and entry.instance_id:
                frozen = connection.execute(
                    "SELECT habit_revision, definition_json FROM life_occurrences "
                    "WHERE instance_id=? AND owner_id=? AND habit_id=?",
                    (entry.instance_id, self.owner_id, entry.habit_id),
                ).fetchone()
            if frozen is None or frozen["habit_revision"] != entry.habit_revision:
                raise LifeRejected(
                    "STALE_REVISION",
                    "Reload the current habit or explicit occurrence revision",
                    "CONFLICT",
                )
            definition = HabitDefinitionInput.model_validate_json(frozen["definition_json"])
        reported_day = entry.time.occurred_date
        if entry.time.occurred_at:
            reported_day = entry.time.occurred_at.astimezone(LOCAL_TIMEZONE).date()
        historical = (
            reported_day is not None
            and reported_day < self.clock().astimezone(LOCAL_TIMEZONE).date()
        )
        if current["status"] != "active" and not historical:
            raise LifeRejected(
                "HABIT_INACTIVE", "Resume or explicitly migrate historical data before checking in"
            )
        if entry.instance_id is not None and self.reminders is None:
            raise LifeRejected(
                "INSTANCE_NOT_BOUND",
                "Occurrence binding is not implemented; omit an unverified instance ID",
            )
        if entry.outcome not in {"skipped", "not_done"}:
            if definition.record_type == "boolean":
                if entry.value not in {None, 1} or entry.unit or entry.text is not None:
                    raise LifeRejected(
                        "VALUE_TYPE_MISMATCH",
                        "Boolean check-ins accept one or unknown, without a unit",
                    )
            elif definition.record_type == "text":
                if entry.value is not None or entry.unit or not entry.text:
                    raise LifeRejected(
                        "VALUE_TYPE_MISMATCH", "Text check-ins require the user's text"
                    )
            elif definition.record_type == "selection":
                if (
                    entry.value is not None
                    or entry.unit is not None
                    or entry.text is not None
                    or not entry.selection_values
                ):
                    raise LifeRejected(
                        "VALUE_TYPE_MISMATCH", "Selection habits retain separate named values"
                    )
                if definition.selection_options and set(entry.selection_values) - set(
                    definition.selection_options
                ):
                    raise LifeRejected(
                        "UNKNOWN_SELECTION", "Reload the available selection options"
                    )
                if any(label not in entry.source_quote for label in entry.selection_values):
                    raise LifeRejected(
                        "SOURCE_QUOTE_MISMATCH", "Selected labels must appear in the user quote"
                    )
            else:
                if entry.text is not None:
                    raise LifeRejected(
                        "VALUE_TYPE_MISMATCH", "Numeric check-ins do not accept replacement text"
                    )
                if (
                    entry.value is not None
                    and entry.unit != definition.unit
                    and not (definition.record_type == "number" and definition.unit is None)
                    and not (definition.record_type == "count" and entry.unit in {None, "time"})
                ):
                    raise LifeRejected(
                        "UNIT_MISMATCH",
                        "Use the explicit habit unit; no implicit conversion is performed",
                    )
                if entry.value is None and entry.unit is not None:
                    raise LifeRejected("VALUE_MISSING", "A unit requires a reported quantity")
                if (
                    definition.record_type == "count"
                    and entry.value is not None
                    and not entry.value.is_integer()
                ):
                    raise LifeRejected("VALUE_TYPE_MISMATCH", "Count must be a whole number")
        payload = entry.model_dump(mode="json")
        if definition.record_type != "selection" and entry.selection_values is not None:
            raise LifeRejected(
                "VALUE_TYPE_MISMATCH", "Named selection values require a selection habit"
            )
        if self.reminders is not None:
            day = entry.time.occurred_date
            if entry.time.occurred_at:
                day = entry.time.occurred_at.astimezone(LOCAL_TIMEZONE).date()
            if day:
                self.reminders.compile_day(day, self.clock(), connection)
            try:
                payload["instance_id"] = self.reminders.bind_checkin(
                    connection,
                    habit_id=entry.habit_id,
                    habit_revision=entry.habit_revision,
                    observation=entry.time,
                    instance_id=entry.instance_id,
                )
            except ValueError as error:
                raise LifeRejected("INSTANCE_NOT_BOUND", str(error)) from error
        # Snapshot the interpretation; later unit/name/target changes never rewrite this fact.
        payload["definition_snapshot"] = definition.model_dump(mode="json")
        return payload

    def record_habit(self, request: HabitCheckinRequest) -> ToolResult:
        def writer(connection, source, operation_id, now):
            identities = [entry.habit_id for entry in request.entries]
            if len(set(identities)) != len(identities):
                raise LifeRejected(
                    "DUPLICATE_BATCH_HABIT", "Use one entry per habit in this atomic batch"
                )
            payloads = []
            for entry in request.entries:
                self._check_quote(source, entry.source_quote)
                if entry.outcome in {"completed", "partial"} and re.match(
                    r"^(?:我)?(?:还)?(?:没|未|计划|打算|准备|如果|假设|明天|不要记录)",
                    entry.source_quote,
                ):
                    raise LifeRejected(
                        "REPORT_NOT_ACTUAL",
                        "A negative, hypothetical or planned report is not completed activity",
                    )
                payloads.append(self._validate_checkin(connection, entry))
            records = [
                self._append(connection, source, operation_id, now, kind="habit", payload=value)
                for value in payloads
            ]
            return records, {
                "entries": payloads,
                "occurrence_binding": "BOUND"
                if all(value.get("instance_id") for value in payloads)
                else "UNBOUND",
            }

        return self._write(request, "record_habit", writer)

    def _check_links(self, connection, identities: list[str]) -> None:
        for identity in identities:
            value = self._require_object(connection, identity)
            if value["kind"] not in {"habit", "body", "diary"} or value["status"] == "void":
                raise LifeRejected(
                    "INVALID_LINK", "Link an effective life fact in the same owner scope"
                )

    @staticmethod
    def _check_body_source(source: sqlite3.Row, observations) -> None:
        for observation in observations:
            for field in (
                "description",
                "body_part",
                "severity_text",
                "change_text",
                "score_scale",
            ):
                value = getattr(observation, field)
                if value is not None and value not in source["raw_content"]:
                    raise LifeRejected(
                        "BODY_FIELD_NOT_REPORTED",
                        "Body descriptions and optional details must retain the user's words",
                    )
            if observation.reported_score is not None:
                reported = f"{observation.reported_score:g}"
                if not re.search(
                    r"(?<![\d.])" + re.escape(reported) + r"(?:\.0+)?(?![\d.])",
                    source["raw_content"],
                ):
                    raise LifeRejected(
                        "BODY_FIELD_NOT_REPORTED",
                        "A score must be explicitly reported in the source",
                    )

    def record_body(self, request: BodyRecordRequest) -> ToolResult:
        def writer(connection, source, operation_id, now):
            self._check_links(connection, request.related_record_ids)
            self._check_body_source(source, request.observations)
            payload = request.model_dump(mode="json", exclude={"request_ref"})
            return [
                self._append(connection, source, operation_id, now, kind="body", payload=payload)
            ], {
                "followup_created": False,
            }

        return self._write(request, "record_body", writer)

    def save_diary(self, request: DiaryRecordRequest) -> ToolResult:
        def writer(connection, source, operation_id, now):
            self._check_links(connection, request.linked_record_ids)
            settings, _ = self._settings(connection)
            if not settings.allow_synthesized_diary and request.content not in source["raw_content"]:
                raise LifeRejected(
                    "DIARY_SOURCE_MISMATCH",
                    "Save the user text; rewriting needs a separate approved revision",
                )
            payload = request.model_dump(mode="json", exclude={"request_ref"})
            payload["time"] = ObservationTime(
                occurred_date=request.diary_date,
                precision="date" if request.diary_date else "unknown",
            ).model_dump(mode="json")
            records = [
                self._append(connection, source, operation_id, now, kind="diary", payload=payload)
            ]
            created = False
            if self.reminders is not None:
                candidates = connection.execute(
                    "SELECT o.object_id, r.revision FROM life_objects o JOIN life_revisions r "
                    "ON o.object_id=r.object_id AND o.head_revision=r.revision "
                    "WHERE o.owner_id=? AND o.kind='habit_definition' AND r.status='active' "
                    "AND json_extract(r.payload_json, '$.definition.semantic_role')='diary'",
                    (self.owner_id,),
                ).fetchall()
                if len(candidates) == 1:
                    entry = HabitCheckinEntry(
                        habit_id=candidates[0]["object_id"],
                        habit_revision=candidates[0]["revision"],
                        outcome="completed",
                        source_quote=request.source_quote,
                        text=request.content,
                        time=ObservationTime.model_validate(payload["time"]),
                    )
                    fact = self._validate_checkin(connection, entry)
                    fact["diary_record_id"] = records[0].id
                    records.append(
                        self._append(
                            connection, source, operation_id, now, kind="habit", payload=fact
                        )
                    )
                    created = True
                elif len(candidates) > 1:
                    raise LifeRejected(
                        "AMBIGUOUS_DIARY_HABIT",
                        "Choose one active diary habit before saving its linked check-in",
                    )
            return records, {
                "habit_checkin_created": created,
                "occurrence_binding": "BOUND" if created else "UNBOUND",
            }

        return self._write(request, "save_diary", writer)

    def correct_record(self, request: RecordCorrectionRequest) -> ToolResult:
        def writer(connection, source, operation_id, now):
            current = self._require_object(connection, request.record_id)
            if current["kind"] not in {"habit", "body", "diary"}:
                raise LifeRejected(
                    "CORRECTION_KIND_MISMATCH",
                    "Definitions and settings have their own configuration operations",
                )
            if current["revision"] != request.expected_revision:
                raise LifeRejected("STALE_REVISION", "Reload the current fact revision", "CONFLICT")
            if current["status"] == "void":
                raise LifeRejected(
                    "RECORD_VOID", "A void fact requires a separate explicit restoration contract"
                )
            payload = current["payload"]
            changes = request.model_fields_set
            allowed = {
                "habit": {
                    "corrected_time",
                    "corrected_value",
                    "corrected_unit",
                    "corrected_text",
                    "corrected_selection_values",
                },
                "body": {"corrected_time", "corrected_observations"},
                "diary": {"corrected_time", "corrected_text"},
            }[current["kind"]]
            if {field for field in changes if field.startswith("corrected_")} - allowed:
                raise LifeRejected(
                    "CORRECTION_KIND_MISMATCH",
                    "Replacement fields must match the original fact type",
                )
            for field, target in (
                ("corrected_time", "time"),
                ("corrected_value", "value"),
                ("corrected_unit", "unit"),
                ("corrected_text", "text"),
                ("corrected_observations", "observations"),
                ("corrected_selection_values", "selection_values"),
            ):
                if field in changes:
                    replacement = getattr(request, field)
                    if field == "corrected_time":
                        replacement = replacement.model_dump(mode="json")
                    elif field == "corrected_observations":
                        replacement = [item.model_dump(mode="json") for item in replacement]
                    payload[
                        "content" if current["kind"] == "diary" and target == "text" else target
                    ] = replacement
            if current["kind"] == "habit" and not request.void:
                # Validate against the original definition, never the current habit's changed unit.
                entry = HabitCheckinEntry.model_validate(
                    {
                        key: value
                        for key, value in payload.items()
                        if key not in {"definition_snapshot", "correction", "diary_record_id"}
                    }
                )
                original = HabitDefinitionInput.model_validate(payload["definition_snapshot"])
                self._validate_original_value(entry, original)
                if "corrected_selection_values" in changes:
                    if original.record_type != "selection" or not entry.selection_values:
                        raise LifeRejected(
                            "VALUE_TYPE_MISMATCH", "Named counters require a selection fact"
                        )
                    if original.selection_options and set(entry.selection_values) - set(
                        original.selection_options
                    ):
                        raise LifeRejected(
                            "UNKNOWN_SELECTION", "Use the original configured selection labels"
                        )
                    if any(label not in request.source_quote for label in entry.selection_values):
                        raise LifeRejected(
                            "SOURCE_QUOTE_MISMATCH",
                            "Corrected labels require the current source quote",
                        )
                if self.reminders is not None and "corrected_time" in changes:
                    day = entry.time.occurred_date
                    if entry.time.occurred_at:
                        day = entry.time.occurred_at.astimezone(LOCAL_TIMEZONE).date()
                    if day:
                        self.reminders.compile_day(day, datetime.fromisoformat(now), connection)
                    try:
                        payload["instance_id"] = self.reminders.bind_checkin(
                            connection,
                            habit_id=entry.habit_id,
                            habit_revision=entry.habit_revision,
                            observation=entry.time,
                            allow_ambiguous=True,
                        )
                    except ValueError as error:
                        raise LifeRejected("INSTANCE_NOT_BOUND", str(error)) from error
            if current["kind"] == "body" and "corrected_observations" in changes:
                self._check_body_source(source, request.corrected_observations)
            if (
                current["kind"] == "diary"
                and "corrected_text" in changes
                and (not payload["content"] or payload["content"] not in source["raw_content"])
            ):
                settings, _ = self._settings(connection)
                if not settings.allow_synthesized_diary:
                    raise LifeRejected(
                        "DIARY_SOURCE_MISMATCH",
                        "Corrected diary text must come from the new user message",
                    )
            payload["correction"] = {
                "reason": request.reason,
                "source_quote": request.source_quote,
                "supersedes_revision": current["revision"],
            }
            record = self._append(
                connection,
                source,
                operation_id,
                now,
                kind=current["kind"],
                object_id=request.record_id,
                expected_revision=request.expected_revision,
                status="void" if request.void else "recorded",
                payload=payload,
            )
            records = [record]
            if current["kind"] == "diary":
                linked = connection.execute(
                    "SELECT o.object_id, r.* FROM life_objects o JOIN life_revisions r "
                    "ON o.object_id=r.object_id AND o.head_revision=r.revision "
                    "WHERE o.owner_id=? AND o.kind='habit' AND r.status!='void' "
                    "AND json_extract(r.payload_json, '$.diary_record_id')=?",
                    (self.owner_id, request.record_id),
                ).fetchall()
                for row in linked:
                    fact = json.loads(row["payload_json"])
                    fact["text"], fact["time"] = payload["content"], payload["time"]
                    if self.reminders is not None:
                        fact["instance_id"] = self.reminders.bind_checkin(
                            connection,
                            habit_id=fact["habit_id"],
                            habit_revision=fact["habit_revision"],
                            observation=ObservationTime.model_validate(fact["time"]),
                            allow_ambiguous=True,
                        )
                    fact["correction"] = payload["correction"]
                    records.append(
                        self._append(
                            connection,
                            source,
                            operation_id,
                            now,
                            kind="habit",
                            object_id=row["object_id"],
                            expected_revision=row["revision"],
                            status="void" if request.void else "recorded",
                            payload=fact,
                        )
                    )
            return records, {"void": request.void, "supersedes_revision": current["revision"]}

        return self._write(request, "correct_record", writer)

    @staticmethod
    def _validate_original_value(
        entry: HabitCheckinEntry, definition: HabitDefinitionInput
    ) -> None:
        if entry.outcome in {"skipped", "not_done"}:
            return
        if definition.record_type == "boolean":
            valid = entry.value in {None, 1} and entry.unit is None and entry.text is None
        elif definition.record_type == "text":
            valid = bool(entry.text) and entry.value is None and entry.unit is None
        elif definition.record_type == "selection":
            valid = (
                bool(entry.selection_values)
                and entry.value is None
                and entry.unit is None
                and entry.text is None
            )
        else:
            valid = entry.text is None and (
                (entry.value is None and entry.unit is None)
                or (
                    entry.value is not None
                    and (
                        entry.unit == definition.unit
                        or (definition.record_type == "number" and definition.unit is None)
                        or (definition.record_type == "count" and entry.unit in {None, "time"})
                    )
                )
            )
            if definition.record_type == "count" and entry.value is not None:
                valid = valid and entry.value.is_integer()
        if not valid:
            raise LifeRejected(
                "VALUE_TYPE_MISMATCH",
                "Correction must retain the original definition's value type and unit",
            )

    def get_operation(
        self, *, operation_id: str | None = None, request_ref: str | None = None
    ) -> ToolResult:
        if (operation_id is None) == (request_ref is None):
            return rejected(
                "LOOKUP_ID_REQUIRED", "Supply exactly one operation ID or request reference"
            )
        with self.store.ledger.connect() as connection:
            row = connection.execute(
                "SELECT result_json FROM life_operations WHERE owner_id = ? "
                "AND (operation_id = ? OR request_ref = ?)",
                (self.owner_id, operation_id, request_ref),
            ).fetchone()
        if row:
            return ToolResult.model_validate_json(row["result_json"])
        return ToolResult(
            ok=False,
            status="NOT_FOUND",
            effect_state="none",
            next_action="READ_OPERATION",
            retry_policy="lookup_only",
            errors=[
                ToolError(
                    code="RECEIPT_NOT_FOUND",
                    message="An absent receipt alone is not proof that an uncertain operation did not occur",
                )
            ],
        )

    def record_anchor(self, request: AnchorRecordRequest) -> ToolResult:
        def writer(connection, source, operation_id, now):
            if self.reminders is None:
                raise LifeRejected(
                    "REMINDER_RUNTIME_UNAVAILABLE", "The reminder runtime is required", "FAILED"
                )
            if re.search(r"明天|后天|打算|计划睡|还没|没有|假设|如果|想.*睡", request.source_quote):
                raise LifeRejected(
                    "ANCHOR_NOT_CURRENT",
                    "Only an explicit current wake/day start/bedtime is an anchor",
                )
            patterns = {
                "wake": r"起床了|起了|醒了|刚起床|woke up|awake now",
                "day_start": r"开始.*(?:今天|一天|计划)|start.*(?:day|plan)",
                "bedtime": r"准备睡|要睡了|睡觉了|去睡|going to bed|bedtime now",
            }
            if not re.search(patterns[request.kind], request.source_quote, re.IGNORECASE):
                raise LifeRejected(
                    "ANCHOR_NOT_EXPLICIT", "Retain the explicit current anchor words"
                )
            observed = datetime.fromisoformat(source["received_at"])
            self.reminders.compile_day(
                observed.astimezone(LOCAL_TIMEZONE).date(), observed, connection
            )
            payload = {
                "kind": request.kind,
                "source_quote": request.source_quote,
                "source_ref": source["source_ref"],
                "observed_at": observed.isoformat(),
                "time": request.time.model_dump(mode="json"),
            }
            identifier = "anchor_" + uuid4().hex
            connection.execute(
                "INSERT INTO life_anchors VALUES (?, ?, ?, ?, ?, ?)",
                (
                    identifier,
                    self.owner_id,
                    source["source_ref"],
                    operation_id,
                    canonical(payload),
                    now,
                ),
            )
            self.reminders.advance_anchor(connection, request.kind, observed, source["source_ref"])
            return [
                RecordReference(
                    id=identifier,
                    kind="anchor",
                    revision=1,
                    occurred_at=request.time.occurred_at,
                    occurred_date=request.time.occurred_date,
                    precision=request.time.precision,
                )
            ], {"observed_at": observed.isoformat(), "delivery_status": "NOT_SENT"}

        return self._write(request, "record_anchor", writer)

    def get_context(
        self,
        *,
        habit_id: str | None = None,
        habit_name: str | None = None,
        business_date: date | None = None,
        compact: bool = False,
    ) -> ToolResult:
        if habit_id and habit_name:
            return rejected("HABIT_FILTER_AMBIGUOUS", "Provide habit_id or habit_name, not both")
        occurrences = []
        if self.reminders is not None:
            today = business_date or self.clock().astimezone(LOCAL_TIMEZONE).date()
            self.reminders.compile_day(today, self.clock())
            occurrences = self.reminders.list_occurrences(today)
        with self.store.ledger.connect() as connection:
            settings, revision = self._settings(connection)
            rows = connection.execute(
                "SELECT o.object_id, o.kind, o.head_revision, r.* FROM life_objects o "
                "JOIN life_revisions r ON r.object_id=o.object_id AND r.revision=o.head_revision "
                "WHERE o.owner_id=? AND o.kind='habit_definition' "
                "AND (r.status!='retired' OR ?=1) "
                "ORDER BY o.object_id",
                (self.owner_id, int(bool(habit_id or habit_name))),
            ).fetchall()
            grants = connection.execute(
                "SELECT q.operation_name, q.request_ref FROM life_requests q "
                "JOIN life_sources s ON s.source_ref=q.source_ref "
                "WHERE s.source_ref=? AND s.owner_id=? AND s.profile=? AND s.session_id=?",
                (self.source_ref, self.owner_id, self.profile, self.session_id),
            ).fetchall()
        habits = [self.store.decode_object(row) for row in rows]
        if habit_id or habit_name:
            habits = [
                value
                for value in habits
                if (
                    value["object_id"] == habit_id
                    if habit_id
                    else habit_name.casefold()
                    in [
                        name.casefold()
                        for name in [
                            value["payload"]["definition"]["name"],
                            *value["payload"]["definition"]["aliases"],
                        ]
                    ]
                )
            ]
            if not habits:
                return rejected(
                    "HABIT_NOT_FOUND", "No matching habit in this owner scope", "NOT_FOUND"
                )
            if len(habits) > 1:
                return rejected(
                    "HABIT_FILTER_AMBIGUOUS", "More than one habit matches; use habit_id"
                )
            occurrences = [
                value for value in occurrences if value["habit_id"] == habits[0]["object_id"]
            ]
        elif compact:
            habits = [
                {
                    "object_id": value["object_id"],
                    "revision": value["revision"],
                    "status": value["status"],
                    **{
                        key: value["payload"]["definition"][key]
                        for key in ("name", "aliases", "record_type", "unit")
                    },
                }
                for value in habits
            ]
            occurrences = []
        return ToolResult(
            ok=True,
            status="READ_OK",
            effect_state="none",
            data={
                "settings": settings.model_dump(mode="json"),
                "settings_revision": revision,
                "settings_persisted": revision != 0,
                "habits": habits,
                "occurrences": occurrences,
                "occurrence_lookup": "Pass habit_id or exact habit_name, and business_date for backfill; copy the returned instance_id and habit_revision.",
                "request_refs": {row["operation_name"]: row["request_ref"] for row in grants},
            },
        )

    def get_history(
        self,
        *,
        record_id: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        view: str = "effective",
        limit: int = 20,
        offset: int = 0,
        cursor: str | None = None,
        kinds: tuple[str, ...] = ("habit", "body", "diary", "anchor", "activity"),
        habit_id: str | None = None,
    ) -> ToolResult:
        try:
            result = history(
                self.store,
                owner_id=self.owner_id,
                record_id=record_id,
                start_date=start_date,
                end_date=end_date,
                view=view,
                limit=limit,
                offset=offset,
                cursor=cursor,
                kinds=kinds,
                habit_id=habit_id,
            )
        except ValueError as error:
            return rejected("INVALID_HISTORY_QUERY", str(error))
        return ToolResult(
            ok=True,
            status="READ_OK",
            effect_state="none",
            data=result,
        )
