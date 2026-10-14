"""Execute the 21 accepted product cases against durable backend state and receipts."""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from test_honc_reminder_runtime import DAY, add_habit, at, checkin, source, tick

from uuma.honc.life_models import AnchorRecordRequest, DiaryRecordRequest, ReminderSlot
from uuma.honc.life_service import LifeService
from uuma.honc.life_store import LifeStore
from uuma.honc.reminder_runtime import ReminderRuntime
from uuma.honc.store import HoncStore

CONTRACT = json.loads(
    (Path(__file__).parents[1] / "docs/plans/honc-reminder-policy-cases-v1.json").read_text(
        encoding="utf-8"
    )
)


def environment(path, owner="owner", target="private"):
    store = LifeStore(HoncStore(path))
    runtime = ReminderRuntime(store, owner_id=owner, delivery_target_id=target)
    return LifeService(
        store,
        owner_id=owner,
        profile="honc",
        session_id="accepted-case",
        reminders=runtime,
        clock=lambda: at("08:00"),
    ), runtime


def bedtime(service, *, diary=True, care=False):
    ids = []
    if diary:
        ids.append(
            add_habit(
                service,
                "diary",
                record_type="text",
                role="diary",
                importance="high",
                slots=[ReminderSlot(key="bed", trigger="bedtime")],
            )
        )
    if care:
        ids.append(add_habit(service, "care", slots=[ReminderSlot(key="bed", trigger="bedtime")]))
    return ids


def anchor(service, runtime, text, clock):
    bound, ref = source(service, "record_anchor", text, at(clock), "anchor-" + clock)
    return bound.record_anchor(
        AnchorRecordRequest(request_ref=ref, source_quote=text, kind="bedtime")
    )


@pytest.mark.parametrize("case", CONTRACT["cases"], ids=lambda value: value["id"])
def test_accepted_policy_case_in_durable_backend(tmp_path, case):
    service, runtime = environment(tmp_path / "honc.db")
    identifier, given, expected = case["id"], case["given"], case["expect"]
    sink = []
    if identifier == "RP01":
        habit = add_habit(service)
        assert checkin(service, habit, None).ok
        assert tick(runtime, at("08:00"), sink) == []
        assert runtime.list_occurrences(DAY)[0]["target_status"] == "met"
        assert sink == [] and expected["new_messages"] == 0
        assert service.get_history(start_date=DAY, end_date=DAY).data["records"]
    elif identifier == "RP02":
        habit = add_habit(
            service,
            record_type="duration",
            target=float(given["target"]),
            slots=[ReminderSlot(key="window", trigger="time_window", start="15:00", end="16:00")],
        )
        assert checkin(service, habit, None, value=float(given["value"]), outcome="partial").ok
        tick(runtime, at("15:00"), sink)
        assert len(sink) == 1 and runtime.list_occurrences(DAY)[0]["target_status"] == "partial"
    elif identifier == "RP03":
        habit = add_habit(
            service,
            slots=[
                ReminderSlot(key="breakfast", trigger="fixed_time", fixed_time="09:00"),
                ReminderSlot(key="lunch", trigger="fixed_time", fixed_time="12:00"),
            ],
        )
        runtime.compile_day(DAY, at("07:00"))
        breakfast = next(
            value for value in runtime.list_occurrences(DAY) if value["slot_key"] == "breakfast"
        )
        assert checkin(service, habit, breakfast["instance_id"]).ok
        assert tick(runtime, at("09:00"), sink) == []
        tick(runtime, at("12:00"), sink)
        assert len(sink) == 1 and breakfast["instance_id"] not in sink[0]["instance_ids_json"]
    elif identifier == "RP04":
        habit = add_habit(
            service,
            record_type="duration",
            target=20.0,
            count=given["configured_count"],
            slots=[
                ReminderSlot(
                    key="two",
                    trigger="time_window",
                    start="15:00",
                    end="16:00",
                    send_times=given["explicit_send_slots"],
                )
            ],
        )
        tick(runtime, at("15:00"), sink)
        assert checkin(
            service, habit, runtime.list_occurrences(DAY)[0]["instance_id"], value=20.0
        ).ok
        assert tick(runtime, at("15:30"), sink) == [] and len(sink) == 1
        assert runtime.list_occurrences(DAY)[0]["consumed_count"] == 1
        with service.store.ledger.connect() as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM life_reminder_events WHERE event_type='DELIVERED'"
                ).fetchone()[0]
                == 1
            )
    elif identifier in {"RP05", "RP06"}:
        add_habit(
            service,
            slots=[ReminderSlot(key="window", trigger="time_window", start="15:00", end="16:00")],
        )
        from datetime import datetime

        tick(runtime, datetime.fromisoformat(given["now"]), sink)
        assert len(sink) == (1 if identifier == "RP05" else 0)
        value = runtime.list_occurrences(DAY)[0]
        assert value["window_end"] == given["window_end"]
        if identifier == "RP06":
            assert value["delivery_status"] == "EXPIRED"
            assert tick(runtime, at("21:30"), sink) == []
    elif identifier in {"RP07", "RP08", "RP09", "RP10"}:
        from datetime import datetime

        due = datetime.fromisoformat(given["fixed_due_at"])
        add_habit(
            service,
            slots=[
                ReminderSlot(key="point", trigger="fixed_time", fixed_time=due.strftime("%H:%M"))
            ],
        )
        tick(runtime, datetime.fromisoformat(given["now"]), sink)
        assert len(sink) == (1 if expected["action"] == "ELIGIBLE_TO_SEND" else 0)
        value = runtime.list_occurrences(DAY)[0]
        assert value["business_date"] == DAY.isoformat()
        if expected["action"] == "EXPIRE":
            assert value["delivery_status"] == "EXPIRED"
        if identifier == "RP10":
            assert runtime.list_occurrences(DAY + timedelta(days=1))[0]["consumed_count"] == 0
    elif identifier in {"RP11", "RP12", "RP13"}:
        ids = bedtime(service, care=identifier != "RP12")
        if identifier == "RP12":
            add_habit(
                service,
                "afternoon",
                slots=[ReminderSlot(key="afternoon", trigger="fixed_time", fixed_time="15:00")],
            )
        if identifier == "RP13":
            assert checkin(service, ids[1], None).ok
        tick(runtime, at("21:30"), sink)
        assert len(sink) == expected["new_messages"]
        assert sink[0]["content"].count("身体状态") == 1
        assert "afternoon" not in sink[0]["content"]
        if identifier == "RP11":
            assert sink[0]["content"].index("日记") < sink[0]["content"].index("care")
            assert all(value["consumed_count"] == 1 for value in runtime.list_occurrences(DAY))
        if identifier == "RP13":
            care = next(
                value for value in runtime.list_occurrences(DAY) if value["habit_id"] == ids[1]
            )
            assert care["consumed_count"] == 0 and "care" not in sink[0]["content"]
    elif identifier == "RP14":
        other_service, other_runtime = environment(
            tmp_path / "honc.db", owner="other", target="other-private"
        )
        bedtime(service)
        bedtime(other_service)
        tick(runtime, at("21:30"), sink)
        tick(other_runtime, at("21:30"), sink)
        assert len(sink) == expected["isolated_group_operations"]
        assert len({value["owner_id"] for value in sink}) == 2
        assert len({value["group_id"] for value in sink}) == 2
    elif identifier in {"RP15", "RP16", "RP17"}:
        bedtime(service)
        runtime.compile_day(DAY, at("20:00"))
        original = runtime.list_occurrences(DAY)[0]["instance_id"]
        if identifier == "RP17":
            tick(runtime, at("21:30"), sink)
        text = given["text"]
        result = anchor(service, runtime, text, "21:31" if identifier == "RP17" else "20:45")
        if identifier == "RP16":
            assert not result.ok
            assert tick(runtime, at("20:45"), sink) == []
            with service.store.ledger.connect() as connection:
                assert connection.execute("SELECT COUNT(*) FROM life_anchors").fetchone()[0] == 0
        else:
            assert result.ok
            tick(runtime, at("21:31" if identifier == "RP17" else "20:45"), sink)
            assert tick(runtime, at("21:32" if identifier == "RP17" else "21:30"), sink) == []
            assert len(sink) == 1
            assert runtime.list_occurrences(DAY)[0]["instance_id"] == original
    elif identifier in {"RP18", "RP19"}:
        if identifier == "RP18":
            bedtime(service, care=True)
            assert anchor(service, runtime, "准备睡了", "20:45").ok
            clock, later = "20:45", "21:30"
        else:
            habit = add_habit(service)
            clock, later = "08:00", "09:00"
        tick(runtime, at(clock), sink, state="DELIVERY_UNKNOWN")
        if identifier == "RP19":
            assert checkin(service, habit, None).ok
        assert tick(runtime, at(later), sink) == [] and len(sink) == 1
        lookups = []
        runtime.reconcile(at(later), lambda identifier: lookups.append(identifier) or None)
        assert len(lookups) == 1
        assert all(
            value["delivery_status"] == "DELIVERY_UNKNOWN"
            for value in runtime.list_occurrences(DAY)
        )
        with service.store.ledger.connect() as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM life_reminder_groups").fetchone()[0] == 1
            )
    elif identifier == "RP20":
        habit = add_habit(service)
        group = runtime.prepare(at("08:00"))[0]
        assert checkin(service, habit, None).ok
        runtime.reconcile(at("08:06"), lambda _: None)
        result = runtime.dispatch(
            group["group_id"],
            group["fence"],
            at("08:07"),
            lambda value: sink.append(value) or {"state": "DELIVERED"},
        )
        assert result["state"] == "STALE_FENCE" and sink == []
        assert runtime.list_occurrences(DAY)[0]["target_status"] == "met"
    elif identifier == "RP21":
        bedtime(service)
        bound, ref = source(
            service, "save_diary", "昨天的日记：读了一章", at("08:00"), "diary-backfill"
        )
        from datetime import date

        saved = bound.save_diary(
            DiaryRecordRequest(
                request_ref=ref,
                source_quote="昨天的日记：读了一章",
                content="读了一章",
                diary_date=date.fromisoformat(given["backfilled_diary_date"]),
            )
        )
        assert saved.ok and len(saved.records) == 2
        tick(runtime, at("21:30"), sink)
        assert len(sink) == 1 and runtime.list_occurrences(DAY)[0]["target_status"] == "unknown"
    else:
        pytest.fail("Accepted case has no actual backend execution: " + identifier)
