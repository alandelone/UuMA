# Hermes observability and performance evaluation

## Decision

Hermes emits backend-neutral observer events. The UuMA observability plugin maps those events to
OpenTelemetry spans, applies OpenInference semantic attributes, and exports OTLP directly to a
local Phoenix instance.

```text
Hermes observer hooks
        |
        v
uuma_observability plugin
  OpenTelemetry mechanism
  OpenInference semantics
        |
        | OTLP/HTTP
        v
Phoenix UI + Phoenix-owned SQLite volume
```

Phoenix does not own control-plane or knowledge state. `uuma.db` remains the UuMA control-plane
source of truth, `wisdom.db` remains Wisdom-Oldman's knowledge store, and Hermes `state.db` remains
untouched. Phoenix keeps only observability/evaluation data in its own Docker volume.

No standalone OpenTelemetry Collector is used in v0.1. Add one only when routing, buffering,
sampling, or multi-backend export actually requires it.

## Trace contract v0.1

One independent user goal is one trace. A conversation session groups multiple traces through the
`session.id` attribute; Session is an application concept, not an OpenTelemetry parent of traces.

| Hermes operation | Span name | OpenInference kind | Correlation |
| --- | --- | --- | --- |
| User goal / turn | `hermes.turn` | `AGENT` | `session_id + turn_id` |
| Provider attempt | `llm.call` | `LLM` | `api_request_id` |
| Tool execution | `tool.<name>` | `TOOL` | `tool_call_id` |
| Delegated work | `agent.delegate` | `AGENT` | `child_subagent_id` / `child_session_id` |
| Approval boundary | `approval.request` | `GUARDRAIL` | approval hook fields |

Provider retries are separate `llm.call` spans. Tool status is one of `ok`, `error`, `blocked`, or
`cancelled`. Child-agent turns are parented beneath `agent.delegate`, keeping delegated execution in
the original user-goal trace when Hermes executes the child in the same process.

The initial high-value attributes are:

- identity: session, turn, task, profile, provider request, and tool-call IDs;
- workload: message count, approximate input tokens, visible tool count, and request characters;
- efficiency: LLM/tool/delegation duration and token usage;
- trajectory: tool names, tool outcomes, provider attempts, retries, and handoffs;
- reliability: span status, error type/message, interruption, block, and cancellation.

## Privacy and failure behavior

Prompt, response, tool arguments, tool results, child goals, and child summaries are excluded by
default. Set `UUMA_OBSERVABILITY_CAPTURE_CONTENT=true` only for a controlled debugging session.
Captured values are bounded by `UUMA_OBSERVABILITY_MAX_CONTENT_CHARS` (default 8000). Hermes'
observer payloads are already sanitized, but this second opt-in prevents routine content retention.

The plugin is fail-open. Missing libraries, an unavailable Phoenix server, correlation misses, and
export failures cannot block an LLM call, tool call, approval, or final response.

## Local operation

Start Phoenix:

```powershell
.\scripts\start-phoenix.ps1
```

The launcher uses Docker when its engine is available. Otherwise it creates an isolated Python
runtime under `%LOCALAPPDATA%\UuMA\phoenix-runtime`; both modes keep Phoenix state separate from
UuMA and Hermes databases. Use `-Runtime docker` or `-Runtime python` to force one mode.

Install the current-user Windows sign-in task once to start Phoenix automatically after a reboot:

```powershell
.\scripts\install-phoenix-autostart.ps1
```

Remove that task with `install-phoenix-autostart.ps1 -Remove`. The scheduled task forces the Python
runtime so a Docker Desktop startup failure cannot prevent Phoenix from starting. It owns Phoenix
as a foreground process with no execution time limit, allowing the service to remain alive for the
entire signed-in Windows session.

Install/configure the observer in every Hermes profile:

```powershell
.\scripts\deploy-observability.ps1
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\hermes.exe" gateway restart
```

The deployment defaults are:

```text
UUMA_PHOENIX_ENABLED=true
UUMA_PHOENIX_ENDPOINT=http://127.0.0.1:6006/v1/traces
UUMA_PHOENIX_PROJECT=hermes
UUMA_OBSERVABILITY_CAPTURE_CONTENT=false
```

Open `http://127.0.0.1:6006`, run a Hermes task, then inspect the `hermes` project. The expected
shape is `hermes.turn -> llm.call / tool.* / agent.delegate`.

## Evaluation phases

Tracing answers how Hermes ran; it does not by itself decide whether the answer is correct. Build
the evaluation loop in this order:

1. Collect representative production traces and real failures.
2. Curate 20-50 golden tasks with explicit outcome checks and difficulty dimensions.
3. Run each task 3-5 times to measure pass@1, consistency, p50/p95 latency, tokens, tool calls,
   retries, and user correction rate.
4. Stress context length, visible-tool count, required steps, and irrelevant-noise level
   independently to find the degradation curve.
5. Compare full tools, tool routing, context compaction, and specialist delegation on the same
   dataset before changing the architecture.

The review boundary owns correctness labels and canonical architecture changes. Telemetry and
automated evaluators may propose findings; they do not silently rewrite control-plane or knowledge
state.
