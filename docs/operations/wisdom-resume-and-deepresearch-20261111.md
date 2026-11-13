# Existing Wisdom research and Deep Research verification — 2026-11-11

The user clarified that cleanup means only clearing stuck requests and continuing the existing
research, retaining research records and sources. They specifically identified the old Deep
Research queue and per-requirement evidence coverage. They then explicitly requested verifying
Deep Research before the proposed automatic-channel fallback is applied.

## Applied request cleanup

Cancelled exactly three Wisdom/main Deep Research requests through the existing authenticated
human API, after checking each was QUEUED/PAUSED, had never been submitted, and had no conversation
URL or result. Their request rows and event histories remain intact:

- cgpt_85da342de4794c8f84856ed2ab77c2d5
- cgpt_fc3c3306dc1d4d319be1432ad9e4816d
- cgpt_fa7bd6257ad74add81bc633f305ae55f

Receipt: `.uuma-local/wisdom-connect-20261111/cancel-stuck-1794386918813119100/receipt.json`.
A consistent chatgpt-before.db backup was retained. All other bridge request objects compared
equal before/after; no records were deleted. The chosen wisdom-work binding remains Profile 9.

Read-only inventory: five Orbits, 19,444 cycles, 27 sources/documents, 194 evidence records and
ten claims. The existing onion research is orbit_9ac4d099873b82f8f5a730cf07792419 under
topic_07a8574b5d504d34a5483407c2a88400. It remains QUEUED, with the normal 19:00–07:00 Malaysia
window. Two old acceptance-test Orbits and two stopped accidental topics are not resumption targets.

## Deep Research verification in progress

The Profile 9 live UI exposed an enabled `Deep research — Get a detailed report` button in the
Add files and more menu. Selecting it inserted a visible native Deep research chip. This proves
menu access, not successful research execution or result retrieval.

Inspection found that the workstation bridge sends a `/Deepresearch ` prefix as plain text.
Extension 0.1.8 now handles that prefix by filling the exact prompt first, selecting the native
research button, verifying the added chip text, and only then sending. Missing, disabled,
ambiguous or non-activating controls fail without sending an ordinary prompt. Tool-menu discovery
also waits for the current plain-button picker instead of relying only on legacy Radix surfaces.
Twenty Node tests passed before loading 0.1.8 (eight DOM, six lifecycle, six mode tests).

The same existing Profile 9 extension was reloaded, and version 0.1.8 was observed. Native
verification subsequently encountered local API/database-lock delays and EXTENSION_UNAVAILABLE.
A diagnostic SQLite connection was explicitly closed; health then returned worker_healthy=true
and last_error=null. The account verification did not establish deep_research capability.
No Deep Research test request has been admitted at this checkpoint.

The pending Windows view repeatedly reported a minimized window and then user input while
activation was attempted. The user has been asked to expand Profile 9 and leave it available.
Do not keep fighting user window input. Browser Use is disabled in Work settings; use the
existing supported Windows Computer Use workflow after the user completes that handoff.

After the initial 20-test pass, a separate protection was added: a lost `send` acknowledgement
must raise SUBMISSION_UNCERTAIN instead of reloading and submitting the prompt a second time.
Its additional lifecycle test still needs to run. The loaded 0.1.8 worker predates that last
background-source edit and must be reloaded only at a verified idle checkpoint after tests pass.

One prepared idempotent native test uses thread profile9-deepresearch-20261111 and key
wisdom-profile9-deepresearch-20261111-v1 on the existing authorized run. Its scope is a bounded
public-source Allium fistulosum review covering recovery, mist intervals, nozzles and nutrients,
with source locations and direct/indirect/missing evidence. The helper refuses submission unless
native capabilities include deep_research. Reconcile its durable receipt before any repeat call.
Do not count the previous 623-character ordinary-search result as a Deep Research result.

## Prepared but not applied

The helper wisdom_continue_existing_20261111.py was prepared for four focused evidence gaps
under the existing topic, cancelling stale cursors through compensating events, and a maximum
five-cycle immediate batch followed by restoration of the normal night worker. It also contains
a proposed channel-disable policy. The user's later instruction requires verifying Deep Research
first; the helper now exits before any action. No new evidence-gap rows, cursor repair, automatic
channel-disable policy, transient batch, worker stop/restart or source deployment was applied by it.

After Deep Research verification, update the concrete continuation operation to use the verified
channel state, preserve exact result/request identities and existing scientific records, and
resume the original research. Keep evidence adequacy separate from transport/mode verification.
