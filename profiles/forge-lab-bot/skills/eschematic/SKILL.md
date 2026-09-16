---
name: eschematic
description: Use eSchematic through forge-lab-bot tools for canonical components, BOM normalization, circuit proposals, ERC, recommendations, and schematic rendering.
---

# eSchematic for forge-lab-bot

Use the `eschematic_*` MCP tools whenever hardware work needs canonical component identity,
pin/electrical metadata, a normalized design BOM, a proposed circuit, validation, or a rendered
schematic. Do not run the eSchematic Python scripts directly.

## Authority boundary

- eSchematic owns component definitions and design intent.
- `lab.db` owns stock, locations, purchase lots, Builds, and As-Built state.
- Store only eSchematic `component_id` references and optional display snapshots in `lab.db`.
- Treat inferred circuits and recommendations as proposals. They do not silently modify a design.
- Use `eschematic_commit_candidate` only after the candidate is shown and the user or engineer
  explicitly approves the catalog write.

## Routing

- Component lookup: `eschematic_get_component` or `eschematic_list_components`.
- Missing component: `eschematic_find_components`, review candidates, then request approval before
  committing one.
- BOM: `eschematic_normalize_bom`; use resolution findings rather than guessing an identity.
- Released design: export a hash-bearing immutable manifest only after every BOM row resolves to one
  canonical component ID; pass its revision and hash into `lab_create_build`.
- Circuit: infer or load Circuit IR, validate connectivity, run ERC, list recommendations, then
  render only after review.
- Availability: pass resolved component IDs to `lab_analyze_bom`; eSchematic does not own stock.
- Design feedback: submit proposed design improvements using `eschematic_submit_design_feedback`.

`connectivity-checked` is not electrical-safety, thermal, or fabrication certification.

