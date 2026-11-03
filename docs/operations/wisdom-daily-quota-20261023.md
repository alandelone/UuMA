# Wisdom daily quota and Brainstormer correction

The user clarified on 2026-10-23 that the refreshing quota request belongs to
Wisdom-Oldman and requested removing the misplaced Brainstormer change.

## Behavior

- Cumulative research time, sources, estimated tokens and search counts remain
  historical records. The old QUICK/STANDARD/DEEP totals no longer stop research.
  Tier labels remain for compatibility and existing reviewer permissions.
- The current policy adds no custom ceiling. Actual upstream quota, RPM and
  resource refusals still prevent execution. An explicit refusal retains the
  research question, frontier, saved discovery cursor and original pending request.
- Provider quota waits retain a retry deadline without spending the ordinary
  three-attempt failure allowance. The worker waits before checking availability
  again; an unknown upstream reset uses a 30-minute probe interval. This interval
  does not establish that an account refreshes at that time or at local midnight.
  Provider-supplied retry intervals take precedence when available.
- Optional `UUMA_RESEARCH_DAILY_LIMITS_JSON` accepts positive finite ceilings for
  `active_seconds`, `sources`, `model_tokens`, and `search_queries`. An empty object
  disables custom ceilings. Any configured ceilings apply across Wisdom research
  runs for the calendar day in `UUMA_RESEARCH_QUOTA_TIMEZONE`. Deployment uses
  `Asia/Kuala_Lumpur` and `{}`; it does not invent an account quota amount.
- Daily usage is the positive counter delta in existing append-only research-run
  events, charged at the event's recorded time. It is application accounting,
  including estimated model usage, not a provider account balance. A new day opens
  a new accounting window without clearing cumulative receipts.
- The worker stays available during a persisted quota wait, even when its normal
  idle timeout would otherwise exit. Daily-ceiling waits can requeue after the
  new window opens. Explicit user pause/stop cancels waiting cycles and takes
  priority. Existing historical paused, failed or completed work is not resumed
  by publication.

## Independent critic

Reference: task `✅梳理 Wisdom-Oldman 架构`,
`docs/architecture/wisdom-research-critic.md`, and
`profiles/wisdom-oldman/skills/wisdom-coverage-critic/SKILL.md`.

The four-tier research order and `complex` critic model, prompt, evidence checks,
verdict validation and canonical knowledge review remain in place. A critic quota
refusal preserves the completed evidence batch and queues a provider wait. It
cannot certify sufficiency. Its model identity, usage and verdict remain in
`cycle_explanation.critic`. Per-request context/output bounds and timeouts still
bound individual calls independently of lifetime reporting totals.

## Server publication

Fixed candidate:
`ab2861c799c316346bb22d5de61f7eb377cbe19950d7bf584c3458cdd64e12e9`.
Server component directory:
`~/.local/share/uuma/components/wisdom-daily-quota/<release>/`.

The candidate copies the currently deployed `wisdom-research/e98cbd.../src`
component, then overlays nine declared modules, including the MCP continuation
entry point for legacy budget stops. It preserves the older fallback
source, Hermes engine and provider runtime references. Immutable prior releases
are not edited. JSON record fields are extended for wait metadata and already
persisted explanations; no SQL schema change is required.

The Brainstormer reversal removes the misplaced SOUL section and its equivalent
empty config default, keeping a compensating version receipt. Wisdom receives
the new source reference, quota environment and SOUL instructions. Existing
prompt-cache invalidation reloads the profiles on subsequent messages. Only the
Wisdom view service needs restarting; the idle Orbit service remains idle and
the shared gateway is preserved. Affected intake: Brainstormer and Wisdom only.
Queued PENDING control tasks remain queued; they are not treated as executing
work or cancelled. Publication requires zero native active agents, no affected
RUNNING/CANCEL_REQUESTED control runs, no unfinished research cycles and no
systemd or on-demand Orbit worker process. Existing task IDs and execution epochs
are retained.

Preview, staging results, activation/verification receipts, private configuration
and consistent SQLite backups live in the server component directory. Sanitized
local receipts and exact before sources are under
`.uuma-local/wisdom-daily-quota-20261023/`. Reversal must restore only owned
configuration/source references after reconciling later changes; never restore
an old database over subsequent work.

## Checks before publication

116 focused quota, Orbit, planner, critic, knowledge and conversation-recovery
checks passed, followed by all ten quota checks including legacy-stop continuation.
The Windows environment required its declared `tzdata` dependency.
A stale provider-factory fixture was corrected to require the existing
`profile_home` argument while retaining its control/knowledge ownership assertions.
The initial missing timezone, clock/cursor and fixture failures remain in the
session history; none were declared passes.

An isolated SQLite backup from the canonical server database retained its valid
event chain. All 3,696 cycles, five Orbits and five research runs validated against
the extended record models without rewriting records. Already persisted
`latest_cycle_explanation`, cycle explanations and discovery attempts are declared
model fields so strict validation preserves their original contents.

Earlier previews were left unapplied when queued work was conservatively treated
as active execution, and when another gateway maintenance owned paused intake.
The final preview captures that maintenance's completed gateway and `complex`
worker configuration. It preserves the queued task rather than cancelling it.

No fresh upstream inference, research replay or Telegram message is part of the
publication checks. These checks do not establish an actual provider reset time.

## Published result

Applied and verified on 2026-10-23 at 16:41 Asia/Kuala_Lumpur (08:41 UTC).
The actual pinned-runtime probe imported `uuma.question_orbit` from the release
directory above and reported provider-only mode, the configured timezone and a
valid canonical event chain. All protected component hashes and canonical
research records matched their prepublication values, including after the probe.
Brainstormer's SOUL section and cache default were absent; its active policy
metadata had a compensating reversal receipt.

Only Wisdom view was restarted (PID `98532` to `154968`). Gateway PID `154353`
remained unchanged by this publication. The Orbit runner remained inactive, five
Telegram adapters were connected, and all five intakes were open after the two
owned intake gates were released. No database schema/history reset, task replay,
inference or Telegram send was performed. Older failed/stopped/budget-stopped
research states were preserved; a legacy budget stop can now be explicitly
continued without adding a lifetime allocation.

Server receipt: `<release>/verification.json`; local copy:
`.uuma-local/wisdom-daily-quota-20261023/verify.json`. Private configuration and
consistent database backups remain on the server only.

The restarted Wisdom view also returned HTTP 200 from its actual loopback
`/health` endpoint with `status: ok` and `loopback_only: true`.
