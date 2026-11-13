# Yonc Daily refinement round 4

Authorized continuation of the published Daily UI refinement. Candidate archive SHA256: e0b3675399222d19af2d0fe532d36c0d5339a44ec760579c18c2f6fa3bca7b72. Target: /home/alandelone/.local/share/uuma/production/yonc/releases/daily-round4-20261110-e0b367539922/source. Baseline: daily-round3-20261109-345517376d5a/source. Explicit package manifest:64files,13 changed including built assets; no schema or dependency changes.

## Behavior

Grouping directly toggles type/project and changes its icon. Completed checklist ancestors hide their descendants; completed tasks fold their notes, with manual expansion preserving content. Activity shows its actual visible duration, uses bounded preset zoom from10minutes to24hours, and toggles full day/restored range and position.

Context records are independent location/body-condition change points, effective until the next meaningful point of that category. Backend derives validity and current state without persisting synthetic periods. Historical blank placeholders remain in history but do not affect state. Disabled placeholders cannot be selected; nonemoji options display their names with no circle fallback. Configuration supports drag ordering and arrow fallback, saved using canonical returned revision/options.

The disappearing sample marker was reproduced on the prior public preview following App focus refresh:1marker became0. Per-day stable preview seeds/state and global preview context/options now survive refresh. Sample operations remain isolated from real APIs.

## Validation

25backend tests,106frontend tests,TypeScript/Vite build and Ruff passed. Browser verified changing grouping icons, checklist/task folding, native drag ordering persisted into dropdowns, disabled placeholders, text fallback, marker retention across focus refresh and more than30seconds polling.10minute minimum and24hour/full-day restore passed. Desktop full day fits927/927pixels;390pixel mobile has no horizontal overflow. Preview business API writes:0. Evidence in .uuma-local/yonc-daily-round4-20261110/browser-verification.json.

## Publication

Pending guarded stage, consistent database backup, exact source/hash checks, session handoff/check, Graph-only restart and public verification. Canonical database identity must remain43a70a25-bb31-47cf-9810-80566f4b62da. Copycat capture remains independently controlled. Mission stays verification/pending_review; unrelated work preserved.

Published at2026-11-10T00:26:25Z. Graph PID464697 to497594; service active,NRestarts0. Exact source/package manifest and consistent backup verified. All27existing business tables unchanged,graph128/nodes691/edges638,sameDBidentity/revision. Backup backup-20261110T002623Z SHA2562a542ade588b766b68958ceae31d9312423b98ede5d8ef4e5246f6715fab2b25. No rollback required. Public HTTP200,no-store,currentUf4Q0XqIasset,drag sorting/icon toggle and24h fit verified; marker survived focus and>30second refresh,noJSerrors orpreviewAPIwrites. Isolated real-mode fixture context POST+GET retained both independent states; restart persistence covered by backend regression. Receipts remote_stage/apply/verify.stdout and public-verification.json.
