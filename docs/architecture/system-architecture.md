# UuMA System Architecture

Status: V1 implementation baseline  
Date: 2026-08-27

## System boundary

UuMA is the local control plane around Hermes. The original Hermes `default` profile is the
Orchestrator. Four isolated Hermes profiles provide specialist reasoning. CopyCat is an independent
MCP project and only exposes reviewed replay actions to the Orchestrator.

```text
User / client
      |
      v
Hermes default profile (Orchestrator)
      |
      +-- UuMA Control MCP -- append-only event store -- graph projections
      |
      +-- Hermes Kanban -- durable scheduling/execution projection
      |
      +-- Brainstormer -- Worker MCP
      +-- Scholar -- Worker MCP
      +-- Wisdom-Oldman -- Worker MCP + Knowledge MCP -- wisdom.db
      +-- 锻造Lab_Bot -- Worker MCP
      |
      +-- CopyCat MCP (external, optional)
      +-- ChatGPT Bridge MCP -- loopback account manager -- visible ChatGPT Web sessions
      +-- computer control
```

The Live Interface project is a client and remains outside this repository.

## Truth and projections

UuMA's immutable, hash-chained event stream is the control-plane record. Current tasks, Runs,
Agents, graph nodes, graph edges, artifacts, and external snapshots are disposable projections and
can be rebuilt. Hermes Kanban is the durable scheduling and execution projection, not a second
control-plane authority. Reconciliation records snapshots and drift rather than silently overwriting
UuMA state.

The graph store is one physical event/projection store with three logical graphs:

- Capability graph: Agents, tools, permissions, risk limits, and availability.
- Work graph: projects, topics, tasks, dependencies, decisions, and artifacts.
- Run graph: executions, attempts, heartbeats, blockers, results, and external Run references.

Graph mutations are event-driven. Node and edge changes may carry `expected_revision`; stale writes
fail. Existing knowledge is corrected by new `CORRECT`, `SUPERSEDE`, or `REVERSE` operations rather
than destructive history edits.

Wisdom-Oldman's domain knowledge is a separate source of truth. `wisdom.db` stores sources,
evidence, claims, evidence links, questions, qualified gaps, conflicts, patch proposals, and an
independent immutable hash chain. Its current SQLite/FTS5 projections are a Phase 1 backend behind
semantic Knowledge MCP tools; they can later be replaced or augmented without changing the skills.

## Routing

Routing is graph-first and semantic-second:

1. Reject permanently prohibited risk or capabilities.
2. Enforce Orchestrator-only tool boundaries.
3. Filter disabled Agents and missing capabilities/tools.
4. Enforce risk ceiling and explicit approval requirements.
5. Account for current workload.
6. Assign only when one Agent clearly qualifies.
7. Return ambiguity to the Orchestrator for semantic resolution or task splitting.

`requires_orchestrator` does not necessarily mean the Orchestrator should execute the whole task. A
contract that combines CopyCat with Scholar research, for example, must be split into coordinated
contracts rather than assigned to an Agent lacking one side of the capability set.

## Run lifecycle

```text
Task Contract
  -> approval when user-visible structure changes
  -> route
  -> assign
  -> Run registration
  -> heartbeat/progress
  -> block/retry/cancel/review
  -> Result Contract validation
  -> complete only when acceptance checks pass
```

Execution classes are `INTERACTIVE`, `BACKGROUND`, `SCHEDULED`, and `CONTINUOUS`. Automatic retry is
limited to idempotent or recoverable failures and at most three attempts. UI and other
non-idempotent actions are not automatically replayed as whole Runs. Human-review outcomes and
partial results enter `REVIEW`.

V1 can guarantee monitoring and cancellation only for work started through UuMA or Hermes
`/v1/runs`. Other direct Hermes channels are audit-only unless they register a Direct Run.

## Permission boundary

Only the Orchestrator receives Control MCP, computer control, CopyCat, and the existing `xhs` MCP.
Specialists receive Worker MCP and safe domain tools. Wisdom-Oldman and the Orchestrator additionally
receive Knowledge MCP, but only the Orchestrator can decide canonical patches. Direct specialist chats may perform safe
read-only or reversible in-domain work after Direct Run registration. Cross-Agent work, shared
structure, CopyCat, and computer UI work return to the Orchestrator.

The ChatGPT Bridge is a separate local service and tool boundary. Orchestrator, Brainstormer, and
Wisdom-Oldman may use chat, search, and deep research; Forge-Lab-Bot may use lab-related search.
Scholar and Yonc are excluded. The bridge owns browser interaction and account verification, while
agents see only request, continuation, status, result, cancellation, and thread-list operations.
Returned text remains external advice and cannot approve UuMA or Wisdom knowledge changes.

Risk classes:

- `READ_ONLY`: no durable external change.
- `REVERSIBLE`: bounded and recoverable change.
- `COMMITTING`: explicit user approval is mandatory.
- `PROHIBITED`: permanent deny, including purchases, deletion, external messages, credential or
  security changes, and dangerous hardware actions.

## Audit

The Hermes observer plugin records session, LLM/API, tool, approval, and subagent lifecycle hooks.
It writes every event to a local spool before best-effort relay to UuMA. Event IDs make replay
idempotent. UuMA stores user/Agent inputs and outputs exposed by Hermes hooks, tool calls/results,
route decisions, structured rationale, graph events, approvals, and versions.

This is an execution audit, not hidden chain-of-thought capture. Secrets are redacted at the plugin
and UuMA write boundaries. V1 audit and spool files are unencrypted and retained until manual
deletion, as explicitly chosen for this deployment. Residual risk remains: secrets embedded in
free-form text or unusual fields may evade redaction, so the data directory must be protected by the
local Windows account and should not be synced to an untrusted service.

The local HTTP health and audit endpoint listens on `127.0.0.1:8766` by default because port 8765
is already used by WSL Relay on the target machine.

## V1 exclusions

- No new monitoring web UI; use the Orchestrator, Hermes Dashboard, and structured reports.
- No CopyCat implementation code; only its handoff and MCP contract live here.
- No full domain database implementation for Brainstormer or Scholar; Wisdom-Oldman has a bounded
  Phase 1 knowledge backend and Forge-Lab-Bot has its existing lab backend.
- No Live Interface changes.
- No guarantee over unregistered direct Hermes sessions beyond audit capture.
