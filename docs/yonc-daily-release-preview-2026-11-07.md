# Yonc Daily candidate — 2026-11-07

Status: **published with explicit user authorization**, 2026-11-07 at 10:19 UTC+8. Mission remains verification / pending_review. The candidate specification and pre-publication evidence below are retained.

## Publication result

- Formal entry: <https://yonc.95963210.xyz/daily>. Public page, Daily API and current JS resource returned HTTP 200. The public JS digest matches the approved candidate; browser reported no JavaScript errors. A 390px window retains tasks left / Activity right without document horizontal overflow.
- Only `uuma-yonc-graph.service` restarted, PID 1325 → 356413. The fixed source is `/home/alandelone/.local/share/uuma/production/yonc/releases/daily-20261107-d8521f19c509/source`; effective WorkingDirectory, PYTHONPATH and canonical database path were verified.
- Before switching, a consistent SQLite backup and private unit/environment backups were saved under the release's `backup-20261107T021932Z` directory. Database backup SHA256: `f363c1b3f4c1706df752fe0d78045a2c03cf2d7e04f64ab3a80a078f386ea37a`.
- Database identity remains `43a70a25-bb31-47cf-9810-80566f4b62da`; 691 nodes / 638 edges. All 24 pre-existing business tables were compared by complete logical row digests and remain unchanged by migration. Revision is now `20261105_0005`, adding only the three Daily tables.
- Copycat health is reachable through the approved read-only URL. Its recorder remains **STOPPED**; no capture switch or Copycat runtime restart was performed.
- Daily currently contains zero arranged tasks in the real database. This is expected: no existing L4 Action satisfies the confirmed date rule. In List, double-click an L4 Action and set its Daily planned day to populate it. No dates, sample tasks or synthetic activity were inserted into production.
- Private receipts: server release directory `stage-receipt.json`, `publication-receipt.json`, `verification-receipt.json`; local task directory `remote_apply.stdout`, `remote_verify.stdout`, `public-verification.json`, and `daily-production-desktop.png` / `daily-production-mobile.png`.
- The pre-existing split-model test mismatch remains outside this release. No shared gateway or other specialist service restarted; no Git commit/push or mission gate approval.

## Review

Open <http://127.0.0.1:18766/daily>. This preview uses synthetic data in an isolated fixture database. Its backend and frontend come from the scoped release candidate, not the complete dirty development checkout.

Daily contains only L4 Actions planned for today and earlier unfinished Actions. It provides the confirmed type/project-module grouping, single-task focus and repeated-click pause, Rest/Toilet/LIJ, canonical completion and undo, persistent stepped notes with independent first-level checkboxes, compact vertical spacing, and left tasks / right Activity. Optional planned times and independently recorded location/body condition are included. Configuration stores the option lists. Shared-boundary dragging and direct time correction update both adjacent intervals with history.

Copycat's own capture switch remains authoritative. Daily reads observations by focus interval and never starts/stops capture. The live workstation recorder was STOPPED during verification; a focus interval correctly displayed no observations. Retrieval is bounded to 500 events and reports unavailable/partial states. The additional Copycat time-range source patch is local and has not been restarted into its running service; Yonc also filters returned timestamps. Busy sources can therefore provide partial historical coverage until that separate patch is released.

## Candidate and scope

- Target: existing Yonc Graph service on `alandelone-server-001`, public entry `https://yonc.95963210.xyz/daily`.
- Verified running baseline: source `b6b5d105cd503d930c32907560615f4cc77be051fa66741e41c21060d66d7b37`; `uuma-yonc-graph.service` active, PID 1325, loopback 8766, observed 2026-11-07.
- Package: `.uuma-local/yonc-daily-implementation-20261105/yonc-daily-candidate.tar.gz`.
- SHA256: `d8521f19c5092cb0fbd86875f32fa61c294f6d8643b492d76c6d17be82f11b96`.
- 54 packaged files; 14 changed/new files relative to the production baseline, including the two current frontend assets. Source hashes are in `candidate-source-manifest.json`; package receipt is alongside it. No node_modules or fixture database is included.
- Existing API/App integration plus new Daily routes, components and stylesheet. Production ListView is retained with only Daily date-editor additions; unrelated local List modifications and other work are excluded.
- Schema: additive `daily_runtime`, `daily_intervals`, `daily_changes`; canonical Graph task identity, transitions and reversible updates remain in use. Migration refuses destructive history removal on downgrade.
- Dependencies unchanged. No Hermes/shared-gateway restart, specialist profile change or Copycat capture change is proposed.

## Verification

- Candidate frontend: 100 tests passed; TypeScript and production build passed. Existing large bundle warning remains.
- Candidate backend: 34 passed, 1 skipped, 1 failed across Daily, Graph v2 and execution suites. The sole failure is the existing split-adapter default (`standard` in production versus `complex` expected by its test). Read-only SSH downloaded the production test and verified the production adapter's exact baseline hash; the unchanged production code reproduces the same failure. This defect is recorded, not hidden by changing its assertion or bundled as an unrelated model-policy change.
- Scoped Ruff checks passed for Daily backend, tests and migration. Prior local full-source run passed 35 / 1 skipped because that checkout contains separate split-adapter work.
- Browser verified: single-task focus, pause/resume and Rest; completion/reopen, global Ctrl+Z and toast cleanup; persistent notes; grouping; planned times; Configuration option save/reload; optional context; Copycat read-only connection; coupled boundary dialog and actual 2-minute drag with no spurious dialog.
- List L4 date editor: moving the fixture Action to tomorrow removed it from today's Daily (3 → 2); restoring today returned it (2 → 3).
- Layout at 1440 / 768 / 390 pixels: left tasks and right Activity, no document horizontal overflow. Switching desktop → narrow → desktop restores all sample outline rows to 26px. Narrow screens wrap text to retain readable type.
- Screenshots: private task directory `daily-final-desktop.png`, `daily-final-mobile.png`. Current preview uses a new fixture for the current day, leaving earlier test fixtures preserved.

## Approved publication procedure (retained)

1. Recheck current unit, baseline hashes, activity and unique database owner before applying this exact package; stop if another release has changed the baseline. Resolve the actual DB path from current non-sensitive configuration. Do not initialize a workstation production database.
2. Quiesce only affected Graph writes, take a SQLite consistent backup of the existing canonical database, and record its identity, table/record counts and backup digest. Retain unit/env backups privately.
3. Extract to a new immutable source directory named from the candidate digest; verify its manifest. Reuse the compatible existing runtime only after dependency validation. Apply the additive migration against the same canonical DB.
4. Point only `uuma-yonc-graph.service` at that fixed source. Proposed read-only Copycat URL is `http://192.168.55.1:8876` (previous health connectivity verified); recheck before configuring it. Restart only Graph.
5. Verify actual imported version, unchanged database identity and prior records, additive schema, health and `/daily` assets through the existing entry. Retain the publication receipt and restore normal Graph work.
6. Code rollback restores the previous source/unit reference. Leave additive tables intact. Never restore an old database over newer writes; any data reversal requires reviewing new records first.

The development/publishing runbook explicitly states: “用户要求开发不自动等于要求上线”. The user separately approved this candidate's formal `/daily` publication on 2026-11-07, and the procedure above was applied within that scope.
