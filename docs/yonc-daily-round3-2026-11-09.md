# Daily autosave, context controls and overview — 2026-11-09

The user requested a further refinement of the live Daily interface and its temporary preview. This continues the authorized publication scope; mission remains verification / pending_review.

## Delivered behavior

- Notes autosave after 900ms idle, pointer leaving the editor, focus leaving it, switching windows, hiding the page or leaving the view. A snapshot queue allows continued typing during saves. Browser-local drafts and canonical conflict checks remain; a graph-version retry is allowed only if this Action's stored outline is unchanged. Preview saves remain in memory.
- Removed the extra Add step, Save notes and Collapse notes buttons. Enter on an L4 card adds a root step; Enter/Tab/Shift+Tab retain sibling/indent/outdent editing. The stated card interaction is pause-and-collapse on repeated focused-card click, focus-and-expand on the next click. Completed cards may expand notes without starting focus.
- Preview completion/reopen checkboxes now work. The sample contains two projects, six Actions and three Task types. Direct grouping-button clicks toggle type/project without a menu. A regression fixes task types accidentally sharing a grouping key because their cognitive tags are identical. Preview keyboard undo cannot invoke real graph history.
- Daily's gear opens the common Yonc Configuration dialog on its Daily tab. Both context option lists have configurable emoji. Optional emoji maps are stored in the existing runtime JSON with append-only settings history; legacy clients keep their mappings unless the corresponding label is removed.
- Context placement no longer uses a persistent pointer/focus pin. Native selections may be repeated, followed by leaving and returning, without manually closing a frozen panel. Body condition is the left control and its configured emoji appears near the time column; location is the right control/marker. Fixed heart icon is removed. The two controls have more separation.
- Activity blocks show their labels without inline start/end time ranges. The title area provides − / 24h / ＋ controls. Full day fits the available height after accounting for the responsive header and padding; default zoom remains available through +/−.

## Storage and validation

Read-only production audit confirms `daily_runtime`, `daily_intervals`, `daily_changes` and canonical `focus_sessions` in the existing Graph database. Activity, corrections, context effective timestamps and settings have persistent real-mode APIs. Current real interval/context counts are zero because the sample was deliberately isolated; preview operations are not production records.

23 scoped backend and 103 frontend tests pass; TypeScript/build and scoped Ruff pass. Browser checks cover repeated native selections, both emoji sides and saved custom icons, global settings preview isolation, six tasks/two projects/three types, completion, pause-collapse/resume-expand, no manual note buttons, independent column scrolling and full-day fit at desktop 927/927px and narrow 892/892px. Live fixture tests persist concurrent editor changes on window blur and preserve newer typing during a delayed in-flight save. The latter produced two save requests and retained the final text with no alerts. Existing bundle-size/framework warnings remain.

Candidate SHA256: `345517376d5a4bd7cc70579484bd10012a90ff360e9a179be1126e8df8f12537`, 60 scoped files / 12 changed. Baseline is the exact deployed `daily-polish-cache-20261109-e5762e014c47/source`. No schema or dependency change is required. Publication uses a consistent backup, source manifest checks, idle/owner guards and only the Graph service restart. Other Agent work and Copycat's independent capture switch are preserved. Actual publication/verification receipts will be recorded below.

## Publication result

Published at 23:37 UTC+8 to <https://yonc.95963210.xyz/daily>. Fresh sample entry: <https://yonc.95963210.xyz/daily?preview=1&v=345517376d5a>. Fixed server source is `daily-round3-20261109-345517376d5a/source`; only `uuma-yonc-graph.service` restarted, PID 461854 → 464697.

Consistent database and private unit/environment backups were taken under `backup-20261109T153722Z` in the release. Database backup SHA256: `2a542ade588b766b68958ceae31d9312423b98ede5d8ef4e5246f6715fab2b25`. All 27 pre-existing business tables retained identical logical contents. Database identity is still `43a70a25-bb31-47cf-9810-80566f4b62da`, graph version 128, 691 nodes / 638 edges, schema revision `20261105_0005`. No new schema, production sample records, Copycat switch change or other service restart.

Formal browser verification returned HTTP 200 with the current manifest-matched JS, no JavaScript errors and zero business API writes during preview. It showed three distinct type groups (two tasks each), two projects, successful completion/reopen, pause-collapse/resume-expand, editable autosaved notes, no extra note action buttons, the common Yonc settings dialog and custom emoji in their correct sides. Leaving the context controls restores floating/hiding. Inline block times are absent. Full-day heights equal scroll heights at desktop and mobile; no document horizontal overflow. Exit preview returns to the real day, still with zero eligible tasks/interval/context records.

The publication pipeline preserved the handoff and passed its check before switching. Receipt files are in the fixed server release and `.uuma-local/yonc-daily-round3-20261109/`, including `public-verification.json` and production screenshots. Publication checks were slower because the shared append-only session journal is large; no journal history or assertions were removed to accelerate them. Code rollback uses the preceding fixed source/configuration, without restoring a database over newer writes. Mission remains pending review; unrelated planning and specialist work is preserved.
