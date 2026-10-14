# Wisdom-Oldman conversation and research recovery — 2026-10-02

## User contract

The reported message `how is the progress?` must read durable research status,
not propose a topic named after the message. Normal conversation, topic listing,
and continue/pause/stop must work across Telegram session resets. New topics still
require explicit user consent. Existing research keeps its ID, document links,
history and cumulative budget. Research answers continue to require the managed
knowledge graph; operational status reads do not require a live graph.

## Confirmed faults and repairs

1. The progress detector omitted the user's exact wording. The output guard then
   treated the question mark as permission to propose research, overriding the
   stored answer with an approval request. Intake now runs before the graph gate,
   distinguishes operational intents, clears stale proposals, and renders actual
   task status, reason, document version, gaps and links. Operational finalization
   records PARTIAL instead of asserting that graph research completed.
2. Windows packaged-app path redirection produced two physically different
   `wisdom.db` files. The view and runner used the original knowledge store while
   Hermes used the unredirected store. A separate `UUMA_KNOWLEDGE_DATA_DIR` now pins
   both Wisdom MCP servers to the original physical store; control data paths are
   unchanged. Deployment resolves an existing database file, not just its directory.
3. The runner passed a database path to `ControlPlane`, whose constructor requires
   `Settings`, preventing startup. It now receives settings and uses the document
   service's port and token location consistently.
4. The graph bridge's shallow health could stay ready while Docker's WSL engine
   had stopped. Real project/schema/storage reads detected the outage. Docker logs
   recorded an abrupt WSL exit. Existing services were restarted without resetting
   any container, volume, database, project or schema. Memory allocation failures
   were also reproduced while loading the FP32 embedding model. The bridge now
   shares one ONNX encoder per model path, serializes bounded batches, and avoids
   packed/optimized copies of the weights. FP32, 1024 dimensions and the 2048-token
   input limit are retained. Readiness timeouts and graph HTTP failures use bounded
   five-minute retries; persistent failure remains visible as BLOCKED.

## Data recovery and deployment

- Preserved original topic `topic_07a8574b5d504d34a5483407c2a88400` and research task
  `orbit_9ac4d099873b82f8f5a730cf07792419`.
- Backed up both stores before recovery under the canonical store's
  `backups/wisdom-conversation-recovery-20261001-233206/`. Both backups passed SQLite
  integrity checks. SHA-256: canonical
  `18148069784ea760d684fe337a01a2ef85815bef4a1b13694971f0b2953d2980`, external
  `cd33e9021de9955c6cb5cbb6367ebf840b8dc6357aad3eddd9d6ee7e2b915b5c`.
- Added a reviewer-audited, reversible document-link recovery for the approved
  duplicate `topic_71aa2ce5c6444bb08d54e18299295aae`. Its link resolves to the
  original topic. The external task was stopped with a recorded reason. Its full
  original store/history remains backed up. No external claims were imported,
  merged or approved by this repair.
- Rebound the existing Telegram route to the original topic, then resumed the
  existing task without resetting budget or creating another research question.
- Deployed the guard, role instructions and pinned knowledge-store environment to
  the Wisdom profile, with profile backups dated `20261001-233307` and
  `20261002-065020`. The thinking model was retained. Other profiles and unrelated
  repository edits were preserved.
- Recovered document, gateway, background runner and existing graph services.
  Temporary diagnostic/recovery tasks are removed after completion. Access remains
  loopback-only with the existing independent read-only token; token values are
  intentionally absent from this report.

## Verification evidence

| Check | Observed result |
| --- | --- |
| Reported wording and conversation reset | Deployed guard plus real MCP stdio replay classified status, removed a stale proposal, returned the original task/document and all-topics links; no graph research or new topic was requested. |
| Controls and permissions | Tests cover repeated continue, pause/stop, existing-task binding, unchanged cumulative budget, stopped/exhausted task protection, reviewer-only link recovery and compensating reversal. |
| Provenance and history | Canonical event chain valid; original IDs, prior versions and candidate permissions retained. |
| Pages | All-topics, original document and recovered duplicate link return HTTP 200. Both topic pages contain the stable overview anchor and return-to-all-topics link. |
| Real research | After the startup/data repair, four real background cycles advanced the original document from version 35 to 39. After the final runtime repair, another real cycle completed and version 41 had nine sections; the next cycle was RUNNING. Sources increased from 12 to 15. Unsupported recovery-time and aeroponics parameters remain identified as evidence gaps. |
| Actual Telegram outbound | Persistent notification `notice_697205dcea6c42468c8334ec13afd8b7` was SENT on attempt 1, with no error, at 2026-10-02 06:58:34 UTC. Recipient reading is unobserved. |
| Fresh inbound acceptance | No new real Telegram inbound message after deployment was observed. The local deployed guard/MCP replay is recorded separately and is not called end-to-end Telegram acceptance. |
| Regression | Final source: 392 tests and 5 subtests passed; two existing dependency deprecation warnings. Ruff and the scoped whitespace check passed. The embedding adjustment also passed the 15 focused lifecycle/memory tests. |

Graph recovery at 07:24 and 07:29 UTC verified the existing Uuma project, schema
and actual storage read. An embedding allocation failure at 07:25 UTC was repaired
without reducing precision or context length. The subsequent real `/retrieve`
returned HTTP 200. The original task completed its retry cycle at 07:32:09 UTC;
the 07:32:42 snapshot showed ACTIVE / RUNNING, document version 41, nine sections
and a valid event chain. Cumulative usage was 2422.64 active seconds, 15 sources,
48490 model tokens and 193 searches over 21 completed cycles. Existing budget
limits remain enforced; future resource availability is not inferred from this
successful snapshot.

At 07:35:54 UTC, the next cycle had also completed. Document version 42 retained
nine sections and the task was PAUSED for source saturation: all current open
questions were checked without finding new verifiable, directly relevant public
evidence. The recorded reason explains this and preserves the gaps. Usage was
2519.64 seconds, 15 sources, 48914 tokens and 213 searches over 22 completed
cycles; the budget was not exhausted. This is not recorded as research completion
or a graph outage. Explicit continue can retry the same task within the remaining
budget; no automatic budget increase is applied.

Local ignored evidence includes `wisdom-runtime-diagnostic.json`,
`wisdom-split-store-repair.json`, `wisdom-conversation-deployment.json`,
`wisdom-live-conversation-probe.json`, `wisdom-ensure-graph.json`,
`wisdom-inspect-retrieval.json` and `wisdom-final-runtime-check.json`.

The ONNX configuration follows the runtime's documented
[prepacking option](https://github.com/microsoft/onnxruntime/blob/main/include/onnxruntime/core/session/onnxruntime_session_options_config_keys.h)
and [graph optimization settings](https://onnxruntime.ai/docs/performance/model-optimizations/graph-optimizations.html).
The verification gate remains pending review.

## Read-only discovery-path audit after the user's pause objection

The user interrupted the pause-rule investigation to ask how many discovery paths
are currently used. Loading the actual Wisdom profile and reading October usage
confirmed five configured external entries: OpenAlex, Crossref, DDGS academic-site
search, DDGS general search and the ChatGPT bridge. The two DDGS entries use the
same search tool, with the academic entry adding `site:edu` or `site:edu.cn`.

| Entry | October recorded calls | Returned discovery results |
| --- | ---: | ---: |
| OpenAlex | 24 | 98 |
| Crossref | 23 | 115 |
| DDGS academic sites | 17 | 85 |
| DDGS general web | 17 | 159 |
| ChatGPT bridge | 24 | 0 |

These are all-task monthly records, before deduplication and relevance checks;
they are not counts of verified evidence or unique sources. A recorded provider
call can also return empty before making an external request. ChatGPT is enabled
in configuration, but these records do not establish a working search delivery.
Brave has no configured key and feed/sitemap seeds are empty, so both optional
entries are absent. Canonical citations and the existing KG are additional local
reuse paths, not external discovery services. No new live searches were submitted.
Evidence is retained in ignored `.uuma-local/wisdom-evidence-paths.json`.

The user's objection to automatic source-saturation pause remains open. No pause
logic or live task was changed during this read-only clarification. Failure to
find new evidence through these configured paths does not establish that all
possible sources or research approaches have been exhausted.

## ChatGPT consultation and Deep Research audit

At 22:56 Malaysia time on October 2, a native read-only audit inspected both
physical control stores, avoiding the packaged-app redirect. Both have zero
`wisdom-oldman` ChatGPT request records across all modes. This establishes no
recorded bridge submission for ordinary consultation, search or Deep Research;
the 24 discovery-provider calls are not evidence of 24 external submissions.

The live unredirected bridge account is enabled and READY, with stored verified
capabilities `chat`, `search` and `deep_research`. The packaged control copy still
reports AUTH_REQUIRED with no capabilities. These are physically different control
stores; this audit did not merge or change them. The live bridge health reports a
healthy worker and no last error. Capability availability is distinct from a
completed consultation or successful research delivery.

Wisdom's deployed profile includes the ChatGPT MCP server. Its request/continue
tools support ordinary consultation and follow-up, while the browser bridge has
Deep Research mode selection. However the automatic discovery mode is currently
`search`. The automatic adapter only turns citations into discoverable source links
with a short answer snippet; it does not consume the complete report as a sustained
consultation workflow. Wisdom's DEEP budget tier does not select ChatGPT's
`deep_research` mode.

The user's expected integration is direct consultation plus Deep Research and
follow-up, with findings, source locations and uncertainty contributing to the
same topic document under the existing candidate/reviewer boundary. That complete
workflow is not established by the current code/configuration or request history.
No new consultations, external messages, browser actions or mode changes were
submitted in this audit. Ignored native/codex audit receipts are retained; the
temporary read-only audit task was removed after completion.

## Research-tool architecture update

The user subsequently clarified that ChatGPT should execute bounded work as Wisdom's tool/worker,
with Wisdom owning the topic and deciding the next task. The accepted contract is now documented in
`docs/architecture/agent-research-tools.md` and linked from the system architecture, Wisdom design,
bridge contract and Orbit deployment plan. It covers extensible tool capabilities, mode choice,
durable request/report handling, result/failure distinctions, meaningful continuation and chat
answers explaining causes and next actions. An empty discovery round is not sufficient to pause.

Updated Wisdom SOUL and the consultation, evidence, Orbit and investigation instructions. Reviewed
the exact differences against the existing Wisdom profile, backed up all five original instruction
files before any replacement, then verified all deployed files against source SHA-256 values.
Receipt: ignored `.uuma-local/wisdom-tool-instructions-deployment.json`. Other profiles, configuration,
model, credentials, databases and shared running services were not changed. File synchronization
does not establish that an existing conversation has reloaded those instructions.

This is an architecture and instruction delivery. Runtime automatic tool/mode scheduling, durable
Deep Research report intake, complete attempt/status queries and the premature source-saturation
pause repair remain unimplemented here. No new ChatGPT task or Telegram message was submitted, and
no real Telegram behavior is marked passed. Mission remains verification/pending_review.

Verification of this delivery: all four changed skills pass the unchanged bundled skill validator
in an isolated PyYAML environment; bridge/profile/allowlist contracts pass 48 tests. Full UuMA
regression passes 392 tests and five subtests with two existing dependency warnings. Diff whitespace
checks pass. These checks validate the architecture/instruction package and existing contracts;
they do not establish automatic Deep Research or a repaired live Orbit pause path.
