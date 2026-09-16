---
name: eschematic-bridge
description: Controlled integration interface with eSchematic for canonical component lookup, immutable design revisions, BOM normalization, validation, and design-feedback proposals.
---

# eSchematic Bridge

The `eschematic-bridge` provides forge-lab-bot with a controlled, decoupled interface to the authoritative `eSchematic` design system.

## Authority & Boundary Invariants

- **Read-Only Intent**: eSchematic is the single source of truth for component specifications (MPN, pins, electrical characteristics) and schematic designs.
- **Immutable Revisions**: Released designs must be exported as hash-verified immutable manifests before physical builds reference them.
- **Proposal-Only Feedback**: Lab findings, substitutions, and improvements cannot directly mutate eSchematic design records; they must be submitted as structured `design-feedback proposals`.
- **Physical Separation**: `lab.db` owns physical inventory and builds; eSchematic never owns physical stock.

## Tool Routing

- **Component Lookup**: `eschematic_get_component`, `eschematic_list_components`.
- **Component Search / Candidate Review**: `eschematic_find_components`, `eschematic_commit_candidate` (requires explicit user approval).
- **BOM Normalization & Resolution**: `eschematic_normalize_bom`.
- **Design Manifest Release**: `eschematic_export_design_manifest`.
- **Circuit Verification**: `eschematic_validate_circuit`, `eschematic_check_electrical_rules`.
- **Design Feedback Proposals**:
  - `eschematic_submit_design_feedback`: submit proposed component or wiring changes with rationale and evidence.
  - `eschematic_list_design_feedback`: query existing feedback proposals.
