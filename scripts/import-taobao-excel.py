"""Import Taobao Excel export workbook into UuMA CommerceStore and lab.db."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uuma.commerce_store import CommerceStore
from uuma.order_workbook import _worksheet_rows, _ITEM_ID


def clean_num(value: Any) -> float:
    if value is None:
        return 0.0
    s = str(value).strip()
    if not s:
        return 0.0
    cleaned = re.sub(r"[^\d.]", "", s)
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def parse_taobao_export_rows(rows: list[tuple[int, list[Any]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse rows with forward-fill for multi-item orders.
    
    Returns:
        (orders_list_for_commerce_store, flat_rows_for_purchase_history)
    """
    orders: list[dict[str, Any]] = []
    flat_rows: list[dict[str, Any]] = []
    curr_order: dict[str, Any] | None = None

    for row_num, row_values in rows[1:]:
        oid = str(row_values[0]).strip() if len(row_values) > 0 and row_values[0] else ""
        pname = str(row_values[4]).strip() if len(row_values) > 4 and row_values[4] else ""
        purl = str(row_values[5]).strip() if len(row_values) > 5 and row_values[5] else ""
        sku = str(row_values[6]).strip() if len(row_values) > 6 and row_values[6] else ""
        qty = clean_num(row_values[7]) if len(row_values) > 7 else 1.0
        price = clean_num(row_values[8]) if len(row_values) > 8 else 0.0
        paid = clean_num(row_values[9]) if len(row_values) > 9 else 0.0
        freight = clean_num(row_values[10]) if len(row_values) > 10 else 0.0

        if not pname and not purl:
            continue

        match = _ITEM_ID.search(purl)
        pid = match.group(1) if match else "p_unknown"

        if oid:
            otime = str(row_values[1]).strip() if len(row_values) > 1 else ""
            status = str(row_values[2]).strip() if len(row_values) > 2 else ""
            shop = str(row_values[3]).strip() if len(row_values) > 3 else ""

            curr_order = {
                "order_id": oid,
                "status": status,
                "total_amount": paid,
                "currency": "CNY",
                "shop_name": shop,
                "order_time": otime,
                "shipping_fee": freight,
                "items": []
            }
            orders.append(curr_order)

        if curr_order is None:
            continue

        item_dict = {
            "product_id": pid,
            "sku_id": f"sku_{sku}" if sku else "",
            "product_name": pname,
            "variant_name": sku,
            "quantity": qty if qty > 0 else 1.0,
            "unit_price": price,
            "line_total": qty * price if price else 0.0,
            "item_url": purl,
            "shop_name": curr_order["shop_name"],
            "order_time": curr_order["order_time"],
            "shipping_fee": curr_order["shipping_fee"],
            "order_status": curr_order["status"],
        }
        curr_order["items"].append(item_dict)

        flat_rows.append({
            "source_row": row_num,
            "order_id": curr_order["order_id"],
            "ordered_at": curr_order["order_time"],
            "status": curr_order["status"],
            "supplier": curr_order["shop_name"],
            "category": "电子元器件 / 仪器实验",
            "product_name": pname,
            "product_url": purl,
            "offer_ref": pid,
            "variant": sku,
            "ordered_quantity": qty if qty > 0 else 1.0,
            "order_unit": "listing_unit",
            "goods_amount_raw": price * qty if price else 0.0,
            "paid_amount_order_raw": curr_order["total_amount"],
            "shipping_amount_order_raw": curr_order["shipping_fee"],
            "identity_key": f"{pid}|{sku}",
        })

    return orders, flat_rows


def import_taobao_excel(excel_path: Path | str, account_id: str = "alansyling@gmail.com") -> dict[str, Any]:
    path = Path(excel_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Workbook not found: {path}")

    raw_bytes = path.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()

    with zipfile.ZipFile(path) as archive:
        sheet_path = "xl/worksheets/sheet1.xml"
        rows = _worksheet_rows(archive, sheet_path)

    if not rows:
        raise ValueError(f"No rows found in {path}")

    orders, flat_rows = parse_taobao_export_rows(rows)

    batch_id = f"taobao_batch_excel_{digest[:16]}"
    batch_payload = {
        "batch_id": batch_id,
        "task_id": "task_excel_taobao",
        "platform": "taobao",
        "account_id": account_id,
        "orders": orders,
    }

    # 1. Ingest via CommerceStore
    store = CommerceStore()
    ingest_result = store.ingest_batch(batch_payload)

    # 2. Ingest into purchase_history_lines
    now_iso = datetime.now(UTC).isoformat()
    ph_committed = 0
    ph_skipped = 0

    with store.connect() as conn:
        for fr in flat_rows:
            source_key = f"sha256:{digest}:订单数据:{fr['source_row']}"
            evidence_ref = f"{path}#订单数据!A{fr['source_row']}:K{fr['source_row']}"
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO purchase_history_lines(
                    source_key, source_workbook_hash, source_sheet, source_row,
                    order_id, ordered_at, status, supplier, category, product_name,
                    product_url, offer_ref, variant, ordered_quantity, order_unit,
                    goods_amount_raw, paid_amount_order_raw, shipping_amount_order_raw,
                    identity_key, component_id, resolution_status, evidence_ref,
                    imported_at, metadata_json
                ) VALUES (?, ?, '订单数据', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'NEEDS_COMPONENT_REVIEW', ?, ?, '{}')
                """,
                (
                    source_key, digest, fr["source_row"],
                    fr["order_id"], fr["ordered_at"], fr["status"], fr["supplier"] or None,
                    fr["category"] or None, fr["product_name"], fr["product_url"] or None,
                    fr["offer_ref"] or None, fr["variant"] or None, fr["ordered_quantity"],
                    fr["order_unit"], fr["goods_amount_raw"], fr["paid_amount_order_raw"],
                    fr["shipping_amount_order_raw"], fr["identity_key"], evidence_ref, now_iso
                )
            )
            if cursor.rowcount > 0:
                ph_committed += 1
            else:
                ph_skipped += 1

    return {
        "batch_id": batch_id,
        "file_sha256": digest,
        "total_parsed_orders": len(orders),
        "total_parsed_items": len(flat_rows),
        "total_paid_amount": round(sum(o["total_amount"] for o in orders), 2),
        "commerce_store": ingest_result,
        "purchase_history_committed": ph_committed,
        "purchase_history_skipped": ph_skipped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Taobao Excel Export")
    parser.add_argument("path", nargs="?", default=r"C:\Users\Alandelone\Downloads\订单数据 (1).xlsx", help="Path to Excel file")
    args = parser.parse_args()

    result = import_taobao_excel(args.path)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
