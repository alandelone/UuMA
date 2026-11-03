# Scholar initial preview repair: live rollout

The scoped repair became live at 01:55 Malaysia time on 29 October 2026. The user's
release boundary is to run the workflow with lightweight, relevant verification.
Initial workflow availability does not wait for the separate original deep sample.

## Problem and resulting behavior

The first automatic initial-reading job returned a local preview whose deeper-reading
reason referred to `data_measurement`, while that dimension was `NOT_ASSESSED`.
The existing validator correctly rejected the inconsistency. The source PDF was
available and fully parsed; the preview covered only its first part.

The worker now reuses that actual returned preview and makes one durable `thinking`
correction request. Only the affected dimension's state and rationale may change.
All original evidence, layer bindings, Themes, reasons, other dimensions and ordering
must remain exact. The same original validator then checks the result. Insufficient
evidence leaves the job held. No unsupported state is promoted by application code.

The existing quick-read prompt, source partition, PaperSkeleton validator, schema,
night window and manual-priority policy are unchanged. Automatic reading remains
00:00–08:00 Asia/Kuala_Lumpur; manual work has priority throughout the day.

## Scoped verification and deployment evidence

- 103 affected tests passed; lint passed. The unchanged full suite was not repeated.
  The previous release's 1,758 full tests remain historical baseline evidence, not a
  claim that the new release ran that suite.
- An exact copy of the held live job reused its original returned call and reached
  only the new correction operation, without a model submission or canonical write.
- The admitted fixed release is `catalog-3f700f55040d`; its actual package digest is
  `357b1c72dac8dd92e7e8249991ba0f14f6f4f69f5677824e31814988ad68e72a`.
- Cutover waited for the active PDF parse to finish. A consistent canonical backup
  was retained, and only Scholar Web and Catalog Reading were restarted. There was
  no schema migration, whole-database replacement, Graph restart or shared Hermes
  restart.
- Actual process environment readback verified one Web process tree and one Reading
  process tree using the new fixed engine. Each tree has a Windows launcher and its
  Python child; these are not duplicate workers.
- Actual HTTP readback retained all 14 candidate Themes on the original initial card.
- The exact held automatic job was requeued with `manual=False`, fence 5 → 6 → 7.
  Its original returned model event remains unchanged.

At the 01:57 Malaysia readback, the actual correction was still running:
`run_d3f5e38289ee46ce82dcecd591e6a8e8`, operation
`rstv4-model-10ffeac936977972618db8a47fa677b47f89c4cd2c4943ba02f2fd48ef49d52c`.
This confirms dispatch, not successful semantic correction or completed initial reading.
Record the actual returned model identity when its response arrives.

Private evidence is under
`.uuma-local/scholar-catalog-implementation-20261023/`: `initial-preview-checks-v187.json`,
`initial-preview-rehearsal-v188/receipt.json`, `initial-preview-publish-v189/receipt.json`,
`initial-preview-source-delivery-v192/receipt.json`, and
`initial-preview-live-readback-v193.json`. Only five checked source/test files were
delivered to RSTV4; concurrent changes and Git state were preserved.

## Remaining work and rollback

Observe the actual correction and subsequent initial parts without resubmitting the
same operation. The original private deep sample continues separately under observer
v16 and its exact scoped scientific repair engine v21. Its continuation guardian v191
preserves the same request and checkpoints. Content/purpose completion, truthful final
archive, positive FULL selective-copy rehearsal and safe selective canonical append
remain outstanding. This rollout is not full scientific acceptance.

For a code rollback, drain active work, restore the preserved release pointer and
restart only the owned Web/Reading tasks. Preserve all newer canonical writes; do not
restore the pre-cutover database over them. The mission gate remains pending review.
