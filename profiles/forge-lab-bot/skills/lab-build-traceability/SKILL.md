---
name: lab-build-traceability
description: Track physical build instances, bind them to immutable eSchematic design revision manifests, and manage build lifecycle states.
---

# Lab Build Traceability

The `lab-build-traceability` skill tracks physical hardware assembly instances (Builds) against design specifications.

## Core Invariants

- **Instance Distinction**: `Design Revision` (design intent) != `Build` (physical unit) != `As-Built` (actual components installed).
- **Manifest Immutability**: A Build binds to an immutable design revision with a cryptographic hash.
- **Lifecycle Progression**: Builds progress through defined states: `OPEN` -> `IN_PROGRESS` -> `COMPLETED` (or `ABANDONED`).

## Tool Routing

- **Create Build**: `lab_create_build` (specifying `design_revision_id` and optional manifest hash).
- **List Builds**: `lab_list_builds` (filter by status).
- **Update Status**: `lab_update_build_status`.
