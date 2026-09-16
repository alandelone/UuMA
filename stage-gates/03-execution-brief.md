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
