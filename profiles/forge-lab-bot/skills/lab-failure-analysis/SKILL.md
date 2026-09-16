---
name: lab-failure-analysis
description: Document hardware failures, smoke events, component damage, severity ratings, and root-cause investigations.
---

# Lab Failure Analysis

The `lab-failure-analysis` skill tracks hardware anomalies, component breakdown, and diagnostic investigations.

## Core Invariants

- **Severity Classification**: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
- **Causality Rigor**: Distinguish `suspected_cause` from `confirmed_cause`. A hypothesis is never stored as confirmed cause without conclusive verification.
- **Component & Build Association**: Link failures to the specific component MPN/ID and physical build instance.
- **Corrective Action**: Record what modifications, repairs, or part replacements were executed.

## Tool Routing

- **Log Failure Incident**: `lab_record_failure`.
- **List / Filter Incidents**: `lab_list_failures` (filter by `severity`, `component_id`, or `build_id`).
- **Mark Part Damaged**: `inventory_transition` with `event_type="MARK_DAMAGED"`.
