---
name: lab-as-built
description: Monitor and record as-built physical configurations, component lot installations, substitutions, and assembly modifications.
---

# Lab As-Built Configuration

The `lab-as-built` skill maintains the authoritative record of what components, lots, and modifications are physically present in a Build.

## Core Invariants

- **Designed BOM != As-Built BOM**: Field substitutions, rework, and lot tracking are recorded as they actually occur.
- **Installation Ledger**: Parts enter a Build via `INSTALL` events from `RESERVED` inventory and leave via `UNINSTALL`.
- **Damage Isolation**: Damaged installed parts are recorded via `MARK_DAMAGED` and replaced with tracked new lots.

## Tool Routing

- **Query As-Built State**: `lab_get_current_as_built` (returns active installed components, lot IDs, and quantities).
- **Record Part Installation**: `inventory_transition` with `event_type="INSTALL"`, `build_id`, and `lot_id`.
- **Record Part Removal/Rework**: `inventory_transition` with `event_type="UNINSTALL"` and `build_id`.
