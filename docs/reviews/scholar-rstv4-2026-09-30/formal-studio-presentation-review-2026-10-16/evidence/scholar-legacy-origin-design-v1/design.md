# Legacy check origins: read-only fixed-version reconstruction

Design only, 2026-10-16. Not implemented, not tested, and not an acceptance pass. Do not modify `studio_response_checks.context_json`, `request_json`, original digests or old evidence IDs. Do not create a new confirmation, generation, package or model call to fill missing historical labels.

## Small complete change

Add one semantic read endpoint, for example:

`GET /api/manuscripts/{manuscript_id}/comments/{comment_id}/response-checks/{check_id}/origins/{evidence_id}`

The caller supplies only the exact check/evidence identity. The server obtains version and revision from that stored check; the browser must not supply an alternate revision, use workspace state or choose the latest generation. No new table or stored cache is necessary.

Return a separate envelope, not a replacement review context:

```json
{
  "status": "RECONSTRUCTED_FROM_FIXED_INPUT",
  "check_id": "original-check-id",
  "evidence_id": "original-evidence-id",
  "original_context_sha256": "original-recorded-digest",
  "source": {
    "manuscript_id": "original-manuscript-id",
    "generated_version_id": "original-generated-version-id",
    "generated_version_number": 6,
    "input_revision": 79,
    "generated_record_sha256": "verified-original-record-digest"
  },
  "origins": []
}
```

`origins` uses the existing `FrozenEvidenceOrigin` shape, including full ordered `intent_thoughts`. The sample array is schematic, not a valid successful result: success must contain the exact proven attributed origin(s). Existing stored origins, if valid, can be returned as `STORED_SNAPSHOT` with the same envelope. Use explicit `UNAVAILABLE` / `AMBIGUOUS` results with stable reason codes when reconstruction cannot be established. Ordinary missing-identity errors should remain scoped 404s.

## Server proof sequence

1. Read the check joined to its comment/review round and requested manuscript, then select the evidence row from that check's frozen context only. Never run the current `response_review_context` to reconstruct old labels. Require the check's stored manuscript, comment, generated version and context identity to agree with its frozen state. Validate the original context digest using its existing serialization contract, excluding only the fields originally excluded by that contract; do not invent a normalization that tolerates altered history.
2. Pin `context.state.generated_version_id` and `context.state.generated_input_revision`; require them to agree with the check record and evidence row's recorded generated version where available. The old check must contain enough fixed identity to prove its target. Missing fixed IDs are `UNAVAILABLE`, not a request to infer them from v-number, display labels, matching prose or current state.
3. Read that exact manuscript version record and compare the digest of its raw `content`/`inputs_json` fields with the old state's recorded `generated_record_sha256`, using the same `response_checks.digest(dict(record))` contract as `state:59-73`. When that recorded hash is absent, expose an explicit weaker/unavailable state rather than silently calling the reconstructed snapshot historically verified.
4. Use the existing read-only `get_generated_version` validator for that version, preserving original model, citation, material and replay-lineage checks. Obtain its original author revision with `get_document_revision`. Require the version input revision to equal the frozen check input revision. Where the old check retained the author's exact serialized-document hash, verify the original revision's exact serialization using the established save/history contract; preserve that hash in the envelope. Do not compare a newly pretty-printed JSON string or relax to partial thought-text equality.
5. Locate by the old evidence row's stable `thought_id`, not by sentence text, list position, current labels or current editor structure. Bind the row's recorded generated paragraph/sentence mapping to that thought in the exact generated version. Missing mapping or an ambiguous origin is unavailable/ambiguous; do not take the first match. **A projected generated paragraph can differ from the original author-bank paragraph.** Use original author-bank `frozen_origins(document, target)` for labels/full Intent text and the verified generated mapping for realization identity; do not require these two paragraph IDs to be accidentally equal.
6. Build the envelope from this verified fixed source. Preserve the old check's response text, evidence, context hash, request ID and CURRENT/STALE status exactly. The envelope means “read back from the fixed input now”; it does not assert that a snapshot existed in the old check, confer scientific validity or upgrade that check.

All operations must remain reads, including helper calls. A missing original PDF need not prevent source navigation if the retained generated record/model/material provenance and exact author input suffice; however missing provenance required by the normal generated-version validator remains unavailable. Never suppress an integrity failure to make navigation work.

## Frontend behavior

Keep the existing snapshot-first `FrozenOrigin` display. When a historical row lacks origins, offer **回查当时固定版本的原思想** as an explicit read action. On success show **从当时固定输入补查 · 成文 v6 / 原稿 r79** and the complete original Intent with the attributed Thought highlighted. Keep this envelope in ephemeral component state, separate from `check.context`; never merge it into the historical evidence or confirmation payload.

Opening a source must not toggle an evidence checkbox. Put its control outside checkbox labels. Key requests by manuscript/comment/check/evidence plus context digest, clear prior results on identity changes, and ignore late responses after a different row/check is opened or the component unmounts. Display loading, retry and unavailable states. Preserve readable old response history if source readback fails. Do not silently navigate the mutable editor or substitute current labels.

## Minimum meaningful verification before adoption

- An old check without origins but with intact fixed record/input hashes returns the exact original Thought/Intent after current labels/text/order have changed; no historical row, digest, status or file changes.
- Two distinct original thoughts mapped to one identical compiled sentence return distinct stable origins; one thought mapped to several sentences preserves the same origin. Include a real correspondence/projection case whose generated slot differs from the author-bank paragraph.
- Cross-manuscript/comment/check/evidence requests cannot read another record. Unknown IDs, absent stable thought/version/revision, ambiguous IDs and altered recorded generated/input context are rejected or explicitly unavailable.
- Broken original generated JSON, model-call linkage, source/material identities or replay lineage remain failures through the existing verifier; no latest-version fallback. Missing original PDF behavior is documented separately from missing model/material provenance.
- Every GET leaves the complete original relevant table/file snapshot unchanged. Before/after byte comparisons include old `context_json` and `request_json`; do not test only the returned payload.
- Frontend tests and actual native navigation verify snapshot-first behavior, clear reconstructed labeling, keyboard access, independent checkbox state, race/late-response handling, unavailable/retry, long full original text and unchanged old CURRENT/STALE display.

This work can close a bounded historical reverse-navigation gap only after implementation and native execution. It does not complete original118 or the integrated11 acceptance by itself.
