# Wisdom-Oldman hybrid KAG architecture

Status: implementation contract  
Backend baseline: OpenSPG/KAG v0.8.0

## Authority

```text
Questions / gaps / research budgets
                |
                v
wisdom.db canonical events and projections
                |
                +-- source snapshots and chunks
                +-- candidate/accepted claims, entities, and relations
                +-- schema modules, review patches, and freshness state
                |
                v
transactional projection outbox
                |
                v
OpenSPG/KAG projection
graph + chunk indexes + embeddings + hybrid solver
```

KAG never becomes a second authority. Deleting and rebuilding its project must not lose canonical
knowledge. Agent skills call only Knowledge MCP semantic operations and never OpenSPG REST, graph
DSL, KAG Python APIs, or the native KAG MCP.

## Construction

Files and public web content enter as a `SourceRecord` plus one or more immutable
`DocumentVersionRecord` objects. Parsers create located `ChunkRecord` objects. KAG extraction and
alignment produce candidate entities, relations, and claims through the UuMA adapter. Direct
duplicates and provenance-only maintenance may be merged automatically; claims, ontology/schema,
rules, supersession, and conflict resolution require human review.

Canonical chunks are projected as KAG-native `Chunk` nodes so the stock raw-chunk retriever can find
them. Accepted entities, relations, and claims are projected as governed knowledge nodes with the
same canonical IDs.
Chunk-to-knowledge links remain bidirectional so a graph result can recover original context and a
text result can recover normalized concepts and claims.

## Retrieval and answering

`AUTO` uses simple hybrid retrieval for a direct fact or single-hop entity lookup. It selects deep
logical-form planning for multi-hop, comparison, numerical, temporal, causal, and conflict
questions. The answer contract contains citations, applicable conditions, conflicts, a structured
operator/retrieval trace, projection watermark, satisfaction level, and worthwhile remaining gaps.
Structured traces are execution evidence, not hidden chain-of-thought.

Hermes direct-chat preflight uses `SIMPLE` KAG retrieval and may cold-start the runtime. The
Wisdom-Oldman profile raises only its plugin-hook callback cap to 450 seconds; Hermes' default
30-second cap would abandon a cold-start preflight before its Knowledge MCP call finished. More
complex questions can still request `AUTO`/`DEEP` in a normal Knowledge MCP tool call.

If KAG is unavailable on a Wisdom-Oldman answer, the runtime manager starts Docker Desktop if needed
and recovers only the named `uuma-wisdom-kag` compose project. Start/stop operations are serialized
across profiles. Pending canonical projection jobs are replayed before retrieval; a lagging projection
is not presented as current KAG knowledge. Cold starts can take several minutes. Recovery failure
returns `DEGRADED_KAG` and uses canonical FTS/evidence retrieval without dropping writes.

The local bridge counts `/project`, `/retrieve`, and `/extract` as activity. After 30 minutes with no
active KAG work (configurable with `UUMA_KAG_IDLE_SECONDS`; `0` disables auto-stop), it closes its
listener and runs `docker compose stop` for only `uuma-wisdom-kag`. Containers, volumes, downloaded
models, and `wisdom.db` remain on disk; this policy saves runtime memory/CPU rather than disk space.
It never quits Docker Desktop because other projects may depend on it. Health probes do not keep KAG
awake. Idle-stop failures are recorded in `.uuma-local/kag/bridge-lifecycle.log`; the next demand
can still recover the bridge. A stopped Windows `com.docker.service` alone does not prove the Docker
engine is unavailable; the runtime probes the engine directly. If the engine is unavailable and
Desktop cannot be started under the Hermes account, an administrator must restore it.

The Wisdom-Oldman Knowledge MCP config points `UUMA_KAG_SECRETS_FILE` at that profile's existing
`.env`. When the bridge is cold-started, the runtime reads an OpenAI/OpenRouter API key from that
file only if no key is already in its environment. The key is passed to the bridge process without
being copied into Hermes YAML, the compose file, logs, or `wisdom.db`. A missing key causes an
explicit KAG fallback rather than a misleading successful retrieval.

## Runtime bootstrap

The supported Windows bootstrap is `deploy/kag/bootstrap.ps1`. It downloads the official OpenSPG
compose definition, pins the KAG toolkit to v0.8.0, creates an isolated bridge environment, downloads
local BGE-M3 unless skipped, restores the `Uuma` project, commits the universal schema, and starts the
localhost-only bridge. It discovers model/provider settings and the OpenRouter key from the Hermes
profile without printing or copying the secret. If an auto-discovered localhost inference endpoint
is not listening, bootstrap uses the default Hermes provider; explicit CLI settings are never
overridden. Re-run `scripts/deploy-hermes.ps1` afterward so Orchestrator and Wisdom-Oldman receive the
runtime paths, including the recovered OpenSPG project ID.

The bridge uses the official BGE-M3 ONNX export on CPU by default, returning normalized 1024-dimension
embeddings while avoiding contention with resident GPU models. Set `UUMA_BGE_BACKEND=flagembedding`
and `UUMA_BGE_DEVICE=cuda:0` to opt into the CUDA/FP16 loader when sufficient dedicated VRAM is
available. `UUMA_BGE_MAX_LENGTH` and `UUMA_BGE_ONNX_THREADS` bound embedding resource use.

OpenSPG validates uploaded project metadata inside its stock server image, which does not contain the
host FlagEmbedding runtime. Bootstrap therefore uploads a secret-free mock LLM/vectorizer only for
server-side project validation. The operative localhost bridge configuration always uses the real
Hermes model provider and local BGE-M3 embeddings.

The bridge environment deliberately retains KAG v0.8's `mcp==1.6.0`; the UuMA/Hermes environment
retains `mcp==1.26.0`. They communicate over the semantic HTTP bridge, so neither runtime is downgraded
or dependency-resolved against the other.

The upstream compose file is intentionally kept in `.uuma-local/kag` rather than copied into source
control. Runtime recovery targets only the compose project name `uuma-wisdom-kag`, starts the bridge
with its isolated Python/config, and never mutates canonical knowledge to repair projection state.
Bootstrap bounds the OpenSPG JVM at 4 GB and the Neo4j heap/page cache at 2 GB/512 MB so their cold
start fits under a typical 8 GB Docker Desktop WSL limit. It also seeds Neo4j's configuration into a
host-mounted directory: an abrupt WSL termination cannot leave the container's writable config
layer with sparse NUL bytes. Compose uses `unless-stopped`, so an idle stop remains stopped across a
later Docker Desktop restart while an explicit on-demand `compose up` still recovers all services.

## Research and freshness

Research tiers are:

| Tier | Active time | Sources | Model tokens |
| --- | ---: | ---: | ---: |
| Quick | 10 minutes | 10 | 50,000 |
| Standard | 60 minutes | 30 | 250,000 |
| Deep | 6 hours | 100 | 1,000,000 |

Standard is the default. A run pauses as `BUDGET_EXHAUSTED` when any limit is reached.

Default re-verification intervals are one day for high-volatility web knowledge, 30 days for SOTA,
software, market, and product information, 90 days for standards and ordinary specifications, and
365 days for stable datasheets, manuals, and primary documents. A new content digest creates a new
document version and marks dependent knowledge for review rather than overwriting it.
