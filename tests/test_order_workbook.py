from __future__ import annotations

from html import escape
from zipfile import ZIP_DEFLATED, ZipFile

from uuma.lab_inventory import InventoryStore
from uuma.order_workbook import REQUIRED_HEADERS, preview_order_workbook


def _cell(reference: str, value: object) -> str:
    if isinstance(value, (int, float)):
        return f'<c r="{reference}"><v>{value}</v></c>'
    return (
        f'<c r="{reference}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
    )


def _write_order_workbook(path) -> None:
    rows = [
        list(REQUIRED_HEADERS),
        [
            "ORDER-1",
            "2026-08-01 10:00:00",
            "交易成功",
            "Parts Shop",
            "电子元器件 / 仪器实验",
            "M2 screw pack",
            "https://item.taobao.com/item.htm?id=123",
            "M2*12-100个",
            1,
            3.5,
            8.0,
            0,
        ],
        [
            "ORDER-2",
            "2026-08-02 10:00:00",
            "交易关闭",
            "Parts Shop",
            "电子元器件 / 仪器实验",
            "Cancelled sensor",
            "https://item.taobao.com/item.htm?id=456",
            "SHT41",
            1,
            12.1,
            12.1,
            0,
        ],
        [
            "ORDER-3",
            "2026-08-03 10:00:00",
            "交易成功",
            "Home Shop",
            "家居日用 / 家纺清洁",
            "Cleaning cloth",
            "https://item.taobao.com/item.htm?id=789",
            "blue",
            2,
            5,
            5,
            0,
        ],
        ["共 3 项明细, 3 笔订单"],
    ]
    worksheet_rows = []
    for row_number, values in enumerate(rows, start=1):
        cells = []
        for index, value in enumerate(values):
            column = chr(ord("A") + index)
            cells.append(_cell(f"{column}{row_number}", value))
        worksheet_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(worksheet_rows)}</sheetData></worksheet>'
    )
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="所有订单明细" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>',
        )
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)


def test_order_workbook_preview_is_purchase_history_not_stock(tmp_path):
    path = tmp_path / "orders.xlsx"
    _write_order_workbook(path)

    preview = preview_order_workbook(path)

    assert preview["detail_rows"] == 3
    assert preview["excluded_footer_rows"] == 1
    assert preview["importable_purchase_history_rows"] == 1
    assert preview["needs_component_review_rows"] == 1
    assert preview["excluded_status_rows"] == 1
    assert preview["excluded_category_rows"] == 1
    row = preview["rows"][0]
    assert row["identity_key"] == "123|M2*12-100个"
    assert row["ordered_quantity"] == 1
    assert row["order_unit"] == "listing_unit"

    inventory = InventoryStore(tmp_path / "lab.db")
    staged = inventory.import_purchase_history(preview["rows"], commit=True)
    duplicate = inventory.import_purchase_history(preview["rows"], commit=True)
    assert staged["committed"] == 1
    assert duplicate["committed"] == 0
    assert duplicate["skipped"] == 1
    assert inventory.balances() == []
    with inventory.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM inventory_events").fetchone()[0] == 0
