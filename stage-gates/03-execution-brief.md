# Execution Brief

## 2026-09-08 specialist completion mission

The user approved the complete specialist repair plan. Implement trustworthy Scholar approval
provenance and approved experiment plans; evidence-content assessment; versioned profile/skill
deployment; real Wisdom KAG recovery checks; and Brainstormer project/topic reasoning state with
reviewed transactions. Keep `uuma.db`, `wisdom.db`, RSTV4 research databases, and Brainstormer JSON
state separate. Preserve existing data and profile customizations through backups and migrations.

Acceptance: focused authorization, experiment, evidence, deployment, KAG, and Brainstormer tests;
full UuMA and RSTV4 regressions; real profile/runtime checks; updated contracts and handoff.

## 2026-09-08 follow-up: executable session lifecycle

User requested automatic recording and enforced handoff. Add a repository session CLI backed by
the local control database. Record command starts, exit codes, file hashes, and versioned handoffs;
render progress automatically. Reject close when handoff is absent, edited, or predates work.
Preserve unfinished sessions after interruption. Validate real CLI failure codes in isolated Git
repositories. This is enforcement at the managed CLI boundary, not a global desktop stop hook.
Full shell output and arguments are intentionally excluded from the journal to avoid secret capture.

Acceptance: focused gate tests, source-file lint, full regression suite, and a real handoff/close
cycle for this implementation session.

## Deliverables

- [x] Keep root `AGENTS.md` under 100 lines and within 200-400 words.
- [x] Add `mission_status.json` as the sole stage and blocker record.
- [x] Add `init.sh` for environment setup, isolated databases, fixture staging, and optional serving.
- [x] Add discovery, design, execution, and verification gate documents.
- [x] Add session progress and handoff documents.
- [x] Add focused rules, repository memory, project/API indexes, and five deterministic fake records.
- [x] Validate JSON, shell syntax, guide size, initialization, lint baseline, and the full test suite.
- [x] Record verification evidence and advance `mission_status.json` to verification review.

On Windows, invoke `init.sh` with the installed Git Bash executable. Do not use the ambient
`python`: it currently resolves to Hermes' runtime, which intentionally lacks UuMA dev dependencies.
The `dev` extra is the authority for evaluator tools and must include both pytest and ruff.
The existing 81-error Ruff baseline is evidence, not scope for this context-only mission. Do not edit
application code to clear it; a future cleanup mission must reduce the count without changing behavior.

## Definition of done

Every startup decision can be made from the hot files and one linked warm file. Cold context has a
clear owner and loading trigger. Initialization is isolated and repeatable. Existing UuMA tests
pass. No application code, production database, or Hermes state is modified.

## Recovery instruction

On repeated failure, do not keep patching code. Read `repomemory/findings.md`, determine whether a
dependency/context is missing or the approved assertion is wrong, update the relevant rule or this
brief, preserve the diff, and rerun from this gate. Never reset an uncommitted repository.
# 2026-09-23 User-authorized Forge Journal lifecycle update

Forge Journal Runner uses explicit on-demand start/stop. The later chat-triggered contract below
refines installation to an inert, armed one-shot with zero time/logon triggers and zero automatic
failure retries; explicit Stop disables delivery. Migration backs up existing task XML and removes
the legacy watchdog. Explicit Start re-arms and drains once; run-once remains a foreground action.
No live synchronization or outbound notification is required to verify migration.
The mission remains at verification/pending_review; this does not approve a gate transition.

# 2026-09-23 User-authorized chat-triggered Forge Journal capture

Relevant Forge-Lab-Bot chat may capture a reversible journal entry when the user reports actual
lab work or explicitly asks to record it. Generic advice, hypothetical planning, sourcing
discussion, and meta-discussion do not qualify. One semantic tool must preserve the chat source,
create an idempotent local worklog, queue a `CREATE_LOG`, and request one runner execution.

The runner remains dormant with no time or logon triggers, watchdog, or automatic retry policy.
Its scheduled task is armed but consumes no resources between requests; explicit Stop disables it,
and Start re-arms it and drains the current queue once. A stopped task leaves new captures queued.
Direct chat registers a `REVERSIBLE` run for this bounded capture path. Raw queue/transport tools,
canonical approvals, purchases, inventory movement, and hardware actions remain blocked.

Acceptance: idempotent capture and wakeup tests, direct-chat guard tests, PowerShell lifecycle
contract, focused Forge regressions, deployed profile verification, and a live no-op-safe task
state check. Do not create a real journal entry or send a notification merely for acceptance.
# 2026-09-24 user-directed graph availability requirement

Scholar and Wisdom-Oldman must verify their own graph before knowledge work. Verify the
bridge, expected project/namespace, required schema and a read against graph storage; an
empty graph is distinct from an unavailable graph. Attempt bounded recovery of existing
services only; do not create missing projects, schemas or knowledge to satisfy the check.
On failure, block domain tools, unsupported answer delivery and completed-result submission,
while retaining progress/blocker reporting. This supersedes the prior permission for Wisdom
to deliver text-only degraded answers. New research Orbits must not start from failed KAG
preflight. Preserve the lower-level diagnostic fallback and traces for explicit inspection.
Mission remains at the current verification review gate.
