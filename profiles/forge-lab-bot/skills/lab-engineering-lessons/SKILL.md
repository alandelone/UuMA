---
name: lab-engineering-lessons
description: Formulate, review, and promote candidate engineering lessons derived from lab worklogs, tests, and failure investigations.
---

# Lab Engineering Lessons

The `lab-engineering-lessons` skill manages the lifecycle of reusable engineering knowledge derived from physical hardware experience.

## Core Invariants

- **Conservative Promotion Pipeline**:
  ```text
  Worklog / Failure -> Extraction -> Candidate Lesson -> Review -> Accepted Lesson -> Operational Rule
  ```
- **Lifecycle Statuses**: `CANDIDATE`, `SUPPORTED`, `ACCEPTED`, `DEPRECATED`, `REJECTED`.
- **Target Systems & Strengths**:
  - Targets: `ESCHEMATIC`, `PROCUREMENT`, `BUILD_PROCESS`, `STOCKKEEPER`, `LAB_ONLY`.
  - Strengths: `BLOCK`, `WARN`, `RECOMMEND`, `PREFERENCE`, `KNOWLEDGE`.
- **Safety Governance**: Safety-critical constraints (`BLOCK` / `WARN`) require high confidence, explicit evidence references, and engineering review.

## Tool Routing

- **Propose Candidate Lesson**: `lab_propose_lesson`.
- **Query Lessons**: `lab_list_lessons` (filter by `target_system` or `status`).
- **Update Status / Review**: `lab_update_lesson_status` (promote to `ACCEPTED` or reject with reason/exceptions).
