# Historical origins: separate read-only source review

Reviewed 2026-10-16 against the exact source hashes below. **No substantive defect found within the requested scope.** This was a separate review of the complete backend/frontend change, not another acceptance execution. The reviewer previously implemented the frontend portion; this is not a claim of a second independent frontend author.

No product files were edited, and no business action, confirmation, model call, generation, package, browser, service or regression was run during this review. Only this review document was added. Test definitions were inspected; their successful execution is evidence owned by the parent run, not independently reproduced here.

## Fixed historical identity and exact JSON bytes

`studio_history_origins.read_origins` first scopes the check through its stored manuscript/comment and the comment's review round. Unknown or foreign manuscript/comment/check identities fail the scoped lookup. Evidence is selected only from that check's stored context, with unknown evidence rejected and duplicate evidence explicitly ambiguous.

Before returning any source, the reader compares the original context digest, state digest, request context/manuscript/comment/request-ID/outcome and stored state owner. It then pins the stored generated-version ID and input revision, checks the row's version and original check's version, and requires that the check was taken at that generated author revision. No active generation, latest revision or current label is substituted.

The frozen generated-record comparison uses `digest(dict(record))` for exactly the stored `content` and raw `inputs_json` strings, matching the original `response_checks.state` contract. It also independently checks the target text digest. An equivalent JSON object with changed serialized `inputs_json` bytes is therefore not silently accepted.

`studio_read_views.document_revision(..., include_serialized_sha=True)` retains the selected original `document_json` / history `before_json` / `after_json` string and hashes that string directly as UTF-8. It does not reconstruct or normalize JSON before hashing. The existing save path writes `_json(document)` to both the live document and its matching history snapshot, so a later revision can be compared with the exact serialized-document digest captured by the old check. The new option is additive; existing callers retain their prior response shape.

## Original provenance and template projection

The reader calls the existing fixed generated-version validator in the same read transaction. That preserves its original model-call/input, source/material and layout replay lineage checks. The returned generated input revision/version and exact author serialized digest must agree with the frozen check before any original text is exposed.

A recorded row must identify one verified generated paragraph realization and one recorded sentence index whose sentence text is exactly the recorded row text and whose thought mapping contains the stable original Thought ID. Labels and prose similarity are never used to guess the origin. The original author-bank `frozen_origins` result must be unique; absent and ambiguous origins remain unavailable/ambiguous, and a stored origin snapshot that disagrees is rejected.

The mapping change resolves generated paragraph placements by original Thought ID and rejects multiple target or baseline placements. It uses the matching baseline placement for sentence comparison. The returned source labels/full Intent remain from the original author bank. Thus a template's generated slot ID can differ from the original author's paragraph ID without losing or fabricating the original thought identity. The inspected real-template test explicitly includes two original thoughts sharing one compiled sentence and different author/generated paragraph IDs.

This readback navigates original source text; it does not re-establish a missing PDF location, upgrade a response check or establish scientific validity. Its intentionally supported missing-PDF case does not compile a replacement PDF.

## Read-only history and frontend isolation

The new service entry opens a read transaction and calls the source reader. The inspected path performs SELECTs, existing provenance reads and digest calculations; it does not call workspace initialization, confirmation, save, generation or packaging. The reader returns a separate envelope and contains no update of old context/request/digests. Existing response-check/history mutation rules are outside this new path and remain unchanged by the diff.

The frontend passes the owning manuscript/comment explicitly. Existing stored snapshots use the existing frozen-origin path; only old non-layout evidence without a snapshot gets an explicit read button. Successful supplemental data must match the check ID, evidence ID, original context SHA, owner, version ID/number, revision, original generated-record SHA and author-document SHA. Original IDs/text fields, complete ordered Intent thoughts, selected-thought identity/text and duplicate entries are checked before rendering.

The response is initially treated as `unknown` and narrowed only after runtime validation. Supplemental results remain in component-local state; they are not merged into `check.context`, evidence, request or confirmation state. The source control is outside evidence-checkbox labels. Loading activation is deduplicated; every completion checks mount state, request serial and the complete pinned identity. Identity changes clear previous state and cleanup invalidates old requests. Unavailable/error states leave historical replies readable and offer retry. Known failure codes have specific Chinese explanations; unknown codes/strings are not echoed as source failure details.

## Inspected tests and remaining limits

The new backend test definitions cover exact old readback after current edits, repeated reads with complete table/file equality, scoped unknown/foreign IDs, nine corruption/insufficiency variants, unchanged history state, missing original PDF without recompilation and a real template-projected shared sentence with distinct original Thought IDs. Related frozen-origin tests cover full author-bank context, historical context retention and citation-only evidence refusing scientific modification.

The frontend controlled tests cover explicit encoded no-store GET without a body, no automatic request, loading deduplication, full original source display, unchanged serialized history, success-envelope identity/hash/shape rejection, missing fixed hashes, retry after failures/ambiguity, old-check late completion, unmount late completion and known/unknown user-facing reason text. Existing presentation/prose evidence predicates and acknowledgement tests remain present.

These are coverage observations from source, not fresh pass counts. The review did not independently exercise actual HTTP/native readback, pointer/keyboard layout, a real browser's focus/scroll behavior, current all-table/file snapshots or the parent's full suite/build. No final original118 or integrated11 completion is implied.

Two bounded hardening/coverage limits remain; neither exposed a wrong-origin success path in this review:

- The new generated-placement ambiguity branches have no directly named test for `AMBIGUOUS_AUTHOR_REALIZATION` / `AMBIGUOUS_BASELINE_REALIZATION` in the inspected Studio tests. The real template test covers the positive single-placement case. A future focused fixture should explicitly preserve unknown/ambiguous attribution for multiple placements.
- The graceful unavailable wrapper catches the existing verifier's declared `RSTV4Error`, `ValueError` and `OSError` failures. Arbitrary structural database corruption causing `KeyError`, `TypeError` or `AttributeError` in an existing verifier is not exhaustively tested here and may surface as an HTTP failure rather than a specific unavailable reason. The client still withholds supplemental origins and retains history on such failures. This review does not claim exhaustive corruption diagnostics or resistance to an actor rewriting all authoritative hashes and records together.

## Exact reviewed source bytes

Paths are relative to `C:/Users/Alandelone/CodeSpace_Local/`.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `RSTV4/src/rstv4/studio_history_origins.py` | 6295 | `7952f79048ab8484994712e28bca76342ceaeeea02575bf3bbeae85ff66f9454` |
| `RSTV4/src/rstv4/studio_read_views.py` | 14702 | `fdaf71276fca52b74531375fcef77a10ca9eb01fa07cdffde409fc7fa8f5455a` |
| `RSTV4/src/rstv4/studio.py` | 160512 | `e0989b52e8a7041006475aea37b529b0c8c363c5a62776475b29a6367325fde3` |
| `RSTV4/src/rstv4/studio_api.py` | 28848 | `f4d89fe9d442828dd655c33785ebc9ad9efeb827369af1037e9ed649b157c765` |
| `RSTV4/src/rstv4/studio_revision_mapping.py` | 17521 | `f6e756e2c1a804f1660784367645f5ba600413f2bad6b21dbca48e09992201e0` |
| `RSTV4/tests/test_studio_historical_origins.py` | 12061 | `d3ec7f44949993ec544bd186202c6ab8e5928a0cc4d865d037003cc7d0b74e7d` |
| `RSTV4/tests/test_studio_frozen_origins.py` | 7218 | `5025df2d6cb68ea391f8e21936532e9203208d97cd0de4d55285f1404bb36f8e` |
| `writing-studio/components/studio-response-review.tsx` | 39560 | `ba55105d9daad1f858446b162b95b5f050b51f20da692bcf0dbe5bfc0f3aafaf` |
| `writing-studio/lib/studio-api.ts` | 13470 | `e19f8f9e805014808fab5aba70f1ff37826769bc1b98e3640c98e45b9dff0b2d` |
| `writing-studio/lib/studio-types.ts` | 17812 | `450e44abb40dc998f340d1284275d17990799ca877d267cf0e0438f1408bdf39` |
| `writing-studio/tests/unit/studio-response-review.cjs` | 29568 | `f95e677e7b3a667e5aff32d4b8d104e82b202c7fe7edbeb6f98cb791be2a0e6a` |
