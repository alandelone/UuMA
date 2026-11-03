# Wisdom runtime status and notification receipts — 2026-10-26

The user reported a FAILED investigation dated 2026-09-21 and asked why a failure
had not become visible to them. The authoritative owner remains
`alandelone-server-001:wisdom.db`; no investigation was restarted or marked successful.

## Findings

- The reported investigation `orbit_7c0097134a7345314d2a6abf11b82cce` failed while
  recovering the old Windows Docker Desktop KAG runtime. Its failure notification
  is recorded SENT at 2026-09-21T03:39:42.615734Z, about seven seconds after failure.
  This is a transport receipt, not proof the user saw or read the message.
- Another investigation's latest failure notification, dated 2026-10-17, is FAILED
  after three attempts with `Hermes send failed.` The existing dispatcher stops
  claiming a notification after three attempts. There is no independent escalation
  of that exhausted notification in this change.
- On 2026-10-26 at 09:46:59 Asia/Kuala_Lumpur, the server loopback KAG health
  endpoint returned ready=true. A healthy service does not complete or resume a
  historical failed investigation.
- Some historical research usage records still say ACTIVE while their owning Orbit
  says FAILED. The UI now discloses this mismatch and uses the Orbit execution status.
  Canonical history was not rewritten to hide the discrepancy.

## Display changes

The existing read-only remote snapshot now includes a bounded KAG health probe,
its check time, and the latest critical notification receipt for each investigation.
Routes, chat identifiers and provider error text are excluded from the new receipt
summary. The database snapshot ends before the independent health request.

A separate runtime item and the expanded Wisdom card show service health and
failed notification delivery. The collapsed card flags the failed critical receipts;
workspace status is BLOCKED when they exist. Historical task timestamps and outcomes
remain unchanged. A service observation older than one minute is labeled stale in
the operational panel. The existing remote snapshot refresh cache is fifteen seconds.

The panel distinguishes SENT from user-read confirmation. It also removes fixed
claims about a daemon PID, forty cycles and always-running research in the expanded
Wisdom banner. Actual execution requires an unexpired running cycle lease.

## Publication and limits

Only the local read-only Observatory listener at 127.0.0.1:8790 was replaced:
PID110908 → PID132040 → PID131144. Browser inspection caught a second fixed
running label in the collapsed preview after the first release; v2 also corrects
that label and its fixed Cycle #40 footer. Its executable, arguments, working directory and environment
were preserved, with a fixed source snapshot first on PYTHONPATH. The unrelated
unbound launcher PID113176 was left untouched. No server service/gateway restart,
domain database writes, historical research replay, model calls or outbound messages.

The fixed source, file hashes, launch context, activation receipt, live API response
and rollback source are under `.uuma-local/observatory-wisdom-status-20261026/`
and the final `.uuma-local/observatory-wisdom-status-20261026-v2/`.
Python parsing and JavaScript syntax checks passed; the live Wisdom API returned
KAG READY, one failed critical receipt and workspace BLOCKED. No tests were added
or run. The rollback source reverses only this task's Python additions while keeping
concurrent source and the static UI already served at publication time.

Earlier command attempts hit Windows memory/paging limits, a console encoding error,
and a query against a JSON-only field as if it were a physical column. Those failures
were retained; no lifecycle checks or assertions were weakened. Publication completed
after the environment could run the managed commands again. Mission remains
verification/pending_review. No commit, push or gate approval was performed.

This makes delivery failure visible in the Observatory. It does not establish a
second notification channel or guarantee a push alert while the dashboard is closed.
