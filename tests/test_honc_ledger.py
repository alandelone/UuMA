from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from uuma.honc.models import (
    ActualKind,
    AssessmentResult,
    EventType,
    ExecutionEvent,
    HabitDefinition,
    RoundStatus,
    TaskSnapshot,
    TrustedInput,
    get_timezone,
)
from uuma.honc.service import HoncService
from uuma.honc.store import HoncStore


@pytest.fixture
def honc_store(tmp_path: Path) -> HoncStore:
    db_path = tmp_path / "honc" / "honc.db"
    return HoncStore(db_path)


@pytest.fixture
def honc_service(honc_store: HoncStore) -> HoncService:
    return HoncService(store=honc_store)


def test_schema_initialization_and_migration(tmp_path: Path):
    db_path = tmp_path / "honc" / "honc.db"
    store = HoncStore(db_path)
    with store.connect() as conn:
        # Check migrations table
        cur = conn.execute("SELECT version, description FROM honc_schema_migrations")
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0]["version"] == 1

        # Check WAL mode
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"

        # Check foreign keys
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1


def test_trusted_input_deduplication(honc_store: HoncStore):
    inp1 = TrustedInput(
        user_id="user_1",
        entrypoint="hermes_local",
        source_receipt_id="msg_100",
        raw_content="Done reading chapter 1",
    )
    saved1 = honc_store.record_trusted_input(inp1)
    assert saved1.input_id == inp1.input_id

    # Second call with identical content & metadata has same source_digest
    inp2 = TrustedInput(
        user_id="user_1",
        entrypoint="hermes_local",
        source_receipt_id="msg_100",
        raw_content="Done reading chapter 1",
    )
    saved2 = honc_store.record_trusted_input(inp2)
    # Deduplicated: returns the original input record
    assert saved2.input_id == saved1.input_id


def test_execution_events_immutability(honc_store: HoncStore):
    event = ExecutionEvent(
        event_type=EventType.PROGRESS,
        outcome="Written 500 words",
        actual_kind=ActualKind.TIMED,
        actual_duration_seconds=1500,
    )
    saved = honc_store.record_execution_event(event)

    # Direct UPDATE must fail via trigger
    with honc_store.connect() as conn, pytest.raises(sqlite3.DatabaseError, match="immutable"):
        conn.execute(
            "UPDATE execution_events SET outcome = 'Mutated' WHERE event_id = ?",
            (saved.event_id,),
        )

    # Direct DELETE must fail via trigger
    with honc_store.connect() as conn, pytest.raises(sqlite3.DatabaseError, match="immutable"):
        conn.execute(
            "DELETE FROM execution_events WHERE event_id = ?",
            (saved.event_id,),
        )


def test_round_lifecycle_and_duration_accounting(honc_service: HoncService):
    # 1. Prepare
    res_prep = honc_service.control_round(
        action="prepare",
        target_outcome="Draft architecture doc",
        tiny_step="Open editor and list headers",
        mode="Focus",
        timer_budget_minutes=25,
    )
    round_id = res_prep["round_id"]
    assert res_prep["status"] == RoundStatus.PREPARED
    assert res_prep["revision"] == 1

    # 2. Cannot create a second active round for the same user
    with pytest.raises(ValueError, match="already has an active round"):
        honc_service.control_round(
            action="prepare",
            target_outcome="Second task",
            tiny_step="Second step",
        )

    # 3. Start
    res_start = honc_service.control_round(action="start", round_id=round_id)
    assert res_start["status"] == RoundStatus.RUNNING
    assert res_start["revision"] == 2

    # 4. Pause
    res_pause = honc_service.control_round(
        action="pause", round_id=round_id, interruption_reason="phone call"
    )
    assert res_pause["status"] == RoundStatus.PAUSED
    assert res_pause["revision"] == 3

    # 5. Resume
    res_resume = honc_service.control_round(action="resume", round_id=round_id)
    assert res_resume["status"] == RoundStatus.RUNNING
    assert res_resume["revision"] == 4

    # 6. End without outcome -> AWAITING_CHECK
    res_end = honc_service.control_round(action="end", round_id=round_id)
    assert res_end["status"] == RoundStatus.AWAITING_CHECK
    assert res_end["revision"] == 5

    # Segments check
    segments = honc_service.store.get_round_segments(round_id)
    assert len(segments) == 2  # first segment before pause, second segment before end
    assert all(s.ended_at is not None for s in segments)
    assert segments[0].interruption_reason == "phone call"


def test_round_revision_conflict(honc_service: HoncService):
    res_prep = honc_service.control_round(
        action="prepare",
        target_outcome="Draft spec",
        tiny_step="Outline section 1",
    )
    round_id = res_prep["round_id"]

    # Starting with wrong expected revision
    with pytest.raises(ValueError, match="Revision conflict"):
        honc_service.control_round(
            action="start",
            round_id=round_id,
            expected_revision=999,
        )


def test_record_execution_unknown_time_enforcement(honc_service: HoncService):
    # User reports doing work without duration -> actual_kind must be UNKNOWN
    res = honc_service.record_execution(
        raw_content="Wrote tests for login module",
        outcome="Login tests done",
        next_step="Run lint",
    )
    event_id = res["record_id"]
    event = honc_service.store.get_event(event_id)
    assert event is not None
    assert event.actual_kind == ActualKind.UNKNOWN
    assert event.actual_duration_seconds is None


def test_backfill_recording_preserves_actual_vs_recorded_time(honc_service: HoncService):
    yesterday_iso = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    res = honc_service.record_execution(
        raw_content="Yesterday night I did 30 mins workout",
        outcome="30 mins workout",
        actual_kind=ActualKind.USER_REPORTED,
        actual_duration_seconds=1800,
        occurred_at=yesterday_iso,
    )
    event_id = res["record_id"]
    event = honc_service.store.get_event(event_id)
    assert event is not None
    assert event.event_type == EventType.BACKFILL
    assert event.occurred_at == yesterday_iso
    assert event.recorded_at != yesterday_iso  # recorded today
    assert event.actual_kind == ActualKind.USER_REPORTED
    assert event.actual_duration_seconds == 1800


def test_habit_checkin_multiple_ticks(honc_service: HoncService):
    honc_service.store.register_habit(
        HabitDefinition(
            habit_id="water",
            name="Drink Water",
            field_type="number",
            unit="ml",
            daily_target=2000,
        )
    )

    tick1 = honc_service.check_habit("water", quantity=500)
    tick2 = honc_service.check_habit("water", quantity=300)

    events = honc_service.store.list_events(limit=10)
    water_events = [e for e in events if e.habit_id == "water"]
    assert len(water_events) == 2
    assert water_events[0].event_id != water_events[1].event_id
    assert tick1["record_id"] != tick2["record_id"]


def test_completion_assessment_criteria_evaluation(honc_service: HoncService):
    task_id = "node-action-123"
    # 1. Snapshot with done_when criteria
    honc_service.store.save_task_snapshot(
        TaskSnapshot(
            graph_database_id="db-uuid",
            node_id=task_id,
            title="Implement user auth",
            done_when="JWT token generated; password hash verified; refresh token working",
        )
    )

    # 2. Insufficient evidence
    eval_insufficient = honc_service.assess_completion(
        task_id=task_id,
        evidence="Password hash verified with argon2",
    )
    assert eval_insufficient["result"] == AssessmentResult.INSUFFICIENT
    assert eval_insufficient["can_apply"] is False
    assert len(eval_insufficient["satisfied_items"]) == 1
    assert len(eval_insufficient["missing_items"]) == 2

    # 3. Sufficient evidence satisfying all criteria
    eval_satisfied = honc_service.assess_completion(
        task_id=task_id,
        evidence="JWT token generated, password hash verified, and refresh token working nicely",
    )
    assert eval_satisfied["result"] == AssessmentResult.SATISFIED
    assert eval_satisfied["can_apply"] is True
    assert len(eval_satisfied["missing_items"]) == 0


def test_correct_record_preserves_history_and_reversal(honc_service: HoncService):
    # 1. Original event
    rec = honc_service.record_execution(
        raw_content="Finished draft v1",
        outcome="Finished draft v1",
        task_id="node-action-1",
    )
    orig_event_id = rec["record_id"]

    # 2. User corrects: actually only outline, not draft
    corr = honc_service.correct_record(
        original_event_id=orig_event_id,
        reason="Only outline completed, not full draft",
        corrected_outcome="Draft outline completed",
        compensating_action="reopen",
    )

    assert corr["assessment_status"] == "CORRECTED"
    corr_event_id = corr["record_id"]

    # 3. History chain query
    chain = honc_service.store.get_correction_chain(orig_event_id)
    assert len(chain) == 2
    assert chain[0].event_id == orig_event_id
    assert chain[1].event_id == corr_event_id
    assert chain[1].correction_ref_id == orig_event_id

    # 4. Original event is unchanged
    orig_reloaded = honc_service.store.get_event(orig_event_id)
    assert orig_reloaded is not None
    assert orig_reloaded.outcome == "Finished draft v1"


def test_daily_report_timezone_aggregation(honc_service: HoncService):
    tz = get_timezone("Asia/Kuala_Lumpur")
    now_kl = datetime.now(tz)
    today_str = now_kl.strftime("%Y-%m-%d")

    # Record some events today
    honc_service.record_execution(
        raw_content="Meeting with client",
        outcome="Met client and agreed scope",
        next_step="Send proposal",
        blocker="Waiting for legal sign-off",
        actual_kind=ActualKind.TIMED,
        actual_duration_seconds=1800,
    )
    honc_service.check_habit("stretch", quantity=1)

    report = honc_service.get_report(date_str=today_str, timezone_name="Asia/Kuala_Lumpur")
    assert report["date"] == today_str
    assert len(report["done_items"]) >= 1
    assert "Send proposal" in report["next_items"]
    assert "Waiting for legal sign-off" in report["blockers"]
    assert report["timed_seconds"] >= 1800
    assert report["active_minutes"] >= 30.0


def test_restart_recovery(tmp_path: Path):
    db_path = tmp_path / "honc" / "honc.db"
    store1 = HoncStore(db_path)
    service1 = HoncService(store=store1)

    service1.control_round(
        action="prepare",
        target_outcome="Persistent task",
        tiny_step="Step 1",
    )
    rec = service1.record_execution(raw_content="Persistent note", outcome="Note taken")

    # Simulate restart by instantiating new store & service on same file
    store2 = HoncStore(db_path)
    service2 = HoncService(store=store2)

    status = service2.get_status()
    assert status["active_round"] is not None
    assert status["active_round"]["target_outcome"] == "Persistent task"

    event = store2.get_event(rec["record_id"])
    assert event is not None
    assert event.outcome == "Note taken"
