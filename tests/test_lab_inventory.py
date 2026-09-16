from __future__ import annotations

import pytest

from uuma.lab_inventory import InventoryError, InventoryStore


@pytest.fixture()
def inventory(tmp_path):
    return InventoryStore(tmp_path / "lab.db")


def test_inventory_event_lifecycle_and_negative_balance_guard(inventory):
    inventory.create_location("Drawer 1", location_id="DRAWER-1")
    inventory.receive(
        "cmp-motor",
        5,
        lot_id="LOT-1",
        location_id="DRAWER-1",
        display_name="Motor driver",
    )
    inventory.transition(
        "RESERVE",
        "cmp-motor",
        2,
        lot_id="LOT-1",
        location_id="DRAWER-1",
        reason="reserve for build",
    )

    balances = inventory.balances("cmp-motor")
    by_bucket = {row["bucket"]: row["quantity"] for row in balances}
    assert by_bucket == {"AVAILABLE": 3.0, "RESERVED": 2.0}

    with pytest.raises(InventoryError, match="Insufficient AVAILABLE"):
        inventory.transition(
            "RESERVE",
            "cmp-motor",
            4,
            lot_id="LOT-1",
            location_id="DRAWER-1",
            reason="cannot over-reserve",
        )


def test_bom_shortage_and_as_built_are_linked_by_component_id(inventory):
    inventory.receive("cmp-a", 4, lot_id="LOT-A", display_name="A")
    inventory.receive("cmp-b", 1, lot_id="LOT-B", display_name="B")

    shortage = inventory.check_bom_shortage(
        [
            {"component_id": "cmp-a", "quantity": 3},
            {"component_id": "cmp-b", "quantity": 2},
        ]
    )
    assert shortage["status"] == "SHORTAGE"
    assert shortage["procurement_requirements"] == [
        {
            "component_id": "cmp-b",
            "required": 2.0,
            "available": 1.0,
            "shortage": 1.0,
            "status": "SHORTAGE",
        }
    ]

    build = inventory.create_build("REV-A", "hash-a")
    inventory.transition(
        "RESERVE", "cmp-a", 1, lot_id="LOT-A", reason="build allocation"
    )
    inventory.transition(
        "INSTALL",
        "cmp-a",
        1,
        lot_id="LOT-A",
        build_id=build["build_id"],
        reason="installed in build",
    )
    as_built = inventory.current_as_built(build["build_id"])
    assert as_built["design_revision_id"] == "REV-A"
    assert as_built["installed_items"] == [
        {"component_id": "cmp-a", "lot_id": "LOT-A", "quantity": 1.0}
    ]


def test_adjustment_is_an_event_not_a_balance_overwrite(inventory):
    inventory.register_component("cmp-a", "A")
    inventory.adjust("cmp-a", "AVAILABLE", 3, reason="verified physical count")
    inventory.adjust("cmp-a", "AVAILABLE", -1, reason="reconciliation recount")

    assert inventory.balances("cmp-a")[0]["quantity"] == 2.0
    with inventory.connect() as connection:
        events = connection.execute(
            "SELECT event_type, reason FROM inventory_events ORDER BY occurred_at"
        ).fetchall()
    assert [tuple(row) for row in events] == [
        ("ADJUST", "verified physical count"),
        ("ADJUST", "reconciliation recount"),
    ]


def test_legacy_excel_rows_preview_then_idempotent_import(inventory):
    rows = [
        {
            "source_key": "inventory.xlsx:Sheet1:2",
            "component_id": "cmp-a",
            "display_name": "Part A",
            "quantity": 7,
            "lot_id": "LEGACY",
            "location_id": "UNLOCATED",
            "evidence_ref": "inventory.xlsx#Sheet1!A2:F2",
        }
    ]
    preview = inventory.import_legacy_rows(rows)
    assert preview["status"] == "preview"
    assert inventory.balances() == []

    first = inventory.import_legacy_rows(rows, commit=True)
    second = inventory.import_legacy_rows(rows, commit=True)
    assert first["committed"] == 1
    assert second["committed"] == 0
    assert second["skipped"] == 1
    assert inventory.balances("cmp-a")[0]["quantity"] == 7.0


def test_build_status_and_listing(inventory):
    build1 = inventory.create_build("REV-1", "hash-1")
    inventory.create_build("REV-2", "hash-2")

    assert build1["status"] == "OPEN"
    updated = inventory.update_build_status(build1["build_id"], "IN_PROGRESS")
    assert updated["status"] == "IN_PROGRESS"

    all_builds = inventory.list_builds()
    assert len(all_builds) == 2

    in_progress = inventory.list_builds(status="IN_PROGRESS")
    assert len(in_progress) == 1
    assert in_progress[0]["build_id"] == build1["build_id"]

    with pytest.raises(InventoryError, match="Unknown build status"):
        inventory.update_build_status(build1["build_id"], "INVALID_STATUS")


def test_commissioning_lifecycle(inventory):
    build = inventory.create_build("REV-1", "hash-1")
    rec = inventory.record_commissioning(
        build["build_id"],
        "Power-On & Voltage Check",
        "PASS",
        metrics={"v_in": 12.02, "v_3v3": 3.301, "temp_c": 28.5},
        notes="No ripple observed",
        evidence_ref="notion://lab/logs/comm-001",
    )

    assert rec["status"] == "PASS"
    assert rec["test_name"] == "Power-On & Voltage Check"

    records = inventory.list_commissioning(build_id=build["build_id"])
    assert len(records) == 1
    assert records[0]["metrics"]["v_in"] == 12.02
    assert records[0]["notes"] == "No ripple observed"

    with pytest.raises(InventoryError, match="Unknown commissioning status"):
        inventory.record_commissioning(build["build_id"], "Bad Test", "MAYBE")


def test_worklog_epistemic_separation(inventory):
    build = inventory.create_build("REV-1", "hash-1")
    log = inventory.record_worklog(
        "UGV Motor Test",
        "Tested 24V PWM driver under 5A load",
        "Driver MOSFET surface reached 85C within 30 seconds",
        build_id=build["build_id"],
        hypothesis="Gate drive voltage insufficient or trace resistance too high",
        confirmed_cause="Gate pull-down resistor was 1k instead of 10k, causing slow turn-off",
        result="Replaced resistor; temperature stabilized at 42C under 5A",
        parts=["cmp-mosfet-01", "cmp-res-10k"],
        next_action="Update BOM note and add thermal pad",
    )

    assert log["project_name"] == "UGV Motor Test"
    logs = inventory.list_worklogs(project_name="UGV Motor Test")
    assert len(logs) == 1
    assert logs[0]["action"] == "Tested 24V PWM driver under 5A load"
    assert logs[0]["observation"] == "Driver MOSFET surface reached 85C within 30 seconds"
    assert "Gate pull-down resistor" in logs[0]["confirmed_cause"]
    assert logs[0]["parts"] == ["cmp-mosfet-01", "cmp-res-10k"]


def test_failure_analysis_and_severity(inventory):
    build = inventory.create_build("REV-1", "hash-1")
    inventory.register_component("cmp-drv", "Motor Driver IC")

    fail = inventory.record_failure(
        "Smoke emitted from driver IC on power switch toggle",
        severity="CRITICAL",
        build_id=build["build_id"],
        component_id="cmp-drv",
        suspected_cause="Reverse polarity from unregulated supply",
        confirmed_cause="DC jack barrel polarity inverted in custom harness",
        action_taken="Re-pinned harness and added series Schottky diode",
        evidence_ref="photo://bench/smoke_event_01.jpg",
    )

    assert fail["severity"] == "CRITICAL"
    fails = inventory.list_failures(severity="CRITICAL")
    assert len(fails) == 1
    assert fails[0]["component_id"] == "cmp-drv"
    assert fails[0]["action_taken"] == "Re-pinned harness and added series Schottky diode"

    with pytest.raises(InventoryError, match="Unknown failure severity"):
        inventory.record_failure("Symptom", severity="DISASTROUS")


def test_engineering_lesson_lifecycle_and_promotion(inventory):
    lesson = inventory.propose_lesson(
        "Always place a flyback diode directly across inductive DC motor terminals",
        scope="Motor driver circuits above 12V",
        target_system="ESCHEMATIC",
        severity="BLOCK",
        confidence=0.95,
        status="CANDIDATE",
        evidence_refs=["worklog://ugv/log-001", "failure://fail-002"],
        exceptions="Does not apply to integrated brushless drivers with internal active freewheeling",
    )

    assert lesson["status"] == "CANDIDATE"
    assert lesson["target_system"] == "ESCHEMATIC"

    candidates = inventory.list_lessons(status="CANDIDATE")
    assert len(candidates) == 1

    # Promote to ACCEPTED
    updated = inventory.update_lesson_status(lesson["lesson_id"], "ACCEPTED")
    assert updated["status"] == "ACCEPTED"

    accepted = inventory.list_lessons(status="ACCEPTED")
    assert len(accepted) == 1
    assert accepted[0]["statement"].startswith("Always place a flyback diode")

    with pytest.raises(InventoryError, match="Unknown lesson status"):
        inventory.update_lesson_status(lesson["lesson_id"], "INVALID")


def test_design_feedback_proposals(inventory):
    inventory.register_component("cmp-cap-10u", "10uF 0805 Ceramic Cap")
    proposal = inventory.propose_design_feedback(
        "REV-A",
        "Add 10uF ceramic capacitor close to VCC pin of buck converter",
        "Observed 400mV switching noise without local bypass",
        target_component_id="cmp-cap-10u",
        evidence_refs=["scope://bench/ripple_trace_01.png"],
    )

    assert proposal["status"] == "PROPOSED"
    proposals = inventory.list_design_feedback(design_revision_id="REV-A")
    assert len(proposals) == 1
    assert proposals[0]["change_summary"] == "Add 10uF ceramic capacitor close to VCC pin of buck converter"

    reviewed = inventory.update_design_feedback_status(
        proposal["proposal_id"], "ACCEPTED", reviewer="Lead Hardware Engineer"
    )
    assert reviewed["status"] == "ACCEPTED"
