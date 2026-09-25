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
- **Visible Editing**: A queued `PATCH_LOG` includes `change_summary` and `change_reason`; append
  `LAB_BOT Enrichment` and `Change Notice` instead of silently rewriting human text.
- **Truth Boundary**: Notion owns the complete human journal. `lab.db` owns the structured
  projection, synchronization ledger, derived records, and retry/conflict history.
- **No False Success**: Only report `Synced` after the connector returns a remote page/content hash.
  Surface `Queued`, `Failed`, and `Conflict` states to the user.

## Tool Routing

- **Record Structured Log**: `lab_record_worklog`.
- **Capture from Chat**: `lab_journal_capture_chat` after the conversational intake below. This
  creates the local worklog, queues the Notion entry, and requests one runner execution.
- **Query Worklogs**: `lab_list_worklogs` (filter by `project_name` or `build_id`).
- **Reconcile Notion Snapshot**: `lab_journal_register_snapshot` after fetching through the
  logical `OpenClaw` connection (Hermes MCP server name may remain `notion`).
- **Stage Notion Write**: `lab_journal_queue_write` with a stable idempotency key before writing.
- **Deliver / Record Outcome**: connector workers use `lab_journal_claim_write` and
  `lab_journal_finish_write`; success requires remote hash evidence.
- **Inspect / Recover**: `lab_journal_sync_status`, `lab_journal_list_events`, and
  `lab_journal_request_resync`. Never resync over `Conflict` without human resolution.
- **User Notices**: `lab_journal_list_notifications`; delivery workers lease and finish notices
  through the latest eligible Forge route, with the default Hermes route as the bootstrap fallback.

## Conversational intake

Use this flow when the user says “record this,” “记一下,” “写进日志,” or reports real lab work and
clearly wants it preserved:

1. Extract the facts already supplied. Preserve the user's raw wording in `raw_note`.
2. Infer the entry type:
   - `Problem`: a fault, unexpected behavior, or unresolved issue;
   - `Experiment`: a test intended to learn or compare;
   - `Repair`: corrective work on an existing item; or
   - `Build`: fabrication, assembly, commissioning, or a new build state.
3. Draft a short title. Use the named project, machine, or subsystem as `project_system`; use
   `Unknown` when the user genuinely does not know it.
4. Separate what was done (`action`) from what was seen (`observation`). Keep hypothesis,
   confirmed cause, result, verification, next step, and candidate lesson empty unless supported.
5. Ask one concise follow-up containing only facts that cannot be derived honestly. Usually that
   means what object/project was involved, what action occurred, or what was observed. Do not ask
   the user to repeat facts or fill every optional field.
6. When title, project/system, type, raw note, action, and observation are available, call
   `lab_journal_capture_chat` once. Pass a platform source reference when one is available; the
   tool derives a stable internal reference and idempotency key otherwise. Never ask the user for
   either internal value. Tell the user whether the entry is `Queued`, `Synced`, `Failed`, or
   `Conflict`; never describe `Queued` as synchronized.

Do not capture generic advice, hypothetical planning, sourcing comparisons, casual mentions, or
meta-discussion about the journal. Respect “do not record” and similar opt-outs. If classification
is genuinely ambiguous, offer the two plausible types in one short question.

## Event-driven delivery

- A chat capture queues one idempotent write and requests one dormant runner execution.
- The scheduled task has no time or logon triggers and consumes no resources between requests.
- Explicit Stop pauses delivery. New captures remain safely queued until the operator starts the
  runner again; the chatbot must disclose that paused state.
- The transport reads the existing default Hermes `notion` connection at runtime and never copies
  its credential into this profile, `lab.db`, source files, or queue payloads.
- No external watchdog, resident polling process, or Task Scheduler retry is allowed.
