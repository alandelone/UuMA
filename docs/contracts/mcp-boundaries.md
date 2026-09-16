# MCP Boundaries

## UuMA Control MCP

Identity: Orchestrator only.

Operations: create/route/assign tasks, propose and approve graph operations, monitor Runs, request
cancellation, review Brainstormer structural-state proposals, and verify system health. Environment
must set `UUMA_AGENT_ID=orchestrator`.

## UuMA Worker MCP

Identity: one of `brainstormer`, `scholar`, `wisdom-oldman`, or `forge-lab-bot`.

Operations: register a safe Direct Run, read its own assignment, report progress, block its own Run,
submit a Result Contract, and propose graph operations. A Worker cannot approve graph changes,
inspect another Agent's assignment, coordinate Agents, use CopyCat, or control the computer.

`forge-lab-bot` additionally receives identity-gated hardware-lab tools through the same Worker MCP:

- read/review eSchematic component, BOM, circuit, ERC, recommendation, and render operations;
- explicitly approved eSchematic candidate commit;
- event-ledger inventory receiving, transitions, reconciliation, and balances;
- BOM shortage analysis plus Build/As-Built traceability;
- dry-run-first legacy inventory migration.
- dry-run/staged marketplace order-history import that never changes stock balances.

Other Worker identities are denied these tools even though they share the MCP server implementation.
The eSchematic catalog remains authoritative for component/design data; `lab.db` remains authoritative
for physical stock and Builds.

`brainstormer` additionally receives identity-gated discussion-state tools. It may propose atomic
JSON transactions, retrieve context, search topics, and safely commit checkpoint-only changes.
Project, topic, decision, and supersession changes remain pending until the Orchestrator reviews
them through Control MCP. Expected revisions reject stale updates.

## Scholar RSTV4 MCP

Identity: `scholar` only; separate from UuMA Worker MCP and backed by RSTV4's global canonical
`catalog.db`. Legacy project databases are migration inputs, not live authorities.

Scientific decisions remain proposals until RSTV4 consumes a single-use approval grant captured
from an exact user message by the Scholar or Orchestrator Hermes profile. Experiment execution is
plan-based, shell-free, and digest-pinned for scripts. Evidence content assessments are explicit
records; citation ID resolution alone never asserts scientific support or faithfulness. Specialist
terminal and arbitrary code-execution toolsets are removed so the RSTV4 boundary cannot be bypassed.
Scholar also has no general Gemini worker, preventing a second delegated experiment path outside
RSTV4.

The same boundary exposes `Field -> Topic -> Track -> Project`, immutable FieldKG Snapshots, and
independently tracked output manuscripts owned directly by Tracks. Snapshot adoption pins content
without importing approvals. Blueprint operations resolve to a Track;
manuscript compilation, citation checks, review, writing status, and submission history resolve to
one output manuscript. Catalog papers remain reference sources rather than output manuscripts.
The ScholarFieldKG OpenSPG/KAG project is a field-scoped, rebuildable query projection fed by an
outbox; it is never a second authority or an approval path.

The boundary also exposes Scholar's native PaperPool as semantic collection, paper, processing,
failure, usage, PDF registration, browser-handoff, Core-ranking, citation-neighborhood, migration,
and FieldKG-publication operations. Inputs are DOI/BibTeX or registered import files. Background
workers cannot control a browser; only the Orchestrator may claim and return a persistent CopyCat
handoff. A paper without an identity-verified PDF cannot expand references or create full-text
evidence. PaperPool ranking and generated Skeletons remain candidates, never scientific approval.

## Wisdom Knowledge MCP

Identity: `wisdom-oldman` and `orchestrator` only.

Both identities may ingest versioned sources/chunks, search/get/answer knowledge, inspect KAG
projection health and bounded graph neighborhoods, inspect history and diffs, register located
evidence, add candidate claims/entities/relations/schema modules, link chunks/evidence, manage
freshness records, record questions/gaps/conflicts, and propose patches. Only `orchestrator` may
apply, reject, or reverse a patch. Canonical changes therefore cannot be self-approved by
Wisdom-Oldman.

The adapter exposes semantic operations rather than SQLite or vendor-specific graph/vector APIs.
Its source of truth is the separate `wisdom.db`, with immutable hash-chained knowledge events and
mutable current projections. It never uses control-plane `uuma.db` or Hermes `state.db` as the
knowledge database. OpenSPG/KAG is a disposable projection fed by an audited outbox, never a second
authority and never a way to bypass candidate review.

## CopyCat MCP

Identity: external service, exposed only to the Orchestrator. It returns asynchronous execution
handles and never auto-executes recognized patterns. See `docs/copycat/handoff.md`.

## Existing xhs MCP

Remains attached only to the original Hermes/default Orchestrator profile. Specialist profile
deployment removes inherited `xhs` configuration.

## Authentication

The HTTP API uses per-identity bearer tokens with fixed roles: control, worker, and ingest. MCP stdio
servers additionally require a fixed `UUMA_AGENT_ID` environment identity. Tokens are generated in
the UuMA data directory and are not committed to this repository.
