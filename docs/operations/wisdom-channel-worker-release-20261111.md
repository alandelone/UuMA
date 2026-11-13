# Wisdom channel recovery worker release

## Applied baseline and login-state amendment

The first package above was applied at 2026-11-11 12:29:48 UTC+8. Only the idle Orbit worker
restarted (PID 292646 to 556878); 19,444 cycle records before and after. Its actual environment
and imported module paths matched the pinned component. The consistent database backup SHA256
is `407cc1b593037c7d77fd0627c22bc4e193f2266a3260cdb947c007a0ac5a6def`.

The real connection test then showed `status=error, stage=needs_login`. A follow-up candidate
classifies needs_login and needs_verification as AUTH_REQUIRED while retaining the original job ID.
Only orbit_mcp_discovery.py differs from the applied component; the other two source files match.
Candidate `d388b57d2cb800f44bd244b1a39a8d9edc3ac3b62748d60a507bc42a8e0d4d47` passed 29 tests
on the server (the same three bridge-only tests excluded). It replaces only the hash-verified
worker drop-in after the same idle/outside-hours checks. Rollback restores the private preceding
drop-in, then restarts the idle worker; it does not restore the database.

The amendment was applied at 12:34:42 UTC+8, PID 556878 to 557116, with the same 19,444 cycle
records and the same consistent backup digest. Receipt:
`/home/alandelone/.local/share/uuma/production/wisdom-oldman/operations/channel-release-1794371682891613289/receipt.json`.
Independent post-switch readback using the actual worker environment and pinned modules succeeded:
the ChatGPT diagnostic produced 623 answer characters and three source artifacts; original XHS job
4dfd3e7471cc4749e06af2c0 produced five leads; the recorded needs_login response maps to
AUTH_REQUIRED while keeping its ID. Zero new searches or business writes in that postcheck.

## Exact scope

Target: `alandelone-server-001`, only `uuma-wisdom-orbit.service`. Candidate component:
`/home/alandelone/.local/share/uuma/components/wisdom-channel-recovery/967cdfcfb9c111f2483b39b5330d6ba34271ed54035be5a474b0312c56ed2e53`.

This candidate preserves the complete current daily-quota overlay and changes three modules:
`orbit_mcp_discovery.py`, `orbit_discovery.py` and `orbit_planner.py`. It retains exact predecessor
paths, interpreter, profile, credentials, quota, schedule and database owner. No schema changes.
Content manifests and full source diffs are in the private channel-release-preview directory.
The payload identity is the SHA256 above; it contains uncommitted source changes, not a new Git
commit. No shared Hermes gateway, other specialist or workstation bridge restart is required.

The change recognizes XHS in_progress/queued responses, preserves exact pending IDs, deduplicates
canonical links, distinguishes WAITING from productive SUCCESS and retains human-paused ChatGPT
requests. It does not implement durable polling backoff, novelty stopping or a full progress UI.

## Validation and operational boundary

The exact candidate passed 27 focused tests on the server, with three tests for bridge-account
operations excluded because those operations are outside this worker-only release. The separately
loaded Chrome ChatGPT extension 0.1.6 passed eight focused Node checks and returned the one original
request as COMPLETED through both human and Wisdom APIs, with 623 answer characters and three links.
XHS's original five-link jobs were recovered through the existing deployed MCP binding.

Before switching, revalidate the active source digests, candidate manifest, unit configuration,
outside-hours boundary and zero RUNNING cycles. Preserve a consistent SQLite backup of the existing
Wisdom database and private copies of service configuration. Hold a short SQLite write reservation
while checking for zero running cycles and stopping the idle worker; do not alter any records.
Never stop a live research cycle to force this deployment. Abort when a precondition changes.

Use a new unit-specific EnvironmentFile after the existing file so the pinned PYTHONPATH override
is effective. Restart only the idle Orbit unit. Confirm its process environment and imported source
paths/hashes, service health, preserved data owner and unchanged cycle counts while outside hours.
Retain a receipt for actual application; this document alone is not a deployment receipt.

## Rollback

Remove only the newly created, hash-verified unit drop-in, reload systemd and restart only the same
idle worker at a verified checkpoint. Keep the new component and receipts for investigation. Revert
the code pointer only; never restore a database backup over later records. Previous component:
`wisdom-daily-quota/ab2861c799c316346bb22d5de61f7eb377cbe19950d7bf584c3458cdd64e12e9/src`.
The mission remains verification/pending_review; this release does not approve scientific claims
or resolve the original Deep Research queue or XHS login requirement.
