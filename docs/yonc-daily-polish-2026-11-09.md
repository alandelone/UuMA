# Daily editor and activity corrections — 2026-11-09

User requested fixes to the deployed Daily/preview and confirmed a **30-second** mode correction window. This continues the authorized formal Daily refinement scope. Mission remains verification / pending_review.

- Focused cards and active task activity blocks use blue consistently. The reported red border was inherited from a configured project color, reproduced on Review and wrap up; historical project colors remain available in the trace.
- Preview outlines are editable in memory. Save, add/delete/check, Enter siblings, Tab indent and Shift+Tab outdent work without production writes. Enter on an L4 card creates and focuses a first-level step. Layout effects move input focus before the next keystroke. Preview drafts survive grouping changes and disappear on leaving preview. Real outlines retain the original canonical L4 storage and explicit Save behavior.
- Calendar icon replaces the Date word. Date text is larger, unboxed and visually aligned with Daily; the native picker opens from the date control.
- Gear and grouping panels close on pointer interaction outside or Escape.
- Selecting location/body condition releases the cursor pin. Moving outside the controls resumes floating placement or hides it on leaving the timeline. The centered control group is narrower, leaving more dashed line visible.
- Selecting a different personal mode within 30 seconds of the last selection corrects the same interval, retaining its ID and original start time. It appends an `activity_replace` history entry with prior/current values and selection time. Repeated quick corrections renew the 30-second window. After 30 seconds, a normal new interval starts. Task focus transitions and pause remain separate. No schema migration is needed.

Scope: 58 candidate files / 7 changed, SHA256 `6d894dd305757f6e921701b4dfb9000164fdd1274494e16357139600c5e3544d`; baseline fixed source `daily-20261109-e2acc730bab3/source`. New source will be `daily-polish-20261109-6d894dd30575/source` on the existing server. No shared gateway, Copycat capture or other Agent changes.

Verification: 20 backend / 102 frontend tests passed, scoped Ruff and TypeScript/build passed. Backend regression verifies chained corrections at 20s and exactly 30s, stale revision rejection, retained interval ID/start, append-only before/after history, 31s new interval and unchanged task work time. Browser reproduced the red border and verifies blue after correction; edited preview notes, Enter/Tab, Save, L4 Enter typing without lost characters, grouping preservation, outside close, narrowed controls and resumed floating. Preview interactions made zero business API writes. Isolated live fixture first-level/nested notes survived Save and reload. Existing bundle/deprecation warnings remain. An unrelated occupied local port was preserved; isolated preview uses 19769.

Deployment and backup receipts will be appended after the guarded Graph-only publication and public verification.

## Published and verified

Functional fixes published at 22:12 UTC+8, followed at 22:18 by an HTML cache-header correction. The final fixed source is `daily-polish-cache-20261109-e5762e014c47/source`; final archive SHA256 `e5762e014c473d735244eb137542d8248fc012f0bfde9eb057c218895ae7d6c8` contains 58 files with only the HTML-serving file changed relative to the preceding functional release. Frontend assets are unchanged from the verified functional build.

The browser had reused its old HTML at the unversioned preview URL even though direct HTTP returned the new asset. `/daily`, `/` and `/v2` now send `Cache-Control: no-store` for HTML; hashed assets retain their normal behavior. Two added regression checks bring the backend suite to 22 passed. Use <https://yonc.95963210.xyz/daily?preview=1&v=e5762e014c47> to bypass a previously cached entry on first review.

Formal browser verification: HTTP 200, no-store response header, JS digest matches manifest, no JavaScript errors; blue focus border, L4 Enter adds complete typed text, note editing/Save/Tab, outside popup close, same interval count on quick Rest→Toilet, resumed floating after context selection, narrower panel, and no mobile document overflow. Preview operations sent no business API writes. Exiting returns to the unchanged real day.

Both publications took consistent database/config backups and restarted only Graph: PID 453456 → 461437 → 461854. No schema changes. Final backup is under `daily-polish-cache-20261109-e5762e014c47/backup-20261109T141805Z`; database digest `2a542ade588b766b68958ceae31d9312423b98ede5d8ef4e5246f6715fab2b25`. The original 691 nodes, 638 edges, graph version 128 and database identity remain unchanged, with complete logical comparison of all 27 existing business tables. Copycat and other specialist services were untouched.

Private receipts for each publication are retained separately in `.uuma-local/yonc-daily-polish-20261109/` and `.uuma-local/yonc-daily-polish-cache-20261109/`, and their corresponding fixed server releases. No production demonstration notes, tasks or activity records were inserted; no Git commit/push or mission gate approval.
