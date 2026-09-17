# UuMA Control Pipeline — Real vs. Designed

> Snapshot: 2026-09-16 14:07 CST

## Remediation Applied (2026-09-16)

- The Orchestrator SOUL now requires `create_task -> route_task -> assign_task` before every
  specialist delegation, with one Task Contract per delegated child.
- The `uuma_control_guard` Hermes plugin enforces that sequence at `pre_tool_call`; it blocks
  `delegate_task` and specialist Worker MCP spawns unless the current session has enough assigned
  UuMA tasks. Live `list`, `steer`, and `stop` actions remain available.
- The guard calls `uuma-control/system_health` at the start of each turn, throttled to five minutes
  per session. Hermes' supported stdio recovery path transparently respawns a dead MCP subprocess
  on that call; failed health leaves delegation fail-closed and injects recovery guidance.
- Control-profile context is bounded with `threshold_tokens: 48000`, deterministic tool-result
  pruning at 36,000 tokens, and idle compaction after 30 minutes. Legacy `session_reset` settings
  were not used because current Hermes ignores them for gateway conversations.
- Deployment now preserves Kanban toolset enablement and writes absolute interpreter paths so MCP
  startup is independent of the gateway working directory.

Verification: 110 UuMA tests passed; the deployed gateway restarted cleanly; `uuma-control`
discovered all 15 tools; a live `system_health` MCP call returned `status: ok` and a valid event
chain. Task/run counts remain zero until the first post-remediation specialist delegation.

## The Architecture Promise (system-architecture.md)

```
Hermes default profile (Orchestrator)
      |
      +-- UuMA Control MCP -- append-only event store -- graph projections
      |
      +-- Hermes Kanban -- durable scheduling/execution projection
      |
      +-- Brainstormer / Scholar / Wisdom-Oldman / 锻造Lab_Bot -- Worker MCP
```

The spec says:
> "UuMA's immutable, hash-chained event stream is the control-plane record."
> "Hermes Kanban is the durable scheduling and execution projection, not a second control-plane authority."

## What Actually Happens (Evidence)

### UuMA Control MCP — Registered but Never Called

| Signal | Finding |
|---|---|
| MCP tools registered per session | ✅ 19 tools registered every restart |
| `mcp__uuma_control__*` spans in Phoenix | **0** — never called |
| `mcp__uuma_control__*` completions in agent.log | **0** |
| `mcp__uuma_control` keepalive failures | ⚠️ `ClosedResourceError` on 2026-09-16 09:12 |
| UuMA `runs` table rows | **0** |
| UuMA `tasks` table rows | **0** |
| UuMA `graph_nodes` rows | **0** |
| UuMA `graph_edges` rows | **0** |
| UuMA `events` rows | **5** — only the 5 initial `AGENT_REGISTERED` bootstrap events from 2026-09-11 |

### UuMA Spool — Audit Flowing, Control Not

The spool **is** collecting events: 3,157 files in `spool/hermes/`. But these are all **observer
hook events** (session_reset, pre_llm_call, post_tool_call, etc.) written by the `uuma_audit`
plugin — **not** Control MCP operations. They are telemetry, not control-plane state.

### Hermes Kanban — Also Empty

`kanban.db` has 0 tasks. The dispatcher runs but has nothing to dispatch. Kanban was also never
called, for the same reason the Control MCP wasn't: the `kanban` toolset was missing from
`platform_toolsets` (fixed today).

### What the Orchestrator Actually Does

Phoenix confirms every Telegram turn follows this pattern:

```
hermes.turn (orchestrator)
  └── llm.call         ← model decides what to do
  └── tool.delegate_task  ← routes to specialist
  └── llm.call         ← synthesizes result
```

Zero `tool.mcp__uuma_control__*` spans. Zero `tool.kanban_*` spans.
The orchestrator has been operating as a **pure RPC relay** — no durable state, no graph, no runs.

---

## Diagnosis: The Three-Layer Gap

```
DESIGNED:                          ACTUAL:
─────────────────────────          ─────────────────────────
User message                       User message
    ↓                                  ↓
Orchestrator                       Orchestrator
    ↓                                  ↓
mcp__uuma_control__create_task     [skipped — model never chooses it]
    ↓                                  ↓
route_task → assign_task           delegate_task("scholar", ...)
    ↓                                  ↓
Hermes Kanban dispatch             Inline RPC response
    ↓                                  ↓
event_store → graph projection     [nothing persisted]
    ↓
Result Contract validation
```

### Why the Model Skips UuMA Control

The orchestrator (default profile) has 19 UuMA Control tools + 34 total tools available per turn.
The model sees them all but:

1. **No forcing instruction** — SOUL.md says *"Use the UuMA Control MCP for shared tasks"* but
   this is advisory, not enforced by tool guards or a required pre-flight. The model interprets
   `delegate_task` as a sufficient shortcut for most requests.

2. **`delegate_task` is faster and simpler** — it's one call; `mcp__uuma_control__create_task` +
   `route_task` + `assign_task` is three sequential calls before any work starts.

3. **No negative feedback** — the model has never been told "you skipped UuMA, that was wrong."
   Every delegation completes and returns a result, so the model has no signal to change.

4. **Context pressure** — at 135k+ tokens per turn (from Phoenix), the model is under heavy
   compression. Minimal-call paths dominate.

5. **MCP keepalive failures** — `uuma-control` entered `degraded` state on 2026-09-16 09:12,
   meaning the server was temporarily unreachable. The model may have silently learned to avoid it.

---

## What IS Working

| Layer | Status |
|---|---|
| UuMA `agents` table (5 agents registered) | ✅ Bootstrapped correctly |
| `uuma_audit` plugin spool (3,157 events) | ✅ Audit telemetry flows |
| Phoenix tracing (turns, LLM, tools) | ✅ Full observability |
| MCP server registration (19 tools) | ✅ Registers on startup |
| Hash-chained event schema | ✅ Correct (5 events, valid chain) |
| Kanban toolset (fixed today) | ✅ Now enabled |

## What Is Broken / Not Activated

| Layer | Status | Root Cause |
|---|---|---|
| `mcp__uuma_control__create_task` ever called | ❌ Never | Model choice — not forced |
| `mcp__uuma_control__route_task` ever called | ❌ Never | Same |
| UuMA `runs` / `tasks` / `graph` populated | ❌ Empty | Upstream never calls |
| Kanban tasks created | ❌ Empty | `kanban` toolset was missing (fixed) |
| Event store as control-plane record | ❌ Audit-only | Control MCP never invoked |
| Graph projections | ❌ 0 nodes, 0 edges | No operations ever issued |

---

## Fixes Needed

### 1. Force UuMA pre-flight in SOUL.md (high impact, immediate)

Add a hard rule:
```
BEFORE calling delegate_task or any specialist tool for multi-step or
cross-agent work, you MUST first call mcp__uuma_control__create_task
and mcp__uuma_control__route_task. Skipping this is a policy violation.
```

### 2. Add a tool guard / check_fn (architectural fix)

Wrap `delegate_task` so it checks whether a UuMA task exists for the current
context. If not, it either rejects the call or auto-creates one first.
This makes the control plane mandatory, not advisory.

### 3. Fix MCP keepalive reliability

The `uuma-control` server went into `degraded` state on 2026-09-16 09:12 with
`ClosedResourceError`. This is likely the UuMA MCP server crashing silently.
Add a health check and auto-restart in `config.yaml`:
```yaml
mcp_servers:
  uuma-control:
    idle_timeout_seconds: 0   # already set — keep persistent
    # Add restart-on-failure if supported
```

### 4. Shrink context to reduce model pressure

At 135k tokens/turn the model is compressing heavily. Reduce `memory_char_limit`
or add a periodic session reset for the orchestrator to keep context lean enough
that multi-call UuMA sequences feel affordable to the model.

---

## Summary

> **The UuMA control pipeline is architecturally complete but behaviorally bypassed.**
> The orchestrator has all 19 Control MCP tools available every turn and has never called
> a single one in production. Every specialist job runs as a raw `delegate_task` RPC
> with no durable state, no graph record, and no run lifecycle.
>
> You don't "feel it" because it isn't running. The audit spool is flowing (3,157 events)
> and Phoenix traces are clean — but those are observer hooks, not control-plane operations.
> The control plane is switched on but the orchestrator always takes the shorter path.

## 2026-09-16 remediation note

The diagnosis above is historical evidence, not the current deployment state. The default
Orchestrator now has a delegation guard. Brainstormer and Wisdom-Oldman now have isolated Telegram
route IDs, profile-scoped audit/Phoenix identity, automatic per-turn Worker Direct Run registration,
semantic domain preflight, and terminal result submission. Local CLI smoke tests produced completed
specialist runs and specialist-attributed Phoenix spans. Wisdom's KAG runtime was offline during the
test, so its Knowledge MCP used a traceable degraded canonical fallback. The next real Telegram
message to each specialist is still needed to verify inbound routing and the fresh system prompt.

The same guard was subsequently deployed to Scholar and Forge Lab Bot. Local CLI turns confirmed
their Worker Direct Runs and RSTV4 PaperPool/lab inventory preflight, with completed runs and
correctly attributed audit/Phoenix events. Telegram inbound acceptance remains open for all four.
