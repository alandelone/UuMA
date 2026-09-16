---
name: lab-worklog
description: Structure raw engineer worklogs and Notion journal entries into parsed hardware records with strict epistemic separation.
---

# Lab Worklog & Journal

The `lab-worklog` skill ingests engineer observations and bench notes, structuring them while preserving epistemic integrity.

## Core Invariants

- **Strict Epistemic Separation**:
  ```text
  Observation != Hypothesis != Confirmed Cause
  ```
- **Provenance Preservation**: Raw Notion notes and engineer inputs remain unaltered and are referenced by `source_ref`.
- **Action & Result Tracking**: Each record preserves what was tested (`action`), what happened (`observation`), what was found (`result`), and what to do next (`next_action`).

## Tool Routing

- **Record Structured Log**: `lab_record_worklog`.
- **Query Worklogs**: `lab_list_worklogs` (filter by `project_name` or `build_id`).
