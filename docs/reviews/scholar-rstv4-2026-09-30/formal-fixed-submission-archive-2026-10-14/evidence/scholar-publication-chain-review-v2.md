# Publication chain — read-only follow-up review

The two backend findings in v1 are resolved in the current source read for this review. One narrow frontend state-consistency issue remains; no backend authorization bypass found. This reviewer did not run tests, models, services, browser or DB operations and did not edit product/shared session files. The active full regression and its reported failure remain with the parent; no repeat was requested or run.

## Resolved backend findings

1. event_record now requires studio_submission_bindings.created_at == submission_events.created_at in its provenance guard. The added bound-timestamp corruption test expects rejection and unchanged logical database. Existing UNBOUND events remain untouched.
2. publication.state now accepts explicit needs_scientific_review, supplied from the actual manuscript by StudioService.get_workspace. CURRENT explicitly requires this flag false. The added legacy no-scientific-binding-stamp fixture completes an archive, changes the pending-review flag, then expects STALE with original completion receipt/all rows retained. This closes the previously identified compatibility gap.

Read-only retained focused receipt .tmp/scholar-publication-chain-chain-v2/receipt.json reports53passed in38.61s, exit0,309source/testfilesunchanged. The parent's real21HTTP/7events/2files/110tables preservation claim is not re-executed by this review.

## Frontend contracts confirmed

- ReadingView supplies the actually displayed GeneratedVersion, activeVersionId and saved workspace publication state. SubmissionPanel derives versionId from generated.generated_version_id and sends that exact ID; historical editorial events can bind the displayed historical version, while SUBMITTED/PUBLISHED/final archive require the displayed version to equal the current active version. It does not silently substitute the active ID for the displayed historical ID.
- boundToForm matches bound version, trimmed venue and round. latestForForm examines the latest event for that venue/round; a later WITHDRAWN or REVISION_REQUESTED makes hasAccepted/hasPublished false. Prior historical ACCEPTED alone cannot re-enable publication.
- If POST succeeds but subsequent workspace GET fails, savedEvent retains the acknowledged receipt, readPending disables forms/uploads/record/archive, and the visible retry calls only onSaved/refreshWorkspace. It does not POST again. Failed POST retries retain the same operation ID when the exact request remains unchanged.
- ARCHIVED is a dedicated completion action with explicit final/proof asset IDs and author acknowledgement. The completion display uses actual backend completion event/version/files/status and retains SHA/byte size for UNAVAILABLE history. Upload success is explicitly not archive success.
- Existing API binding fields and strict acknowledged input match the client request.

## Remaining actionable UI issue

### P2 — Pending science can leave final-action buttons enabled for a legacy generated version

The backend completion fix is correct, but the frontend still passes only stale={workspace.generated_is_stale} into ReadingView. For the exact retained legacy no-stamp case covered by the new backend regression, scientific_generation_is_stale can remain false when needs_scientific_review becomes true and no scientific-review event exists. Thus currentVersion/canEnterPublication/canArchive can remain true even though the backend reports the prior completion STALE and rejects a new protected action. This is UI/server inconsistency and an avoidable failed action, not a server-side guard bypass.

Minimum future fix after the frozen regression boundary: include workspace.manuscript.needs_scientific_review in the effective stale/hold prop or supply a distinct hold flag to ReadingView/SubmissionPanel. Final submission, publication and archive controls should be disabled with a review-required message. Preserve historical receipts and do not invent a changed author/generated version. Add one shipped-component check with active/displayed IDs equal, stale=false, needs_scientific_review=true, accepted/published history present: protected controls must stay disabled and click must create no request.

The STALE completion heading currently says current version changed, but STALE also includes withdrawal or pending scientific review. A neutral “historical archive / current prerequisites changed” label avoids asserting a version change that did not occur. This wording refinement is secondary.

## Scope

These findings address event integrity and frontend/backend contract consistency only. Original118/final11, native complete WF10 acceptance/final/proof/archive flow, external journal actions and scientific approval/quality are not established by this review.

Source SHA256 read in this review:

- studio_publication.py: 649de6d2111cf28eed8e508d7bdff31ce8614dfb68db193286dc73edd5fc4f43
- studio.py: 41949007432e9fe7e71fbbe9a6f0b53d4b658ae537a5faf881ea60da757db7c8
- studio-workspace.tsx: c3c6ce2dda30f46594a6d9f50cc7738372f9a8d3a449a284a1dfe2d4cf879c51
- test_studio_publication_chain.py: f82577a451769eb82fc2e138e516e46d43f0a6b1a7dc64994ce5aa888830fc59
