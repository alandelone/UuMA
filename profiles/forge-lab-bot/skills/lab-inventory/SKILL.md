---
name: lab-inventory
description: Operate forge-lab-bot physical inventory, location hierarchies, event-ledger transitions, balances, and reconciliation adjustments.
---

# Lab Inventory

The `lab-inventory` skill manages the physical stock ledger and locations within `lab.db`.

## Core Invariants

- **Ledger-Driven**: Quantities are never overwritten directly. All changes occur through immutable events (`RECEIVE`, `RESERVE`, `RELEASE`, `INSTALL`, `UNINSTALL`, `MARK_DAMAGED`, `REPAIR`, `CONSUME`, `SCRAP`, or `ADJUST`).
- **Inventory Buckets**: `AVAILABLE`, `RESERVED`, `INSTALLED`, `DAMAGED`, `CONSUMED`.
- **No Negative Balances**: Moving stock out of a bucket requires sufficient on-hand quantity.
- **Physical Locations**: Locations form a stable hierarchy (e.g. Lab -> Cabinet -> Drawer -> Box).
- **Reasoned Adjustments**: Reconciliation counts must use `inventory_adjust` with explicit reason and evidence.

## Tool Routing

- **Status & Counts**: `inventory_status`.
- **Location Management**: `inventory_create_location`.
- **Balance Inquiries**: `inventory_get_balances` (optionally filtered by `component_id`).
- **Bucket Transitions**: `inventory_transition`.
- **Physical Reconciliation**: `inventory_adjust`.
- **Legacy Migration**: `inventory_preview_or_import_legacy_rows`.
