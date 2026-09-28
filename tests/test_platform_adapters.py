from __future__ import annotations

from pathlib import Path

from uuma.commerce_adapters import (
    PinduoduoOrderAdapter,
    ShopeeMYAdapter,
    TaobaoOrderAdapter,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "test-fixtures" / "commerce"


def test_shopee_adapter_parses_five_sample_cases():
    html_path = FIXTURES_DIR / "shopee_orders.html"
    assert html_path.exists(), "Shopee orders HTML fixture missing."
    html_content = html_path.read_text(encoding="utf-8")

    orders = ShopeeMYAdapter.parse_orders_html(html_content)
    assert len(orders) == 5, f"Expected 5 Shopee orders, got {len(orders)}."

    # Sample 1: One order with multiple items (一单多行)
    ord1 = next(o for o in orders if o["order_id"] == "260927MY891001")
    assert ord1["status"] == "Completed"
    assert ord1["total_amount"] == 87.0
    assert ord1["currency"] == "MYR"
    assert len(ord1["items"]) == 3
    assert ord1["items"][0]["product_name"] == "STM32F401CCU6 BlackPill Development Board"
    assert ord1["items"][0]["quantity"] == 2.0
    assert ord1["items"][0]["unit_price"] == 16.5
    assert ord1["items"][1]["product_name"] == "ESP32-S3-WROOM-1 DevKit N16R8"
    assert ord1["items"][1]["quantity"] == 1.0
    assert ord1["items"][2]["quantity"] == 4.0

    # Sample 2: SKU differences (规格封装差异)
    ord2 = next(o for o in orders if o["order_id"] == "260927MY891002")
    assert ord2["status"] == "To Ship"
    assert len(ord2["items"]) == 2
    assert "10K Ohm" in ord2["items"][0]["variant_name"]
    assert "100nF" in ord2["items"][1]["variant_name"]

    # Sample 3: Missing fields (缺少规格与店铺字段)
    ord3 = next(o for o in orders if o["order_id"] == "260927MY891003")
    assert len(ord3["items"]) == 1
    assert ord3["items"][0]["variant_name"] == ""
    assert ord3["items"][0]["quantity"] == 3.0

    # Sample 4: Order total != item subtotal (优惠券与运费)
    ord4 = next(o for o in orders if o["order_id"] == "260927MY891004")
    assert ord4["total_amount"] == 44.50
    items_sum = sum(i["line_total"] for i in ord4["items"])
    assert items_sum == 49.00  # 25 + 24
    assert ord4["total_amount"] != items_sum

    # Sample 5: Cancelled / Refund Completed
    ord5 = next(o for o in orders if o["order_id"] == "260927MY891005")
    assert "Refund" in ord5["status"]
    assert ord5["total_amount"] == 0.0


def test_taobao_adapter_parses_phase_1b_cases():
    html_path = FIXTURES_DIR / "taobao_orders.html"
    assert html_path.exists(), "Taobao orders HTML fixture missing."
    html_content = html_path.read_text(encoding="utf-8")

    orders = TaobaoOrderAdapter.parse_orders_html(html_content)
    assert len(orders) == 3, f"Expected 3 Taobao orders, got {len(orders)}."

    # Sample 1
    ord1 = orders[0]
    assert ord1["order_id"] == "2026092700010011"
    assert ord1["currency"] == "CNY"
    assert ord1["status"] == "交易成功"
    assert ord1["total_amount"] == 97.0
    assert len(ord1["items"]) == 1
    assert "STM32G474RET6" in ord1["items"][0]["product_name"]
    assert ord1["items"][0]["quantity"] == 2.0

    # Sample 2: Multi-line order
    ord2 = orders[1]
    assert ord2["order_id"] == "2026092700010012"
    assert len(ord2["items"]) == 2
    assert "W5500" in ord2["items"][0]["product_name"]
    assert "焊锡丝" in ord2["items"][1]["product_name"]

    # Sample 3: Refunded order
    ord3 = orders[2]
    assert ord3["order_id"] == "2026092700010013"
    assert "退款成功" in ord3["status"]


def test_pinduoduo_adapter_parses_five_sample_cases():
    html_path = FIXTURES_DIR / "pdd_orders.html"
    assert html_path.exists(), "Pinduoduo orders HTML fixture missing."
    html_content = html_path.read_text(encoding="utf-8")

    orders = PinduoduoOrderAdapter.parse_orders_html(html_content)
    assert len(orders) == 5, f"Expected 5 Pinduoduo orders, got {len(orders)}."

    # Sample 1: PDD Lab Tool (858D热风枪)
    ord1 = orders[0]
    assert ord1["order_id"] == "2609271002003004001"
    assert ord1["currency"] == "CNY"
    assert ord1["status"] == "拼单成功"
    assert ord1["total_amount"] == 108.0
    assert "858D热风枪" in ord1["items"][0]["product_name"]
    assert ord1["items"][0]["ai_category_suggestion"] == "tool"
    assert ord1["items"][0]["ai_ownership_suggestion"] == "self"
    assert ord1["shop_name"] == "快克工具官方旗舰店"
    assert "mobile.yangkeduo.com/goods.html?goods_id=890001" in ord1["items"][0]["item_url"]

    # Sample 2: Consumables with missing unit price (助焊膏)
    ord2 = orders[1]
    assert ord2["status"] == "已签收"
    assert "助焊膏" in ord2["items"][0]["product_name"]
    assert ord2["items"][0]["quantity"] == 2.0
    assert ord2["items"][0]["unit_price"] == 9.95
    assert ord2["items"][0]["ai_category_suggestion"] == "consumable"

    # Sample 3: Refunded order (T12烙铁头)
    ord3 = orders[2]
    assert "退款成功" in ord3["status"]
    assert ord3["total_amount"] == 0.0

    # Sample 4: Multi-line order (一单多行: ESP32-CAM + FT232RL)
    ord4 = orders[3]
    assert ord4["order_id"] == "2609271002003004004"
    assert ord4["status"] == "拼单成功"
    assert len(ord4["items"]) == 2
    assert "ESP32-CAM" in ord4["items"][0]["product_name"]
    assert ord4["items"][0]["quantity"] == 2.0
    assert ord4["items"][0]["unit_price"] == 18.50
    assert ord4["items"][0]["ai_category_suggestion"] == "electronics"
    assert "FT232RL" in ord4["items"][1]["product_name"]
    assert ord4["items"][1]["quantity"] == 1.0
    assert ord4["items"][1]["unit_price"] == 9.80

    # Sample 5: Order with shipping fee & discount (万用表)
    ord5 = orders[4]
    assert ord5["order_id"] == "2609271002003004005"
    assert ord5["status"] == "待发货"
    assert ord5["shipping_fee"] == 6.0
    assert ord5["total_amount"] == 39.0

