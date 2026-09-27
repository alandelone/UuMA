from __future__ import annotations

import io
from pathlib import Path

import openpyxl
import pytest

from uuma.commerce_adapters import (
    PinduoduoOrderAdapter,
    ShopeeMYAdapter,
    TaobaoOrderAdapter,
)
from uuma.commerce_control import CommerceControlStore
from uuma.commerce_review import (
    commit_review,
    generate_review_workbook,
    preview_review_workbook,
)
from uuma.commerce_store import CommerceStore
from uuma.lab_inventory import InventoryError, InventoryStore

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "test-fixtures" / "commerce"


@pytest.fixture
def multi_platform_env(tmp_path):
    control_db = tmp_path / "uuma_control.db"
    lab_db = tmp_path / "lab.db"
    archive_dir = tmp_path / "commerce_archive"

    control_store = CommerceControlStore(control_db)
    commerce_store = CommerceStore(lab_db, archive_dir)
    inventory_store = InventoryStore(lab_db)

    # Register canonical components
    inventory_store.register_component("CMP-STM32F401", "STM32F401 MCU Board")
    inventory_store.register_component("CMP-STM32G474", "STM32G474RET6 Microcontroller")

    return control_store, commerce_store, inventory_store, archive_dir


def test_multi_platform_commerce_lifecycle_e2e(multi_platform_env):
    control_store, commerce_store, inventory_store, _archive_dir = multi_platform_env

    # -------------------------------------------------------------------------
    # 1. Tasks in uuma.db for Shopee, Taobao, and PDD
    # -------------------------------------------------------------------------
    shopee_task = control_store.create_task(platform="shopee", account_id="acc_my_01", max_orders=10)
    taobao_task = control_store.create_task(platform="taobao", account_id="acc_cn_01", max_orders=10)
    pdd_task = control_store.create_task(platform="pdd", account_id="acc_pdd_01", max_orders=10)

    assert shopee_task["status"] == "QUEUED"
    assert taobao_task["status"] == "QUEUED"
    assert pdd_task["status"] == "QUEUED"

    # Worker claims Shopee command
    shopee_cmd = control_store.claim_command("worker_browser")
    assert shopee_cmd["task_id"] == shopee_task["task_id"]
    assert shopee_cmd["fencing_token"] == 1

    # -------------------------------------------------------------------------
    # 2. Parse orders from test fixtures
    # -------------------------------------------------------------------------
    shopee_html = (FIXTURES_DIR / "shopee_orders.html").read_text(encoding="utf-8")
    shopee_orders = ShopeeMYAdapter.parse_orders_html(shopee_html)
    assert len(shopee_orders) == 5

    taobao_html = (FIXTURES_DIR / "taobao_orders.html").read_text(encoding="utf-8")
    taobao_orders = TaobaoOrderAdapter.parse_orders_html(taobao_html)
    assert len(taobao_orders) == 3

    pdd_html = (FIXTURES_DIR / "pdd_orders.html").read_text(encoding="utf-8")
    pdd_orders = PinduoduoOrderAdapter.parse_orders_html(pdd_html)
    assert len(pdd_orders) == 3

    # -------------------------------------------------------------------------
    # 3. Ingest batches into lab.db & verify immutable archives
    # -------------------------------------------------------------------------
    batch_shopee = {
        "batch_id": "batch_shopee_live_01",
        "task_id": shopee_task["task_id"],
        "platform": "shopee",
        "account_id": "acc_my_01",
        "orders": shopee_orders,
    }
    rc_shopee = commerce_store.ingest_batch(batch_shopee)
    assert rc_shopee["status"] == "DURABLE_STORED"
    assert Path(rc_shopee["archive_path"]).exists()

    batch_taobao = {
        "batch_id": "batch_taobao_live_01",
        "task_id": taobao_task["task_id"],
        "platform": "taobao",
        "account_id": "acc_cn_01",
        "orders": taobao_orders,
    }
    rc_taobao = commerce_store.ingest_batch(batch_taobao)
    assert rc_taobao["status"] == "DURABLE_STORED"

    batch_pdd = {
        "batch_id": "batch_pdd_live_01",
        "task_id": pdd_task["task_id"],
        "platform": "pdd",
        "account_id": "acc_pdd_01",
        "orders": pdd_orders,
    }
    rc_pdd = commerce_store.ingest_batch(batch_pdd)
    assert rc_pdd["status"] == "DURABLE_STORED"

    # Advance checkpoint in uuma.db
    control_store.report_checkpoint(
        shopee_task["task_id"],
        shopee_cmd["lease_token"],
        shopee_cmd["fencing_token"],
        {"orders_extracted": 5, "batch_id": "batch_shopee_live_01"},
        status="COMPLETED",
    )
    status = control_store.get_task_status(shopee_task["task_id"])
    assert status["status"] == "COMPLETED"

    # -------------------------------------------------------------------------
    # 4. Generate 4-sheet Excel review workbook
    # -------------------------------------------------------------------------
    all_lines = commerce_store.list_order_lines(limit=100)
    assert len(all_lines) >= 14  # 3+2+1+2+1 (shopee) + 1+2+1 (taobao) + 1+1+1 (pdd) = 15 lines

    wb_bytes = generate_review_workbook(all_lines, task_scope="ALL_PLATFORMS")
    wb = openpyxl.load_workbook(io.BytesIO(wb_bytes))
    ws_orders = wb["订单待核对"]

    # Locate specific lines in workbook:
    # 1. Shopee STM32F401 -> set ownership='self', category='electronics'
    # 2. Shopee Tweezers -> set ownership='others', category='tool'
    # 3. Taobao STM32G474 -> set ownership='self', category='electronics'
    # 4. PDD 858D Hot Air Gun -> set ownership='self', category='tool'
    for row_idx in range(2, ws_orders.max_row + 1):
        p_name = str(ws_orders.cell(row=row_idx, column=3).value or "")
        if "STM32F401" in p_name:
            ws_orders.cell(row=row_idx, column=9, value="electronics")  # category
            ws_orders.cell(row=row_idx, column=10, value="self")        # ownership
        elif "Tweezers" in p_name:
            ws_orders.cell(row=row_idx, column=9, value="tool")
            ws_orders.cell(row=row_idx, column=10, value="others")
        elif "STM32G474" in p_name:
            ws_orders.cell(row=row_idx, column=9, value="electronics")
            ws_orders.cell(row=row_idx, column=10, value="self")
        elif "858D热风枪" in p_name:
            ws_orders.cell(row=row_idx, column=9, value="tool")
            ws_orders.cell(row=row_idx, column=10, value="self")

    mod_buf = io.BytesIO()
    wb.save(mod_buf)
    mod_bytes = mod_buf.getvalue()

    # -------------------------------------------------------------------------
    # 5. Preview & Commit Review (Enforcing whole-line self/others)
    # -------------------------------------------------------------------------
    preview = preview_review_workbook(mod_bytes, commerce_store)
    assert preview["total_conflicts"] == 0
    assert preview["total_updates"] >= 4

    commit_res = commit_review(preview, commerce_store)
    assert commit_res["status"] == "COMMITTED"

    # Verify updated database lines
    shopee_stm32 = next(l for l in commerce_store.list_order_lines() if "STM32F401" in l["product_name"])
    assert shopee_stm32["ownership"] == "self"
    assert shopee_stm32["category"] == "electronics"

    shopee_tweezers = next(l for l in commerce_store.list_order_lines() if "Tweezers" in l["product_name"])
    assert shopee_tweezers["ownership"] == "others"

    pdd_gun = next(l for l in commerce_store.list_order_lines() if "858D热风枪" in l["product_name"])
    assert pdd_gun["ownership"] == "self"
    assert pdd_gun["category"] == "tool"

    taobao_stm32 = next(l for l in commerce_store.list_order_lines() if "STM32G474" in l["product_name"])
    assert taobao_stm32["ownership"] == "self"
    assert taobao_stm32["category"] == "electronics"

    # -------------------------------------------------------------------------
    # 6. Governed Receipt Preview & Execution for eligible lines
    # -------------------------------------------------------------------------
    # Eligible: Shopee STM32 (self + electronics)
    preview_stm32 = inventory_store.preview_receipt(
        shopee_stm32["line_id"],
        "CMP-STM32F401",
        quantity=2.0,
        location_id="DRAWER-01",
    )
    assert preview_stm32["approval_ref"].startswith("appr_")
    assert preview_stm32["quantity"] == 2.0

    # Ineligible 1: Shopee Tweezers (others) -> Rejected
    with pytest.raises(InventoryError, match="only 'self' is eligible"):
        inventory_store.preview_receipt(
            shopee_tweezers["line_id"],
            "CMP-TOOL-01",
            quantity=1.0,
        )

    # Ineligible 2: PDD Hot Air Gun (self + tool) -> Non-electronics rejected from lab inventory
    with pytest.raises(InventoryError, match="non-electronics cannot be received"):
        inventory_store.preview_receipt(
            pdd_gun["line_id"],
            "CMP-TOOL-02",
            quantity=1.0,
        )

    # Execute Governed Receipt for Shopee STM32
    receive_res = inventory_store.governed_receive(
        confirmation_id="conf_shopee_stm32_001",
        approval_ref=preview_stm32["approval_ref"],
        line_id=shopee_stm32["line_id"],
        component_id="CMP-STM32F401",
        quantity=2.0,
        location_id="DRAWER-01",
    )
    assert receive_res["status"] == "CONFIRMED"

    # Check inventory balance updated in lab.db
    balances = inventory_store.balances("CMP-STM32F401")
    avail = sum(b["quantity"] for b in balances if b["bucket"] == "AVAILABLE")
    assert avail == 2.0
