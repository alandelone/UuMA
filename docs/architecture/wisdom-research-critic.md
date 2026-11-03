# Wisdom research order and independent critic

The user-approved source order from 2026-10-22 is:

1. ChatGPT consultation, initially `deep_research`.
2. Academic sources: canonical citation reuse, OpenAlex, Crossref, DDGS academic.
3. General web: DDGS and optional Brave.
4. Configured supplemental providers: XHS MCP and optional Feed/Sitemap seeds.

`AdaptiveResearchPlanner` returns a relevant batch from one tier to `OrbitRunner`.
Empty/irrelevant results may fall through immediately. The runner ingests actual
source content, synthesizes the current answer and delegates coverage review to
`WisdomCritic`. An insufficient review advances the next durable cycle to the next
tier. After the final tier, remaining worthwhile questions can start another pass
within available provider capacity and any configured daily ceiling. Source
presence alone does not certify completeness. Cumulative research totals remain
reporting records, as described in `../operations/wisdom-daily-quota-20261023.md`.

## Critic delegate

This is a bounded, tool-free delegate with its own system prompt and model endpoint.
It does not need a general autonomous agent framework. Its contract consists of
question/purpose/scope, answer, canonical excerpts with source/ref IDs and locations,
remaining gaps, and the remaining research budget. Evidence text is untrusted data.

The JSON result contains `verdict`, `rationale`, `requirements`,
`remaining_questions` and `material_conflicts_resolved`. A sufficient result needs
located support for every covered requirement, references that were actually
supplied and cited by the current answer, no material unresolved conflict, and no
remaining worthwhile question. Invalid output or unavailable service keeps the
answer provisional. This review changes research satisfaction only; canonical
candidate claims still require Orchestrator/user patch review.

Configuration:

| Variable | Default |
| --- | --- |
| `UUMA_WISDOM_CRITIC_BASE_URL` | `http://192.168.55.2:8080/v1` |
| `UUMA_WISDOM_CRITIC_MODEL` | `complex` |
| `UUMA_WISDOM_CRITIC_API_KEY` | `audit` (the operator's currently open audit gateway) |
| `UUMA_WISDOM_CRITIC_TIMEOUT_SECONDS` | `90` |
| `UUMA_WISDOM_CRITIC_MAX_CONTEXT_CHARACTERS` | `100000` |

The delegate requests a bounded completion and bounds input against remaining
tokens/time. Record actual model identity, token usage (or explicitly estimated
usage), request ID, prompt version/hash, input/output hashes and the verdict under
`cycle_explanation.critic`. Critic use contributes to cumulative receipts and any
configured shared daily research ceiling. The default policy has no custom ceiling.
No new database schema or independent critic spending allocation is introduced.

## Durable continuation

`cycle_explanation.discovery_state` records the next tier/query, attempted providers,
and the pending request ID plus provider. `QuestionOrbitService.discovery_state`
loads this per-question cursor from completed, waiting and recovered cycles, including after the currently
running cycle has been acquired. Polls do not submit a duplicate request or consume
another search-query allowance. Pending research does not increment the empty-source
failure counter. Human paused/stopped Orbits are not implicitly resumed. Quota waits
retain their retry deadline; daily-ceiling waits requeue when the new window opens.

## XHS MCP

Wisdom's production profile has an `xhs` MCP binding. Its actual tools include
`xhs_search_links`, `xhs_search_status`, `xhs_browser_status`, `xhs_resolve_link`,
`xhs_process_link`, `xhs_job_status`, `xhs_fetch_post`, `xhs_link_to_text`,
`xhs_text_status`, `xhs_login_start` and `xhs_login_status`.

The Orbit provider uses only the read-only search/status pair through the existing
Agent-scoped MCP binding. Search results are discovery leads, not evidence; normal
source ingestion must still obtain content before the critic can rely on it.
Signed browsing tokens are stripped from canonical locators and metadata. Pairing,
login and offline errors remain explicit blockers; cached results for another query
are rejected. Media/comment extraction stays a separately authorized operation.

The workstation relay must launch XHS in its own Python/Conda environment. Remove
inherited UuMA `PYTHONPATH`, `PYTHONHOME` and `VIRTUAL_ENV` for that external child;
otherwise UuMA's copied dependency directory can load incompatible Pydantic binaries.
