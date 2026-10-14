"""Non-destructive inheritance of legacy habit configuration and raw local history."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .life_models import HabitConfigureRequest, HabitDefinitionInput, ReminderRule, ReminderSlot
from .life_service import LifeService
from .life_store import canonical

LEGACY_TYPES = {
    "晨仪:💊": "checkbox",
    "睡前15": "rich_text",
    "eat_bh": "checkbox",
    "锻体tod": "number",
    "OffJobBh": "multi_select",
    "FullRest": None,
    "泡脚": "checkbox",
    "Dairy": "rich_text",
}
ALIASES = {
    "晨仪:💊": ["晨仪", "服药", "营养素"],
    "睡前15": ["睡前保养", "保养"],
    "eat_bh": ["吃饭习惯", "早餐", "午餐", "晚餐"],
    "锻体tod": ["锻炼", "运动", "训练"],
    "OffJobBh": ["微习惯", "断水", "PC练习", "腹式呼吸"],
    "FullRest": ["深度休息"],
    "泡脚": ["足浴"],
    "Dairy": ["日记", "diary", "journal"],
}


def migration_plan(cache: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in cache["entries"]:
        grouped.setdefault(entry["name_in_db"], []).append(entry)
    plan = []
    for name, entries in grouped.items():
        if name not in LEGACY_TYPES:
            raise ValueError("Unmapped original habit: " + name)
        legacy_type = LEGACY_TYPES[name]
        record_type = {
            "checkbox": "boolean",
            "rich_text": "text",
            "number": "number",
            "multi_select": "selection",
            None: "text",
        }[legacy_type]
        definition = HabitDefinitionInput(
            name=name,
            record_type=record_type,
            semantic_role="diary" if name == "Dairy" else "habit",
            legacy_property_type=legacy_type,
            description="\n".join(dict.fromkeys(entry["description"] for entry in entries)),
            aliases=ALIASES[name],
        )
        slots = []
        if name == "晨仪:💊":
            slots = [ReminderSlot(key="wake", trigger="wake")]
        elif name in {"Dairy", "睡前15", "泡脚"}:
            slots = [ReminderSlot(key="bedtime", trigger="bedtime")]
        elif name != "OffJobBh":
            hours = []
            for entry in entries:
                hours.append(entry["start_hour"])
                if isinstance(entry.get("end_hour"), list):
                    hours.extend(entry["end_hour"])
            slots = [
                ReminderSlot(
                    key=f"at_{hour:02d}", trigger="fixed_time", fixed_time=f"{hour:02d}:00"
                )
                for hour in sorted(set(hours))
            ]
        reminder = ReminderRule(count=1, slots=slots) if slots else None
        plan.append(
            {
                "legacy_name": name,
                "definition": definition.model_dump(mode="json"),
                "reminder": reminder.model_dump(mode="json") if reminder else None,
                "original_entries": entries,
                "mapping_notes": "原始数字单位未知；逐条保存显式报告单位，不把旧数字猜成次数或分钟。"
                if name == "锻体tod"
                else (
                    "保留原属性类型不确定的信息；新记录保存原文，不改写旧值。"
                    if legacy_type is None
                    else (
                        "保留内容但不恢复 Toilet/Rest 触发。"
                        if name == "OffJobBh"
                        else (
                            "睡前统一 21:30 或明确更早睡觉；不恢复次晨追问昨晚是否完成。"
                            if name in {"Dairy", "睡前15", "泡脚"}
                            else "保留原内容和独立时段。"
                        )
                    )
                ),
            }
        )
    return plan


def apply_migration(
    service: LifeService,
    cache_path: Path,
    history_directory: Path,
    user_authorization: str = "settle until fully setup honc as i expected",
) -> dict[str, Any]:
    raw_cache = cache_path.read_bytes()
    cache = json.loads(raw_cache)
    plan = migration_plan(cache)
    now = datetime.now(UTC)
    mapping = []
    for item in plan:
        text = canonical(
            {
                "user_authorization": user_authorization,
                "legacy_name": item["legacy_name"],
                "original_entries": item["original_entries"],
                "origin": "CONFIGURATION_IMPORT",
            }
        )
        event_id = "legacy-habit:" + hashlib.sha256(item["legacy_name"].encode()).hexdigest()
        with service.store.ledger.connect() as connection:
            prior = connection.execute(
                "SELECT received_at FROM life_sources WHERE owner_id=? AND adapter_id=? AND source_event_id=?",
                (service.owner_id, "authorized-local-habit-migration", event_id),
            ).fetchone()
        receipt = service.receive_user_message(
            adapter_id="authorized-local-habit-migration",
            source_event_id=event_id,
            raw_content=text,
            received_at=datetime.fromisoformat(prior[0]) if prior else now,
            granted_operations=("configure_habit",),
            source_origin="configuration_import",
        )
        result = service.bind_source(receipt["source_ref"]).configure_habit(
            HabitConfigureRequest(
                request_ref=receipt["request_refs"]["configure_habit"],
                source_quote=user_authorization,
                action="create",
                definition=HabitDefinitionInput.model_validate(item["definition"]),
                reminder=ReminderRule.model_validate(item["reminder"])
                if item["reminder"]
                else None,
            )
        )
        if not result.ok:
            raise ValueError("Migration conflict for " + item["legacy_name"] + ": " + result.status)
        mapping.append(
            {**item, "habit_id": result.records[0].id, "operation_id": result.operation_id}
        )
    with service.store.transaction() as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS life_legacy_events (
            record_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, source_path TEXT NOT NULL,
            source_digest TEXT NOT NULL, line_number INTEGER NOT NULL,
            raw_line TEXT NOT NULL, payload_json TEXT NOT NULL, recorded_at TEXT NOT NULL,
            UNIQUE(owner_id,source_path,source_digest,line_number))""")
        for action in ("UPDATE", "DELETE"):
            connection.execute(
                f"CREATE TRIGGER IF NOT EXISTS life_legacy_events_no_{action.lower()} "
                f"BEFORE {action} ON life_legacy_events BEGIN SELECT RAISE(ABORT,'legacy history is immutable'); END"
            )
        for path in sorted(history_directory.glob("*.jsonl")):
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            try:
                original_date = date.fromisoformat(path.stem).isoformat()
            except ValueError:
                original_date = None
            for number, line in enumerate(raw.decode("utf-8-sig").splitlines(), start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                payload = {
                    "original": value,
                    "time": {
                        "precision": "date" if original_date else "unknown",
                        "occurred_date": original_date,
                    },
                    "import_note": "原始旧账本；不推断单位、完成状态或精确时区。",
                }
                connection.execute(
                    "INSERT OR IGNORE INTO life_legacy_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "legacy_"
                        + hashlib.sha256(
                            canonical((service.owner_id, str(path), digest, number)).encode()
                        ).hexdigest(),
                        service.owner_id,
                        str(path),
                        digest,
                        number,
                        line,
                        canonical(payload),
                        now.isoformat(),
                    ),
                )
    # Neither the original bytes nor the original IDs/times are edited.
    assert cache_path.read_bytes() == raw_cache
    return {
        "original_cache_sha256": hashlib.sha256(raw_cache).hexdigest(),
        "mapping": mapping,
        "original_files_unchanged": True,
        "notion_sync_enabled": False,
    }
