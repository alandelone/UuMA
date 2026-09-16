from __future__ import annotations

from pathlib import Path

import pytest

from uuma.lab_inventory import InventoryStore
from uuma.lab_procurement import ProcurementError, ProcurementStore


@pytest.fixture()
def lab_db(tmp_path: Path) -> Path:
    return tmp_path / "test_lab.db"


def test_requirements_crud(lab_db: Path) -> None:
    store = ProcurementStore(lab_db)

    # 1. Create requirement with component_id
    req1 = store.create_requirement(
        item_name="BTS7960 43A Motor Driver",
        target_quantity=5.0,
        component_id="CMP-BTS7960",
        specs="TO-263 module",
        target_unit_price=15.0,
    )
    assert req1["item_name"] == "BTS7960 43A Motor Driver"
    assert req1["component_id"] == "CMP-BTS7960"
    assert req1["target_quantity"] == 5.0
    assert req1["status"] == "OPEN"

    # 2. Create requirement without component_id (pure hardware/consumable)
    req2 = store.create_requirement(
        item_name="M3 12mm Hex Socket Screw",
        target_quantity=100.0,
        specs="Stainless Steel 304",
    )
    assert req2["component_id"] is None
    assert req2["target_quantity"] == 100.0

    # 3. Validation errors
    with pytest.raises(ProcurementError, match="item_name is required"):
        store.create_requirement("", 1.0)
    with pytest.raises(ProcurementError, match="target_quantity must be positive"):
        store.create_requirement("Item", 0)

    # 4. List and status update
    reqs = store.list_requirements(status="OPEN")
    assert len(reqs) == 2

    updated = store.update_requirement_status(req1["requirement_id"], "SOURCING")
    assert updated["status"] == "SOURCING"

    # 5. Shortage conversion
    shortages = [
        {"component_id": "CMP-RES-10K", "shortage": 50.0, "item_name": "10K Resistor 0805"},
        {"component_id": "CMP-CAP-10UF", "shortage": 20.0, "display_name": "10uF Capacitor 1206"},
    ]
    created_from_shortage = store.create_requirements_from_shortages(shortages)
    assert len(created_from_shortage) == 2
    assert created_from_shortage[0]["component_id"] == "CMP-RES-10K"
    assert created_from_shortage[0]["target_quantity"] == 50.0


def test_term_rules_and_expansion(lab_db: Path) -> None:
    store = ProcurementStore(lab_db)

    # 1. Heuristic expansion for unknown term
    expanded = store.lookup_or_expand_terms("IBT-2")
    assert expanded["source"] == "heuristic_candidate"
    assert "IBT-2" in expanded["aliases"]

    # 2. Save deterministic rule
    saved = store.save_term_rule(
        target_name="IBT-2",
        aliases=["BTS7960", "43A 直流电机驱动", "大功率 H桥模块"],
        package_keywords=["TO-263", "贴片散热片"],
        raw_materials=[
            {
                "name": "BTS7960 裸芯片 2颗 + 打样 PCB + 铜散热片",
                "estimated_diy_cost": 8.50,
                "details": "需要手动焊接 TO-263 贴片与背面涂覆导热硅脂",
            }
        ],
    )
    assert saved["target_name"] == "IBT-2"
    assert len(saved["aliases"]) == 3
    assert len(saved["raw_material_alternatives"]) == 1

    # 3. Lookup rule matches
    rule_hit = store.lookup_or_expand_terms("ibt-2")
    assert rule_hit["source"] == "local_rule"
    assert "BTS7960" in rule_hit["aliases"]
    assert rule_hit["raw_material_alternatives"][0]["estimated_diy_cost"] == 8.50


def test_snippet_parsing_and_offers(lab_db: Path) -> None:
    store = ProcurementStore(lab_db)

    # 1. Parse Taobao snippet
    tb_snippet = """
    【淘宝】https://item.taobao.com/item.htm?id=987654 优信电子旗舰店
    BTS7960 43A电机驱动板 智能车模块
    单价: 16.50 运费: 0.00 满68包邮
    """
    parsed_tb = store.parse_offer_snippet(tb_snippet)
    assert parsed_tb["platform"] == "taobao"
    assert parsed_tb["unit_price"] == 16.50
    assert parsed_tb["shipping_fee"] == 0.0
    assert parsed_tb["free_shipping_threshold"] == 68.0
    assert "优信电子" in parsed_tb["shop_name"]

    # 2. Parse 1688 snippet with MOQ
    p1688_snippet = """
    【1688】https://detail.1688.com/offer/123456.html 深圳市华强原厂直销
    BTS7960 原装芯片 10个起批
    单价: 4.50 运费: 8.00
    """
    parsed_1688 = store.parse_offer_snippet(p1688_snippet)
    assert parsed_1688["platform"] == "1688"
    assert parsed_1688["unit_price"] == 4.50
    assert parsed_1688["moq"] == 10.0
    assert parsed_1688["shipping_fee"] == 8.00

    # 3. Record parsed offer
    recorded = store.record_offers([
        {
            "platform": parsed_tb["platform"],
            "shop_name": parsed_tb["shop_name"],
            "product_title": parsed_tb["product_title"],
            "product_url": parsed_tb["product_url"],
            "unit_price": parsed_tb["unit_price"],
            "shipping_fee": parsed_tb["shipping_fee"],
            "free_shipping_threshold": parsed_tb["free_shipping_threshold"],
        }
    ])
    assert len(recorded) == 1
    assert recorded[0]["unit_price"] == 16.50


def test_multi_strategy_sourcing_evaluation(lab_db: Path) -> None:
    store = ProcurementStore(lab_db)

    # Save term rule for IBT-2
    store.save_term_rule(
        target_name="IBT-2",
        aliases=["BTS7960", "43A 电机驱动"],
        raw_materials=[
            {
                "name": "BTS7960 芯片x2 + 打样 PCB",
                "estimated_diy_cost": 8.00,
                "details": "自焊方案",
            }
        ],
    )

    # Create 2 requirements
    req1 = store.create_requirement(
        item_name="IBT-2",
        target_quantity=2.0,
        component_id="CMP-IBT2",
    )
    req2 = store.create_requirement(
        item_name="0805 10K 电阻",
        target_quantity=100.0,
        component_id="CMP-RES-10K",
    )

    # Setup Offers:
    # Shop A (优信电子): Has both items. Single-shop bundle.
    #   IBT-2: 18.00 CNY, shipping 0 (free over 30). Total goods = 2*18 = 36.
    #   0805 10K 电阻: 5.00 CNY for pack of 100.
    #   Total = 36 + 5 = 41.00 CNY.
    # Shop B (1688 动力科技): Has IBT-2 only at 12.00 CNY, shipping 8.00 CNY. Total = 2*12 + 8 = 32.00 CNY.
    # Shop C (立创商城): Has 0805 10K 电阻 at 2.00 CNY, shipping 6.00 CNY. Total = 2 + 6 = 8.00 CNY.
    # Combined Shop B + Shop C = 32 + 8 = 40.00 CNY (Lowest landed cost).
    store.record_offers([
        # Shop A
        {
            "requirement_id": req1["requirement_id"],
            "platform": "taobao",
            "shop_name": "优信电子",
            "product_title": "IBT-2 43A 驱动板",
            "unit_price": 18.00,
            "shipping_fee": 6.00,
            "free_shipping_threshold": 30.00,
        },
        {
            "requirement_id": req2["requirement_id"],
            "platform": "taobao",
            "shop_name": "优信电子",
            "product_title": "0805 10K 电阻 100只装",
            "unit_price": 5.00,
            "pack_quantity": 100.0,
            "shipping_fee": 6.00,
            "free_shipping_threshold": 30.00,
        },
        # Shop B
        {
            "requirement_id": req1["requirement_id"],
            "platform": "1688",
            "shop_name": "动力科技1688",
            "product_title": "BTS7960 驱动板",
            "unit_price": 12.00,
            "shipping_fee": 8.00,
        },
        # Shop C
        {
            "requirement_id": req2["requirement_id"],
            "platform": "lcsc",
            "shop_name": "立创商城",
            "product_title": "0805 10K 电阻 1% 盘装",
            "unit_price": 2.00,
            "pack_quantity": 100.0,
            "shipping_fee": 6.00,
        },
    ])

    eval_res = store.evaluate_sourcing([req1["requirement_id"], req2["requirement_id"]])
    assert len(eval_res["missing_requirements"]) == 0

    strategies = eval_res["strategies"]

    # Strategy 1: Lowest Landed Cost
    lowest = strategies["lowest_landed_cost"]
    assert lowest["status"] == "FEASIBLE"
    assert lowest["total_landed_cost"] == 40.00  # 24 (IBT-2) + 2 (Resistor) + 8 (ship B) + 6 (ship C) = 40.00
    assert lowest["shop_count"] == 2

    # Strategy 2: Single-Shop Bundle
    single = strategies["minimal_shipments"]
    assert single["status"] == "FEASIBLE"
    assert single["shop_name"] == "优信电子"
    assert single["shop_count"] == 1
    assert single["total_landed_cost"] == 41.00  # 36 + 5 = 41.00, free shipping over 30 reached!
    assert single["total_shipping_fee"] == 0.0

    # Strategy 3: DIY alternative
    diy = strategies["raw_material_diy"]
    assert diy["status"] == "AVAILABLE"
    assert len(diy["alternatives"]) == 1
    assert diy["alternatives"][0]["estimated_diy_cost"] == 8.00


def test_order_confirmation_to_inventory_receive_loop(lab_db: Path) -> None:
    proc_store = ProcurementStore(lab_db)
    inv_store = InventoryStore(lab_db)

    req = proc_store.create_requirement(
        item_name="LM2596S Step-down Module",
        target_quantity=4.0,
        component_id="CMP-LM2596S",
    )

    # Confirm order for this requirement
    order_plan = {
        "order_id": "ORD-2026-001",
        "selected_offers": [
            {
                "requirement_id": req["requirement_id"],
                "component_id": "CMP-LM2596S",
                "ordered_quantity": 4.0,
                "unit_price": 3.50,
                "shop_name": "创客电子专营店",
                "platform": "taobao",
                "product_url": "https://item.taobao.com/item.htm?id=111",
            }
        ],
        "notes": "Testing order confirmation bridge",
    }

    confirmed = proc_store.confirm_order(order_plan)
    assert confirmed["status"] == "ORDER_CONFIRMED"
    assert len(confirmed["created_purchase_lots"]) == 1
    lot = confirmed["created_purchase_lots"][0]
    lot_id = lot["lot_id"]
    assert lot["ordered_quantity"] == 4.0

    # Requirement status updated to ORDERED
    req_updated = proc_store.get_requirement(req["requirement_id"])
    assert req_updated["status"] == "ORDERED"

    # Inventory before receiving: should be 0 available
    balances_before = inv_store.balances()
    assert not any(b["component_id"] == "CMP-LM2596S" and b["bucket"] == "AVAILABLE" for b in balances_before)

    # Package arrives at lab: receive using existing InventoryStore.receive
    receive_event = inv_store.receive(
        component_id="CMP-LM2596S",
        quantity=4.0,
        lot_id=lot_id,
        supplier=lot["supplier"],
        offer_ref=lot["offer_ref"],
    )
    assert receive_event["event_type"] == "RECEIVE"
    assert receive_event["quantity"] == 4.0

    # Inventory after receiving: should now be 4.0 in AVAILABLE bucket!
    balances_after = inv_store.balances()
    lm2596_balance = next(b for b in balances_after if b["component_id"] == "CMP-LM2596S" and b["bucket"] == "AVAILABLE")
    assert lm2596_balance["quantity"] == 4.0
