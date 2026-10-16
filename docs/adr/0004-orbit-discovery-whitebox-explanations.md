# White-Box Explanations and Outcome Taxonomy for Autonomous Orbit Discovery

To eliminate the opacity where Orbit cycles conflate empty search results, authentication failures, rate limits, and network errors into a single "zero-source" pause, we introduce a dual-level white-box explanation model with a canonical six-state Discovery Outcome taxonomy (`SUCCESS`, `NO_MATCH`, `TRANSIENT_FAILURE`, `AUTH_REQUIRED`, `BUDGET_REACHED`, `SKIPPED`). Discovery attempts are persisted inside `orbit_cycles.record_json` and audited via append-only `knowledge_events` in `wisdom.db`, preserving the strict database separation boundary without requiring schema migrations. Untried paths are dynamically computed against the configured agent capability catalog (`Configured & Authorized - Attempted - Blocked`), surfacing structured explanations across user dialogue, topic documents, and the Observatory timeline.

## Provider Protocol & Intra-cycle Fallback

`DiscoveryResponse` carries `outcome`, `error_detail`, and `duration_ms`. Providers self-classify operational status (e.g., missing credentials produce `AUTH_REQUIRED` rather than an empty result). When an attempt yields `NO_MATCH` or non-fatal failure, `OrbitRunner` performs intra-cycle sequential fallback, evaluating the next viable untried provider before concluding a cycle.

## State Transitions & Premature Pause Prevention

1. **Non-empty Untried Paths**: Orbit remains `QUEUED` / `ACTIVE`; automated transition to `PAUSED` is strictly prohibited while unexplored authorized routes remain.
2. **Blocked Prerequisite**: If all remaining paths require user credentials or exceed budget limits, Orbit transitions to `BLOCKED` with explicit remedial instructions.
3. **True Source Saturation**: Transition to `PAUSED` is permitted only when all authorized providers have executed and returned `NO_MATCH` across all open research questions, backed by a persistent `Cycle Explanation`.
4. **Surfacing**: User status inquiries and Telegram digests adopt a structured tri-part template (overall status, white-box attempt trace with outcome tags, and remaining untried paths with next action).
