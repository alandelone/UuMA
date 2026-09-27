from __future__ import annotations

import json

import pytest

from uuma.commerce_store import CommerceStore
from uuma.lab_inventory import InventoryError, InventoryStore
from uuma.mcp_worker import inventory_receive


@pytest.fixture
def lab_setup(tmp_path):
    db_path = tmp_path / "test_lab_receipt.db"
    archive_dir = tmp_path / "archive"
    store = CommerceStore(db_path, archive_dir)
    inventory = InventoryStore(db_path)

    # Ingest lines: one self electronics, one others electronics, one self consumable
    batch = {
        "batch_id": "b_receipt_001",
        "task_id": "t_01",
        "platform": "shopee",
        "account_id": "acc_01",
        "orders": [
            {
                "order_id": "ord_receipt_001",
                "items": [
                    {
                        "line_id": "line_self_elec",
                        "product_id": "p_mcu",
                        "product_name": "ESP32 Board",
                        "quantity": 10.0,
                    },
                    {
                        "line_id": "line_others_elec",
                        "product_id": "p_mcu_2",
                        "product_name": "ESP32 Board Others",
                        "quantity": 5.0,
                    },
                    {
                        "line_id": "line_self_tool",
                        "product_id": "p_tool",
                        "product_name": "Screwdriver",
                        "quantity": 1.0,
                    },
                ],
            }
        ],
    }
    store.ingest_batch(batch)

    # Update review statuses in DB
    with store.connect() as conn:
        conn.execute(
            "UPDATE commerce_order_lines SET ownership='self', category='electronics' WHERE line_id='line_self_elec'"
        )
        conn.execute(
            "UPDATE commerce_order_lines SET ownership='others', category='electronics' WHERE line_id='line_others_elec'"
        )
        conn.execute(
            "UPDATE commerce_order_lines SET ownership='self', category='tool' WHERE line_id='line_self_tool'"
        )

    # Register canonical component
    inventory.register_component("CMP-ESP32-S3", "ESP32 Microcontroller")
    return inventory, db_path


def test_preview_receipt_eligibility_and_over_receipt(lab_setup):
    inventory, _ = lab_setup

    # 1. 'others' ownership cannot enter receipt preview
    with pytest.raises(InventoryError, match="only 'self' is eligible"):
        inventory.preview_receipt("line_others_elec", "CMP-ESP32-S3", 5.0)

    # 2. Non-electronics ('tool') cannot enter receipt preview
    with pytest.raises(InventoryError, match="non-electronics cannot be received"):
        inventory.preview_receipt("line_self_tool", "CMP-ESP32-S3", 1.0)

    # 3. Valid self electronics preview
    preview = inventory.preview_receipt("line_self_elec", "CMP-ESP32-S3", 6.0)
    assert preview["line_id"] == "line_self_elec"
    assert preview["quantity"] == 6.0
    assert preview["cumulative_received"] == 0.0
    assert preview["remaining_quantity"] == 4.0
    assert preview["approval_ref"].startswith("appr_")

    # 4. Over-receipt: requesting 11 when total quantity is 10
    with pytest.raises(InventoryError, match="Over-receipt prevented"):
        inventory.preview_receipt("line_self_elec", "CMP-ESP32-S3", 11.0)


def test_governed_receive_idempotency(lab_setup):
    inventory, _ = lab_setup

    preview = inventory.preview_receipt("line_self_elec", "CMP-ESP32-S3", 4.0)
    appr_ref = preview["approval_ref"]

    # First receive execution
    conf_id = "conf_idempotent_001"
    receipt1 = inventory.governed_receive(
        conf_id,
        appr_ref,
        "line_self_elec",
        "CMP-ESP32-S3",
        4.0,
        location_id="UNLOCATED",
    )
    assert receipt1["status"] == "CONFIRMED"
    assert receipt1["confirmation_id"] == conf_id
    event_id = receipt1["event_id"]

    # Duplicate receive with identical confirmation_id and payload
    receipt2 = inventory.governed_receive(
        conf_id,
        appr_ref,
        "line_self_elec",
        "CMP-ESP32-S3",
        4.0,
        location_id="UNLOCATED",
    )
    assert receipt2["status"] == "ALREADY_CONFIRMED"
    assert receipt2["event_id"] == event_id

    # Duplicate receive with conflicting payload raises InventoryError
    with pytest.raises(InventoryError, match="Conflict: confirmation_id"):
        inventory.governed_receive(
            conf_id,
            appr_ref,
            "line_self_elec",
            "CMP-ESP32-S3",
            2.0,  # Different quantity!
            location_id="UNLOCATED",
        )


def test_native_worker_mode_blocks_inventory_receive(monkeypatch):
    monkeypatch.setenv("UUMA_AGENT_ID", "forge-lab-bot")
    monkeypatch.setenv("UUMA_WORKER_MODE", "native")

    # When worker mode is native, inventory_receive must be blocked
    with pytest.raises(PermissionError, match="Tool not permitted in native worker mode"):
        inventory_receive(json.dumps({"component_id": "CMP-TEST", "quantity": 1}))
