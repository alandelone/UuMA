import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import date, datetime, timedelta
from threading import Barrier

import pytest

from uuma.honc.life_models import (
    LOCAL_TIMEZONE,
    AnchorRecordRequest,
    BodyObservation,
    BodyRecordRequest,
    DiaryRecordRequest,
    HabitCheckinEntry,
    HabitCheckinRequest,
    HabitConfigureRequest,
    HabitDefinitionInput,
    ObservationTime,
    RecordCorrectionRequest,
    ReminderRule,
    ReminderSlot,
    SettingsUpdateRequest,
)
from uuma.honc.life_service import LifeService
from uuma.honc.life_store import LifeStore
from uuma.honc.reminder_runtime import ReminderRuntime
from uuma.honc.service import HoncService
from uuma.honc.store import HoncStore

DAY = date(2026, 10, 13)


def test_body_facts_preserve_running_work_round_and_do_not_invent_score(setup):
    service, runtime = setup
    work = HoncService(service.store.ledger, default_user_id="owner")
    prepared = work.control_round(action="prepare", target_outcome="写一节", tiny_step="写标题")
    work.control_round(action="start", round_id=prepared["round_id"])
    before = asdict(work.store.get_round(prepared["round_id"]))
    segments = [asdict(value) for value in work.store.get_round_segments(prepared["round_id"])]
    bound, ref = source(service, "record_body", "膝盖有点痛", at("08:00"), "body-in-focus")
    invented = bound.record_body(
        BodyRecordRequest(
            request_ref=ref,
            source_quote="膝盖有点痛",
            observations=[
                BodyObservation(
                    description="膝盖有点痛",
                    reported_score=3.0,
                    score_scale="10分",
                )
            ],
        )
    )
    assert invented.status == "NEEDS_INPUT" and invented.records == []
    saved = bound.record_body(
        BodyRecordRequest(
            request_ref=ref,
            source_quote="膝盖有点痛",
            observations=[BodyObservation(description="膝盖有点痛")],
        )
    )
    assert saved.status == "APPLIED"
    assert asdict(work.store.get_round(prepared["round_id"])) == before
    assert [
        asdict(value) for value in work.store.get_round_segments(prepared["round_id"])
    ] == segments
    assert runtime.list_occurrences(DAY) == []


def test_invalid_multi_send_order_and_settings_window_are_rejected_before_commit(setup):
    service, runtime = setup
    bound, ref = source(service, "configure_habit", "添加提醒", at("06:00"), "invalid-order")
    rejected = bound.configure_habit(
        HabitConfigureRequest(
            request_ref=ref,
            source_quote="添加提醒",
            action="create",
            definition=HabitDefinitionInput(name="无效顺序", record_type="boolean"),
            reminder=ReminderRule(
                count=2,
                slots=[
                    ReminderSlot(
                        key="fixed",
                        trigger="fixed_time",
                        fixed_time="08:00",
                        send_times=["08:20", "08:10"],
                    )
                ],
            ),
        )
    )
    assert rejected.status == "NEEDS_INPUT"
    assert service.get_context().data["habits"] == []
    add_habit(
        service,
        "有效两次",
        count=2,
        slots=[
            ReminderSlot(
                key="fixed", trigger="fixed_time", fixed_time="08:00", send_times=["08:00", "08:15"]
            )
        ],
    )
    bound, ref = source(
        service, "update_settings", "设置固定有效期5分钟", at("06:00"), "invalid-grace"
    )
    rejected = bound.update_settings(
        SettingsUpdateRequest(
            request_ref=ref,
            source_quote="设置固定有效期5分钟",
            expected_revision=0,
            patch={"fixed_point_grace_minutes": 5},
        )
    )
    assert rejected.status == "NEEDS_INPUT"
    assert service.get_context().data["settings_revision"] == 0
    runtime.compile_day(DAY, at("07:00"))
    assert runtime.list_occurrences(DAY)[0]["reminder_limit"] == 2


def test_early_anchor_and_independent_tick_race_deliver_one_occurrence(setup):
    service, runtime = setup
    service.clock = lambda: at("07:00")
    add_habit(service)
    bound, ref = source(service, "record_anchor", "刚起床了", at("07:00"), "race-anchor")
    barrier, sink = Barrier(2), []

    def anchor_path():
        barrier.wait()
        result = bound.record_anchor(
            AnchorRecordRequest(request_ref=ref, source_quote="刚起床了", kind="wake")
        )
        assert result.status == "APPLIED"
        tick(runtime, at("07:00"), sink)

    def tick_path():
        independent = ReminderRuntime(
            LifeStore(HoncStore(service.store.ledger.path)),
            owner_id="owner",
            delivery_target_id="bound-private-chat",
        )
        barrier.wait()
        tick(independent, at("07:00"), sink)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(anchor_path), pool.submit(tick_path)]
        for future in futures:
            future.result()
    assert len(sink) == 1
    assert tick(runtime, at("08:00"), sink) == [] and len(sink) == 1
    assert runtime.list_occurrences(DAY)[0]["consumed_count"] == 1


def at(clock, day=DAY):
    return datetime.fromisoformat(f"{day.isoformat()}T{clock}:00").replace(tzinfo=LOCAL_TIMEZONE)


def test_native_suppression_is_terminal_and_never_requeued(setup):
    service, runtime = setup
    add_habit(service)
    sent = []
    tick(runtime, at("08:00"), sent, state="SUPPRESSED")
    assert len(sent) == 1
    assert runtime.prepare(at("08:01")) == []
    value = runtime.list_occurrences(DAY)[0]
    assert value["delivery_status"] == "SUPPRESSED"
    assert value["consumed_count"] == 0 and value["reserved_count"] == 0


def test_correcting_day_moves_completion_without_erasing_original(setup):
    service, runtime = setup
    habit = add_habit(service)
    recorded = checkin(service, habit, None)
    assert recorded.status == "APPLIED"
    assert runtime.prepare(at("07:55")) == []
    bound, ref = source(service, "correct_record", "更正，那是昨天的", at("08:00"), "correct-day")
    result = bound.correct_record(
        RecordCorrectionRequest(
            request_ref=ref,
            source_quote="更正，那是昨天的",
            record_id=recorded.records[0].id,
            expected_revision=1,
            reason="日期误记",
            corrected_time=ObservationTime(precision="date", occurred_date=DAY - timedelta(days=1)),
        )
    )
    assert result.status == "APPLIED"
    assert runtime.list_occurrences(DAY)[0]["target_status"] == "unknown"
    assert runtime.list_occurrences(DAY - timedelta(days=1))[0]["target_status"] == "met"
    audit = bound.get_history(record_id=recorded.records[0].id, view="audit")
    assert len(audit.data["records"]) == 2
    sink = []
    tick(runtime, at("08:00"), sink)
    assert len(sink) == 1


def test_pause_then_resume_retains_unused_instance_and_quota(setup):
    service, runtime = setup
    habit = add_habit(service)
    runtime.compile_day(DAY, at("07:00"))
    original = runtime.list_occurrences(DAY)[0]["instance_id"]
    for action, version, event in (("pause", 1, "pause"), ("resume", 2, "resume")):
        bound, ref = source(service, "configure_habit", action, at("07:10"), event)
        result = bound.configure_habit(
            HabitConfigureRequest(
                request_ref=ref,
                source_quote=action,
                action=action,
                habit_id=habit,
                expected_revision=version,
            )
        )
        assert result.status == "APPLIED"
        assert runtime.prepare(at("07:20")) == []
    sink = []
    tick(runtime, at("08:00"), sink)
    assert len(sink) == 1
    current = runtime.list_occurrences(DAY)[0]
    assert current["instance_id"] == original and current["consumed_count"] == 1


def test_filtered_context_exposes_exact_occurrence_with_frozen_revision_after_unit_edit(setup):
    service, runtime = setup
    habit = add_habit(service, "运动", record_type="duration", target=20)
    runtime.compile_day(DAY, at("07:00"))
    original = runtime.list_occurrences(DAY)[0]
    bound, ref = source(service, "configure_habit", "运动单位改成hour", at("08:01"), "change-unit")
    changed = bound.configure_habit(
        HabitConfigureRequest(
            request_ref=ref,
            source_quote="运动单位改成hour",
            action="update",
            habit_id=habit,
            expected_revision=1,
            definition_patch={"unit": "hour", "target_value": 1.0},
        )
    )
    assert changed.status == "APPLIED"
    context = service.get_context(habit_name="运动", compact=True)
    assert len(context.data["habits"]) == 1 and len(context.data["occurrences"]) == 1
    assert context.data["habits"][0]["revision"] == 2
    assert context.data["occurrences"][0]["habit_revision"] == 1
    assert context.data["occurrences"][0]["definition_snapshot"]["unit"] == "minute"
    assert checkin(service, habit, original["instance_id"], value=20).status == "APPLIED"
    assert runtime.list_occurrences(DAY)[0]["target_status"] == "met"


def test_compact_overview_avoids_long_definition_payload_and_unknown_filter_does_not_create(setup):
    service, _runtime = setup
    for index in range(8):
        add_habit(
            service,
            "习惯" + str(index),
            slots=[
                ReminderSlot(key="first", trigger="fixed_time", fixed_time="09:00"),
                ReminderSlot(key="second", trigger="fixed_time", fixed_time="12:00"),
            ],
        )
    context = service.get_context(compact=True)
    assert len(context.data["habits"]) == 8 and context.data["occurrences"] == []
    assert len(context.model_dump_json()) < 5000
    selected = service.get_context(habit_name="习惯3", compact=True)
    assert len(selected.data["habits"]) == 1 and len(selected.data["occurrences"]) == 2
    assert service.get_context(habit_name="不存在", compact=True).status == "NOT_FOUND"
    assert len(service.get_context(compact=True).data["habits"]) == 8


def test_weekly_target_uses_effective_values_and_original_units(setup):
    service, runtime = setup
    habit = add_habit(service, "周运动", record_type="duration", target=40, target_period="week")
    assert (
        checkin(
            service,
            habit,
            None,
            value=20,
            outcome="partial",
            event="monday",
            day=DAY - timedelta(days=1),
        ).status
        == "APPLIED"
    )
    today = checkin(service, habit, None, value=20, outcome="partial", event="tuesday")
    assert today.status == "APPLIED"
    assert runtime.list_occurrences(DAY)[0]["target_status"] == "met"
    bound, ref = source(
        service, "correct_record", "更正今天运动为10分钟", at("08:00"), "weekly-correction"
    )
    corrected = bound.correct_record(
        RecordCorrectionRequest(
            request_ref=ref,
            source_quote="更正今天运动为10分钟",
            record_id=today.records[0].id,
            expected_revision=1,
            reason="数字误记",
            corrected_value=10.0,
        )
    )
    assert corrected.status == "APPLIED"
    assert runtime.list_occurrences(DAY)[0]["target_status"] == "partial"


def test_new_reminder_inherits_changed_defaults_but_explicit_count_is_preserved(setup):
    service, runtime = setup
    bound, ref = source(
        service, "update_settings", "默认提醒次数设为0，重要度高", at("06:00"), "defaults"
    )
    settings = bound.update_settings(
        SettingsUpdateRequest(
            request_ref=ref,
            source_quote="默认提醒次数设为0，重要度高",
            expected_revision=0,
            patch={"default_reminder_count": 0, "default_importance": "high"},
        )
    )
    assert settings.status == "APPLIED"
    bound, ref = source(service, "configure_habit", "添加新习惯", at("06:00"), "new-default")
    new = bound.configure_habit(
        HabitConfigureRequest(
            request_ref=ref,
            source_quote="添加新习惯",
            action="create",
            definition=HabitDefinitionInput(name="新习惯", record_type="boolean"),
            reminder=ReminderRule(slots=[ReminderSlot(key="wake", trigger="wake")]),
        )
    )
    assert new.status == "APPLIED"
    assert new.data["reminder"]["count"] == 0 and new.data["reminder"]["importance"] == "high"
    add_habit(service, "显式一次", count=1, importance="normal")
    runtime.compile_day(DAY, at("07:00"))
    occurrences = runtime.list_occurrences(DAY)
    assert len(occurrences) == 2
    disabled = next(value for value in occurrences if value["habit_id"] == new.records[0].id)
    assert disabled["reminder_limit"] == 0 and disabled["enabled"] is False
    enabled = next(value for value in occurrences if value["habit_id"] != new.records[0].id)
    assert enabled["reminder_limit"] == 1
    sink = []
    tick(runtime, at("08:00"), sink)
    assert len(sink) == 1 and disabled["instance_id"] not in sink[0]["instance_ids_json"]


@pytest.fixture
def setup(tmp_path):
    store = LifeStore(HoncStore(tmp_path / "honc.db"))
    runtime = ReminderRuntime(store, owner_id="owner", delivery_target_id="bound-private-chat")
    service = LifeService(
        store,
        owner_id="owner",
        profile="honc",
        session_id="fixture-session",
        clock=lambda: at("08:00"),
        reminders=runtime,
    )
    return service, runtime


def source(service, operation, text, now, event):
    receipt = service.receive_user_message(
        adapter_id="authenticated-fixture",
        source_event_id=event,
        raw_content=text,
        received_at=now,
        granted_operations=(operation,),
    )
    return service.bind_source(receipt["source_ref"]), receipt["request_refs"][operation]


def add_habit(
    service,
    name="晨仪",
    slots=None,
    record_type="boolean",
    target=None,
    count=1,
    importance="normal",
    role="habit",
    target_period="day",
):
    bound, ref = source(service, "configure_habit", f"添加{name}", at("06:00"), name)
    result = bound.configure_habit(
        HabitConfigureRequest(
            request_ref=ref,
            source_quote=f"添加{name}",
            action="create",
            definition=HabitDefinitionInput(
                name=name,
                record_type=record_type,
                unit="minute" if record_type == "duration" else None,
                target_value=target,
                semantic_role=role,
                target_period=target_period,
            ),
            reminder=ReminderRule(
                count=count,
                importance=importance,
                slots=slots or [ReminderSlot(key="wake", trigger="wake")],
            ),
        )
    )
    assert result.status == "APPLIED"
    return result.records[0].id


def tick(runtime, now, sink, state="DELIVERED"):
    prepared = runtime.prepare(now)
    for group in prepared:

        def deliver(value):
            sink.append(value)
            return {"state": state, "native_execution_id": "native-" + value["group_id"]}

        runtime.dispatch(group["group_id"], group["fence"], now, deliver)
    return prepared


def checkin(
    service,
    habit_id,
    instance,
    text="完成了",
    value=None,
    outcome="completed",
    day=DAY,
    event="checkin",
):
    bound, ref = source(service, "record_habit", text, at("07:50"), event)
    return bound.record_habit(
        HabitCheckinRequest(
            request_ref=ref,
            entries=[
                HabitCheckinEntry(
                    habit_id=habit_id,
                    habit_revision=1,
                    instance_id=instance,
                    outcome=outcome,
                    source_quote=text,
                    value=value,
                    unit="minute" if value is not None else None,
                    time=ObservationTime(occurred_date=day, precision="date"),
                )
            ],
        )
    )


def test_default_morning_once_and_tick_does_not_invent_wake_observation(setup):
    service, runtime = setup
    add_habit(service)
    sink = []
    assert tick(runtime, at("07:59"), sink) == []
    assert len(tick(runtime, at("08:00"), sink)) == 1
    assert tick(runtime, at("08:05"), sink) == []
    assert len(sink) == 1 and runtime.list_occurrences(DAY)[0]["consumed_count"] == 1
    with service.store.ledger.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM life_anchors").fetchone()[0] == 0


@pytest.mark.parametrize("kind,text", [("wake", "刚起床了"), ("day_start", "开始今天的计划")])
def test_early_explicit_morning_shares_fallback_quota_and_keeps_actual_precision(setup, kind, text):
    service, runtime = setup
    add_habit(service)
    runtime.compile_day(DAY, at("06:00"))
    original = runtime.list_occurrences(DAY)[0]["instance_id"]
    bound, ref = source(service, "record_anchor", text, at("07:00"), "anchor")
    result = bound.record_anchor(AnchorRecordRequest(request_ref=ref, source_quote=text, kind=kind))
    assert result.status == "APPLIED" and result.records[0].precision == "unknown"
    sink = []
    assert len(tick(runtime, at("07:00"), sink)) == 1
    assert tick(runtime, at("08:00"), sink) == []
    assert runtime.list_occurrences(DAY)[0]["instance_id"] == original and len(sink) == 1


def test_early_bedtime_group_once_no_afternoon_chase_and_optional_body_invitation(setup):
    service, runtime = setup
    add_habit(
        service,
        "日记",
        [ReminderSlot(key="bed", trigger="bedtime")],
        record_type="text",
        role="diary",
        importance="high",
    )
    add_habit(service, "睡前15", [ReminderSlot(key="bed", trigger="bedtime")], record_type="text")
    add_habit(
        service,
        "下午休息",
        [ReminderSlot(key="rest", trigger="time_window", start="15:00", end="16:00")],
    )
    text = "准备睡了"
    bound, ref = source(service, "record_anchor", text, at("20:45"), "bed-anchor")
    assert (
        bound.record_anchor(
            AnchorRecordRequest(request_ref=ref, source_quote=text, kind="bedtime")
        ).status
        == "APPLIED"
    )
    sink = []
    assert len(tick(runtime, at("20:45"), sink)) == 1
    assert "身体状态" in sink[0]["content"] and "下午休息" not in sink[0]["content"]
    assert tick(runtime, at("21:30"), sink) == [] and len(sink) == 1


def test_future_or_quoted_bedtime_is_not_an_anchor(setup):
    service, _runtime = setup
    add_habit(service)
    for index, text in enumerate(("明天准备睡早一点", "如果准备睡了", "还没准备睡了")):
        bound, ref = source(service, "record_anchor", text, at("07:00"), str(index))
        result = bound.record_anchor(
            AnchorRecordRequest(request_ref=ref, source_quote=text, kind="bedtime")
        )
        assert not result.ok and not result.records
    with service.store.ledger.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM life_anchors").fetchone()[0] == 0


def test_complete_corresponding_occurrence_suppresses_but_not_other_meal(setup):
    service, runtime = setup
    identity = add_habit(
        service,
        "eat_bh",
        [
            ReminderSlot(key="breakfast", trigger="fixed_time", fixed_time="09:00"),
            ReminderSlot(key="lunch", trigger="fixed_time", fixed_time="12:00"),
        ],
    )
    runtime.compile_day(DAY, at("08:00"))
    occurrences = runtime.list_occurrences(DAY)
    breakfast = next(value for value in occurrences if value["slot_key"] == "breakfast")
    assert checkin(service, identity, breakfast["instance_id"]).status == "APPLIED"
    sink = []
    assert tick(runtime, at("09:00"), sink) == []
    assert len(tick(runtime, at("12:00"), sink)) == 1
    assert len(sink) == 1


def test_partial_quantity_does_not_meet_target_and_two_sends_share_quota(setup):
    service, runtime = setup
    identity = add_habit(
        service,
        "运动",
        [
            ReminderSlot(
                key="sport",
                trigger="time_window",
                start="15:00",
                end="16:00",
                send_times=["15:00", "15:30"],
            )
        ],
        record_type="duration",
        target=40,
        count=2,
        importance="high",
    )
    runtime.compile_day(DAY, at("14:00"))
    occurrence = runtime.list_occurrences(DAY)[0]
    assert (
        checkin(service, identity, occurrence["instance_id"], value=20, outcome="partial").status
        == "APPLIED"
    )
    sink = []
    assert len(tick(runtime, at("15:00"), sink)) == 1
    assert tick(runtime, at("15:01"), sink) == []
    assert len(tick(runtime, at("15:30"), sink)) == 1
    assert tick(runtime, at("15:40"), sink) == []
    assert len(sink) == 2 and runtime.list_occurrences(DAY)[0]["consumed_count"] == 2


def test_completion_after_first_send_preserves_receipt_and_cancels_second(setup):
    service, runtime = setup
    identity = add_habit(
        service,
        "运动",
        [
            ReminderSlot(
                key="sport",
                trigger="time_window",
                start="15:00",
                end="16:00",
                send_times=["15:00", "15:30"],
            )
        ],
        record_type="duration",
        target=40,
        count=2,
    )
    sink = []
    tick(runtime, at("15:00"), sink)
    occurrence = runtime.list_occurrences(DAY)[0]
    assert checkin(service, identity, occurrence["instance_id"], value=40).status == "APPLIED"
    assert tick(runtime, at("15:30"), sink) == [] and len(sink) == 1
    with service.store.ledger.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM life_reminder_events WHERE event_type='DELIVERED'"
            ).fetchone()[0]
            == 1
        )


@pytest.mark.parametrize("clock", ["08:30", "09:00", "21:30"])
def test_missed_morning_expires_and_never_moves_to_night(setup, clock):
    service, runtime = setup
    add_habit(service)
    sink = []
    assert tick(runtime, at(clock), sink) == []
    assert runtime.list_occurrences(DAY)[0]["delivery_status"] == "EXPIRED"


def test_cross_midnight_business_date_and_custom_window_end(setup):
    service, runtime = setup
    add_habit(service, slots=[ReminderSlot(key="late", trigger="fixed_time", fixed_time="23:50")])
    sink = []
    tick(runtime, at("00:10", DAY + timedelta(days=1)), sink)
    assert len(sink) == 1
    assert runtime.list_occurrences(DAY)[0]["consumed_count"] == 1
    assert runtime.list_occurrences(DAY + timedelta(days=1))[0]["consumed_count"] == 0


def test_completed_member_removed_from_group_and_importance_order_is_stable(setup):
    service, runtime = setup
    normal = add_habit(service, "normal")
    add_habit(service, "high", importance="high")
    runtime.compile_day(DAY, at("07:00"))
    instance = next(
        value["instance_id"]
        for value in runtime.list_occurrences(DAY)
        if value["habit_id"] == normal
    )
    checkin(service, normal, instance)
    sink = []
    tick(runtime, at("08:00"), sink)
    assert len(sink) == 1 and "high" in sink[0]["content"] and "normal" not in sink[0]["content"]


def test_reservation_fence_completion_and_two_worker_race(setup):
    service, runtime = setup
    identity = add_habit(service)
    barrier = Barrier(2)

    def reserve(_):
        independent = ReminderRuntime(
            LifeStore(HoncStore(service.store.ledger.path)),
            owner_id="owner",
            delivery_target_id="bound-private-chat",
        )
        barrier.wait()
        return independent.prepare(at("08:00"))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reserve, range(2)))
    groups = [group for result in results for group in result]
    assert len(groups) == 1
    instance = runtime.list_occurrences(DAY)[0]["instance_id"]
    assert checkin(service, identity, instance).status == "APPLIED"
    sink = []
    receipt = runtime.dispatch(
        groups[0]["group_id"], groups[0]["fence"], at("08:01"), lambda value: sink.append(value)
    )
    assert receipt["state"] == "CANCELLED" and sink == []


def test_lost_reservation_fence_cannot_submit_and_recovery_reclaims_unsent_only(setup):
    service, runtime = setup
    add_habit(service)
    original = runtime.prepare(at("08:00"), lease_minutes=1)[0]
    runtime.reconcile(at("08:02"), lambda _: None)
    replacement = runtime.prepare(at("08:02"))[0]
    assert (
        original["group_id"] == replacement["group_id"]
        and original["fence"] != replacement["fence"]
    )
    sink = []
    stale = runtime.dispatch(
        original["group_id"], original["fence"], at("08:02"), lambda value: sink.append(value)
    )
    assert stale["state"] == "STALE_FENCE" and sink == []


@pytest.mark.parametrize("state", ["QUEUED", "DELIVERY_UNKNOWN"])
def test_uncertain_or_queued_delivery_survives_restart_without_blind_resend(setup, state):
    service, runtime = setup
    add_habit(service)
    sink = []
    tick(runtime, at("08:00"), sink, state=state)
    reopened = ReminderRuntime(
        LifeStore(HoncStore(service.store.ledger.path)),
        owner_id="owner",
        delivery_target_id="bound-private-chat",
    )
    reopened.reconcile(at("08:05"), lambda _: None)
    assert tick(reopened, at("08:05"), sink) == [] and len(sink) == 1
    assert reopened.list_occurrences(DAY)[0]["reserved_count"] == 1
    reopened.reconcile(
        at("08:06"), lambda native: {"state": "DELIVERED", "native_execution_id": native}
    )
    assert reopened.list_occurrences(DAY)[0]["consumed_count"] == 1
    assert tick(reopened, at("08:10"), sink) == []


def test_exception_after_external_handoff_is_unknown_not_retryable_failure(setup):
    service, runtime = setup
    add_habit(service)
    group = runtime.prepare(at("08:00"))[0]

    def unknown(_):
        raise TimeoutError("acknowledgment lost")

    receipt = runtime.dispatch(
        group["group_id"],
        group["fence"],
        at("08:00"),
        unknown,
        allocate=lambda _: "original-native-attempt",
    )
    assert receipt["state"] == "DELIVERY_UNKNOWN"
    assert runtime.prepare(at("08:10")) == []
    with service.store.ledger.connect() as connection:
        value = connection.execute(
            "SELECT native_execution_id FROM life_reminder_groups"
        ).fetchone()[0]
        assert value == "original-native-attempt"


def test_diary_and_one_related_checkin_atomic_replay_backfill_and_void(setup):
    service, runtime = setup
    add_habit(
        service,
        "Dairy",
        [ReminderSlot(key="bed", trigger="bedtime")],
        record_type="text",
        role="diary",
    )
    text = "昨天很开心"
    bound, ref = source(service, "save_diary", text, at("08:00"), "diary")
    request = DiaryRecordRequest(
        request_ref=ref, source_quote=text, content=text, diary_date=DAY - timedelta(days=1)
    )
    result = bound.save_diary(request)
    assert result.status == "APPLIED" and len(result.records) == 2
    assert bound.save_diary(request).records == result.records
    runtime.compile_day(DAY, at("08:00"))
    assert runtime.list_occurrences(DAY)[0]["target_status"] == "unknown"
    assert runtime.list_occurrences(DAY - timedelta(days=1))[0]["target_status"] == "met"
    bound, ref = source(service, "correct_record", "撤销昨天日记", at("08:00"), "void")
    voided = bound.correct_record(
        RecordCorrectionRequest(
            request_ref=ref,
            source_quote="撤销昨天日记",
            record_id=result.records[0].id,
            expected_revision=1,
            reason="重复",
            void=True,
        )
    )
    assert len(voided.records) == 2 and voided.status == "APPLIED"
    assert runtime.list_occurrences(DAY - timedelta(days=1))[0]["target_status"] == "unknown"


def test_reminder_and_anchor_history_is_append_only(setup):
    service, runtime = setup
    add_habit(service)
    tick(runtime, at("08:00"), [])
    with (
        service.store.ledger.connect() as connection,
        pytest.raises(sqlite3.IntegrityError, match="immutable"),
    ):
        connection.execute("DELETE FROM life_reminder_events")
