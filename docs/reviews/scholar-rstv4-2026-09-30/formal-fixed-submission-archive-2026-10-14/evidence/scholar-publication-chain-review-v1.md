# Publication chain — independent read-only review

Two actionable integrity/state issues found in the reviewed source. No code, database, browser, service, model, test, session handoff or close operation was executed by this reviewer. This reviews the original source state read at task start; main agent may apply fixes separately.

## Findings

### P2 — Legacy generated versions can retain CURRENT completion after scientific invalidation

studio_publication.py:246–251 determines CURRENT from active version, author revision, generated_is_stale, live acceptance and version integrity, but never directly checks manuscripts.needs_scientific_review. StudioService.get_workspace passes generated_is_stale computed from scientific_generation_is_stale plus author revision. The existing compatibility branch in scientific_generation_is_stale returns only current event_id != None when the generated inputs have no saved scientific_binding; it ignores the scientific-review flag in that branch.

Concrete reachable retained-data case: a valid successful legacy generated version has job/studio revision provenance but no scientific_binding stamp. Accept, publish and archive it while review is clear. A later source withdrawal or upstream invalidation sets needs_scientific_review=1 without creating a manuscript_scientific_review_event. The existing helper returns false, author/version remain unchanged, acceptance stays valid, so the new completion readback still says CURRENT. New record writes are correctly refused by the explicit flag in record_submission_event; the defect is the completion status.

Minimum fix: require no pending scientific review when computing completion CURRENT, reading the flag within the same transaction or explicitly passing it from the caller. Do not rewrite the legacy version or event snapshot. Necessary focused test: complete a declared legacy no-stamp version, invalidate its scientific flag through the fixture boundary, then assert completion STALE and all original receipts/files remain exact. No new model or native replay needed.

### P2 — Bound submission timestamps are outside the original-event provenance check

studio_publication.py:45–52 compares the frozen event's owner/venue/round/status/detail and snapshot SHA, but omits submission_events.created_at. record_binding already stores the exact event timestamp separately in studio_submission_bindings.created_at. If a bound event timestamp is accidentally changed, event_record returns BOUND with the altered displayed time; its “original submission event” provenance check still succeeds. Other mutable event fields are already checked.

Minimum fix: also compare stored.created_at with event.created_at for bound events. Existing UNBOUND legacy events must stay UNBOUND and must not be assigned a synthetic timestamp/snapshot. Focused corruption test: modify only the bound event timestamp in an isolated fixture, then require provenance rejection; retain the original bytes/receipt as the test baseline. This is integrity checking against accidental row damage, not a claim that normal APIs expose timestamp editing.

## Contracts that read correctly

- Explicit earlier generated versions are owner-checked and freeze successful GENERATE provenance, revision, raw version/input digests and recorded template context. Previously unbound event rows are never backfilled by event_record.
- Acceptance is scoped to the same venue/round/version. Latest per-scope WITHDRAWN/REVISION_REQUESTED/other nonacceptance state invalidates a prior acceptance; later PUBLISHED/ARCHIVED retains the specific accepted_event_id. New archive needs an existing publication of the exact version and explicit author acknowledgment.
- Operation replay checks owner and full normalized request digest before returning the exact original immutable event. It deliberately does not reinterpret the replay as a new event after author edits; changed request with the same operation ID conflicts.
- Archive files are checked for asset ownership, DOCUMENT/READY state, resolved path inside Studio storage, actual existence, byte count and actual SHA. File damage yields UNAVAILABLE while retained event/files metadata remain readable.
- Binding insert, event insert and protected stage/history changes use one transaction. Existing _set_stage version/science checks still occur before same-stage early return.
- Missing acknowledgment/final/proof/publication, wrong owner, tampered/missing files, rejected stage, append-only snapshots and atomic insert failure have focused tests. This reviewer read the tests; the supplied 18PASS/22PASS results were not rerun.

## Scope boundary

This review does not prove complete WF10, native user publication/acceptance/archiving, scientific approval, real external journal events, original118 or final11 workflow completion. Files are explicitly local author-selected final/proof records, not an assertion that arbitrary uploaded content matches a scientific claim.

Reviewed source SHA256:

- studio_publication.py: 5f72d58b49901e12f6386f84e2789c9b1aadca33d199b0e98e1709b13eda9c25
- studio.py: 4d12509dc7ef2689ce91b000c0465abb7bd7200f6a8cd4a5110d6861f5127cf3
- studio_api.py: 0550c2bf33d50212034db99f09d1a0b1a01a7b9378d900a8bed08296c9d97aac
- tests/test_studio_publication_chain.py: 4b32c1f2758dab1667f5d25b50b1a87733c3c9deeba8dd4279b4c3471fb62cd2
