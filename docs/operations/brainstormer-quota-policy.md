# Brainstormer usage and provider quota

## Current status: reversed on 2026-10-23

The user requested removing this misplaced change. Release
`ab2861c799c316346bb22d5de61f7eb377cbe19950d7bf584c3458cdd64e12e9`
removed the entire `Usage and provider quota` SOUL section and its explicit empty
`agent.disabled_toolsets` cache default from the server Brainstormer profile.
The active `usage_policy_release` metadata was replaced with a compensating
reversal receipt; the original receipt remains in history. The workstation SOUL
section was also removed. Existing Telegram navigation/menu and the independently
updated `complex` worker configuration were preserved.

The actual Wisdom runtime quota implementation is recorded in
`wisdom-daily-quota-20261023.md`. The remainder of this document is historical.

## 2026-10-23 scope correction

The user clarified that the refreshing daily-quota discussion was intended for
Wisdom-Oldman in another chat. Applying it to Brainstormer was an assistant scope
error. The record below describes the actual historical publication; it is not
evidence that the requested Wisdom daily-quota mechanism was implemented.

The publication added only Brainstormer prompt guidance, an equivalent empty config
default to refresh its prompt cache, and version metadata. It added no quota
accounting, daily reset or automatic recovery code. Brainstormer had no custom
cumulative research spending cap to remove; actual provider limits still apply.
Wisdom's deployed Question Orbit code still compares cumulative research-run usage
against QUICK/STANDARD/DEEP tier limits without a daily reset. This clarification
does not revert the historical profile or change Wisdom runtime/state.

Historical publication date: 2026-10-22. Target actually changed: Brainstormer
profile on `alandelone-server-001`.

## Policy

- Cumulative token, estimated cost, elapsed time and account usage remain historical
  records. They do not define a lifetime spending allocation or permanently stop a topic.
- No additional spending ceiling is configured by this change. If the user later
  requests a ceiling, configure it per day with an explicit timezone and scope,
  separately from lifetime reporting totals.
- Actual provider quota, RPM/rate limits and resource failures can prevent execution.
  Report the observed condition and provider-supplied reset/retry time when available.
  Do not infer that a local cooldown or local midnight guarantees quota recovery.
- After availability returns, the next user message or explicit retry should restore
  the topic and checkpoint and continue unfinished work. This release adds no automatic
  retry scheduler and does not replay uncertain external actions.
- Per-request context/output bounds, per-turn loop bounds and execution timeouts
  remain technical execution limits. They do not implement cumulative spending caps.

## Scope and runtime evidence

The inspected Brainstormer state/navigation, control task contract and deployed profile
had no cumulative spending stop to remove. Wisdom Question Orbit's research-run tier
budgets belong to a different component and are outside this change.

The change adds the `Usage and provider quota` section to
`profiles/brainstormer/SOUL.md`. Deployment inserts that exact section into the current
server profile, preserving its server-specific runtime boundary and other content.
It does not replace the profile from the workstation wholesale.

Release: `3dcf764da23a2773dd8faf0cdc1f9e9de8a873d7f9cf1529ddbb00e92125186c`.
Server release directory:
`~/.local/share/uuma/brainstormer-policy-releases/<release>/`.
The concrete preview records before/after hashes, protected component hashes,
the source commit plus uncommitted overlay, shared gateway impact and rollback.

The pinned Hermes gateway caches agent system prompts. The initial shared-restart
preview (`185a98e1...`) was not applied because Honc and Forge control runs remained
`RUNNING`. Its owned drain markers were removed and intake restored.

The replacement preview uses the engine's existing configuration cache signature:
Brainstormer's previously implicit empty `agent.disabled_toolsets` is written as an
explicit `[]`. Parsed configuration remains semantically identical after normalizing
that default; its cache signature changes from the absent value to `[]`. The next
Brainstormer turn therefore constructs a fresh agent and loads the updated SOUL.
Only Brainstormer intake is paused for the atomic profile publication. This approach
requires no gateway restart and preserves other agents' task states.

Navigation service, provider runtime, credentials, model configuration and domain
databases retain their current owners and versions. A concurrent Telegram plugin
release observed during preparation is preserved by the new preview's fresh hashes.
An intermediate refresh preview (`7450b119...`) was also left unapplied when its
gateway environment hash changed; the final preview uses the refreshed baseline.

Deployment receipts and private rollback copies stay in the server release directory.
Sanitized local receipts are under
`.uuma-local/brainstormer-quota-policy-20261022/`.
Profile loading and adapter connection checks do not prove a fresh model response or
an upstream quota reset.

## Publication and current readback

Published and verified on 2026-10-22 at 15:14 UTC. The SOUL SHA-256 is
`1be792beacfa406b9f2556254c2112e3ee920921727551fb29928058f441aff6`;
the published configuration SHA-256 is
`e04c1f13379c38d679517e54bf32dacfa4358f1d6fcf85ee55b1dc298552e513`.
The real pinned runtime loaded the entire policy section. The configuration check
confirmed an altered cache signature and equivalent configuration semantics after
normalizing the empty default. All five Telegram adapters were connected, all five
intakes open, and protected component hashes and Brainstormer domain data unchanged.
No service restart, inference, Telegram message or task replay was performed by this
publication. No test suite was added or run for this policy-only change.

Read-only confirmation on 2026-10-23 at 04:22 UTC found the same policy release and
SOUL hash, the cache-refresh default still configured, a running gateway, all five
adapters connected and all five intakes open. Gateway PID was then `144499` and
navigation PID `112910`; the gateway had been restarted independently since the
original publication. No repeat publication or runtime mutation was performed by
this readback. Receipts: `verify-refresh.json` and `read-current.json` in the local
receipt directory above.
