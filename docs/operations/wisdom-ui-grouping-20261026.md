# Wisdom current research and history grouping — 2026-10-26

The user requested resolving the mixed research, acceptance-history and notification
status display in the Observatory. The source change is limited to
`observatory/static/app.js` and `observatory/adapters/wisdom.py`.

## Current research

The preview pipeline now draws only from the active knowledge topic's investigations.
Archived topics and orphan investigation records do not contribute steps or execution
liveness to that pipeline. The existing green-onion topic therefore shows ten steps,
six completed, instead of eighteen mixed steps. No archived topic is silently chosen
as a current topic when an active topic is absent.

The workspace execution status reflects the current investigation (PAUSED at release),
with actual running leases required for RUNNING. Current KAG unavailability remains a
separate blocking service condition. An old failed notification no longer replaces the
research status with BLOCKED; its warning stays visible as notification delivery status.

## Preserved history and updates

The four other Orbits appear in an expandable historical-record section, one record
per Orbit. This includes two archived invalid-input topics and both RFC acceptance
records. Existing detail links and terminal statuses remain available. The expansion
choice survives periodic card rendering. No records were deleted, reclassified in the
domain database, resumed or marked complete.

The existing SSE stream transports activity, not live domain snapshots. Periodic
domain polling now runs every ten seconds even while SSE is connected. The selected
Wisdom inspector updates from the fresh snapshot while retaining its scroll position
and existing session metadata. The remote reader's existing fifteen-second cache and
source-unavailable handling remain in place.

## Publication evidence

Only the local read-only listener at 127.0.0.1:8790 was replaced, PID131144 → PID133508.
The fixed release copied the exact previous Observatory source snapshot and overlaid
only the two declared files; other source bytes were verified unchanged. The process
executable, arguments, working directory and environment were preserved, with the new
source first on PYTHONPATH. The old source remains a rollback reference. The server
gateway and research services were not restarted and no domain state was written.

Python parsing, JavaScript syntax and scoped whitespace checks passed. Live API
readback showed workspace PAUSED and ten current-topic pipeline entries. Browser
readback confirmed six of ten completed, no RFC text inside the main pipeline, and
four expandable historical records with their original statuses. A stale accessibility
node after periodic refresh was handled with the already observed text locator.
No tests were added or run; no research/model/message was triggered by this repair.

Private source-before files, preview, source hashes, exact launch context, activation,
live response and rollback information are under
`.uuma-local/wisdom-ui-grouping-20261026/`. Mission remains verification/pending_review;
no commit, push, canonical claim approval or stage-gate approval occurred.
