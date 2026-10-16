# Independent read-only review: PRESENTATION_MODIFIED

Reviewed 2026-10-16. Scope: the live source listed below, supporting service flow and existing test definitions. No product edits, tests, confirmation requests, generation, packaging, model calls, browser actions, session start/close or service changes were performed by this review. The parent's ongoing full regression and unique A215 confirmation were not replayed. This is source review, not another execution pass or scientific approval.

**Result: no substantive defect found in the added presentation outcome within this scope.**

## Guard separation

- `RSTV4/src/rstv4/studio_response_checks.py:117-168` keeps two evidence branches. Scientific `MODIFIED` continues to require a nonempty fixed-baseline text diff and `GENERATED_TEXT_CHANGED` evidence with actual boxes/page/line. `LAYOUT_ONLY`, citation-only, retained or unknown rows do not satisfy that branch.
- `PRESENTATION_MODIFIED` additionally requires an available baseline, an empty raw text diff and equal nonempty baseline/target text digests. Every selected row must be `LAYOUT_ONLY` / `PRESENTATION`, explicitly have `supports_scientific_text_modification is False`, have empty changed text, different nonempty old/new boxes, final location, the exact target/baseline version IDs, distinct PDF digests and the target digest recorded by the context. These conditions do not turn layout into evidence of a scientific prose edit.
- The shared author/reply/revision checks, exact UTF-16 selection, Unicode-boundary handling, nonoverlap, nonempty evidence selection and duplicate-evidence rejection remain active. The API request type adds the explicit outcome without changing those assertion request fields or strict acknowledgement typing (`studio_api.py:105-119`).
- The UI uses separate evidence predicates and clears claims plus acknowledgement on an outcome switch (`studio-response-review.tsx:223-229`). The confirmation predicate rechecks the selected evidence against the current outcome. The explanatory text and history label explicitly distinguish presentation from scientific text modification. A weaker client display predicate cannot bypass server validation.

## Original request IDs and history

- `studio.py:1758-1770` retrieves an existing request's frozen context before attempting fresh context reconstruction. `studio_response_checks.py:173-178` compares the entire canonical request, including manuscript, comment, outcome, context digest and claims, before returning the original check. An identical old request remains idempotent after later edits; reuse with another outcome conflicts.
- The new outcome does not revise prior records. `record:185-190` writes a new check with its frozen context; `history:94-97` reads existing JSON directly. `ResponseHistory:279-286` renders each check's own stored context, including its own evidence and origins, rather than the active manuscript context.
- The inspected test definitions include the real compiler/HTTP confirmation, same-request retry, exported history equality, later reply staleness, preserved history, and changed-outcome collision (`tests/test_studio_presentation_review.py:99-129`). Their execution belongs to the parent's regression; this review did not execute them.

## Explicit limits and remaining coverage

- This review did not independently establish the compiler output, actual PDF geometry, original artifact integrity, native pointer behavior, A215 state, delivery ZIP contents or the complete test result. Those require the parent's retained execution evidence.
- It did not independently review every earlier layout classifier, source/provenance validator, authorization path or database corruption scenario. The new branch receives a server-built context; clients cannot supply arbitrary evidence rows through this request schema.
- The contract records an explicit author acknowledgement and exact selected reply text. It does not automatically prove that every sentence in a natural-language reply is truthful or that scientific conclusions are valid. This limitation is shared with the existing outcomes and is stated by the UI.
- UI acknowledgement reset and evidence-type checks were inspected in source, not exercised here. The existing unit test definitions cover the presentation request/history path; stale/cancel/artifact behavior is outside this narrow review.
- Older history lacking origin snapshots remains incomplete for reverse navigation. A separate read-only reconstruction design is recorded in `../scholar-legacy-origin-design-v1/design.md`; it requires no mutation of old context JSON and cannot retroactively change verification status.

## Exact reviewed source bytes

| File | SHA-256 |
| --- | --- |
| `RSTV4/src/rstv4/studio_response_checks.py` | `40bb5250163e6c065acb233adb9b2bc769f193dd089dc9db0af0e55eee02c43b` |
| `RSTV4/src/rstv4/studio_api.py` | `cba2a102300e8fc78aaf91c5b5ed5178522c47fa258774d72087c135199e67b9` |
| `RSTV4/src/rstv4/studio.py` | `7b6f3ae03d03b3fccd8353f4969b43d276801434f2f40ee8c7d0be618a79886b` |
| `writing-studio/components/studio-response-review.tsx` | `77397bd54474ab27cfe02f1e1e43711b6e7d93f95ef0e7c3386eb1935ee27e87` |
| `writing-studio/lib/studio-types.ts` | `5210d587000901339075d07a394657ba71c18469035d414fec3fb637c67bb1a1` |
| `RSTV4/tests/test_studio_presentation_review.py` | `8254e41ea0d975a7a72c1938f384d676e9bcad12ec32269d75ce34c804291527` |
