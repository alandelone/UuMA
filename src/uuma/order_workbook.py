from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

DETAIL_SHEET = "所有订单明细"
REQUIRED_HEADERS = (
    "订单号",
    "订单提交时间",
    "订单状态",
    "店铺名称",
    "种类",
    "商品名称",
    "商品链接",
    "型号款式",
    "商品数量",
    "商品金额",
    "实付金额",
    "运费",
)
DEFAULT_LAB_CATEGORIES = (
    "电子元器件 / 仪器实验",
    "电脑硬件 / 网络设备",
    "3D打印 / 打印耗材",
    "数码配件 / 摄影配件",
    "五金建材 / 工具劳保",
    "电脑外设 / 办公文具",
)
USABLE_STATUSES = {"交易成功", "卖家已发货"}

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL_REF = re.compile(r"([A-Z]+)(\d+)")
_ITEM_ID = re.compile(r"[?&]id=(\d+)")


class OrderWorkbookError(ValueError):
    pass


def _column_index(cell_reference: str) -> int:
    match = _CELL_REF.fullmatch(cell_reference)
    if not match:
        raise OrderWorkbookError(f"Unsupported cell reference: {cell_reference}")
    result = 0
    for char in match.group(1):
        result = result * 26 + ord(char) - ord("A") + 1
    return result - 1


def _shared_strings(archive: ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(node.text or "" for node in item.iter(f"{{{_MAIN_NS}}}t")) for item in root]


def _sheet_path(archive: ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationship_id = None
    for sheet in workbook.findall(f".//{{{_MAIN_NS}}}sheet"):
        if sheet.attrib.get("name") == sheet_name:
            relationship_id = sheet.attrib.get(f"{{{_DOC_REL_NS}}}id")
            break
    if not relationship_id:
        raise OrderWorkbookError(f"Workbook does not contain sheet '{sheet_name}'.")

    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    for relationship in relationships.findall(f"{{{_PKG_REL_NS}}}Relationship"):
        if relationship.attrib.get("Id") == relationship_id:
            target = relationship.attrib["Target"].lstrip("/")
            if target.startswith("xl/"):
                return target
            return str(PurePosixPath("xl") / target)
    raise OrderWorkbookError(f"Workbook relationship for sheet '{sheet_name}' is missing.")


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> Any:
    value_type = cell.attrib.get("t")
    if value_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{_MAIN_NS}}}t"))
    value = cell.find(f"{{{_MAIN_NS}}}v")
    if value is None or value.text is None:
        return ""
    if value_type == "s":
        return shared_strings[int(value.text)]
    if value_type in {"str", "e"}:
        return value.text
    try:
        number = float(value.text)
    except ValueError:
        return value.text
    return int(number) if number.is_integer() else number


def _worksheet_rows(archive: ZipFile, sheet_path: str) -> list[tuple[int, list[Any]]]:
    root = ET.fromstring(archive.read(sheet_path))
    shared = _shared_strings(archive)
    result: list[tuple[int, list[Any]]] = []
    for row in root.findall(f".//{{{_MAIN_NS}}}row"):
        row_number = int(row.attrib.get("r", len(result) + 1))
        values: list[Any] = []
        for cell in row.findall(f"{{{_MAIN_NS}}}c"):
            index = _column_index(cell.attrib.get("r", "A1"))
            while len(values) <= index:
                values.append("")
            values[index] = _cell_value(cell, shared)
        result.append((row_number, values))
    return result


def _number(value: Any, field_name: str, row_number: int) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise OrderWorkbookError(
            f"Row {row_number} has a non-numeric {field_name}: {value!r}."
        ) from exc


def preview_order_workbook(
    workbook_path: Path | str,
    *,
    categories: list[str] | tuple[str, ...] | None = None,
    component_mapping: dict[str, str] | None = None,
    sample_limit: int = 25,
) -> dict[str, Any]:
    path = Path(workbook_path).expanduser().resolve()
    if not path.is_file():
        raise OrderWorkbookError(f"Workbook not found: {path}")
    if path.suffix.casefold() != ".xlsx":
        raise OrderWorkbookError("Order workbook import currently supports .xlsx files only.")

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    selected_categories = set(categories or DEFAULT_LAB_CATEGORIES)
    mapping = component_mapping or {}
    try:
        with ZipFile(path) as archive:
            rows = _worksheet_rows(archive, _sheet_path(archive, DETAIL_SHEET))
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        raise OrderWorkbookError(f"Cannot read XLSX workbook: {exc}") from exc
    if not rows:
        raise OrderWorkbookError(f"Sheet '{DETAIL_SHEET}' is empty.")

    header_row_number, header_values = rows[0]
    headers = [str(value).strip() for value in header_values]
    if tuple(headers[: len(REQUIRED_HEADERS)]) != REQUIRED_HEADERS:
        raise OrderWorkbookError(
            f"Unexpected headers in row {header_row_number}; expected {list(REQUIRED_HEADERS)}."
        )

    normalized: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    excluded_footer_rows = 0
    for row_number, raw_values in rows[1:]:
        values = list(raw_values) + [""] * (len(REQUIRED_HEADERS) - len(raw_values))
        status = str(values[2]).strip()
        if not status:
            excluded_footer_rows += 1
            continue
        category = str(values[4]).strip()
        status_counts[status] = status_counts.get(status, 0) + 1
        category_counts[category] = category_counts.get(category, 0) + 1
        product_url = str(values[6]).strip()
        item_match = _ITEM_ID.search(product_url)
        item_id = item_match.group(1) if item_match else ""
        variant = str(values[7]).strip()
        identity_key = f"{item_id}|{variant}"
        component_id = str(mapping.get(identity_key, "")).strip()
        if status not in USABLE_STATUSES:
            disposition = "EXCLUDED_STATUS"
        elif category not in selected_categories:
            disposition = "EXCLUDED_CATEGORY"
        elif component_id:
            disposition = "MAPPED_PURCHASE_HISTORY"
        else:
            disposition = "NEEDS_COMPONENT_REVIEW"
        normalized.append(
            {
                "source_key": f"sha256:{digest}:{DETAIL_SHEET}:{row_number}",
                "source_workbook_hash": digest,
                "source_sheet": DETAIL_SHEET,
                "source_row": row_number,
                "order_id": str(values[0]).strip(),
                "ordered_at": str(values[1]).strip(),
                "status": status,
                "supplier": str(values[3]).strip(),
                "category": category,
                "product_name": str(values[5]).strip(),
                "product_url": product_url,
                "offer_ref": item_id,
                "variant": variant,
                "ordered_quantity": _number(values[8], "商品数量", row_number),
                "order_unit": "listing_unit",
                "goods_amount_raw": _number(values[9], "商品金额", row_number),
                "paid_amount_order_raw": _number(values[10], "实付金额", row_number),
                "shipping_amount_order_raw": _number(values[11], "运费", row_number),
                "identity_key": identity_key,
                "component_id": component_id or None,
                "disposition": disposition,
                "evidence_ref": f"{path}#{DETAIL_SHEET}!A{row_number}:L{row_number}",
            }
        )

    importable = [
        row
        for row in normalized
        if row["disposition"] in {"MAPPED_PURCHASE_HISTORY", "NEEDS_COMPONENT_REVIEW"}
    ]
    orders: dict[str, dict[str, float]] = {}
    for row in normalized:
        orders.setdefault(
            row["order_id"],
            {
                "paid": row["paid_amount_order_raw"],
                "shipping": row["shipping_amount_order_raw"],
            },
        )
    return {
        "status": "preview",
        "workbook_path": str(path),
        "workbook_sha256": digest,
        "sheet": DETAIL_SHEET,
        "headers": headers[: len(REQUIRED_HEADERS)],
        "detail_rows": len(normalized),
        "orders": len({row["order_id"] for row in normalized}),
        "excluded_footer_rows": excluded_footer_rows,
        "status_counts": status_counts,
        "category_counts": category_counts,
        "selected_categories": sorted(selected_categories),
        "importable_purchase_history_rows": len(importable),
        "mapped_rows": sum(row["component_id"] is not None for row in importable),
        "needs_component_review_rows": sum(row["component_id"] is None for row in importable),
        "excluded_status_rows": sum(row["disposition"] == "EXCLUDED_STATUS" for row in normalized),
        "excluded_category_rows": sum(
            row["disposition"] == "EXCLUDED_CATEGORY" for row in normalized
        ),
        "quantity_is_listing_units": True,
        "unique_order_paid_amount_raw": round(sum(item["paid"] for item in orders.values()), 2),
        "warning": (
            "This workbook is order history, not a physical count. Importing purchase history "
            "does not create inventory balances. 商品数量 remains listing_unit; pack sizes require review."
        ),
        "rows": importable,
        "sample_rows": importable[: max(0, sample_limit)],
    }
