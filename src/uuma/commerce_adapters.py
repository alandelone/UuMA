"""Platform-specific commerce order adapters and HTML DOM parsers for Shopee MY, Taobao, and Pinduoduo."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup


class CommerceAdapterError(ValueError):
    pass


def _clean_text(elem: Any) -> str:
    if elem is None:
        return ""
    return re.sub(r"\s+", " ", elem.get_text()).strip()


def _parse_price(text: str) -> float:
    if not text:
        return 0.0
    cleaned = re.sub(r"[^\d.]", "", text)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


class ShopeeMYAdapter:
    """Shopee MY order list and card parser supporting Phase 1A requirements."""

    PLATFORM = "shopee"
    CURRENCY = "MYR"

    @classmethod
    def parse_orders_html(cls, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(
            ".purchase-list-page__order-card, .order-card, div[class*='order-card'], "
            "div[class*='orderCard'], div[class*='purchase-card'], div[class*='order-list-item']"
        )
        if not cards:
            # Fallback to searching containers with order-sn or order-id
            cards = [
                parent for parent in soup.find_all(lambda tag: tag.name in {"div", "section"} and tag.find(class_=re.compile(r"order-(id|sn|card)")))
            ]

        results = []
        for card in cards:
            # 1. Order ID
            order_id = ""
            id_el = card.find(class_=re.compile(r"order-(id|sn|number)"))
            raw_id_txt = _clean_text(id_el) if id_el else ""
            if raw_id_txt:
                cleaned_id = re.sub(r"^(order\s*(sn|id|number)?\s*[:：]?\s*)", "", raw_id_txt, flags=re.IGNORECASE)
                order_id = re.sub(r"[^A-Za-z0-9]", "", cleaned_id)
            if not order_id:
                for tag in card.find_all(["span", "div"]):
                    txt = _clean_text(tag)
                    if "Order SN" in txt or "Order ID" in txt:
                        match = re.search(r"[A-Za-z0-9]{8,}", txt)
                        if match:
                            order_id = match.group(0)
                            break
            if not order_id:
                continue

            # 2. Status
            status = "Completed"
            status_el = card.find(class_=re.compile(r"order-status|status-text|order-state"))
            if status_el:
                status = _clean_text(status_el)

            # Shop name
            shop_el = card.find(class_=re.compile(r"shop-name|seller-name|shop"))
            shop_name = _clean_text(shop_el)

            # Order time & shipping fee
            card_text = card.get_text()
            time_match = re.search(r"\b(\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)\b", card_text)
            order_time = time_match.group(1) if time_match else ""
            ship_match = re.search(r"shipping\s*fee[：:\s]*RM\s*([0-9]+\.?[0-9]*)", card_text, re.IGNORECASE)
            shipping_fee = float(ship_match.group(1)) if ship_match else 0.0

            # 3. Order Total
            total_amount = 0.0
            total_el = card.find(class_=re.compile(r"total-price|order-total|purchase-card__total-price"))
            if total_el:
                total_amount = _parse_price(_clean_text(total_el))

            # 4. Items
            item_nodes = card.select(".order-item, .product-item, div[class*='order-item'], div[class*='product-item']")
            items = []
            for idx, node in enumerate(item_nodes):
                name_el = node.find(class_=re.compile(r"item-name|product-name|title|product-title"))
                var_el = node.find(class_=re.compile(r"variation|model|spec|item-variation"))
                qty_el = node.find(class_=re.compile(r"quantity|item-quantity|qty"))
                price_el = node.find(class_=re.compile(r"item-price|price|item-total"))
                link_el = node.find("a", href=True)

                p_name = _clean_text(name_el) or f"Shopee Item {idx + 1}"
                v_name = _clean_text(var_el)
                qty_str = _clean_text(qty_el)
                qty = _parse_price(qty_str) if qty_str else 1.0
                if qty <= 0:
                    qty = 1.0

                if price_el:
                    unit_price = _parse_price(_clean_text(price_el))
                else:
                    unit_price = round(total_amount / (qty if len(item_nodes) == 1 else len(item_nodes)), 2)

                # Extract product id and url from link if present
                p_id = ""
                item_url = ""
                if link_el and link_el.get("href"):
                    href = link_el["href"]
                    item_url = href if href.startswith("http") else f"https://shopee.com.my{href}"
                    match = re.search(r"/product/(\d+)/(\d+)|/(\d+)/(\d+)|\?item_id=(\d+)", href)
                    if match:
                        p_id = next(g for g in match.groups() if g)

                if not p_id:
                    p_id = f"p_shopee_{abs(hash(p_name)) % 10000000}"

                sku_id = f"sku_{abs(hash(v_name)) % 1000000}" if v_name else ""

                items.append({
                    "product_id": p_id,
                    "sku_id": sku_id,
                    "product_name": p_name,
                    "variant_name": v_name,
                    "quantity": qty,
                    "unit_price": unit_price,
                    "line_total": round(unit_price * qty, 2),
                    "ai_category_suggestion": "electronics" if any(k in p_name.lower() for k in ["mcu", "esp32", "board", "stm32", "sensor", "oled", "chip", "resistor"]) else "consumable",
                    "ai_ownership_suggestion": "self",
                    "shop_name": shop_name,
                    "item_url": item_url,
                    "order_time": order_time,
                    "shipping_fee": shipping_fee,
                    "order_status": status,
                })

            if not items and total_amount > 0:
                items.append({
                    "product_id": f"p_shopee_{order_id}",
                    "sku_id": "",
                    "product_name": "Shopee Order Item",
                    "variant_name": "",
                    "quantity": 1.0,
                    "unit_price": total_amount,
                    "line_total": total_amount,
                    "ai_category_suggestion": "electronics",
                    "ai_ownership_suggestion": "self",
                    "shop_name": shop_name,
                    "item_url": "",
                    "order_time": order_time,
                    "shipping_fee": shipping_fee,
                    "order_status": status,
                })

            results.append({
                "order_id": order_id,
                "status": status,
                "total_amount": total_amount,
                "currency": cls.CURRENCY,
                "shop_name": shop_name,
                "order_time": order_time,
                "shipping_fee": shipping_fee,
                "items": items,
            })

        return results


class TaobaoOrderAdapter:
    """Taobao buyer order parser supporting Phase 1B contract verification."""

    PLATFORM = "taobao"
    CURRENCY = "CNY"

    @classmethod
    def parse_orders_html(cls, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        # Taobao order list table / mod wrappers
        order_wrappers = soup.select(".bought-wrapper-mod, div[class*='bought-wrapper'], tbody[class*='order-body'], .index-mod__order-container___")
        if not order_wrappers:
            order_wrappers = soup.select("table.bought-table, tr[class*='order-item']")

        results = []
        for wrapper in order_wrappers:
            # 1. Order ID
            order_id = ""
            id_el = wrapper.find(class_=re.compile(r"order-info|order-id|order-num|bought-wrapper-mod__order-info"))
            if id_el:
                m = re.search(r"\d{15,}", _clean_text(id_el))
                if m:
                    order_id = m.group(0)
            if not order_id:
                attr_id = wrapper.get("data-id") or wrapper.get("data-orderid")
                if attr_id:
                    order_id = str(attr_id)

            if not order_id:
                continue

            # 2. Status
            status = "交易成功"
            status_el = wrapper.find(class_=re.compile(r"order-status|status|trade-status"))
            if status_el:
                status = _clean_text(status_el)

            # Shop name
            shop_el = wrapper.find(class_=re.compile(r"shop-name|seller-name|seller|shop"))
            shop_name = _clean_text(shop_el)

            # Order time & shipping fee
            wrapper_text = wrapper.get_text()
            time_match = re.search(r"\b(\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)\b", wrapper_text)
            order_time = time_match.group(1) if time_match else ""
            ship_match = re.search(r"(?:含运费|运费)[：:\s]*[¥￥]?\s*([0-9]+\.?[0-9]*)", wrapper_text)
            shipping_fee = float(ship_match.group(1)) if ship_match else 0.0

            # 3. Total amount
            total_amount = 0.0
            total_el = wrapper.find(class_=re.compile(r"real-price|total-price|realprice|amount"))
            if not total_el:
                total_el = wrapper.find(class_=re.compile(r"price"))
            if total_el:
                total_amount = _parse_price(_clean_text(total_el))

            # 4. Items
            item_rows = wrapper.select(".item-mod, tr[class*='item'], div[class*='item-row']")
            items = []
            for idx, item_el in enumerate(item_rows or [wrapper]):
                name_el = item_el.find(class_=re.compile(r"item-title|title|desc|name"))
                spec_el = item_el.find(class_=re.compile(r"item-spec|sku|spec|props"))
                qty_el = item_el.find(class_=re.compile(r"quantity|count|num"))
                price_el = item_el.find(class_=re.compile(r"unit-price|price"))
                link_el = item_el.find("a", href=True)

                p_name = _clean_text(name_el) or f"Taobao Item {idx + 1}"
                v_name = _clean_text(spec_el)
                qty = _parse_price(_clean_text(qty_el)) if qty_el else 1.0
                if qty <= 0:
                    qty = 1.0
                unit_price = _parse_price(_clean_text(price_el)) if price_el else (total_amount / (len(item_rows) or 1))

                p_id = ""
                item_url = ""
                if link_el and link_el.get("href"):
                    href = link_el["href"]
                    item_url = href if href.startswith("http") else f"https:{href}"
                    match = re.search(r"[?&]id=(\d+)", href)
                    if match:
                        p_id = match.group(1)

                if not p_id:
                    p_id = f"p_tb_{abs(hash(p_name)) % 10000000}"
                if not item_url and p_id.isdigit():
                    item_url = f"https://item.taobao.com/item.htm?id={p_id}"

                items.append({
                    "product_id": p_id,
                    "sku_id": f"sku_tb_{abs(hash(v_name)) % 1000000}" if v_name else "",
                    "product_name": p_name,
                    "variant_name": v_name,
                    "quantity": qty,
                    "unit_price": unit_price,
                    "line_total": round(unit_price * qty, 2),
                    "ai_category_suggestion": "electronics" if any(k in p_name.lower() for k in ["元件", "芯片", "电阻", "传感器", "开发板", "mcu", "esp32"]) else "tool",
                    "ai_ownership_suggestion": "self",
                    "shop_name": shop_name,
                    "item_url": item_url,
                    "order_time": order_time,
                    "shipping_fee": shipping_fee,
                    "order_status": status,
                })

            results.append({
                "order_id": order_id,
                "status": status,
                "total_amount": total_amount,
                "currency": cls.CURRENCY,
                "shop_name": shop_name,
                "order_time": order_time,
                "shipping_fee": shipping_fee,
                "items": items,
            })

        return results


class PinduoduoOrderAdapter:
    """Pinduoduo buyer order parser supporting Phase 1B contract verification and multi-line orders."""

    PLATFORM = "pdd"
    CURRENCY = "CNY"

    @classmethod
    def parse_orders_html(cls, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(
            ".order-item-card, .order-card, div[class*='order-item'], div[class*='order_card'], "
            "div[class*='OrderItem'], div[class*='pdd-order'], div[role='listitem']"
        )
        if not cards:
            cards = [
                parent for parent in soup.find_all(
                    lambda tag: tag.name in {"div", "section"} and tag.find(class_=re.compile(r"order-(id|sn|state)"))
                )
            ]

        results = []

        for card in cards:
            # 1. Order ID
            order_id = ""
            id_el = card.find(class_=re.compile(r"order-id|order-sn|order_sn|sn"))
            if id_el:
                m = re.search(r"[0-9\-]{10,}", _clean_text(id_el))
                if m:
                    order_id = m.group(0).replace("-", "")
            if not order_id:
                for tag in card.find_all(["span", "div", "p"]):
                    txt = _clean_text(tag)
                    if "订单编号" in txt or "订单号" in txt:
                        m = re.search(r"[0-9\-]{10,}", txt)
                        if m:
                            order_id = m.group(0).replace("-", "")
                            break
            if not order_id:
                continue

            # 2. Status
            status = ""
            status_el = card.find(class_=re.compile(r"order-status|order-state|status|state"))
            if status_el:
                status = _clean_text(status_el)
            if not status:
                card_raw_text = card.get_text()
                for candidate in ["拼单成功", "已签收", "待发货", "已发货", "运输中", "待收货", "交易成功", "退款成功", "拼单中", "待付款", "交易关闭"]:
                    if candidate in card_raw_text:
                        status = candidate
                        break
            if not status:
                status = "拼单成功"

            # 3. Shop name
            shop_el = card.find(class_=re.compile(r"mall-name|mall_name|shop-name|shop|merchant|seller"))
            shop_name = _clean_text(shop_el)
            if shop_name:
                shop_name = re.sub(r"^(进店\s*[>》]?|商家[：:]\s*|店铺[：:]\s*)", "", shop_name).strip()

            # 4. Order time & shipping fee
            card_text = card.get_text()
            time_match = re.search(r"\b(\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)\b", card_text)
            order_time = time_match.group(1) if time_match else ""

            shipping_fee = 0.0
            ship_match = re.search(r"(?:含运费|运费)[：:\s]*[¥￥]?\s*([0-9]+\.?[0-9]*)", card_text)
            if ship_match:
                shipping_fee = float(ship_match.group(1))

            # 5. Total amount
            total_amount = 0.0
            total_el = card.find(class_=re.compile(r"order-amount|total-price|pay-amount|real-price"))
            if not total_el:
                total_el = card.find(class_=re.compile(r"price"))
            if total_el:
                total_amount = _parse_price(_clean_text(total_el))
            if total_amount <= 0:
                tot_match = re.search(r"(?:实付金额|实付款|实付|合计|订单总额)[：:\s]*[¥￥]?\s*([0-9]+\.?[0-9]*)", card_text)
                if tot_match:
                    total_amount = float(tot_match.group(1))

            # 6. Items (Multi-line support)
            item_nodes = card.select(
                ".goods-info, .goods-item, .order-item, div[class*='goods-info'], div[class*='goods-item'], "
                "div[class*='order-item'], div[class*='product-item']"
            )
            if not item_nodes:
                links_with_goods = card.select("a[href*='goods_id']")
                if links_with_goods:
                    item_nodes = [l.parent for l in links_with_goods]
                else:
                    item_nodes = [card]

            items = []
            seen_items: set[str] = set()

            for idx, item_el in enumerate(item_nodes):
                name_el = item_el.find(class_=re.compile(r"goods-name|goods-title|title|product-name|name"))
                spec_el = item_el.find(class_=re.compile(r"spec|sku|sku-desc|props"))
                qty_el = item_el.find(class_=re.compile(r"goods-number|quantity|count|qty|num"))
                price_el = item_el.find(class_=re.compile(r"goods-price|unit-price|price"))
                link_el = item_el.find("a", href=True) or card.find("a", href=True)

                p_name = _clean_text(name_el) or f"Pinduoduo Item {idx + 1}"
                # Clean promotional markers
                p_name = re.sub(r"^[【\[](?:拼单返现|正品保障|退货包运费)[】\]]\s*", "", p_name).strip()

                raw_spec = _clean_text(spec_el)
                v_name = re.sub(r"^(配置|规格|型号|已选)[：:\s]*", "", raw_spec).strip()

                qty = 1.0
                if qty_el:
                    qty_txt = _clean_text(qty_el)
                    m_qty = re.search(r"(\d+(?:\.\d+)?)\s*件", qty_txt)
                    if m_qty:
                        qty = float(m_qty.group(1))
                    else:
                        parsed_q = _parse_price(qty_txt)
                        if parsed_q > 0:
                            qty = parsed_q

                unit_price = 0.0
                if price_el:
                    unit_price = _parse_price(_clean_text(price_el))

                p_id = ""
                item_url = ""
                if link_el and link_el.get("href"):
                    href = link_el["href"]
                    item_url = href if href.startswith("http") else f"https://mobile.yangkeduo.com{href}"
                    m_pid = re.search(r"goods_id=(\d+)", href)
                    if m_pid:
                        p_id = m_pid.group(1)

                if not p_id:
                    p_id = f"p_pdd_{abs(hash(p_name)) % 10000000}"

                sku_id = f"sku_pdd_{abs(hash(v_name)) % 1000000}" if v_name else ""

                item_key = f"{p_id}_{v_name}"
                if item_key in seen_items:
                    continue
                seen_items.add(item_key)

                # AI Category Suggestion
                p_lower = p_name.lower()
                if any(k in p_lower for k in ["mcu", "esp32", "stm32", "芯片", "元件", "电阻", "电容", "传感器", "开发板", "oled", "模块", "串口", "单片机", "电路"]):
                    ai_cat = "electronics"
                elif any(k in p_lower for k in ["热风枪", "烙铁", "工具", "万用表", "分析仪", "钳", "螺丝刀", "镊子", "拆焊台"]):
                    ai_cat = "tool"
                else:
                    ai_cat = "consumable"

                items.append({
                    "product_id": p_id,
                    "sku_id": sku_id,
                    "product_name": p_name,
                    "variant_name": v_name,
                    "quantity": qty,
                    "unit_price": unit_price,
                    "line_total": round(unit_price * qty, 2),
                    "ai_category_suggestion": ai_cat,
                    "ai_ownership_suggestion": "self",
                    "shop_name": shop_name,
                    "item_url": item_url,
                    "order_time": order_time,
                    "shipping_fee": shipping_fee,
                    "order_status": status,
                })

            # Derive unit price if zero or if card price equals total_amount with qty > 1
            if items:
                tot_qty = sum(it["quantity"] for it in items)
                for it in items:
                    if it["unit_price"] <= 0 and total_amount > 0:
                        if len(items) == 1:
                            it["unit_price"] = round(total_amount / it["quantity"], 2)
                        else:
                            it["unit_price"] = round(total_amount / (tot_qty or len(items)), 2)
                    elif len(items) == 1 and it["quantity"] > 1 and abs(it["unit_price"] - total_amount) < 0.01:
                        # Card showed order total as price
                        it["unit_price"] = round(total_amount / it["quantity"], 2)
                    it["line_total"] = round(it["unit_price"] * it["quantity"], 2)
            else:
                items.append({
                    "product_id": f"p_pdd_{order_id}",
                    "sku_id": "",
                    "product_name": "Pinduoduo Order Item",
                    "variant_name": "",
                    "quantity": 1.0,
                    "unit_price": total_amount,
                    "line_total": total_amount,
                    "ai_category_suggestion": "consumable",
                    "ai_ownership_suggestion": "self",
                    "shop_name": shop_name,
                    "item_url": "",
                    "order_time": order_time,
                    "shipping_fee": shipping_fee,
                    "order_status": status,
                })

            results.append({
                "order_id": order_id,
                "status": status,
                "total_amount": total_amount,
                "currency": cls.CURRENCY,
                "shop_name": shop_name,
                "order_time": order_time,
                "shipping_fee": shipping_fee,
                "items": items,
            })

        return results
