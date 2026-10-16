# Publication event guard — independent read-only review

No actionable defect found in the reviewed change. Scope: current studio.py set_stage/_set_stage/record_submission_event, new test_studio_submission_events.py, and the existing transaction/scientific-generation helper contracts. No tests, services, models, browser actions or database operations were run by this reviewer; only source and retained receipts were read.

## Verified implementation

- studio.py:743–747 keeps public set_stage inside BEGIN IMMEDIATE and delegates all existing transition/version/science/CAS checks to _set_stage on the same connection. The extraction does not introduce a separate commit or workspace read inside that transaction.
- studio.py:770–788 checks legal transition, manuscript revision, successful GENERATE provenance, current author/generated revision, scientific binding freshness and needs_scientific_review before any stage write.
- studio.py:789 puts the preserve_same_stage early return **after** all validation. Therefore an additional PUBLISHED event at PUBLICATION cannot skip the successful/current version or scientific checks. It preserves stage revision/history only for a valid same-stage event.
- studio.py:1435–1456 records PUBLISHED through the same _set_stage within one BEGIN IMMEDIATE, then inserts submission_events on that exact connection. Existing database.transaction commits after its yield, rolls back on exceptions and closes; return inside the with still exits through commit. Failed event INSERT therefore rolls back both stage and history. No other connection writes or external side effects occur on this path.
- Non-PUBLISHED events preserve existing append-only event behavior without implicitly advancing a stage or author document. Expected manuscript revision for PUBLISHED is read under the same immediate write lock, so no read/update race is introduced by passing it into _set_stage.

## Evidence and limits

The retained focused receipt is PASS, exit0, 41 passed in32.48s (33.28s elapsed), source/tests unchanged307 files. Tests directly cover zero successful versions including same PUBLICATION stage; stale author input; scientific-review flag; illegal PLANNING transition; valid first publication+one history transition; valid same-stage append without extra stage history; same-stage subsequent scientific refusal with complete logical DB preservation; event-insert trigger failure with complete logical DB rollback; and all five nonpublication event types retaining other manuscript/document fields. The trigger and legacy-stage SQL are explicit isolated test setup, not native workflow evidence.

No new assertion weakening or a same-stage validation bypass is apparent. database_state uses SQLite iterdump, so “all tables unchanged” is logical schema/row preservation; it does not prove raw DB/WAL byte identity. The actual helper checks scientific binding freshness as well as the explicit flag using this transaction's connection; the new tests' flag case does not independently exercise every binding-stamp combination, but that is a coverage boundary rather than a demonstrated code defect.

This review supports this PUBLISHED bypass/atomicity fix only. It does not establish ACCEPTED semantics, fixed final manuscript/archive links, native publication event submission, all WF10, original118, final11 integrated acceptance, scientific approval or external journal actions.

Reviewed source SHA256:

- studio.py: 04d222b466d774fb1d82f681fc9b87e2711947c60e2a9a7f90c824102678f0da
- tests/test_studio_submission_events.py: 5bed9afa5b446250e8d5a13ebb3d9fbb8765217a097024852da9cb99d253aa21

Shared session/HANDOFF/gate and product/tests were not modified by this reviewer.
