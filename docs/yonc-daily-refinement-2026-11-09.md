# Daily Activity refinement — 2026-11-09

User requested these changes on the formal site, including an in-page temporary task/activity preview. Development and scoped publication are authorized. Mission remains verification / pending_review.

- Daily is the first primary navigation view. Its heading consistently reads Daily.
- Rest, Toilet and LIJ share the Activity heading row with subdued controls. The visible Actual / UTC+8 text is removed; internal date interpretation remains UTC+8.
- Location and body condition move from the top toolbar to a dashed line in the Activity region. Hover or tap to place the line; focus or click pins its controls. Select either optional dimension or both. Keyboard users can focus the context-entry button and edit its time.
- User explicitly confirmed placement in gaps and at block boundaries only. Inside a completed block the line snaps to its nearest edge; inside an ongoing block it snaps to its start. Scrolling covers the full day, allowing past entries. Future times are rejected.
- Context entries retain actual append-only recording time plus an effective time for the selected position. Daily retrieval and carry-forward order use that effective time. No schema migration is needed; old context records remain compatible. The server also rejects explicit timestamps inside activity blocks.
- A gear sits beside the new four-cell grouping icon. Both open small panels. The gear edits option lists and offers the sample-day preview; the existing Configuration entry remains available.
- `?preview=1` shows sample tasks, notes and colored activity blocks in the formal interface. Focus, modes, context selections and option changes stay in memory. Sample completion is disabled, notes are read-only, and no sample tasks, intervals, context or options are written to the real database. Exiting returns to the real Daily view.

Candidate: `e2acc730bab3f249e58fe91823ef4dacc34053d0bbff9d53311b7f451de1a9f3`; 58 scoped files / 12 changed or new relative to the exact November 7 deployed source. Existing unrelated local work is excluded.

Validation: 19 backend tests and 102 frontend tests passed; scoped Ruff, TypeScript and production build passed. Existing bundle-size and framework deprecation warnings remain. Browser verified gap placement, snapping both ends, filling either/both fields, settings panel save, project grouping, preview focus and modes, first navigation position, narrow layout and zero preview write requests. An isolated live-mode fixture saved both dimensions at yesterday 09:22 and read them back at that exact effective time.

Deployment evidence is held under `.uuma-local/yonc-daily-refinement-20261109/` and the corresponding fixed server release. Use a consistent backup and Graph-only switch, preserve all existing logical table contents, and keep Copycat capture independent. A final publication result will be appended after formal verification.

## Published result

Published 2026-11-09 at 17:38 UTC+8 to <https://yonc.95963210.xyz/daily>. Temporary sample entry: <https://yonc.95963210.xyz/daily?preview=1>. The sample entry is optional; leaving it returns to the real day.

Fixed source: `/home/alandelone/.local/share/uuma/production/yonc/releases/daily-20261109-e2acc730bab3/source`. Only Graph restarted, PID 356413 → 453456. No schema changes or other service restart. Before switching, consistent database and private configuration backups were saved under `backup-20261109T093833Z` in that release; database backup SHA256 is `2a542ade588b766b68958ceae31d9312423b98ede5d8ef4e5246f6715fab2b25`.

The real database retains identity `43a70a25-bb31-47cf-9810-80566f4b62da`, graph version 128, 691 nodes and 638 edges. Complete logical digests of all 27 pre-existing business tables remain unchanged after switching and public preview interaction. Real Daily still has no eligible task or activity/context records; no sample business records were created.

Public live and preview pages returned HTTP 200; current JS resource hash matches the packaged manifest. Browser has no JavaScript errors. The real-site sample supports task focus, modes, both context selections and grouping without any `/api/` write requests. Cloudflare's existing RUM telemetry POST is separate from business API requests. Exit preview returned to the empty real day. At 390px the two columns retain their order without document horizontal overflow. Historical mode controls are disabled while retrospective context remains available.

Server `stage-receipt.json`, `publication-receipt.json`, `verification-receipt.json` and local `public-verification.json` preserve the evidence. Code/config rollback uses the previous fixed source and backed-up configuration, without restoring an old database over new writes. The first staged candidate was superseded before publication by the final historical-mode guard; only the final digest above was applied.
