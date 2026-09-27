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
        cards = soup.select(".purchase-list-page__order-card, .order-card, div[class*='order-card']")
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

                unit_price = _parse_price(_clean_text(price_el)) if price_el else (total_amount / (len(item_nodes) or 1))

                # Extract product id from link if present
                p_id = ""
                if link_el and link_el.get("href"):
                    match = re.search(r"/product/(\d+)/(\d+)|/(\d+)/(\d+)|\?item_id=(\d+)", link_el["href"])
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
                })

            results.append({
                "order_id": order_id,
                "status": status,
                "total_amount": total_amount,
                "currency": cls.CURRENCY,
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

                p_name = _clean_text(name_el) or f"Taobao Item {idx + 1}"
                v_name = _clean_text(spec_el)
                qty = _parse_price(_clean_text(qty_el)) if qty_el else 1.0
                if qty <= 0:
                    qty = 1.0
                unit_price = _parse_price(_clean_text(price_el)) if price_el else (total_amount / (len(item_rows) or 1))

                items.append({
                    "product_id": f"p_tb_{abs(hash(p_name)) % 10000000}",
                    "sku_id": f"sku_tb_{abs(hash(v_name)) % 1000000}" if v_name else "",
                    "product_name": p_name,
                    "variant_name": v_name,
                    "quantity": qty,
                    "unit_price": unit_price,
                    "line_total": round(unit_price * qty, 2),
                    "ai_category_suggestion": "electronics" if any(k in p_name.lower() for k in ["元件", "芯片", "电阻", "传感器", "开发板", "mcu", "esp32"]) else "tool",
                    "ai_ownership_suggestion": "self",
                })

            results.append({
                "order_id": order_id,
                "status": status,
                "total_amount": total_amount,
                "currency": cls.CURRENCY,
                "items": items,
            })

        return results


class PinduoduoOrderAdapter:
    """Pinduoduo buyer order parser supporting Phase 1B contract verification."""

    PLATFORM = "pdd"
    CURRENCY = "CNY"

    @classmethod
    def parse_orders_html(cls, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(".order-item-card, .order-card, div[class*='order-item'], div[class*='order_card']")
        results = []

        for card in cards:
            # 1. Order ID
            order_id = ""
            id_el = card.find(class_=re.compile(r"order-id|order-sn|sn"))
            if id_el:
                m = re.search(r"[0-9\-]{10,}", _clean_text(id_el))
                if m:
                    order_id = m.group(0).replace("-", "")
            if not order_id:
                for tag in card.find_all(["span", "div", "p"]):
                    txt = _clean_text(tag)
                    if "订单编号" in txt or "订单号" in txt:
                        m = re.search(r"\d{12,}", txt)
                        if m:
                            order_id = m.group(0)
                            break
            if not order_id:
                continue

            # 2. Status
            status = "拼单成功"
            status_el = card.find(class_=re.compile(r"status|order-state|state"))
            if status_el:
                status = _clean_text(status_el)

            # 3. Total amount
            total_amount = 0.0
            total_el = card.find(class_=re.compile(r"order-amount|total-price|pay-amount|price"))
            if total_el:
                total_amount = _parse_price(_clean_text(total_el))

            # 4. Items
            name_el = card.find(class_=re.compile(r"goods-name|title|product-name"))
            spec_el = card.find(class_=re.compile(r"spec|sku|sku-desc"))
            qty_el = card.find(class_=re.compile(r"quantity|goods-number|count"))

            p_name = _clean_text(name_el) or "Pinduoduo Item"
            v_name = _clean_text(spec_el)
            qty = _parse_price(_clean_text(qty_el)) if qty_el else 1.0
            if qty <= 0:
                qty = 1.0

            items = [{
                "product_id": f"p_pdd_{abs(hash(p_name)) % 10000000}",
                "sku_id": f"sku_pdd_{abs(hash(v_name)) % 1000000}" if v_name else "",
                "product_name": p_name,
                "variant_name": v_name,
                "quantity": qty,
                "unit_price": round(total_amount / qty, 2) if total_amount else 0.0,
                "line_total": total_amount,
                "ai_category_suggestion": "tool" if "工具" in p_name else "consumable",
                "ai_ownership_suggestion": "self",
            }]

            results.append({
                "order_id": order_id,
                "status": status,
                "total_amount": total_amount,
                "currency": cls.CURRENCY,
                "items": items,
            })

        return results
