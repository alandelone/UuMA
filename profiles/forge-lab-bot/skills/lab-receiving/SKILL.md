---
name: lab-receiving
description: Handle purchase lots, receiving inspection, supplier lot provenance, and order workbook staging.
---

# Lab Receiving

The `lab-receiving` skill converts arriving packages and orders into inspected, ledger-backed inventory stock.

## Core Invariants

- **Ordered is Not Stock**: Goods in transit or staged orders are not stock. Only inspected goods receiving into a physical location increment `AVAILABLE` balances.
- **Lot Provenance**: Retain purchase lot IDs, suppliers, offer references, and arrival inspection records.
- **Order Workbook Staging**: Staged order history lines are evidence only (`purchase_history_lines`), and must be resolved to canonical component IDs before receiving.

## Tool Routing

- **Receive & Inspect Stock**: `inventory_receive`.
- **Order History Ingest**: `inventory_preview_or_import_order_workbook` (preview with `commit=false` first).
- **Review Staged Orders**: `inventory_list_purchase_history` (filter by `needs_review_only=true`).
- **Resolve Component Identity**: `inventory_resolve_purchase_history_line`.
