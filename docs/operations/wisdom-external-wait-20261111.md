# Wisdom durable external waits — 2026-11-11

## Scope and verified behavior

This follows the ChatGPT/XHS channel recovery. It does not certify Deep Research availability
or the adequacy of the returned scientific material. The mission remains verification/pending_review.

The previous runner completed research cycles while a remote task was still pending, performed
graph reasoning again on the next cycle, and polled roughly every worker tick. The new scheduler
keeps one cycle in RETRY with decision WAITING_EXTERNAL and a durable external_wait cursor.
It preserves the provider/request pair and releases the worker lease until the next check.

- Unchanged checks back off for 30, 60, 120, then 300 seconds. Authentication requires attention
  immediately; five minutes without a status change also requires attention. Explicit provider
  retry delays take precedence, bounded to one day.
- Waiting checks do not increment retry attempts or completed research cycles and do not repeat
  graph/model work. The original search and actual work are still charged through existing
  discovery usage and RESEARCH_RUN_UPDATED events; daily limits remain enforced.
- Other authorized Orbits and other open questions in the same Orbit can run during the wait.
  Completing a sibling question cannot close an Orbit that still has a pending external request.
- A user pause/stop and lease ownership/expiry remain authoritative.
- A completed poll retains its remote identity until processing succeeds. Graph failure after
  receiving a result therefore cannot silently turn the next retry into another submission.
- No schema changes, request cancellation, historical replay, model calls, or accepted-knowledge
  changes are required to publish this fix.

## Validation

Local: 118 focused pytest cases passed across external waits, Orbit runtime, Question Orbit,
research quota, planner and connection recovery. Existing pending-request tests retain their
assertions and now share the scheduler's simulated clock. Thirteen new cases cover restart,
not-yet-due checks, no repeated models, stable attempts beyond the normal retry ceiling,
finished-result ingestion, authentication/offline/quota delays, sibling progress, pause/stop,
expired/incorrect ownership, failure after completed polling and channel handoff accounting.

Server fixed candidate: 119 passed, three bridge-only tests excluded. The extra suite includes
the existing XHS MCP tests. One existing Pydantic settings warning remains.

First runs are retained: the independent-Orbit fixture initially omitted its research gap;
the existing restart test initially advanced only the old scheduler clock. Corrected the fixtures
and clock wiring; no production guard or assertion was weakened. Import-format lint issues
were corrected separately.

## Publication candidate

Component:
`/home/alandelone/.local/share/uuma/components/wisdom-external-wait/bcdede8d971d959c04e3962932b7f75fc0327734ea44c2647365f53643e01a58`.

The six imported live module files were retrieved and compared before staging. Only
question_orbit.py and orbit_runner.py differ; orbit_wait.py is new. Existing research_quota.py,
orbit_planner.py, orbit_discovery.py and orbit_mcp_discovery.py match the live runtime. The
fixed component copies the existing overlay and preserves all previous fallback paths.
Private preview, exact source manifest and test output are under
`.uuma-local/wisdom-connect-20261111/wait-release-preview-1794383158644119500`.

Published at 16:01 Malaysia time at the guarded outside-hours idle checkpoint. Source/unit hashes,
zero running cycles and the configured 19:00–07:00 window were checked. Only Wisdom Orbit
restarted, PID 557116 to 561417. Actual imports of all three scheduler modules point into the
fixed component. All 37 tables retained identical schema/content fingerprints, and all 19,444
cycle records remained unchanged. No new searches or models were invoked by publication.
The shared gateway and other Agent services were not restarted.

Receipt:
`~/.local/share/uuma/production/wisdom-oldman/operations/external-wait-release-1794384085944293256/receipt.json`.
The consistent wisdom-before.db backup has SHA256
`407cc1b593037c7d77fd0627c22bc4e193f2266a3260cdb947c007a0ac5a6def`.
New drop-in: `uuma-wisdom-orbit.service.d/30-external-wait.conf`, SHA256
`47fe637b94c3c001573e8e43f90e925ae82c6f1a4b7ca9f398b1f8071fef1e22`.

Rollback selects the previous code path at an idle checkpoint. Never restore an old database
over new research or user changes. Waiting decisions/cursors are append-only historical data;
an old worker does not implement the new waiting semantics, so inspect pending work first.

## Follow-up browser lifecycle fix

The final pre-publication inspection still reported extension_connected=false. The Profile 9
extension manager independently showed the 0.1.6 ChatGPT worker as Inactive while the XHS
worker was active. The old ChatGPT background loop used network polling and timers without
periodic extension API activity, allowing MV3 idle termination.

Extension 0.1.7 adds one shared activity timer while authenticated polling/commands are active,
using its existing storage permission every 20 seconds. It releases that timer when all paired
loops stop; token rotation and repeated wakes cannot duplicate pollers or remove the replacement
loop. No new permission, dependency, browser restart or bridge-service restart is required.
Six new lifecycle tests plus the eight DOM return tests passed (14 total).

Loaded the same existing extension in the existing Profile 9 window through its Reload control;
observed version 0.1.7 and active service worker. Minimized that window for live observation.
At 16:08 Malaysia the bridge reported extension_connected=true without refreshing the dashboard.
The bounded observation does not certify indefinite uptime. Account verification and the final
native-provider readbacks are recorded separately; Deep Research is still unverified here.

Final checks: account wisdom-work returned READY, extension_connected=true, action/error empty,
with chat/search capabilities. The window remained minimized through this verification. A later
window observation still showed the active 0.1.7 worker. This is a bounded live check, not an
indefinite-uptime guarantee.

The deployed native discovery providers read back the original ChatGPT request (623 characters,
three citations) and the resumed XHS job (three links), with no new searches or business writes.
Worker PID 561417, 19,444 cycles and zero RUNNING cycles remained intact. The first native
postcheck failed an assertion during XHS readback; it produced no success receipt. A subsequent
read-only check of the same IDs passed. The initial response was not retained in sufficient
detail to assign its cause; do not describe it as proven data loss or a fixed parsing defect.

## Remaining scope

The old main-account Deep Research queue, deep mode on the chosen account, original-research
ingestion, per-requirement scientific evidence coverage, no-novelty strategy and complete UI
progress counts remain unfinished. The scheduler fix prevents waiting from creating new completed
rounds; it does not establish that the returned leads answer the research question.
