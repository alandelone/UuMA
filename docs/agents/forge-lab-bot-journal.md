# Forge Journal and LAB_BOT Responsibilities

Status: V1 active; V2 conversational capture and event-driven delivery active, 2026-09-23

This document records the agreed boundary for the human-facing Forge Journal and the
`锻造Lab_BOT` worklog and engineering-memory capability. V1 is active in Notion. The V2 local
synchronization ledger is implemented in `lab.db`, and the live OpenClaw/Notion transport and
Hermes notification worker are deployed for unattended operation.

## Canonical Notion location

- Parent: `锻造界の深入~`
- Hub: `锻造日志与工程经验｜Forge Journal`
- Log database: `锻造日志｜Forge Logs`

On 2026-09-22, twenty existing `Log_*` pages were moved into Forge Logs without rewriting their
page bodies. They retain their original format and are marked `Legacy Import` and `Inbox`.
`3DP Issue &Improvement` and `锻造工作流笔记` were also moved under the Forge Journal hub as
reference pages, with their content unchanged.

## Agreed operating rules

1. The human and LAB_BOT use one shared, human-visible journal in Notion.
2. New manual entries will have exactly four entry buttons: `Problem`, `Experiment`, `Repair`,
   and `Build`.
3. LAB_BOT may edit a human-authored page, but it must never do so silently. Every automatic edit
   must notify the user and state what changed and why.
4. Synchronization uses event-triggered one-shot delivery and an explicit manual resync command.
   A normal chat capture requests one runner execution; there is no timed polling.
5. LAB_BOT must notify the user when a write is queued offline, fails, remains degraded, or
   recovers. A queued or failed write must never be reported as successfully synchronized.
6. Old logs remain in their original body format after relocation; the new templates are for new
   entries only.
7. Engineering lessons and SOPs are derived knowledge. They do not become mandatory rules without
   review.

## LAB_BOT responsibilities

LAB_BOT is responsible for:

0. **Conversational intake**
   - When the user asks to record actual lab work, infer `Problem`, `Experiment`, `Repair`, or
     `Build` from the facts already supplied.
   - Preserve the user's raw wording, draft the title, and ask only for facts that cannot be
     inferred honestly. Missing optional structure is not a reason to reject the entry.
   - Do not capture generic advice, hypothetical plans, sourcing comparisons, casual mentions,
     meta-discussion, or anything the user opts out of recording.

1. **Capture and routing**
   - Create or update a Forge Log for fabrication, electronics, machines, laboratory work,
     procurement, builds, repairs, maintenance, commissioning, experiments, and troubleshooting.
   - Associate the entry with the correct date, project, machine, build, parts, and evidence when
     those facts are known.

2. **Structured enrichment**
   - Separate observations, hypotheses, confirmed causes, actions, results, verification, and next
     actions.
   - Preserve unsuccessful attempts as part of the engineering trace.
   - Link photos, measurements, configuration files, drawings, purchase records, and related logs
     instead of inventing evidence.

3. **Transparent editing**
   - Keep the user's original meaning and wording available.
   - When editing or reorganizing human text, add a change notice containing time, changed content,
     and reason, then notify the user through the agreed notification channel.
   - Never silently turn a hypothesis into a confirmed fact or a personal note into a rule.

4. **Traceability and synchronization**
   - Preserve the Notion page ID or URL as the human-visible source reference.
   - Link each structured `lab.db` worklog, build, failure, or lesson back to its Notion source.
   - Use idempotent writes and retain queue, retry, failure, reconciliation, and recovery state.

5. **Engineering-memory extraction**
   - Extract reusable candidate lessons from worklogs, tests, and failure investigations.
   - Preserve scope, evidence, confidence, exceptions, affected systems, and correction history.
   - Keep the distinction `Worklog != Finding != Engineering Lesson != Operational Rule`.
   - Never promote one ambiguous event directly into a universal rule.

6. **Review boundary**
   - New engineering lessons remain candidates until reviewed.
   - Safety-critical or blocking rules require strong evidence and explicit user or engineering
     approval.
   - LAB_BOT may propose a design, procurement, maintenance, or SOP change, but it cannot approve
     its own mandatory rule.

## Human responsibilities

The human may record only the minimum useful facts:

- what object, project, or machine was involved;
- what was attempted or what happened;
- what was observed; and
- what should happen next, if known.

Missing structure is not a reason to reject a log. LAB_BOT should organize it while preserving the
original meaning and making every automatic change visible.

## Four-button templates (implemented V1)

The four native Notion database templates deliberately keep required input small. Each template
sets `Date=Today`, `Source=Manual`, `Status=Inbox`, `Sync Status=Local`, and its corresponding
`Type`.

### Common database fields

Minimum human input:

- `Title`: a short description of the work or event.
- `Project / System`: project, machine, subsystem, or `Unknown`.
- `Raw Note`: natural-language account of what happened.

Automatic fields:

- `Date`: creation date, editable when backfilling.
- `Type`: set by the selected button.
- `Status`: starts as `Inbox`.
- `Source`: `Manual`, `LAB_BOT`, or `Legacy Import`.
- `Sync Status`: `Local`, `Queued`, `Synced`, `Failed`, or `Conflict`.
- `Related`: links to related logs, parts, builds, files, or evidence.

### Problem

```text
## Quick record / 原始记录
What happened? What did you observe?

## Context and impact
Expected behavior, actual behavior, affected system, urgency, and safety impact.

## Attempts and results
Action -> observed result. Keep failed attempts.

## Diagnosis
Hypotheses, tests, confirmed cause, and supporting evidence.

## Resolution and verification
Fix applied, verification performed, current result, and remaining risk.

## Next action

## Candidate lesson
Reusable only after review.
```

### Experiment

```text
## Question / objective

## Baseline and setup
Equipment, version, material, environment, and starting condition.

## Variables
Changed variables and controlled variables.

## Procedure

## Results and measurements
Record raw results before interpretation.

## Interpretation
Separate observation from hypothesis.

## Conclusion and confidence

## Next experiment

## Candidate lesson
```

### Repair

```text
## Asset and fault
Asset ID or machine, symptom, and condition before work.

## Safety isolation
Power, pressure, heat, motion, chemical, or other precautions.

## Diagnosis and checks

## Parts, tools, and work performed

## As-built changes
Anything now different from the prior configuration.

## Verification / commissioning

## Remaining risk and next maintenance

## Candidate lesson
```

### Build

```text
## Intended result and design reference

## Materials / BOM / parts

## Build steps

## Deviations and substitutions
Record departures from the design and why.

## As-built state
Final configuration, firmware, settings, drawings, and photos.

## Tests / commissioning

## Result, open issues, and next action

## Candidate lesson
```

For all four templates, LAB_BOT may append a clearly labelled `LAB_BOT Enrichment` section and a
`Change Notice` when it modifies existing content. Empty sections may be left blank; the log should
not be rejected for incompleteness.

## Engineering Knowledge Candidates (implemented V1)

Use a separate derived collection, linked back to Forge Logs, rather than mixing reviewed rules
into raw journal entries.

Implemented fields:

- `Statement`: concise lesson or instruction.
- `Kind`: `Lesson`, `SOP Candidate`, `Warning`, `Preference`, or `Block`.
- `Scope`: affected machine, process, material, project, or environment.
- `Source Logs`: bidirectional relation to one or more Forge Logs.
- `Confidence`: `Low`, `Medium`, or `High`.
- `Status`: `Candidate`, `Under Review`, `Accepted`, `Rejected`, `Superseded`, or `Deprecated`.
- `Conditions / Exceptions`: when the lesson does not apply.
- `Decision Notes`, `Owner`, `Reviewer`, and `Review Date`.
- `Supersedes / Superseded By`: append-only correction history.

Enforced permissions:

- LAB_BOT may create and refine `Candidate` records.
- Only the user or an explicitly authorized reviewer may accept, reject, supersede, deprecate, or
  promote a record.
- `Block` and safety-critical rules require explicit approval and strong linked evidence.

## Approved data-ownership boundary

Use a federated source-of-truth boundary:

- Notion is canonical for the complete human-authored journal and page history.
- `lab.db` is canonical for structured operational state, synchronization metadata, derived
  findings, and reviewed engineering knowledge.
- Every derived record links back to its Notion source.
- Neither side silently overwrites the other; conflicts become visible review items.

This boundary keeps the full human record visible while allowing `lab.db` to be the complete
machine-readable operational source for LAB_BOT.

## V2 synchronization foundation

The additive `lab.db` synchronization schema owns four durable records:

- `forge_journal_pages`: Notion identity, observed and reconciled hashes, snapshot metadata, and
  `Local / Queued / Synced / Failed / Conflict` state;
- `forge_journal_sync_jobs`: pull/push operation, payload digest, base remote hash, idempotency key,
  bounded attempts, availability time, and worker lease;
- `forge_journal_sync_events`: append-only queue, lease, retry, failure, conflict, and recovery
  evidence; and
- `forge_journal_notifications`: durable user-notification outbox with its own bounded retry state.

Current contracts:

1. Every write requires a caller-supplied idempotency key. Reusing it with changed content fails
   closed.
2. A `PATCH_LOG` requires a visible change summary and reason before it may enter the queue.
3. The default delivery limit is three attempts. Retry delay starts at 60 seconds and doubles up to
   one hour. Terminal failures and their evidence are retained.
4. A concurrent Notion edit against a queued local base becomes `Conflict`; neither side is
   overwritten and manual resync is blocked until a human resolves the conflict.
5. Successful delivery requires the observed remote content hash. A queued or failed write cannot
   be reported as synchronized without that evidence.
6. Offline queueing, retry, terminal failure, conflict, and recovery create durable notification
   records. Delivery uses the latest eligible Forge route and falls back to the latest default
   Hermes route until Forge has its own conversation route.
7. LAB_BOT may write only `Candidate` knowledge. Acceptance, rejection, supersession, deprecation,
   and mandatory-rule promotion remain user or designated-reviewer actions.
8. `OpenClaw` is the logical connection name. Hermes may continue using its internal MCP server
   name `notion`; credentials must remain outside `lab.db`, source files, and sync payloads.

## Active V2 deployment

- The runner loads the internal Hermes `notion` connection at runtime; credentials are not copied
  into the Forge profile, `lab.db`, source files, or queue payloads.
- The limited-user Scheduled Task is an armed one-shot with no time/logon triggers, watchdog, or
  automatic failure retries. It consumes no resources while idle. A queued chat capture requests
  one execution; the runner drains writes and notices, reconciles both databases, then exits.
- Use `scripts/manage-forge-journal-runner.ps1 -Action stop` to pause delivery. New records remain
  queued while paused. `start` re-arms the task and drains the current queue once.
- The manager also supports `status`, `restart`, `run-once`, `acceptance`, and `uninstall`.
  `migrate` backs up the existing task XML and removes legacy scheduling.
  `run-once` explicitly performs one queue/notification/reconciliation cycle and exits.
- Reversible live acceptance appended `LAB_BOT Enrichment` and `Change Notice`, verified the remote
  content hash, removed the temporary blocks, restored the original body hash, and delivered the
  acceptance notice through Hermes.
- All twenty legacy logs reconcile to one canonical compact Notion page identity and remain
  `Synced`; the normalization migration preserves their job, event, and notification evidence.

## Remaining V2 product decision

- Define the user-facing conflict-resolution action that records either remote-wins or a reviewed
  replacement write. Conflict resolution will remain human-authorized.
