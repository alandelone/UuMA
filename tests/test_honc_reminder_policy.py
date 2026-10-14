from datetime import date, datetime, timedelta

import pytest

from uuma.honc.life_models import DailyAnchor, ReminderOccurrence
from uuma.honc.reminder_policy import (
    advance_on_anchor,
    evaluate_reminder,
    plan_reminder_groups,
)


def at(clock: str, day: str = "2026-10-13") -> datetime:
    return datetime.fromisoformat(f"{day}T{clock}:00+08:00")


def occurrence(**changes) -> ReminderOccurrence:
    data = {
        "instance_id": "morning",
        "habit_id": "care",
        "owner_id": "owner",
        "delivery_target_id": "bound",
        "business_date": date(2026, 10, 13),
        "due_at": at("08:00"),
        "window_start": at("08:00"),
        "window_end": at("08:30"),
        "trigger": "wake",
    }
    return ReminderOccurrence(**{**data, **changes})


def test_completed_instance_suppresses_only_unsent_reminder():
    decision = evaluate_reminder(occurrence(target_status="met"), at("08:00"))
    assert decision.action == "SUPPRESS"
    assert decision.reason == "TARGET_MET"
    assert evaluate_reminder(occurrence(target_status="partial"), at("08:00")).action == "ELIGIBLE"


@pytest.mark.parametrize(
    "clock, expected",
    [
        ("07:59", "WAIT"),
        ("08:00", "ELIGIBLE"),
        ("08:29", "ELIGIBLE"),
        ("08:30", "EXPIRE"),
        ("18:00", "EXPIRE"),
    ],
)
def test_point_window_boundaries_are_start_inclusive_end_exclusive(clock, expected):
    assert evaluate_reminder(occurrence(), at(clock)).action == expected


def test_custom_window_does_not_get_an_extra_thirty_minutes():
    item = occurrence(
        trigger="time_window", due_at=at("15:00"), window_start=at("15:00"), window_end=at("16:00")
    )
    assert evaluate_reminder(item, at("15:20")).action == "ELIGIBLE"
    assert evaluate_reminder(item, at("16:00")).action == "EXPIRE"


def test_cross_midnight_window_preserves_original_business_instance():
    item = occurrence(
        trigger="fixed_time",
        due_at=at("23:50"),
        window_start=at("23:50"),
        window_end=at("00:20", "2026-10-14"),
    )
    decision = evaluate_reminder(item, at("00:10", "2026-10-14"))
    assert decision.action == "ELIGIBLE"
    assert decision.instance_id == "morning"
    assert item.business_date == date(2026, 10, 13)


@pytest.mark.parametrize("state", ["DELIVERED", "DELIVERY_UNKNOWN", "SENDING", "QUEUED"])
def test_existing_external_attempt_wins_over_completion_and_expiry(state):
    decision = evaluate_reminder(
        occurrence(delivery_status=state, target_status="met"), at("18:00")
    )
    assert decision.action not in {"ELIGIBLE", "SUPPRESS", "EXPIRE"}
    if state == "DELIVERY_UNKNOWN":
        assert decision.action == "LOOKUP_RECEIPT"


def test_failed_delivery_needs_proof_of_no_external_effect_before_retry():
    failed = occurrence(delivery_status="FAILED")
    assert evaluate_reminder(failed, at("08:00")).action == "LOOKUP_RECEIPT"
    proven = occurrence(delivery_status="FAILED", failure_proven_unsent=True)
    assert evaluate_reminder(proven, at("08:00")).action == "ELIGIBLE"


def test_quota_and_active_claim_block_even_high_importance():
    assert (
        evaluate_reminder(occurrence(importance="high", consumed_count=1), at("08:00")).action
        == "QUOTA_EXHAUSTED"
    )
    assert evaluate_reminder(occurrence(active_claim=True), at("08:00")).action == "IN_FLIGHT"
    assert evaluate_reminder(occurrence(reminder_limit=0), at("08:00")).action == "SUPPRESS"


def test_configured_two_sends_do_not_let_importance_change_remaining_quota():
    item = occurrence(reminder_limit=2, consumed_count=1, importance="high")
    assert evaluate_reminder(item, at("08:00")).action == "ELIGIBLE"
    used = occurrence(reminder_limit=2, consumed_count=2, importance="low")
    assert evaluate_reminder(used, at("08:00")).action == "QUOTA_EXHAUSTED"


def test_simultaneous_group_has_stable_order_and_each_own_instance():
    care = occurrence(instance_id="care_i", habit_id="care", importance="normal")
    diary = occurrence(instance_id="diary_i", habit_id="diary", importance="high")
    plan = plan_reminder_groups([care, diary], at("08:00"))
    assert len(plan.groups) == 1
    assert plan.groups[0].instance_ids == ("diary_i", "care_i")
    reversed_plan = plan_reminder_groups([diary, care], at("08:00"))
    assert reversed_plan.groups == plan.groups
    assert care.consumed_count == diary.consumed_count == 0


def test_groups_never_mix_owners_targets_or_original_due_times():
    items = [
        occurrence(),
        occurrence(instance_id="other_owner", owner_id="other"),
        occurrence(instance_id="other_target", delivery_target_id="other"),
        occurrence(
            instance_id="later",
            due_at=at("08:01"),
            window_start=at("08:01"),
            window_end=at("08:31"),
        ),
    ]
    assert len(plan_reminder_groups(items, at("08:02")).groups) == 4


def test_completed_item_is_removed_without_suppressing_other_group_members():
    care = occurrence(instance_id="care_i", habit_id="care", target_status="met")
    diary = occurrence(instance_id="diary_i", habit_id="diary")
    plan = plan_reminder_groups([care, diary], at("08:00"))
    assert plan.groups[0].instance_ids == ("diary_i",)
    assert {decision.instance_id: decision.action for decision in plan.decisions} == {
        "care_i": "SUPPRESS",
        "diary_i": "ELIGIBLE",
    }


def test_expired_afternoon_is_not_added_to_bedtime_recovery_message():
    old = occurrence(
        instance_id="afternoon",
        due_at=at("15:00"),
        window_start=at("15:00"),
        window_end=at("16:00"),
        trigger="fixed_time",
    )
    diary = occurrence(
        instance_id="diary",
        habit_id="diary",
        trigger="bedtime",
        due_at=at("21:30"),
        window_start=at("21:30"),
        window_end=at("22:00"),
    )
    plan = plan_reminder_groups([old, diary], at("21:40"))
    assert len(plan.groups) == 1
    assert plan.groups[0].instance_ids == ("diary",)


def test_duplicate_input_instances_are_not_double_charged_or_silently_merged():
    with pytest.raises(ValueError, match="duplicate instance"):
        plan_reminder_groups([occurrence(), occurrence()], at("08:00"))


def test_explicit_early_wake_advances_same_instance_and_preserves_fallback():
    original = occurrence()
    anchor = DailyAnchor(
        owner_id="owner", kind="day_start", occurred_at=at("07:00"), source_ref="source_1"
    )
    advanced = advance_on_anchor(original, anchor)
    assert advanced.instance_id == original.instance_id
    assert advanced.due_at == at("07:00")
    assert advanced.fallback_due_at == at("08:00")
    assert advanced.window_end == at("07:00") + timedelta(minutes=30)
    assert original.due_at == at("08:00")
    delivered = advanced.model_copy(update={"delivery_status": "DELIVERED", "consumed_count": 1})
    assert evaluate_reminder(delivered, at("08:00")).action == "ALREADY_HANDLED"


def test_early_bedtime_shares_nightly_identity_and_unknown_is_not_replayed():
    original = occurrence(
        instance_id="bedtime",
        trigger="bedtime",
        due_at=at("21:30"),
        window_start=at("21:30"),
        window_end=at("22:00"),
    )
    anchor = DailyAnchor(
        owner_id="owner", kind="bedtime", occurred_at=at("20:45"), source_ref="source_1"
    )
    advanced = advance_on_anchor(original, anchor)
    assert advanced.instance_id == original.instance_id
    assert advanced.fallback_due_at == at("21:30")
    uncertain = advanced.model_copy(update={"delivery_status": "DELIVERY_UNKNOWN"})
    assert advance_on_anchor(uncertain, anchor) == uncertain
    assert evaluate_reminder(uncertain, at("21:30")).action == "LOOKUP_RECEIPT"


def test_anchor_cannot_change_other_owner_wrong_trigger_or_another_day():
    item = occurrence()
    with pytest.raises(ValueError, match="owner"):
        advance_on_anchor(
            item,
            DailyAnchor(owner_id="other", kind="wake", occurred_at=at("07:00"), source_ref="src"),
        )
    wrong = DailyAnchor(owner_id="owner", kind="bedtime", occurred_at=at("07:00"), source_ref="src")
    assert advance_on_anchor(item, wrong) == item
    other_day = DailyAnchor(
        owner_id="owner", kind="wake", occurred_at=at("07:00", "2026-10-14"), source_ref="src"
    )
    assert advance_on_anchor(item, other_day) == item


def test_late_anchor_does_not_reopen_expired_fallback_or_move_delivery_later():
    anchor = DailyAnchor(owner_id="owner", kind="wake", occurred_at=at("09:00"), source_ref="src")
    item = occurrence()
    assert advance_on_anchor(item, anchor) == item
    assert evaluate_reminder(item, at("09:00")).action == "EXPIRE"


def test_naive_evaluation_clock_is_rejected():
    with pytest.raises(ValueError, match="timezone"):
        evaluate_reminder(occurrence(), datetime(2026, 10, 13, 8))  # noqa: DTZ001 -- intentionally invalid input
