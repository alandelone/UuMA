# Wisdom Observatory blank panel — 2026-11-11

The reported screenshot showed zero topics and gaps while also claiming ACTIVE, 40 cycles,
PID 12700 and document v45. Those progress values were literal frontend defaults, not observations.

The read-only live Observatory API at loopback 8790 returned four knowledge topics and the original
onion Orbit with ten frontier items. The configured remote-owner marker and authoritative Ubuntu
reader were healthy. No research records had been removed by the earlier three-request cleanup.

Two frontend problems sustained the misleading view:

1. When the first snapshot had no items, the renderer invented liveness/count/version values.
   QUEUED or configured ACTIVE state was also treated as proof of a running worker.
2. The event stream refreshes an initial snapshot and subsequent activity events; it does not
   continuously deliver fresh domain snapshots. The HTTP refresh was disabled while SSE stayed
   connected, so a temporary empty source read could remain visible indefinitely.

The fix removes the invented values, preserves zero values, retains every topic plus
historical/orphan investigations, and requires the backend's current-cycle/lease evidence for
live execution. Missing data is explicit. Each frontier row retains its original detail owner.
The fleet snapshot refresh now runs every 15 seconds regardless of event-stream connectivity,
shares overlapping requests and preserves known records on failed reads.

On November 12, the live API briefly reported an SSH timeout while returning the last available
snapshot. The panel now labels these records and suppresses execution indicators until the source
recovers. The Wisdom changes were reapplied to the current source with the newer Yonc changes intact.

The Windows Observatory on port 8790 served the updated asset on November 12. The live owner API
returned four topics and ten frontier records on the original onion Orbit. It reported `QUEUED`
and `runner_live: false`. Eleven Node tests passed against the served JavaScript and a snapshot
from the live API. The tests cover the timeout state, empty states, zero usage, queued versus
live execution, retained history, duplicate investigations and refresh recovery.
No backend, database, model, research queue, account or service restart is part of this change.

Private source backup, candidate manifest/diff and publication receipt:
`.uuma-local/wisdom-connect-20261111/panel-fix-rebased/`.
The receipt's applied flag and served asset digest are the authority for publication status.
The configured API owner snapshot is separately retained in blank-panel-diagnosis-*.json.

The UI's data availability, a worker executing a research cycle, scientific evidence coverage and
successful Deep Research execution remain separate observations. This display correction does
not certify completion of the ongoing Deep Research verification.
