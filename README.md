# UuMA

UuMA is a local-first control plane for a Hermes multi-agent system. The
original Hermes profile acts as the Orchestrator. Four specialized profiles
provide bounded domain work:

- Brainstormer
- Scholar
- Wisdom-Oldman
- 锻造Lab_Bot (`forge-lab-bot` on disk)

CopyCat is an external MCP service, not an Agent. Only the Orchestrator may
discover or execute its reviewed actions.

## V1 architecture

```text
User / client
      |
      v
Hermes Orchestrator ---- Control MCP ---- UuMA Runtime
      |                                      |
      +---- Hermes Kanban execution view ----+
      |
      +---- specialized Hermes profiles ---- Worker MCP
      |          |
      |          +---- Wisdom-Oldman ---- Knowledge MCP ---- wisdom.db
      |
      +---- CopyCat MCP (external, optional)
```

The append-only UuMA event log is the control-plane source of truth. Hermes
Kanban remains the durable scheduler and execution projection. Current graph,
task, and run tables can always be rebuilt from UuMA events.

## Development

Repository work uses the executable session journal described in
[`rules/session-lifecycle.md`](rules/session-lifecycle.md). With the project Python, run
`python -m uuma.session start` (or `resume`), execute commands through
`python -m uuma.session run -- COMMAND ARGS`, then supply a structured `handoff` and run `close`.
The close gate rejects missing or stale handoffs and returns exit code 2. Command outcomes and
handoff versions persist in `.uuma-local/uuma.db`; `active-session/progress.md` is rendered from them.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

Runtime data defaults to `%LOCALAPPDATA%\UuMA`. Override it with
`UUMA_DATA_DIR`. See `docs/architecture/system-architecture.md` for boundaries
and invariants.

## Local Hermes deployment

The deployment script creates the four specialist profiles by cloning the current `default`
profile, preserves its model/provider credentials, installs the correct UuMA MCP boundary, removes
inherited `xhs` access from specialists, disables specialist computer/terminal/delegation toolsets,
removes unrelated cloned credentials, installs the audit observer, and creates the `uuma-control`
Kanban board. Managed SOUL sections are updated without overwriting unrelated local customization;
conflicts are preserved as `.uuma-pending` files with recoverable backups.

Brainstormer receives four discussion-continuity skills and identity-gated persistent JSON state
tools. Scholar receives the isolated sibling RSTV4 research OS, trusted user-message approvals,
approved experiment-plan execution, and content-level evidence assessment. For `forge-lab-bot`,
deployment installs all eleven eSchematic and lab lifecycle skills, configures the sibling
`eSchematic_skillset`, and exposes the event-ledger `lab.db` tools.

```powershell
.\scripts\deploy-hermes.ps1
```

The default eSchematic location is the sibling folder
`..\eSchematic_skillset`; override `-ESchematicRoot` or `-ESchematicPython` when needed. Lab runtime
data remains outside both repositories under `%LOCALAPPDATA%\UuMA\forge-lab-bot`.

For `wisdom-oldman`, deployment installs six focused knowledge-lifecycle skills and the semantic
Knowledge MCP. Durable sources, documents/chunks, evidence, claims, entities, relations, schema
modules, questions, gaps, conflicts, proposals, and their hash-chained history live in
`%LOCALAPPDATA%\UuMA\wisdom.db`. OpenSPG/KAG v0.8.0 is a rebuildable graph/vector/reasoning
projection; text retrieval is explicitly marked degraded when that runtime is unavailable. The
Orchestrator can review/apply, reject, or reverse proposed canonical changes; Wisdom-Oldman cannot
self-approve them.

Question Orbit background research is opt-in. Enabling it installs a hidden per-user Scheduled Task,
backs up `wisdom.db`, and activates the governed runner, safe public-source discovery, usage ledger,
cycle recovery, and Hermes notification outbox. Removing the task preserves all Orbit history.

Prepare the real OpenSPG/KAG runtime, inject its recovered project/model settings into Hermes, and
reload the gateway with:

```powershell
.\deploy\kag\bootstrap.ps1
.\scripts\deploy-hermes.ps1 -QuestionOrbitEnabled $true
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\hermes.exe" gateway restart
```

To stop and remove only the background runner while preserving knowledge and research state:

```powershell
.\scripts\install-orbit-runner.ps1 -Uninstall
```

## ChatGPT Web consultations

The local ChatGPT Web Bridge exposes chat, search, and deep-research consultations to the
Orchestrator, Brainstormer, and Wisdom-Oldman. Forge-Lab-Bot receives lab-related search only.
Scholar and Yonc are excluded at profile, guard, MCP, and service boundaries. Accounts and browser
login remain human-controlled through a loopback dashboard; consultation requests are durable,
idempotent, run-bound, and isolated by agent and project conversation.

```powershell
.\scripts\install-chatgpt-bridge.ps1 -StartNow
```

See [`docs/agents/chatgpt-web-bridge.md`](docs/agents/chatgpt-web-bridge.md) for onboarding,
permissions, recovery, and rollback.

The default embedding path is the official local BGE-M3 ONNX export (1024 dimensions, CPU), leaving
an already occupied GPU undisturbed. KAG construction outputs remain candidates until Orchestrator
or user review accepts a patch.

It appends the Orchestrator policy to the existing default `SOUL.md` once and makes a backup before
doing so. Existing specialist SOUL files are not overwritten on later deployments.

Start the optional local HTTP control/audit endpoint with:

```powershell
.\scripts\start-uuma.ps1
```

Then restart the Hermes gateway so it reloads the profile MCP and observer configuration. MCP stdio
control remains usable without the HTTP process; observer events remain safely spooled and can be
replayed later with:

```powershell
$env:PYTHONPATH = ".\src"
python -m uuma ingest-spool
```

## Hermes observability

Hermes can export one trace per user goal to a local Phoenix instance through OpenTelemetry and
OpenInference. Prompt and tool content are excluded by default; structural trajectory, latency,
token usage, retries, tool outcomes, and delegation are retained.

```powershell
.\scripts\start-phoenix.ps1
.\scripts\install-phoenix-autostart.ps1
.\scripts\deploy-observability.ps1
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\hermes.exe" gateway restart
```

Open `http://127.0.0.1:6006` and select the `hermes` project. See
[`docs/observability/hermes-performance.md`](docs/observability/hermes-performance.md) for the trace
schema, privacy controls, and the golden-task/stress-test evaluation path.

## Design records

- [`docs/architecture/system-architecture.md`](docs/architecture/system-architecture.md)
- [`docs/architecture/graph-engineering.md`](docs/architecture/graph-engineering.md)
- [`docs/contracts/mcp-boundaries.md`](docs/contracts/mcp-boundaries.md)
- [`docs/observability/hermes-performance.md`](docs/observability/hermes-performance.md)
- [`docs/copycat/handoff.md`](docs/copycat/handoff.md)
- [`docs/agents/`](docs/agents/)
