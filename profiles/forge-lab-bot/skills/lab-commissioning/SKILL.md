---
name: lab-commissioning
description: Record bring-up test logs, voltage verifications, oscilloscope measurements, and calibration results tied to physical builds.
---

# Lab Commissioning & Testing

The `lab-commissioning` skill records hardware verification logs, functional bring-up checks, and calibration history.

## Core Invariants

- **Traceable Results**: Every test log binds to a `build_id`, `test_name`, `status` (`PASS`, `FAIL`, `IN_PROGRESS`, `BLOCKED`), and `operator`.
- **Structured Metrics**: Numerical readings (e.g. supply voltages, ripple, current draw, temperatures) are stored in structured `metrics`.
- **Evidence Linking**: Logs should link to oscilloscope waveforms, photos, or raw Notion journal entries.

## Tool Routing

- **Record Test / Calibration**: `lab_record_commissioning`.
- **List Verification History**: `lab_list_commissioning` (filter by `build_id` or `status`).
