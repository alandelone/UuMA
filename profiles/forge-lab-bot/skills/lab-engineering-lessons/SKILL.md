---
name: lab-engineering-lessons
description: Formulate candidate engineering lessons derived from lab worklogs, tests, and failure investigations without crossing the reviewer boundary.
---

# Lab Engineering Lessons

The `lab-engineering-lessons` skill manages the lifecycle of reusable engineering knowledge derived from physical hardware experience.

## Core Invariants

- **Conservative Promotion Pipeline**:
  ```text
  Worklog / Failure -> Extraction -> Candidate Lesson -> Review -> Accepted Lesson -> Operational Rule
  ```
- **Lifecycle Statuses**: `CANDIDATE`, `SUPPORTED`, `ACCEPTED`, `DEPRECATED`, `REJECTED`.
- **Reviewer Boundary**: LAB_BOT creates and refines `CANDIDATE` records only. A user or designated
  reviewer performs acceptance, rejection, supersession, deprecation, or rule promotion.
- **Target Systems & Strengths**:
  - Targets: `ESCHEMATIC`, `PROCUREMENT`, `BUILD_PROCESS`, `STOCKKEEPER`, `LAB_ONLY`.
  - Strengths: `BLOCK`, `WARN`, `RECOMMEND`, `PREFERENCE`, `KNOWLEDGE`.
- **Safety Governance**: Safety-critical constraints (`BLOCK` / `WARN`) require high confidence, explicit evidence references, and engineering review.

## Tool Routing

- **Propose Candidate Lesson**: `lab_propose_lesson`.
- **Query Lessons**: `lab_list_lessons` (filter by `target_system` or `status`).
- **Refine Candidate**: `lab_update_lesson_status` may only retain `CANDIDATE` while updating
  exceptions. Reviewer lifecycle decisions occur outside the LAB_BOT tool boundary.
