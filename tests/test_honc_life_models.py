from datetime import date, datetime

import pytest
from pydantic import ValidationError

from uuma.honc.life_models import (
    BodyObservation,
    BodyRecordRequest,
    HabitCheckinRequest,
    HabitDefinitionInput,
    LifeSettings,
    ObservationTime,
    ReminderOccurrence,
    ReminderRule,
    ReminderSlot,
    ToolResult,
)


def test_life_settings_keep_confirmed_defaults_and_forbid_body_followup():
    settings = LifeSettings()
    assert settings.wake_fallback_time == "08:00"
    assert settings.bedtime_fallback_time == "21:30"
    assert settings.fixed_point_grace_minutes == 30
    assert settings.default_reminder_count == 1
    assert settings.suppress_when_complete and settings.group_simultaneous
    assert settings.advance_explicit_bedtime
    assert not settings.body_followup_enabled
    with pytest.raises(ValidationError):
        LifeSettings(body_followup_enabled=True)


@pytest.mark.parametrize("clock", ["8:00", "24:00", "08:60", "08:00:00", "tomorrow"])
def test_invalid_setting_clock_is_rejected(clock):
    with pytest.raises(ValidationError):
        LifeSettings(wake_fallback_time=clock)


@pytest.mark.parametrize("value", [True, "2", -1, 1.5])
def test_reminder_count_is_a_real_nonnegative_integer(value):
    with pytest.raises(ValidationError):
        LifeSettings(default_reminder_count=value)


def test_extra_identity_or_delivery_fields_cannot_enter_settings():
    with pytest.raises(ValidationError):
        LifeSettings(user_id="other_user")
    with pytest.raises(ValidationError):
        LifeSettings(delivery_target="arbitrary_recipient")


def test_slot_uses_only_fields_for_its_trigger():
    with pytest.raises(ValidationError):
        ReminderSlot(key="morning", trigger="wake", fixed_time="08:00")
    with pytest.raises(ValidationError):
        ReminderSlot(key="afternoon", trigger="time_window", start="15:00")
    with pytest.raises(ValidationError):
        ReminderSlot(key="meal", trigger="after_meal")
    slot = ReminderSlot(key="afternoon", trigger="time_window", start="15:00", end="16:00")
    assert slot.trigger == "time_window"


def test_multiple_reminders_require_explicit_distinct_send_times():
    with pytest.raises(ValidationError):
        ReminderRule(
            count=2, slots=[ReminderSlot(key="afternoon", trigger="fixed_time", fixed_time="15:00")]
        )
    with pytest.raises(ValidationError):
        ReminderRule(
            count=2,
            slots=[
                ReminderSlot(
                    key="afternoon",
                    trigger="time_window",
                    start="15:00",
                    end="16:00",
                    send_times=["15:00", "15:00"],
                )
            ],
        )
    rule = ReminderRule(
        count=2,
        slots=[
            ReminderSlot(
                key="afternoon",
                trigger="time_window",
                start="15:00",
                end="16:00",
                send_times=["15:00", "15:30"],
            )
        ],
    )
    assert rule.count == 2
    with pytest.raises(ValidationError):
        ReminderRule(
            count=2,
            slots=[
                ReminderSlot(
                    key="afternoon",
                    trigger="time_window",
                    start="15:00",
                    end="16:00",
                    send_times=["15:00", "16:00"],
                )
            ],
        )


def test_weekday_rule_requires_real_unique_weekdays():
    with pytest.raises(ValidationError):
        ReminderRule(recurrence="weekdays", slots=[ReminderSlot(key="wake", trigger="wake")])
    with pytest.raises(ValidationError):
        ReminderRule(
            recurrence="weekdays", weekdays=[1, 1], slots=[ReminderSlot(key="wake", trigger="wake")]
        )
    with pytest.raises(ValidationError):
        ReminderRule(
            recurrence="weekdays", weekdays=[True], slots=[ReminderSlot(key="wake", trigger="wake")]
        )


def test_habit_definition_does_not_mix_units_or_record_types():
    with pytest.raises(ValidationError):
        HabitDefinitionInput(name="Stretch", record_type="duration", unit="times")
    with pytest.raises(ValidationError):
        HabitDefinitionInput(name="Diary", record_type="text", unit="minute")
    with pytest.raises(ValidationError):
        HabitDefinitionInput(name="Water", record_type="quantity")
    assert (
        HabitDefinitionInput(name="Stretch", record_type="duration", unit="minute").unit == "minute"
    )


def test_approximate_observation_keeps_date_without_inventing_a_minute():
    time = ObservationTime(
        occurred_date=date(2026, 10, 12), time_text="昨晚", precision="approximate"
    )
    assert time.occurred_at is None
    assert time.occurred_date == date(2026, 10, 12)
    with pytest.raises(ValidationError):
        ObservationTime(
            occurred_at=datetime.fromisoformat("2026-10-12T21:30:00+08:00"), precision="approximate"
        )


def test_exact_observation_requires_timezone_and_consistent_local_date():
    with pytest.raises(ValidationError):
        ObservationTime(occurred_at=datetime(2026, 10, 12, 12), precision="exact")  # noqa: DTZ001 -- intentionally invalid input
    with pytest.raises(ValidationError):
        ObservationTime(
            occurred_at=datetime.fromisoformat("2026-10-12T18:00:00+00:00"),
            occurred_date=date(2026, 10, 12),
            precision="exact",
        )
    time = ObservationTime(
        occurred_at=datetime.fromisoformat("2026-10-12T18:00:00+00:00"),
        occurred_date=date(2026, 10, 13),
        precision="exact",
    )
    assert time.occurred_date == date(2026, 10, 13)


def test_unknown_observation_does_not_disguise_a_date_as_unknown():
    assert ObservationTime().occurred_at is None
    with pytest.raises(ValidationError):
        ObservationTime(occurred_date=date(2026, 10, 13), precision="unknown")


def test_body_observation_preserves_positive_state_without_requiring_score():
    body = BodyRecordRequest(
        request_ref="req_body",
        source_quote="今天精神很好",
        observations=[BodyObservation(description="今天精神很好")],
    )
    assert body.observations[0].reported_score is None
    assert body.observations[0].body_part is None
    assert body.time.precision == "unknown"
    with pytest.raises(ValidationError):
        BodyObservation(description="有点累", reported_score=3)
    with pytest.raises(ValidationError):
        BodyRecordRequest(
            request_ref="req_body",
            source_quote="有点累",
            observations=[BodyObservation(description="有点累")],
            schedule_followup=True,
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "20"])
def test_habit_values_reject_nonfinite_boolean_or_coerced_quantity(value):
    with pytest.raises(ValidationError):
        HabitCheckinRequest(
            request_ref="req_habit",
            entries=[
                {
                    "habit_id": "stretch",
                    "habit_revision": 1,
                    "outcome": "completed",
                    "source_quote": "拉伸",
                    "value": value,
                    "unit": "minute",
                }
            ],
        )


def test_negative_report_cannot_carry_completed_quantity():
    with pytest.raises(ValidationError):
        HabitCheckinRequest(
            request_ref="req_habit",
            entries=[
                {
                    "habit_id": "stretch",
                    "habit_revision": 1,
                    "outcome": "not_done",
                    "source_quote": "今天没拉伸",
                    "value": 1,
                }
            ],
        )


def test_success_result_must_have_real_committed_record_references():
    with pytest.raises(ValidationError):
        ToolResult(ok=True, status="APPLIED", effect_state="none", operation_id="op_1")
    with pytest.raises(ValidationError):
        ToolResult(ok=True, status="APPLIED", effect_state="committed", operation_id="op_1")
    with pytest.raises(ValidationError):
        ToolResult(ok=True, status="UNKNOWN", effect_state="unknown", next_action="READ_OPERATION")


def test_failure_result_cannot_contain_a_fake_saved_record():
    with pytest.raises(ValidationError):
        ToolResult(
            ok=False,
            status="FAILED",
            effect_state="none",
            records=[{"id": "fake", "kind": "body", "revision": 1}],
        )


def test_occurrence_rejects_naive_window_and_negative_quota():
    base = {
        "instance_id": "morning",
        "habit_id": "care",
        "owner_id": "owner",
        "delivery_target_id": "bound",
        "business_date": date(2026, 10, 13),
        "due_at": datetime.fromisoformat("2026-10-13T08:00:00+08:00"),
        "window_start": datetime.fromisoformat("2026-10-13T08:00:00+08:00"),
        "window_end": datetime.fromisoformat("2026-10-13T08:30:00+08:00"),
    }
    with pytest.raises(ValidationError):
        ReminderOccurrence(**{**base, "window_end": datetime(2026, 10, 13, 8, 30)})  # noqa: DTZ001 -- intentionally invalid input
    with pytest.raises(ValidationError):
        ReminderOccurrence(**{**base, "consumed_count": -1})
