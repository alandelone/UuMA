"""Strict life-domain contracts; no database, scheduler, or model side effects.

These models validate shape and consistency. Authentication, source ownership,
operation receipts, and transactional delivery claims belong to the service boundary.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, StrictBool, StrictInt, model_validator

from ..models import StrictModel

LOCAL_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Kuala_Lumpur")
ClockTime = Annotated[str, Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")]
Nonempty = Annotated[str, Field(min_length=1, max_length=4000)]
Identifier = Annotated[str, Field(min_length=1, max_length=200)]
NonnegativeInt = Annotated[StrictInt, Field(ge=0)]
PositiveRevision = Annotated[StrictInt, Field(ge=1)]
NonnegativeNumber = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]


def require_aware(value: datetime, name: str = "time") -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} requires a timezone")
    return value


def clock_minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


class LifeSettings(StrictModel):
    """Explicit user configuration; settings are not inferred from chat summaries."""

    revision: PositiveRevision = 1
    timezone: Literal["Asia/Kuala_Lumpur"] = "Asia/Kuala_Lumpur"
    wake_fallback_time: ClockTime = "08:00"
    bedtime_fallback_time: ClockTime = "21:30"
    default_reminder_count: NonnegativeInt = 1
    default_importance: Literal["low", "normal", "high"] = "normal"
    fixed_point_grace_minutes: Annotated[StrictInt, Field(ge=1)] = 30
    suppress_when_complete: StrictBool = True
    group_simultaneous: StrictBool = True
    advance_explicit_wake_or_day_start: StrictBool = True
    advance_explicit_bedtime: StrictBool = True
    missed_window_policy: Literal["expire"] = "expire"
    body_followup_enabled: StrictBool = False
    nightly_unchecked_habit_chase_enabled: StrictBool = False
    importance_does_not_change_count: StrictBool = True
    allow_synthesized_diary: StrictBool = False

    @model_validator(mode="after")
    def preserve_behavior_boundaries(self) -> LifeSettings:
        if self.body_followup_enabled or self.nightly_unchecked_habit_chase_enabled:
            raise ValueError("body follow-up and nightly chasing are not permitted")
        if not self.importance_does_not_change_count:
            raise ValueError("importance cannot change reminder count")
        return self


class ReminderSlot(StrictModel):
    key: Identifier
    trigger: Literal["fixed_time", "time_window", "wake", "bedtime"]
    fixed_time: ClockTime | None = None
    start: ClockTime | None = None
    end: ClockTime | None = None
    fallback_time: ClockTime | None = None
    send_times: list[ClockTime] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_trigger_fields(self) -> ReminderSlot:
        if self.trigger == "fixed_time":
            if self.fixed_time is None or any((self.start, self.end, self.fallback_time)):
                raise ValueError("fixed_time requires only its fixed_time field")
        elif self.trigger == "time_window":
            if self.start is None or self.end is None or self.fixed_time or self.fallback_time:
                raise ValueError("time_window requires only start and end")
            if self.start == self.end:
                raise ValueError("time_window must not be empty")
        elif any((self.fixed_time, self.start, self.end)):
            raise ValueError("anchor slots cannot contain fixed_time or window fields")
        if len(set(self.send_times)) != len(self.send_times):
            raise ValueError("send_times must be distinct")
        if self.trigger == "time_window" and self.send_times:
            start = clock_minutes(self.start)
            width = (clock_minutes(self.end) - start) % (24 * 60)
            positions = [(clock_minutes(value) - start) % (24 * 60) for value in self.send_times]
            if positions != sorted(positions) or any(position >= width for position in positions):
                raise ValueError("send_times must be ordered inside the start-inclusive window")
        return self


class ReminderRule(StrictModel):
    enabled: StrictBool = True
    count: NonnegativeInt = 1
    importance: Literal["low", "normal", "high"] = "normal"
    recurrence: Literal["daily", "weekdays"] = "daily"
    weekdays: list[Annotated[StrictInt, Field(ge=0, le=6)]] = Field(default_factory=list)
    slots: list[ReminderSlot] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_occurrences(self) -> ReminderRule:
        if self.recurrence == "weekdays" and not self.weekdays:
            raise ValueError("weekdays recurrence needs explicit weekdays")
        if self.recurrence == "daily" and self.weekdays:
            raise ValueError("daily recurrence does not accept weekdays")
        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("weekdays must be unique")
        if len({slot.key for slot in self.slots}) != len(self.slots):
            raise ValueError("slot keys must be unique")
        for slot in self.slots:
            if self.count > 1 and len(slot.send_times) != self.count:
                raise ValueError("multiple reminders need count-matching explicit send_times")
            if self.count <= 1 and len(slot.send_times) > self.count:
                raise ValueError("send_times exceed the configured count")
        return self


def validate_reminder_schedule(rule: ReminderRule, settings: LifeSettings) -> None:
    """Reject invalid settings/rule combinations before persisting a usable schedule."""
    for slot in rule.slots:
        if slot.trigger == "time_window":
            start = clock_minutes(slot.start)
            width = (clock_minutes(slot.end) - start) % (24 * 60)
        else:
            clock = (
                slot.fixed_time
                or slot.fallback_time
                or (
                    settings.wake_fallback_time
                    if slot.trigger == "wake"
                    else settings.bedtime_fallback_time
                )
            )
            start, width = clock_minutes(clock), settings.fixed_point_grace_minutes
        positions = [(clock_minutes(value) - start) % (24 * 60) for value in slot.send_times]
        if positions != sorted(positions) or any(value >= width for value in positions):
            raise ValueError("Explicit send_times must be ordered inside the configured window")


class HabitDefinitionInput(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    record_type: Literal["boolean", "count", "quantity", "duration", "text", "number", "selection"]
    semantic_role: Literal["habit", "diary"] = "habit"
    unit: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    target_value: Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)] | None = None
    target_period: Literal["day", "week"] = "day"
    description: Annotated[str, Field(max_length=4000)] = ""
    aliases: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(default_factory=list)
    selection_options: list[Identifier] = Field(default_factory=list)
    legacy_property_type: Literal["checkbox", "number", "rich_text", "multi_select"] | None = None

    @model_validator(mode="after")
    def validate_record_unit(self) -> HabitDefinitionInput:
        if self.semantic_role == "diary" and self.record_type != "text":
            raise ValueError("diary habits retain original text")
        if self.record_type == "selection" and (
            self.unit is not None or self.target_value is not None
        ):
            raise ValueError(
                "selection facts keep separate named counters and no scalar unit/target"
            )
        if self.record_type != "selection" and self.selection_options:
            raise ValueError("only selection habits accept selection_options")
        if self.record_type in {"boolean", "text"} and self.unit is not None:
            raise ValueError("boolean and text habits do not accept numeric units")
        if self.record_type == "quantity" and self.unit is None:
            raise ValueError("quantity requires an explicit unit")
        if self.record_type == "duration" and self.unit not in {"second", "minute", "hour"}:
            raise ValueError("duration requires second, minute, or hour")
        if self.record_type == "count" and self.unit not in {None, "time"}:
            raise ValueError("count unit must be time or omitted")
        if self.record_type == "boolean" and self.target_value not in {None, 1}:
            raise ValueError("boolean target must be one")
        if self.record_type == "text" and self.target_value is not None:
            raise ValueError("text habits do not have numeric targets")
        if (
            self.record_type == "count"
            and self.target_value is not None
            and not self.target_value.is_integer()
        ):
            raise ValueError("count target must be a whole number")
        aliases = [alias.casefold() for alias in self.aliases]
        if len(set(aliases)) != len(aliases):
            raise ValueError("aliases must be unique")
        return self


class ObservationTime(StrictModel):
    occurred_at: datetime | None = None
    occurred_date: date | None = None
    time_text: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    precision: Literal["exact", "date", "approximate", "unknown"] = "unknown"

    @model_validator(mode="after")
    def preserve_time_precision(self) -> ObservationTime:
        if self.precision == "exact":
            if self.occurred_at is None:
                raise ValueError("exact precision requires occurred_at")
            require_aware(self.occurred_at, "occurred_at")
            local_date = self.occurred_at.astimezone(LOCAL_TIMEZONE).date()
            if self.occurred_date is not None and self.occurred_date != local_date:
                raise ValueError("occurred_date differs from the local exact date")
        elif self.occurred_at is not None:
            raise ValueError("non-exact observations cannot invent an exact occurred_at")
        if self.precision == "date" and self.occurred_date is None:
            raise ValueError("date precision requires occurred_date")
        if self.precision == "unknown" and self.occurred_date is not None:
            raise ValueError("a known date is not unknown precision")
        if self.precision == "approximate" and not self.time_text:
            raise ValueError("approximate precision requires the original time expression")
        return self


class HabitCheckinEntry(StrictModel):
    habit_id: Identifier
    habit_revision: PositiveRevision
    outcome: Literal["completed", "partial", "skipped", "not_done"]
    source_quote: Nonempty
    instance_id: Identifier | None = None
    value: NonnegativeNumber | None = None
    unit: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    text: Annotated[str, Field(max_length=16000)] | None = None
    reason: Annotated[str, Field(max_length=4000)] | None = None
    selection_values: dict[Identifier, NonnegativeInt | None] | None = None
    time: ObservationTime = Field(default_factory=ObservationTime)

    @model_validator(mode="after")
    def separate_negative_outcomes(self) -> HabitCheckinEntry:
        if self.outcome in {"not_done", "skipped"} and (self.value is not None or self.unit):
            raise ValueError("negative outcomes do not carry completion quantities")
        return self


class HabitCheckinRequest(StrictModel):
    request_ref: Identifier
    entries: list[HabitCheckinEntry] = Field(min_length=1, max_length=8)


class BodyObservation(StrictModel):
    description: Nonempty
    body_part: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    severity_text: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    reported_score: NonnegativeNumber | None = None
    score_scale: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    change_text: Annotated[str, Field(min_length=1, max_length=1000)] | None = None

    @model_validator(mode="after")
    def require_user_score_scale(self) -> BodyObservation:
        if (self.reported_score is None) != (self.score_scale is None):
            raise ValueError("reported score and user-supplied scale must be paired")
        return self


class BodyRecordRequest(StrictModel):
    request_ref: Identifier
    source_quote: Nonempty
    observations: list[BodyObservation] = Field(min_length=1, max_length=8)
    time: ObservationTime = Field(default_factory=ObservationTime)
    related_record_ids: list[Identifier] = Field(default_factory=list)


class HabitConfigureRequest(StrictModel):
    request_ref: Identifier
    source_quote: Nonempty
    action: Literal["create", "update", "pause", "resume", "retire"]
    habit_id: Identifier | None = None
    expected_revision: PositiveRevision | None = None
    definition: HabitDefinitionInput | None = None
    reminder: ReminderRule | None = None
    definition_patch: dict[str, Any] | None = None
    reminder_patch: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_action_fields(self) -> HabitConfigureRequest:
        if self.action == "create":
            if self.habit_id or self.expected_revision or self.definition is None:
                raise ValueError("create requires a definition and forbids an existing identity")
            if self.definition_patch is not None or self.reminder_patch is not None:
                raise ValueError("create does not accept patches")
        else:
            if not self.habit_id or self.expected_revision is None:
                raise ValueError("existing habits require an identity and expected_revision")
            if self.definition is not None or self.reminder is not None:
                raise ValueError("existing definitions change through patches")
            if self.action == "update":
                if not self.definition_patch and not self.reminder_patch:
                    raise ValueError("update requires a nonempty patch")
            elif self.definition_patch is not None or self.reminder_patch is not None:
                raise ValueError("lifecycle actions do not change definitions")
        return self


class SettingsUpdateRequest(StrictModel):
    request_ref: Identifier
    source_quote: Nonempty
    expected_revision: NonnegativeInt
    patch: dict[str, Any] = Field(min_length=1)


class DiaryRecordRequest(StrictModel):
    request_ref: Identifier
    source_quote: Nonempty
    content: Annotated[str, Field(min_length=1, max_length=16000)]
    diary_date: date | None = None
    linked_record_ids: list[Identifier] = Field(default_factory=list)


class RecordCorrectionRequest(StrictModel):
    request_ref: Identifier
    source_quote: Nonempty
    record_id: Identifier
    expected_revision: PositiveRevision
    reason: Nonempty
    void: StrictBool = False
    corrected_time: ObservationTime | None = None
    corrected_value: NonnegativeNumber | None = None
    corrected_unit: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    corrected_text: Annotated[str, Field(max_length=16000)] | None = None
    corrected_selection_values: dict[Identifier, NonnegativeInt | None] | None = None
    corrected_observations: list[BodyObservation] | None = Field(
        default=None, min_length=1, max_length=8
    )

    @model_validator(mode="after")
    def require_unambiguous_correction(self) -> RecordCorrectionRequest:
        changes = self.model_fields_set & {
            "corrected_time",
            "corrected_value",
            "corrected_unit",
            "corrected_text",
            "corrected_observations",
            "corrected_selection_values",
        }
        if self.void and changes:
            raise ValueError("void cannot be combined with replacement fields")
        if not self.void and not changes:
            raise ValueError("correction requires an explicit replacement field")
        if ("corrected_time" in changes and self.corrected_time is None) or (
            "corrected_observations" in changes and self.corrected_observations is None
        ):
            raise ValueError("time and observations cannot be cleared with null")
        return self


class AnchorRecordRequest(StrictModel):
    request_ref: Identifier
    source_quote: Nonempty
    kind: Literal["wake", "day_start", "bedtime"]
    time: ObservationTime = Field(default_factory=ObservationTime)


class RecordReference(StrictModel):
    id: Identifier
    kind: Literal["habit", "body", "diary", "anchor", "activity", "settings"]
    revision: PositiveRevision
    occurred_at: datetime | None = None
    occurred_date: date | None = None
    precision: Literal["exact", "date", "approximate", "unknown"] = "unknown"


class ToolError(StrictModel):
    code: Identifier
    field: Annotated[str, Field(max_length=500)] | None = None
    message: Nonempty


class ToolResult(StrictModel):
    ok: StrictBool
    status: Literal[
        "READ_OK",
        "APPLIED",
        "ALREADY_APPLIED",
        "NEEDS_INPUT",
        "CONFLICT",
        "FAILED",
        "UNKNOWN",
        "NOT_FOUND",
    ]
    effect_state: Literal["none", "committed", "unknown"]
    operation_id: Identifier | None = None
    records: list[RecordReference] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    receipt_refs: dict[str, str] = Field(default_factory=dict)
    next_action: Literal[
        "NONE",
        "ASK_USER",
        "READ_OPERATION",
        "RELOAD_OBJECT",
        "REPORT_FAILURE",
    ] = "NONE"
    retry_policy: Literal["none", "lookup_only", "retry_same"] = "none"
    errors: list[ToolError] = Field(default_factory=list)

    @model_validator(mode="after")
    def make_effect_state_explicit(self) -> ToolResult:
        successful = self.status in {"READ_OK", "APPLIED", "ALREADY_APPLIED"}
        if self.ok != successful:
            raise ValueError("ok must agree with operation status")
        if self.status in {"APPLIED", "ALREADY_APPLIED"}:
            if self.effect_state != "committed" or not self.operation_id or not self.records:
                raise ValueError("applied results require committed records and operation identity")
        elif self.status == "UNKNOWN":
            if self.effect_state != "unknown" or self.next_action != "READ_OPERATION":
                raise ValueError("unknown effects require receipt lookup")
            if self.records:
                raise ValueError("unknown effects cannot claim saved records")
        elif self.effect_state != "none":
            raise ValueError("non-applied operations cannot claim committed effects")
        if not successful and self.records:
            raise ValueError("failed or unresolved operations cannot contain saved records")
        return self


class DailyAnchor(StrictModel):
    """Internal semantic input; callers must separately verify its source ownership."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)
    owner_id: Identifier
    kind: Literal["wake", "day_start", "bedtime"]
    occurred_at: datetime
    source_ref: Identifier

    @model_validator(mode="after")
    def require_anchor_timezone(self) -> DailyAnchor:
        require_aware(self.occurred_at, "anchor time")
        return self


class ReminderOccurrence(StrictModel):
    """Immutable snapshot for policy evaluation, never a delivery claim or receipt."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)
    instance_id: Identifier
    habit_id: Identifier
    owner_id: Identifier
    delivery_target_id: Identifier
    business_date: date
    trigger: Literal["fixed_time", "time_window", "wake", "bedtime"] = "fixed_time"
    due_at: datetime
    window_start: datetime
    window_end: datetime
    fallback_due_at: datetime | None = None
    target_status: Literal["met", "partial", "unknown"] = "unknown"
    importance: Literal["low", "normal", "high"] = "normal"
    enabled: StrictBool = True
    reminder_limit: NonnegativeInt = 1
    consumed_count: NonnegativeInt = 0
    reserved_count: NonnegativeInt = 0
    active_claim: StrictBool = False
    delivery_status: Literal[
        "NOT_SENT",
        "QUEUED",
        "SENDING",
        "DELIVERED",
        "DELIVERY_UNKNOWN",
        "FAILED",
        "EXPIRED",
        "SUPPRESSED",
    ] = "NOT_SENT"
    failure_proven_unsent: StrictBool = False

    @model_validator(mode="after")
    def validate_window(self) -> ReminderOccurrence:
        for name in ("due_at", "window_start", "window_end", "fallback_due_at"):
            value = getattr(self, name)
            if value is not None:
                require_aware(value, name)
        if self.window_end <= self.window_start:
            raise ValueError("window end must be after its start")
        if not self.window_start <= self.due_at < self.window_end:
            raise ValueError("due_at must be inside the configured window")
        return self
