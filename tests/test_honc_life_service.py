import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta, timezone
from threading import Barrier

import pytest

from uuma.honc.life_models import (
    BodyObservation,
    BodyRecordRequest,
    DiaryRecordRequest,
    HabitCheckinEntry,
    HabitCheckinRequest,
    HabitConfigureRequest,
    HabitDefinitionInput,
    ObservationTime,
    RecordCorrectionRequest,
    SettingsUpdateRequest,
)
from uuma.honc.life_service import LifeService
from uuma.honc.life_store import LifeStore
from uuma.honc.store import HoncStore

NOW = datetime(2026, 10, 13, 20, tzinfo=timezone(timedelta(hours=8)))


@pytest.fixture
def service(tmp_path):
    return LifeService(
        LifeStore(HoncStore(tmp_path / "honc.db")),
        owner_id="owner",
        profile="honc",
        session_id="session",
        clock=lambda: NOW,
    )


def message(service, operation, text, event="event"):
    receipt = service.receive_user_message(
        adapter_id="fixture-user-adapter",
        source_event_id=event,
        raw_content=text,
        received_at=NOW,
        granted_operations=(operation,),
    )
    return service.bind_source(receipt["source_ref"]), receipt["request_refs"][operation]


def habit(service, name="运动", record_type="duration", unit="minute", event="create"):
    bound, ref = message(service, "configure_habit", name, event)
    result = bound.configure_habit(
        HabitConfigureRequest(
            request_ref=ref,
            source_quote=name,
            action="create",
            definition=HabitDefinitionInput(name=name, record_type=record_type, unit=unit),
        )
    )
    assert result.status == "APPLIED"
    return result.records[0].id


def body(service, text="流鼻涕，也有点累", event="body"):
    bound, ref = message(service, "record_body", text, event)
    request = BodyRecordRequest(
        request_ref=ref, source_quote=text, observations=[BodyObservation(description=text)]
    )
    return bound, request, bound.record_body(request)


def test_adapter_replay_uses_transport_identity_and_rejects_source_collision(service):
    first = service.receive_user_message(
        adapter_id="adapter",
        source_event_id="message-id",
        raw_content="今天很好",
        received_at=NOW,
        granted_operations=("record_body",),
    )
    replay = service.receive_user_message(
        adapter_id="adapter",
        source_event_id="message-id",
        raw_content="今天很好",
        received_at=NOW,
        granted_operations=("record_body",),
    )
    assert replay == first
    with pytest.raises(ValueError, match="reused"):
        service.receive_user_message(
            adapter_id="adapter",
            source_event_id="message-id",
            raw_content="别的内容",
            received_at=NOW,
            granted_operations=("record_body",),
        )


def test_grants_are_closed_by_default_and_model_cannot_mint_request_reference(service):
    receipt = service.receive_user_message(
        adapter_id="adapter", source_event_id="read-only", raw_content="看看历史", received_at=NOW
    )
    assert receipt["request_refs"] == {}
    result = service.bind_source(receipt["source_ref"]).record_body(
        BodyRecordRequest(
            request_ref="made-up",
            source_quote="看看历史",
            observations=[BodyObservation(description="累")],
        )
    )
    assert result.status == "FAILED" and result.records == []
    assert result.errors[0].code == "UNBOUND_REQUEST"


@pytest.mark.parametrize("context", ["owner", "profile", "session", "message"])
def test_bound_request_cannot_cross_context_or_be_reused_in_another_message(service, context):
    bound, request, _ = body(service)
    kwargs = {
        "owner_id": "owner",
        "profile": "honc",
        "session_id": "session",
        "source_ref": bound.source_ref,
        "clock": lambda: NOW,
    }
    if context == "message":
        other, _ = message(service, "record_body", "状态好", "another")
        kwargs["source_ref"] = other.source_ref
    else:
        kwargs[{"owner": "owner_id", "profile": "profile", "session": "session_id"}[context]] = (
            "other"
        )
    result = LifeService(service.store, **kwargs).record_body(request)
    assert result.status == "FAILED" and not result.records


def test_source_grant_is_specific_to_operation_and_quote_is_checked(service):
    bound, ref = message(service, "save_diary", "日记", "diary-grant")
    wrong = bound.record_body(
        BodyRecordRequest(
            request_ref=ref, source_quote="日记", observations=[BodyObservation(description="好")]
        )
    )
    assert wrong.errors[0].code == "UNBOUND_REQUEST"
    bound, ref = message(service, "record_body", "状态好", "quote-grant")
    wrong = bound.record_body(
        BodyRecordRequest(
            request_ref=ref, source_quote="生病", observations=[BodyObservation(description="病")]
        )
    )
    assert wrong.errors[0].code == "SOURCE_QUOTE_MISMATCH"
    assert not wrong.records


@pytest.mark.parametrize(
    "observation",
    [
        BodyObservation(description="感冒"),
        BodyObservation(description="状态好", change_text="比昨天好"),
        BodyObservation(description="状态好", severity_text="严重"),
    ],
)
def test_body_cannot_turn_user_words_into_diagnosis_or_invent_changed_state(service, observation):
    bound, ref = message(service, "record_body", "状态好", "no-inference")
    result = bound.record_body(
        BodyRecordRequest(request_ref=ref, source_quote="状态好", observations=[observation])
    )
    assert result.errors[0].code == "BODY_FIELD_NOT_REPORTED"
    assert not result.records


def test_body_unknown_fields_stay_unknown_and_replay_survives_reopen(service):
    bound, request, result = body(service)
    assert result.status == "APPLIED" and result.data["followup_created"] is False
    reopened = LifeService(
        LifeStore(HoncStore(service.store.ledger.path)),
        owner_id="owner",
        profile="honc",
        session_id="session",
        source_ref=bound.source_ref,
        clock=lambda: NOW,
    )
    replay = reopened.record_body(request)
    assert replay.status == "ALREADY_APPLIED"
    assert replay.records == result.records and replay.operation_id == result.operation_id
    saved = reopened.get_history(record_id=result.records[0].id).data["records"][0]
    assert saved["payload"]["time"]["precision"] == "unknown"
    assert saved["payload"]["observations"][0]["reported_score"] is None
    assert saved["payload"]["observations"][0]["body_part"] is None
    assert reopened.get_operation(request_ref=request.request_ref).records == result.records


def test_same_request_changed_content_conflicts_and_new_message_is_new_fact(service):
    bound, request, first = body(service, "今天很好")
    changed = request.model_copy(update={"observations": [BodyObservation(description="不同说法")]})
    conflict = bound.record_body(changed)
    assert conflict.status == "CONFLICT" and not conflict.records
    _, _, second = body(service, "今天很好", "different-event")
    assert second.status == "APPLIED" and first.records != second.records


def test_independent_connections_racing_same_write_commit_only_one_record(service):
    bound, ref = message(service, "record_body", "状态很好", "concurrent")
    request = BodyRecordRequest(
        request_ref=ref,
        source_quote="状态很好",
        observations=[BodyObservation(description="状态很好")],
    )
    barrier = Barrier(2)

    def submit(_):
        independent = LifeService(
            LifeStore(HoncStore(service.store.ledger.path)),
            owner_id="owner",
            profile="honc",
            session_id="session",
            source_ref=bound.source_ref,
            clock=lambda: NOW,
        )
        barrier.wait()
        return independent.record_body(request)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(submit, range(2)))
    assert sorted(result.status for result in results) == ["ALREADY_APPLIED", "APPLIED"]
    assert results[0].operation_id == results[1].operation_id
    assert results[0].records == results[1].records
    assert (
        len(
            service.get_history(start_date=date(2026, 10, 13), end_date=date(2026, 10, 13)).data[
                "records"
            ]
        )
        == 1
    )


def test_habit_update_preserves_old_definition_and_rejects_stale_revision(service):
    identity = habit(service)
    bound, ref = message(service, "configure_habit", "换成小时", "update")
    result = bound.configure_habit(
        HabitConfigureRequest(
            request_ref=ref,
            source_quote="换成小时",
            action="update",
            habit_id=identity,
            expected_revision=1,
            definition_patch={"unit": "hour"},
        )
    )
    assert result.records[0].revision == 2
    with service.store.ledger.connect() as connection:
        original = service.store.get_object(connection, "owner", identity, 1)
        assert original["payload"]["definition"]["unit"] == "minute"
    stale_bound, stale_ref = message(service, "configure_habit", "改名", "stale")
    stale = stale_bound.configure_habit(
        HabitConfigureRequest(
            request_ref=stale_ref,
            source_quote="改名",
            action="update",
            habit_id=identity,
            expected_revision=1,
            definition_patch={"name": "新名字"},
        )
    )
    assert stale.status == "CONFLICT" and not stale.records


def test_habit_patch_revalidates_units_and_unknown_fields_without_consuming_request(service):
    identity = habit(service)
    bound, ref = message(service, "configure_habit", "改单位", "bad-patch")
    for patch in ({"unit": "ml"}, {"unexpected": True}):
        result = bound.configure_habit(
            HabitConfigureRequest(
                request_ref=ref,
                source_quote="改单位",
                action="update",
                habit_id=identity,
                expected_revision=1,
                definition_patch=patch,
            )
        )
        assert result.status == "NEEDS_INPUT" and not result.records
    assert service.get_context().data["habits"][0]["revision"] == 1


def test_pause_resume_retire_keep_history_and_disallow_unknown_auto_creation(service):
    identity = habit(service)
    for revision, action in enumerate(("pause", "resume", "retire"), start=1):
        bound, ref = message(service, "configure_habit", action, action)
        result = bound.configure_habit(
            HabitConfigureRequest(
                request_ref=ref,
                source_quote=action,
                action=action,
                habit_id=identity,
                expected_revision=revision,
            )
        )
        assert result.status == "APPLIED"
    assert service.get_context().data["habits"] == []
    bound, ref = message(service, "record_habit", "运动了", "unknown")
    for target in (identity, "unknown_habit"):
        result = bound.record_habit(
            HabitCheckinRequest(
                request_ref=ref,
                entries=[
                    HabitCheckinEntry(
                        habit_id=target,
                        habit_revision=4,
                        outcome="completed",
                        source_quote="运动了",
                    ),
                ],
            )
        )
        assert not result.ok and not result.records
    with service.store.ledger.connect() as connection:
        assert service.store.get_object(connection, "owner", identity, 1) is not None


def test_atomic_habit_batch_has_no_partial_commit_and_unit_error_is_explicit(service):
    identity = habit(service)
    other = habit(service, name="喝水", record_type="quantity", unit="ml", event="water")
    bound, ref = message(service, "record_habit", "运动二十分钟，喝水一杯", "batch")
    entries = [
        HabitCheckinEntry(
            habit_id=identity,
            habit_revision=1,
            outcome="completed",
            source_quote="运动二十分钟",
            value=20,
            unit="minute",
        ),
        HabitCheckinEntry(
            habit_id=other,
            habit_revision=1,
            outcome="completed",
            source_quote="喝水一杯",
            value=1,
            unit="cup",
        ),
    ]
    result = bound.record_habit(HabitCheckinRequest(request_ref=ref, entries=entries))
    assert result.errors[0].code == "UNIT_MISMATCH" and not result.records
    assert service.get_history(start_date=NOW.date(), end_date=NOW.date()).data["records"] == []


def test_backfill_records_original_date_and_definition_snapshot_not_active_work(service):
    identity = habit(service)
    bound, ref = message(service, "record_habit", "昨天运动二十分钟", "backfill")
    result = bound.record_habit(
        HabitCheckinRequest(
            request_ref=ref,
            entries=[
                HabitCheckinEntry(
                    habit_id=identity,
                    habit_revision=1,
                    outcome="completed",
                    source_quote="昨天运动二十分钟",
                    value=20,
                    unit="minute",
                    time=ObservationTime(occurred_date=date(2026, 10, 12), precision="date"),
                )
            ],
        )
    )
    assert result.status == "APPLIED"
    saved = service.get_history(start_date=date(2026, 10, 12), end_date=date(2026, 10, 12)).data[
        "records"
    ]
    assert saved[0]["payload"]["value"] == 20
    assert saved[0]["payload"]["definition_snapshot"]["unit"] == "minute"
    assert service.get_history(start_date=NOW.date(), end_date=NOW.date()).data["records"] == []
    with service.store.ledger.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM rounds").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM execution_events").fetchone()[0] == 0


def test_unverified_instance_id_cannot_cancel_reminders(service):
    identity = habit(service)
    bound, ref = message(service, "record_habit", "运动完成", "instance")
    result = bound.record_habit(
        HabitCheckinRequest(
            request_ref=ref,
            entries=[
                HabitCheckinEntry(
                    habit_id=identity,
                    habit_revision=1,
                    outcome="completed",
                    source_quote="运动完成",
                    instance_id="model-invented-instance",
                )
            ],
        )
    )
    assert result.errors[0].code == "INSTANCE_NOT_BOUND" and not result.records


def test_default_settings_reads_do_not_write_and_updates_have_revision_guard(service):
    context = service.get_context().data
    assert context["settings_revision"] == 0 and not context["settings_persisted"]
    assert context["settings"]["wake_fallback_time"] == "08:00"
    assert context["settings"]["bedtime_fallback_time"] == "21:30"
    bound, ref = message(service, "update_settings", "起床改成七点", "settings")
    result = bound.update_settings(
        SettingsUpdateRequest(
            request_ref=ref,
            source_quote="起床改成七点",
            expected_revision=0,
            patch={"wake_fallback_time": "07:00"},
        )
    )
    assert result.status == "APPLIED"
    assert service.get_context().data["settings_revision"] == 1
    other, other_ref = message(service, "update_settings", "晚上九点", "stale-settings")
    stale = other.update_settings(
        SettingsUpdateRequest(
            request_ref=other_ref,
            source_quote="晚上九点",
            expected_revision=0,
            patch={"bedtime_fallback_time": "21:00"},
        )
    )
    assert stale.status == "CONFLICT"


@pytest.mark.parametrize(
    "patch",
    [
        {"body_followup_enabled": True},
        {"delivery_target": "other"},
        {"default_reminder_count": "2"},
        {"revision": 999},
    ],
)
def test_settings_cannot_expand_behavior_or_recipient_authority(service, patch):
    bound, ref = message(service, "update_settings", "修改设置", "invalid-settings")
    result = bound.update_settings(
        SettingsUpdateRequest(
            request_ref=ref, source_quote="修改设置", expected_revision=0, patch=patch
        )
    )
    assert not result.ok and not result.records
    assert service.get_context().data["settings_revision"] == 0


def test_diary_preserves_original_text_and_rejects_model_rewrite(service):
    bound, ref = message(service, "save_diary", "今天走了一圈，心情很好。", "diary")
    bad = bound.save_diary(
        DiaryRecordRequest(
            request_ref=ref, source_quote="今天走了一圈", content="今天度过了美妙的一天"
        )
    )
    assert bad.errors[0].code == "DIARY_SOURCE_MISMATCH"
    saved = bound.save_diary(
        DiaryRecordRequest(
            request_ref=ref,
            source_quote="今天走了一圈",
            content="今天走了一圈，心情很好。",
            diary_date=NOW.date(),
        )
    )
    assert saved.status == "APPLIED" and saved.data["habit_checkin_created"] is False
    assert len(service.get_history(start_date=NOW.date(), end_date=NOW.date()).data["records"]) == 1


def test_body_related_record_links_never_cross_owner(service):
    _, _, original = body(service)
    other = LifeService(
        service.store, owner_id="other", profile="honc", session_id="session", clock=lambda: NOW
    )
    bound, ref = message(other, "record_body", "状态好", "cross-link")
    result = bound.record_body(
        BodyRecordRequest(
            request_ref=ref,
            source_quote="状态好",
            observations=[BodyObservation(description="状态好")],
            related_record_ids=[original.records[0].id],
        )
    )
    assert result.status == "NOT_FOUND" and not result.records
    assert other.get_history(record_id=original.records[0].id).data["records"] == []
    assert other.get_operation(operation_id=original.operation_id).status == "NOT_FOUND"


def test_body_correction_then_void_preserve_audit_and_remove_effective_fact(service):
    _, _, original = body(service)
    identity = original.records[0].id
    bound, ref = message(service, "correct_record", "刚才说错了，是状态好", "correction")
    corrected = bound.correct_record(
        RecordCorrectionRequest(
            request_ref=ref,
            source_quote="刚才说错了，是状态好",
            record_id=identity,
            expected_revision=1,
            reason="说错了",
            corrected_observations=[BodyObservation(description="状态好")],
        )
    )
    assert corrected.status == "APPLIED" and corrected.records[0].revision == 2
    audit = service.get_history(record_id=identity, view="audit").data["records"]
    assert [value["revision"] for value in audit] == [1, 2]
    assert audit[0]["payload"]["observations"][0]["description"] == "流鼻涕，也有点累"
    bound, ref = message(service, "correct_record", "撤销这条记录", "void")
    voided = bound.correct_record(
        RecordCorrectionRequest(
            request_ref=ref,
            source_quote="撤销这条记录",
            record_id=identity,
            expected_revision=2,
            reason="重复记录",
            void=True,
        )
    )
    assert voided.status == "APPLIED"
    assert service.get_history(record_id=identity).data["records"] == []
    assert len(service.get_history(record_id=identity, view="audit").data["records"]) == 3


def test_repeated_habit_correction_uses_original_unit_even_after_definition_changes(service):
    identity = habit(service)
    bound, ref = message(service, "record_habit", "运动二十分钟", "initial-fact")
    fact = (
        bound.record_habit(
            HabitCheckinRequest(
                request_ref=ref,
                entries=[
                    HabitCheckinEntry(
                        habit_id=identity,
                        habit_revision=1,
                        outcome="completed",
                        source_quote="运动二十分钟",
                        value=20,
                        unit="minute",
                    )
                ],
            )
        )
        .records[0]
        .id
    )
    bound, ref = message(service, "configure_habit", "以后用小时", "future-unit")
    bound.configure_habit(
        HabitConfigureRequest(
            request_ref=ref,
            source_quote="以后用小时",
            action="update",
            habit_id=identity,
            expected_revision=1,
            definition_patch={"unit": "hour"},
        )
    )
    for revision, number in ((1, 25), (2, 30)):
        text = f"改成{number}分钟"
        bound, ref = message(service, "correct_record", text, f"correction-{revision}")
        result = bound.correct_record(
            RecordCorrectionRequest(
                request_ref=ref,
                source_quote=text,
                record_id=fact,
                expected_revision=revision,
                reason="记错了",
                corrected_value=number,
            )
        )
        assert result.status == "APPLIED"
    effective = service.get_history(record_id=fact).data["records"][0]
    assert effective["payload"]["value"] == 30 and effective["payload"]["unit"] == "minute"
    assert len(service.get_history(record_id=fact, view="audit").data["records"]) == 3


def test_wrong_kind_correction_and_stale_revision_do_not_change_fact(service):
    _, _, initial = body(service)
    bound, ref = message(service, "correct_record", "改成20", "wrong-kind")
    result = bound.correct_record(
        RecordCorrectionRequest(
            request_ref=ref,
            source_quote="改成20",
            record_id=initial.records[0].id,
            expected_revision=1,
            reason="修正",
            corrected_value=20,
        )
    )
    assert result.errors[0].code == "CORRECTION_KIND_MISMATCH"
    stale = bound.correct_record(
        RecordCorrectionRequest(
            request_ref=ref,
            source_quote="改成20",
            record_id=initial.records[0].id,
            expected_revision=99,
            reason="修正",
            void=True,
        )
    )
    assert stale.status == "CONFLICT"
    assert (
        len(service.get_history(record_id=initial.records[0].id, view="audit").data["records"]) == 1
    )


@pytest.mark.parametrize(
    "table", ["life_sources", "life_requests", "life_operations", "life_revisions"]
)
def test_source_receipts_and_history_cannot_be_updated_or_deleted(service, table):
    body(service)
    with service.store.ledger.connect() as connection:
        for action in (f"DELETE FROM {table}", f"UPDATE {table} SET rowid=rowid"):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(action)


def test_failure_after_first_append_rolls_back_fact_and_receipt_and_requires_lookup(
    service, monkeypatch
):
    bound, ref = message(service, "record_body", "有点累", "storage-failure")
    original_append = service.store.append_revision

    def fail_after_append(*args, **kwargs):
        original_append(*args, **kwargs)
        raise sqlite3.OperationalError("simulated failure")

    monkeypatch.setattr(service.store, "append_revision", fail_after_append)
    result = bound.record_body(
        BodyRecordRequest(
            request_ref=ref,
            source_quote="有点累",
            observations=[BodyObservation(description="有点累")],
        )
    )
    assert (
        result.status == "UNKNOWN" and result.records == [] and result.retry_policy == "lookup_only"
    )
    with service.store.ledger.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM life_objects").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM life_revisions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM life_operations").fetchone()[0] == 0
    assert service.get_operation(request_ref=ref).retry_policy == "lookup_only"


def test_lost_commit_acknowledgment_returns_unknown_but_receipt_proves_saved_fact(
    service, monkeypatch
):
    bound, ref = message(service, "record_body", "状态很好", "lost-ack")
    original_transaction = service.store.transaction

    @contextmanager
    def lost_acknowledgment():
        with original_transaction() as connection:
            yield connection
        raise sqlite3.OperationalError("simulated lost acknowledgment after durable commit")

    monkeypatch.setattr(service.store, "transaction", lost_acknowledgment)
    result = bound.record_body(
        BodyRecordRequest(
            request_ref=ref,
            source_quote="状态很好",
            observations=[BodyObservation(description="状态很好")],
        )
    )
    assert (
        result.status == "UNKNOWN" and not result.records and result.retry_policy == "lookup_only"
    )
    receipt = service.get_operation(request_ref=ref)
    assert receipt.status == "APPLIED" and len(receipt.records) == 1
    assert receipt.operation_id == result.operation_id
    assert len(service.get_history(record_id=receipt.records[0].id).data["records"]) == 1


def test_history_requires_range_and_marks_unknown_date_as_recorded_not_occurred(service):
    body(service)
    assert service.get_history().status == "NEEDS_INPUT"
    history = service.get_history(start_date=NOW.date(), end_date=NOW.date()).data["records"]
    assert history[0]["range_basis"] == "recorded_date"
    assert history[0]["payload"]["time"]["occurred_date"] is None
    assert (
        service.get_history(start_date=NOW.date(), end_date=NOW.date(), limit=True).status
        == "NEEDS_INPUT"
    )


def test_life_tables_are_additive_and_cannot_use_other_database_name(tmp_path):
    ledger = HoncStore(tmp_path / "honc.db")
    LifeStore(ledger)
    LifeStore(ledger)
    with ledger.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM honc_schema_migrations").fetchone()[0] == 1
        assert (
            connection.execute("SELECT COUNT(*) FROM honc_life_schema_migrations").fetchone()[0]
            == 1
        )
    with pytest.raises(ValueError, match="isolated"):
        LifeStore(HoncStore(tmp_path / "fixture-other.db"))


def test_history_uses_local_exact_date_and_returns_bounded_distinct_pages(service):
    for index in range(3):
        bound, ref = message(service, "record_body", "状态好", f"page-{index}")
        result = bound.record_body(
            BodyRecordRequest(
                request_ref=ref,
                source_quote="状态好",
                observations=[BodyObservation(description="状态好")],
                time=ObservationTime(
                    occurred_at=datetime(2026, 10, 12, 20, 30, tzinfo=UTC),
                    precision="exact",
                ),
            )
        )
        assert result.status == "APPLIED"
    assert (
        service.get_history(start_date=date(2026, 10, 12), end_date=date(2026, 10, 12)).data[
            "records"
        ]
        == []
    )
    first = service.get_history(start_date=NOW.date(), end_date=NOW.date(), limit=2).data
    assert len(first["records"]) == 2 and first["next_offset"] == 2
    second = service.get_history(start_date=NOW.date(), end_date=NOW.date(), limit=2, offset=2).data
    assert len(second["records"]) == 1 and second["next_offset"] is None
    assert all(value["range_basis"] == "occurred_date" for value in first["records"])
    assert {value["object_id"] for value in first["records"]}.isdisjoint(
        value["object_id"] for value in second["records"]
    )
