import json
from datetime import UTC, date, datetime, timedelta

import pytest

from uuma.honc.life_context import LifeContextBroker, allowed_operations
from uuma.honc.life_migration import apply_migration, migration_plan
from uuma.honc.life_models import BodyObservation, BodyRecordRequest, RecordCorrectionRequest
from uuma.honc.life_service import LifeService
from uuma.honc.life_store import LifeStore
from uuma.honc.store import HoncStore

NOW = datetime(2026, 10, 13, 12, tzinfo=UTC)


def config(tmp_path, owner="owner"):
    return {
        "profile": "honc",
        "owner_id": owner,
        "database_path": str(tmp_path / "honc.db"),
        "profile_home": str(tmp_path / "profiles/honc"),
        "repository_root": str(tmp_path),
        "delivery_binding": {"platform": "telegram", "chat_id": owner},
        "scheduler_job_id": "fixture-job",
    }


@pytest.mark.parametrize(
    "text",
    [
        "如果我很累",
        "明天运动",
        "别人说我流鼻涕",
        '"我运动了"',
        "状态好吗？",
        "看看历史",
        "不要记录今天状态好",
    ],
)
def test_non_report_inputs_do_not_authorize_personal_facts(text):
    assert not {"record_habit", "record_body", "save_diary"} & set(allowed_operations(text))


@pytest.mark.parametrize(
    "text,expected",
    [
        ("流鼻涕，也有点累", "record_body"),
        ("状态很好", "record_body"),
        ("刚起床了", "record_anchor"),
        ("准备睡了", "record_anchor"),
        ("暂停泡脚习惯", "configure_habit"),
        ("今天日记：状态很好", "save_diary"),
        ("昨天运动二十分钟", "record_habit"),
    ],
)
def test_real_report_or_explicit_configuration_grants_correct_domain(text, expected):
    assert expected in allowed_operations(text)


def test_context_token_is_host_minted_owner_scoped_revoked_and_not_stored_as_plaintext(tmp_path):
    broker = LifeContextBroker(config(tmp_path), clock=lambda: NOW)
    token, receipt = broker.open_message(
        raw_content="状态很好",
        transport_id="actual-msg-1",
        session_id="session",
        turn_id="turn",
        received_at=NOW,
        actor_id="owner",
    )
    service = broker.service(token)
    assert service.owner_id == "owner" and service.source_ref == receipt["source_ref"]
    with broker.store.ledger.connect() as connection:
        assert token not in str(
            connection.execute("SELECT * FROM life_context_bindings").fetchall()
        )
    for invalid in (None, "model-invented"):
        with pytest.raises(PermissionError):
            broker.service(invalid)
    other = LifeContextBroker(config(tmp_path, "other"), clock=lambda: NOW)
    with pytest.raises(PermissionError):
        other.service(token)
    broker.close_turn("session", "turn")
    with pytest.raises(PermissionError):
        broker.service(token)


def test_new_turn_revokes_old_context_and_expiry_remains_closed(tmp_path):
    clock = [NOW]
    broker = LifeContextBroker(config(tmp_path), clock=lambda: clock[0])
    old, _ = broker.open_message(
        raw_content="状态很好",
        transport_id="msg-1",
        session_id="session",
        turn_id="turn-1",
        received_at=NOW,
        actor_id="owner",
    )
    new, _ = broker.open_message(
        raw_content="有点累",
        transport_id="msg-2",
        session_id="session",
        turn_id="turn-2",
        received_at=NOW,
        actor_id="owner",
    )
    with pytest.raises(PermissionError):
        broker.service(old)
    clock[0] += timedelta(hours=3)
    with pytest.raises(PermissionError):
        broker.service(new)


def test_read_only_turn_returns_no_write_refs_and_configuration_import_cannot_mint_body_grant(
    tmp_path,
):
    broker = LifeContextBroker(config(tmp_path), clock=lambda: NOW)
    token, receipt = broker.open_message(
        raw_content="看看历史",
        transport_id="msg",
        session_id="session",
        turn_id="turn",
        received_at=NOW,
        actor_id="owner",
    )
    assert receipt["request_refs"] == {}
    assert broker.service(token).get_context().status == "READ_OK"
    with pytest.raises(ValueError, match="personal"):
        broker.service(token).receive_user_message(
            adapter_id="configuration",
            source_event_id="import",
            raw_content="原配置",
            received_at=NOW,
            source_origin="configuration_import",
            granted_operations=("record_body",),
        )


def body(service, index):
    receipt = service.receive_user_message(
        adapter_id="fixture",
        source_event_id=str(index),
        raw_content="状态好",
        received_at=NOW,
        granted_operations=("record_body",),
    )
    return service.bind_source(receipt["source_ref"]).record_body(
        BodyRecordRequest(
            request_ref=receipt["request_refs"]["record_body"],
            source_quote="状态好",
            observations=[BodyObservation(description="状态好")],
        )
    )


def test_history_cursor_freezes_versions_even_with_identical_clock_and_rejects_other_owner(
    tmp_path,
):
    store = LifeStore(HoncStore(tmp_path / "honc.db"))
    service = LifeService(
        store, owner_id="owner", profile="honc", session_id="session", clock=lambda: NOW
    )
    original = [body(service, index).records[0].id for index in range(3)]
    first = service.get_history(start_date=NOW.date(), end_date=NOW.date(), limit=1)
    cursor = first.data["next_cursor"]
    assert cursor
    body(service, 4)
    target = next(value for value in original if value != first.data["records"][0]["object_id"])
    receipt = service.receive_user_message(
        adapter_id="fixture",
        source_event_id="correct",
        raw_content="撤销记录",
        received_at=NOW,
        granted_operations=("correct_record",),
    )
    voided = service.bind_source(receipt["source_ref"]).correct_record(
        RecordCorrectionRequest(
            request_ref=receipt["request_refs"]["correct_record"],
            source_quote="撤销记录",
            record_id=target,
            expected_revision=1,
            reason="重复",
            void=True,
        )
    )
    assert voided.status == "APPLIED"
    second = service.get_history(
        start_date=NOW.date(), end_date=NOW.date(), limit=100, cursor=cursor
    )
    ids = {value["object_id"] for value in first.data["records"] + second.data["records"]}
    assert ids == set(original) and all(value["revision"] == 1 for value in second.data["records"])
    other = LifeService(
        store, owner_id="other", profile="honc", session_id="session", clock=lambda: NOW
    )
    assert (
        other.get_history(start_date=NOW.date(), end_date=NOW.date(), cursor=cursor).status
        == "NEEDS_INPUT"
    )
    assert (
        service.get_history(start_date=NOW.date(), end_date=NOW.date(), cursor=cursor + "x").status
        == "NEEDS_INPUT"
    )
    assert (
        service.get_history(start_date=NOW.date(), end_date=NOW.date(), kinds=("habit",)).data[
            "records"
        ]
        == []
    )


def test_migration_preserves_raw_source_and_ids_and_never_seeds_observations(tmp_path):
    cache = {
        "entries": [
            {
                "name_in_db": "晨仪:💊",
                "start_hour": 8,
                "end_hour": None,
                "description": "原晨仪",
                "cron_type": "trace",
            },
            {
                "name_in_db": "Dairy",
                "start_hour": 21,
                "end_hour": None,
                "description": "Record Daily",
                "cron_type": "trace",
            },
            {
                "name_in_db": "OffJobBh",
                "start_hour": 9,
                "end_hour": 18,
                "description": "原微习惯",
                "cron_type": "Trighear",
            },
            {
                "name_in_db": "锻体tod",
                "start_hour": 9,
                "end_hour": [12, 15, 18],
                "description": "原训练",
                "cron_type": "traceXlt",
            },
        ]
    }
    cache_path = tmp_path / "cron_cache.json"
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    directory = tmp_path / "old-daily"
    directory.mkdir()
    raw = '{"original_id":"keep-me","activity":"旧活动","started_at":"2026-05-01T09:00:00","habits_done":["原微习惯"]}\n'
    original_path = directory / "2026-05-01.jsonl"
    original_path.write_text(raw, encoding="utf-8")
    before = original_path.read_bytes(), cache_path.read_bytes()
    store = LifeStore(HoncStore(tmp_path / "honc.db"))
    service = LifeService(
        store, owner_id="owner", profile="honc", session_id="setup", clock=lambda: NOW
    )
    first = apply_migration(service, cache_path, directory)
    second = apply_migration(service, cache_path, directory)
    assert [value["habit_id"] for value in first["mapping"]] == [
        value["habit_id"] for value in second["mapping"]
    ]
    assert before == (original_path.read_bytes(), cache_path.read_bytes())
    plan = migration_plan(cache)
    assert next(value for value in plan if value["legacy_name"] == "OffJobBh")["reminder"] is None
    number = next(value for value in plan if value["legacy_name"] == "锻体tod")
    assert number["definition"]["record_type"] == "number" and number["definition"]["unit"] is None
    assert (
        next(value for value in plan if value["legacy_name"] == "Dairy")["reminder"]["slots"][0][
            "trigger"
        ]
        == "bedtime"
    )
    with store.ledger.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM life_objects WHERE kind IN ('habit','body','diary')"
            ).fetchone()[0]
            == 0
        )
        assert {
            row[0] for row in connection.execute("SELECT DISTINCT source_origin FROM life_sources")
        } == {"configuration_import"}
    old = service.get_history(start_date=date(2026, 5, 1), end_date=date(2026, 5, 1)).data[
        "records"
    ]
    assert len(old) == 1 and old[0]["payload"]["original"]["original_id"] == "keep-me"
    assert old[0]["payload"]["original"]["started_at"] == "2026-05-01T09:00:00"
