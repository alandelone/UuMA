# Antigravity account lease supervision

Deployed on alandelone-server-001 on 2026-10-27 (Asia/Kuala_Lumpur).
This fixes the observed incident where three orphaned native processes retained
all three account locks for hours after their pool wrappers had exited.

## Execution ownership

Each inference call now has an independent Linux guardian. Only the pool wrapper
and guardian inherit the account lease descriptor. The native executable and its
descendants never receive that descriptor.

The wrapper owns the sole write end of a lifetime pipe. Wrapper exit, cancellation,
SIGTERM or SIGKILL closes that pipe. The guardian detects EOF, kills the native
process group, reaps adopted descendants and then closes its lease descriptor.
It is a Linux subreaper, so a child that forks and creates another session is still
owned and cleaned up. The native launch shim also sets a parent-death signal.
Cleanup targets this call's own process group and adopted children, without
scanning or killing another account's processes.

Cleanup runs before output collection can wait on pipes inherited by orphaned
children. A stalled provider turn has a 900-second execution deadline, configurable
with `UUMA_AGY_POOL_EXECUTION_TIMEOUT` up to 3600 seconds. Account acquisition still
uses the existing bounded queue. No call is automatically replayed by the pool;
quota cooldown semantics and separate account credentials are preserved.

## Availability

`AccountPool.status()` now probes each actual kernel lease lock. An authorized,
enabled account outside cooldown is `BUSY` while locked and `READY` otherwise.
The operator page translates `BUSY` as 使用中. The probe is a point-in-time
observation, not a reservation or a live upstream quota/authentication test.
The startup authentication probe does not reserve a lease.

## Published components

Release:
`~/.local/share/uuma/provider-pool-releases/32fd3e3d4b2dd3ff32faed881736e3b71bb7e7e546b493c7062a4590ea683888`.

- Runtime adds `uuma_provider_guard.py` and updates the pool and availability page.
- Gateway uses `90-provider-supervision.conf` with a release-specific environment.
- The existing provider startup check points at the matching new runtime.
- The effective Python path retains the Brainstormer/Wisdom shared overlay and
  the pinned Hermes/UuMA sources. Earlier environment files remain available.
- Brainstormer, Forge and Wisdom Gemini Worker executables now use the new pool
  wrapper, replacing their older a734 release references.
- The account-pool console uses the same release through a separate service drop-in.

Only the shared gateway and account-pool console were restarted. All five
specialists were paused and drained before switching, then reopened. No profile
permissions, knowledge lifecycle, domain database schema or browser authorization
was changed. No model prompt, failed-request replay or external business write
was initiated for this repair.

## Verification and rollback

39 isolated Linux checks passed on the final candidate. Fake executables cover
normal parent exit with a surviving child, escaped-session descendants, deadline
expiry, wrapper SIGTERM/SIGKILL, lock exclusivity, BUSY/READY transitions and existing
OAuth/console/account-pool contracts. The previous test that allowed a surviving
child to retain a lease was replaced with cleanup and eventual lease reuse; new
process checks independently require the child to be dead. Standalone deployment
imports were also exercised with a fake pool and `/usr/bin/true`. Ruff passed.
No real provider inference was used for these checks.

Operational receipts, fixed preview, manifests, previous profile/drop-in bytes and
a consistent control database backup are under
`~/.local/share/uuma/operations/provider-pool-supervision-20261027/<release-id>/`.
Local sanitized receipts are under `.uuma-local/provider-pool-supervision-20261027/`.
The first staging hash enumeration included `__pycache__` and failed before any
live change; it was corrected to hash files. An initial console-path check used
`/status`, stopped before switching, and restored intake; the correct endpoint is
`/api/status`. Both failed attempts are retained.

For rollback, pause all five specialists, drain active execution and confirm the
console is not authorizing an account. Restore only backed-up profile/preflight
references and remove the two new service drop-ins, then reload and restart the
affected services. Preserve all current account credentials and business data;
never restore the old control database over subsequent writes. Returning to an
older pool also returns its incomplete cancellation cleanup, so prefer repairing
forward. Capacity limits and upstream outages remain possible; this release does
not promise uninterrupted Google service or unlimited concurrent accounts.
