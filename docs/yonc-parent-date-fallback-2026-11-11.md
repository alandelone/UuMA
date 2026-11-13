# Daily inherits the nearest parent schedule

The user requested that an L4 without a more specific date use its parent's existing project schedule. Daily previously read only the Action's own Daily date, Timeline start or legacy import date, so the synchronized project trees were absent from Daily despite their scheduled roots.

The candidate resolves dates at read time through canonical `contains` parents. The Action's own Daily date or Timeline range wins; otherwise the nearest scheduled L3, L2 or L1 supplies its range. Parent edits, reparenting and native schedule undo are reflected on the next read. It never copies dates into descendants or changes graph versions during reads. Clearing an own Daily date returns to the parent schedule while continuing to suppress obsolete own Timeline/import metadata. Cancelled/superseded ancestor history cannot supply a fallback plan.

Tasks enter Daily when their effective start is reached and unfinished work carries forward after the range ends. Existing completion/activity history rules remain. This supplies a default availability window; it does not allocate every Action to a fixed hour or introduce prerequisite enforcement. The Graph's own saved Timeline dates remain authoritative and unchanged. Daily shows the inherited source and range, and its empty-state text explains both direct and parent schedules. Interface language is preserved.

The source candidate changes only `graph_app/daily.py`, `graph_app/frontend/src/DailyView.tsx`, `graph_app/frontend/src/dailyApi.ts` and the rebuilt entry HTML/JavaScript. No schema or dependency changes. The package is based on the exact currently deployed `daily-zoom-center-20261110-e138ce810266` snapshot, with unrelated dirty development changes excluded.

Validation: 30 Daily backend tests, 106 frontend tests and TypeScript/Vite build passed. A separate fixture replay of the synchronized ten projects contains 266 nodes and shows 50 eligible unfinished L4s on November 11, 2026, all from projects 1–5. Future projects 6–10 remain absent until their own windows begin. All 124 new unfinished Actions retain unset individual dates. Tests cover nearest-parent precedence, explicit Action dates, before-start filtering, overdue carryover, read-only resolution, parent edits, reparenting, undo, clearing an own date back to the parent and historical states.

Candidate archive SHA256: `bcb6307304b8478daacc9b0628887eefdaf3bd9261bf4116b4081ed3bf314b90`.

Published after the user confirmed continuation on November 11, 2026 at 11:58 UTC+08. The active source is `/home/alandelone/.local/share/uuma/production/yonc/releases/inherited-schedule-20261111-bcb6307304b8/source`. Only `uuma-yonc-graph.service` restarted (PID 515872 → 555533); its runtime, canonical database owner, Copycat configuration and other services are unchanged. No migration or business-data update ran.

Independent production health, Daily and HTML/asset HTTP checks passed. Live Daily on November 11 returns exactly the 50 expected L4s, all using inherited dates. All 28 database tables, including the schema revision, match the consistent pre-publication backup; graph version remains 510, with 953 nodes and 899 edges. This feature does not create graph operations or child schedule entries.

Backup: `/home/alandelone/.local/share/uuma/production/yonc/releases/inherited-schedule-20261111-bcb6307304b8/backup-20261111T035835Z/project_graph.sqlite3`, SHA256 `92c438090a2c06dab44657c5126f3f68934a872723003c265631d3a896b24e8f`. Rollback may restore the earlier code/configuration; never overwrite subsequent business writes with this backup.

Receipts and the source package are in `.uuma-local/yonc-inherited-schedule-20261111/`. The isolated preview process was stopped after live verification; its fixture and earlier candidates remain as evidence. Live Daily: https://yonc.95963210.xyz/daily .
