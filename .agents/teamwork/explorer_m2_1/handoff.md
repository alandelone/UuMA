# Technical Investigation & Blueprint: Milestone M2 (W22, W23, W24)
**Agent**: `explorer_m2_1`  
**Milestone**: M2 (Delivery 3 — PaperSkeleton Deep Analysis: W22, W23, W24)  
**Date**: 2026-11-04  
**Working Directory**: `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\explorer_m2_1\`

---

## 1. Observation

### 1.1 W22: v419 Deep-Role Artifacts and NEEDS_HUMAN Boundary
1. **Existing Artifact Directory**:
   - Path: `C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\new-role-recovery-proposal-v419\`
   - Contains:
     - `proposal.json` (size: 1,084 bytes)
     - `exact-failed-request.json` (size: 10,214 bytes)
     - `prompt.txt` (size: 10,045 bytes)
     - `original-state.json` (size: 1,355,169 bytes)
2. **Proposal Contents (`proposal.json`)**:
   ```json
   {
     "at": "2026-10-29T16:13:14.533877+00:00",
     "status": "PREPARED_AWAITING_NEW_EXPLICIT_APPROVAL",
     "job_id": "skeletonviewjob_1216bde784964dc42990bbd92b55cd7431a23a60a43d94a05fe1bd58c6ec81e6",
     "expected_fencing_token": 211,
     "failed_call_id": "catalogdeepmodelcall_3098dded1bb69f1f48bc449897135f18eaa4bce2c2c86bd69324212650b6d96a",
     "failed_run_id": "run_37f86c0abcd84a7b8b82b4e001994410",
     "failed_model": "gemini-3.6-flash",
     "theme": "Private Blockchain Governance and Trade-offs",
     "task": "skeleton_theme_role_json_recovery",
     "prompt_version": "approved-role-json-v1",
     "tier": "thinking",
     "prompt_sha256": "81c5ff91c712fcd0a60647e272e5826e06ed260fd376f3aa1e5f27b6cbce1f67",
     "maximum_additional_model_requests": 1,
     "earlier_single_request_approval_consumed": true,
     "actual_reply": "C:\\Users\\Alandelone\\CodeSpace_Local\\UuMA\\.uuma-local\\scholar-catalog-implementation-20261023\\held-role-inspection-v415\\actual-run-v416.json",
     "new_model_submissions": 0,
     "canonical_job_changed": false,
     "source_and_successes_preserved": true
   }
   ```
3. **Exact Failure Cause (`held-role-inspection-v415\actual-run-v416.json`)**:
   - `model`: `gemini-3.6-flash`
   - Content returned: `"I seem to be encountering an error. Can I try something else for you?"`
   - Finish reason: `stop`.
   - Error recorded on job: `last_error = 'Model output is not a JSON object'`.
4. **Current Pinned Database State**:
   - Database: `C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\real-reading-compact-refs-v1\library\data\catalog.db`
   - Table `catalog_reading_jobs`:
     - `job_id`: `skeletonviewjob_1216bde784964dc42990bbd92b55cd7431a23a60a43d94a05fe1bd58c6ec81e6`
     - `job_type`: `SKELETON_VIEW`
     - `status`: `NEEDS_HUMAN`
     - `fencing_token`: 211
     - `last_error`: `Model output is not a JSON object`
   - Table `catalog_reading_events` admission counts:
     - `MODEL_STAGE_RETRY_REQUESTED`: 3
     - `SKELETON_ROLE_FORMAT_RECOVERY_ADMITTED`: 1
     - `SKELETON_DIGEST_ENVELOPE_READER_FIX_APPLIED`: 2
   - Prior authorization: exactly one prior grant existed for `catalogdeepmodelcall_3780efeac11a4533e017541539f967ebbd68d50faa902db5245926b55df68790` (authorized under v329 "批准仅这一次"). That grant is consumed.
5. **Review Status (`distinct-role-review-v570.json`)**:
   - `status`: `PREVIEW_ONLY_AWAITING_SEPARATE_DIRECT_HUMAN_REPLY`
   - `direct_user_approval_received`: false
   - `actual_new_model_result_received`: false
   - `actual_worker_resumption_verified`: false
   - `model_calls`: 0, `database_writes`: 0, `may_submit`: false, `may_admit`: false

### 1.2 W23: Authorized Admission & Single-Call Submission Contracts
1. **Submission Control (`distinct_role_submit_once_v559.py`)**:
   - Hardcoded approval pin: `DIRECT_HUMAN_APPROVAL_SHA256 = None` (lines 22, 49-51).
   - Verifies that approval hash does not equal old v329 approval hash: `expected != OLD_APPROVAL_SHA` (`93d135b24e90d61ca2bc049ebe05cad541947ec85708d3f0f92d537e8e316f0e`).
   - Verifies `CLAIM_DIR / 'human-approval.json'` matches scope:
     ```python
     scope = {
         'scope': 'distinct-role-v419',
         'job_id': JOB,
         'failed_call_id': FAILED,
         'expected_fencing_token': 211,
         'prompt_sha256': PROMPT_SHA,
         'maximum_additional_model_requests': 1,
         'channel': 'thinking',
         'decision': 'APPROVED',
     }
     ```
   - Atomic reservation via `reserve_once` in `second_role_claim_v531.py` creating `submission-claim.json` with exclusive open mode (`'x'`).
   - Submits single POST to `ENDPOINT + '/runs'` with header `Idempotency-Key: operation` and `model: 'thinking'`.
   - Before POST, creates `single-post-attempt.json` with `'xb'` mode (`maximum_posts: 1`).
   - If POST is unconfirmed or times out, returns `POST_UNCONFIRMED_RECONCILIATION_REQUIRED` and strictly prevents second POSTs (tested in `test_distinct_role_submit_once_v560.py:65`).
2. **Admission Implementation (`prepare_second_role_admission_v556.py`)**:
   - Function: `admit_distinct(service, job_id, *, expected_fencing_token, bundle, request_id, reason)`
   - Requires `job['status'] == 'NEEDS_HUMAN'`, `job['fencing_token'] == 211`, `job['last_error'] == 'Model output is not a JSON object'`, exactly one prior grant.
   - Updates `catalog_reading_jobs SET status='READY', fencing_token=fencing_token+1, lease_owner=NULL, lease_until=NULL, available_at=?, updated_at=?, last_error=NULL WHERE job_id=?`.
   - Records grant and event `_event(conn, job['intent_id'], SECOND_EVENT, grant, job_id)`.
   - Records request in `catalog_reading_requests`.

### 1.3 W24: Genuine L1–L4 Source Coverage & Sample paper_dd83af8026e3
1. **Sample Paper Provenance**:
   - `paper_id`: `paper_dd83af8026e39dd2a2e9316622a7ca49`
   - Title: `Blockchain applications in microgrids an overview of current projects and concepts C2017-`
   - PDF SHA256: `cad2c7cd590728783e6112cb8e584419b155683956f8c44fd20508d873c3dd6f`
   - Parse Run ID: `parse_run_c3873033e0729a9dab355d6af14622ac`
   - Paper Version ID: `paper_version_54b7e08d63f54fbc87d654f2dd1e4e93`
2. **Document Blocks Inspection (`document_blocks` in `catalog.db`)**:
   - Total blocks: exactly 85 blocks (sequence `0` to `84`).
   - Block 0: `block_2a2495f329c498c72f40a3a259e82bd4` (`HEADING`, page 1, "Blockchain Applications In Microgrids An overview of current projects and concepts").
   - Block 84: `block_7cdb04386ddc81fd3a7dd8bee8edf404` (`TEXT`, page 6, "Consortia and organizations for cooperation between companies, DSOs, TSOs, and national governments are needed.").
3. **Skeleton State (`paper_skeletons` & `skeleton_units` in UuMA compact library `catalog.db`)**:
   - Skeleton row: `skeleton_id = 'skeleton_e87a79f2f1e6fc99acb67b4568757132'`, `version = 1`, `extractor_model = 'gemini-3.8-flash'`, `prompt_version = 'original-paperskeleton-located-windows-v2'`, `content_digest = '1ab17b66767104f4dd28014248c55664ab48c0223cd97b432930fcba12cf6455'`.
   - Total `skeleton_units`: exactly 85 units (`seq_idx` 0 to 84), matching 1:1 with all 85 document blocks.
   - Total `skeleton_triplets`: 347 triplets across units.
   - Total `skeleton_checkpoints`: 340 checkpoints (85 blocks × 4 layers), all in status `SUCCEEDED`.
   - `skeleton_runs`: `skeleton_run_a131f3224b1d599737673680a93aafae`, status `SUCCEEDED`.
4. **Codebase Implementation in RSTV4**:
   - `src/rstv4/skeleton_contract.py`:
     - Schema definitions: `Atom`, `Triplet`, `ObjectAnchor`, `BlockAtoms`, `DiscourseRelation`, `BlockIntents`, `BlockRole`.
     - Span slicing & verification: `source_spans()`, `located_span()`, `canonical_atoms()`, `validate_layers()`, `canonical_units()`.
     - Ontology literals:
       - L4 MacroRole: `Abstract`, `Motivation_Intro`, `Related_Work`, `Core_Methodology`, `Empirical_Experiment`, `Result_Performance`, `Deep_Discussion`, `Global_Conclusion`, `Front_Matter`, `Acknowledgment`, `Funding`, `References`, `UNKNOWN`.
       - L3 Intent: `Fact_Background`, `Research_Gap`, `Paper_Objective`, `Proposed_Idea`, `Method_Overview`, `Method_Detail`, `Method_Justification`, `Evaluation_Metric`, `Figure_Intro`, `Objective_Finding`, `Comparison`, `Explanation`, `Limitation`, `Boundary_Condition`, `Implication`, `Conclusion`, `Future_Work`, `Formal`, `UNKNOWN`.
       - L2 RelationType: `Cause`, `Contrast`, `Elaboration`, `Support`, `Condition`, `Sequential`, `Parallel`, `Coreference`, `Citation`, `Topic_Shift`, `UNKNOWN`.
       - L1 EpistemicStatus: `AUTHOR_REPORT`, `AUTHOR_HYPOTHESIS`, `AUTHOR_INTERPRETATION`, `BACKGROUND`, `UNKNOWN`.
   - `src/rstv4/skeleton_dspy.py`:
     - Signatures: `AtomicExtraction` (L1), `DiscourseExtraction` (L2), `IntentExtraction` (L3), `MacroExtraction` (L4), `PaperArgumentAssembly`.
     - Predictor module: `PaperSkeletonProgram` coordinating all 4 layers sequentially with bounded reflection/retry.
   - `src/rstv4/catalog_skeleton_views.py`:
     - Verifies snapshot against receipts (`snapshot()`), content pipelines (`content_pipeline()`), and enforces view scope (`require_view()`).
   - Tests:
     - `tests/test_skeleton_contract.py`: verifies required source span IDs, chunking without gaps, quote localization, unit canonicalization, and fail-closed validation.
     - `tests/test_catalog_skeleton.py`: tests `/api/catalog/papers/{paper_id}/skeletons/{skeleton_id}` lossless retrieval of all 4 layers.

---

## 2. Logic Chain

1. **W22 Decision Boundary Logic**:
   - From §3 & §4 (W22, W23) of the work plan and `proposal.json`, the v419 deep-role failure occurred on job `skeletonviewjob_1216bde784964dc42990bbd92b55cd7431a23a60a43d94a05fe1bd58c6ec81e6` during content view generation for theme `"Private Blockchain Governance and Trade-offs"`.
   - The provider returned a conversational non-JSON string (`"I seem to be encountering an error. Can I try something else for you?"`), causing `last_error = 'Model output is not a JSON object'` and setting job status to `NEEDS_HUMAN` at fence `211`.
   - Because the prior v329 grant (`human-approval-v329.json` "批准仅这一次") was already consumed for the first failure, the system cannot automatically retry.
   - The proposal `new-role-recovery-proposal-v419` was created in `PREPARED_AWAITING_NEW_EXPLICIT_APPROVAL` status with zero model submissions.
   - Therefore, the boundary is pinned strictly at `NEEDS_HUMAN`. Proceeding requires a direct user decision:
     - If approved: User provides an explicit grant with `decision: 'APPROVED'` and matching scope.
     - If declined: User sets `decision: 'DECLINED'`. No model call is submitted; the disposition is durably recorded.

2. **W23 Execution vs. Decline Contract Logic**:
   - From `distinct_role_submit_once_v559.py`, `DIRECT_HUMAN_APPROVAL_SHA256` is initialized to `None`. Any attempt to execute without hardcoding the exact sha256 of `human-approval.json` throws `PermissionError`.
   - Exclusive filesystem operations (`_exclusive` with mode `'xb'`) ensure idempotency and enforce `maximum_posts: 1`. Even in race conditions or network timeouts, the POST cannot be repeated automatically.
   - Once a confirmed run ID is obtained, `prepare_second_role_admission_v556.py` (`admit_distinct`) executes within a `BEGIN IMMEDIATE` database transaction, validating fence `211`, incrementing to `212`, setting status to `READY`, and logging `catalog_reading_events`.
   - If the user declines, no model call occurs. A declined receipt is preserved in the audit trail, and the job remains unsubmitted and bounded.

3. **W24 Genuine L1–L4 Source Coverage Logic**:
   - From inspection of `catalog.db`, `paper_dd83af8026e39dd2a2e9316622a7ca49` has 85 document blocks under `parse_run_c3873033e0729a9dab355d6af14622ac`.
   - In the compact library catalog (`real-reading-compact-refs-v1/library/data/catalog.db`), `skeleton_e87a79f2f1e6fc99acb67b4568757132` covers all 85 units (`seq_idx` 0 to 84) and has 340 completed checkpoints (`85 × 4`).
   - In `RSTV4/data/catalog.db`, the 85 blocks are stored in `document_blocks`.
   - The generation process in `skeleton_contract.py` and `skeleton_dspy.py` guarantees complete coverage:
     - L1 extracts propositions anchored to verbatim quotes and indexed source spans.
     - L2 links propositions via typed discourse relations.
     - L3 assigns communicative intents to propositions.
     - L4 assigns macro roles to document blocks.
     - `canonical_units()` joins these layers losslessly.
   - Thus, PaperSkeleton already has the complete 85-block L1–L4 structure implemented and validated by tests.

---

## 3. Caveats

1. **Database Bifurcation**: The complete `paper_skeletons` (85 units, 347 triplets, 340 checkpoints) for `paper_dd83af8026e3` currently resides in `.uuma-local/scholar-catalog-implementation-20261023/real-reading-compact-refs-v1/library/data/catalog.db`. In `RSTV4/data/catalog.db`, `document_blocks` has the 85 blocks, but the `paper_skeletons` table does not yet have this skeleton record populated. During delivery execution, the skeleton data will need to be synced/admitted into `RSTV4/data/catalog.db` using the verified adoption helper.
2. **Detached Worker Replay**: In `distinct-role-review-v570.json`, `original_owner_readonly_replay_passed` is `true`, but `detached_worker_replay_passed` was noted as `false` pending the resolution of execution-origin context. The work plan notes: "Resolve detached-worker execution-origin context through an explicit scoped contract, not a writable identity bypass."
3. **Execution Freeze**: Under Governing Execution Constraints (§9), all implementation remains paused until orchestrator/user gate transition. This report performs strictly read-only analysis.

---

## 4. Conclusion

1. **W22**: The v419 deep-role failure is fully captured and isolated in `new-role-recovery-proposal-v419/`. It is pinned at `NEEDS_HUMAN` (fencing token 211) due to a Gemini fallback response. It cannot be auto-retried. User approval requires a distinct JSON approval file with matching parameters and SHA256 pinned in code. User decline results in zero model calls and durable recording of the declined disposition.
2. **W23**: If approved, single-call submission is tightly constrained by `distinct_role_submit_once_v559.py` (idempotency key, exclusive file locks, max 1 post, timeout fail-closed) and admitted atomically by `admit_distinct()` in `prepare_second_role_admission_v556.py`. If declined, zero model calls occur and the disposition is recorded.
3. **W24**: Genuine sample `paper_dd83af8026e3` has exactly 85 document blocks (sequence 0–84). Its complete PaperSkeleton (`skeleton_e87a79f2f1e6fc99acb67b4568757132`) contains 85 units, 347 triplets, and 340 succeeded checkpoints across L1 (propositions), L2 (relations), L3 (atom intents), and L4 (macro roles). The architecture, generation mechanics, and unit tests in RSTV4 (`skeleton_contract.py`, `skeleton_dspy.py`, `tests/test_skeleton_contract.py`, `tests/test_catalog_skeleton.py`) provide the complete foundation for Delivery 3.

---

## 5. Verification Method

To independently verify these findings:

1. **Verify v419 Proposal and Failure File**:
   ```powershell
   Get-Content "C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\new-role-recovery-proposal-v419\proposal.json"
   Get-Content "C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\held-role-inspection-v415\actual-run-v416.json"
   ```
2. **Verify Job Status and Fencing Token**:
   ```powershell
   python -c "import sqlite3; conn = sqlite3.connect('file:C:/Users/Alandelone/CodeSpace_Local/UuMA/.uuma-local/scholar-catalog-implementation-20261023/real-reading-compact-refs-v1/library/data/catalog.db?mode=ro', uri=True); cur = conn.cursor(); print(cur.execute(\"SELECT job_id, status, fencing_token, last_error FROM catalog_reading_jobs WHERE job_id='skeletonviewjob_1216bde784964dc42990bbd92b55cd7431a23a60a43d94a05fe1bd58c6ec81e6'\").fetchone())"
   ```
   *Expected*: `('skeletonviewjob_1216bde784964dc42990bbd92b55cd7431a23a60a43d94a05fe1bd58c6ec81e6', 'NEEDS_HUMAN', 211, 'Model output is not a JSON object')`
3. **Verify All 85 Document Blocks**:
   ```powershell
   python -c "import sqlite3; conn = sqlite3.connect('file:C:/Users/Alandelone/CodeSpace_Local/RSTV4/data/catalog.db?mode=ro', uri=True); cur = conn.cursor(); print('Block count:', cur.execute(\"SELECT COUNT(*) FROM document_blocks WHERE parse_run_id='parse_run_c3873033e0729a9dab355d6af14622ac'\").fetchone()[0])"
   ```
   *Expected*: `Block count: 85`
4. **Verify Skeletons, Units, Triplets, and Checkpoints**:
   ```powershell
   python -c "import sqlite3; conn = sqlite3.connect('file:C:/Users/Alandelone/CodeSpace_Local/UuMA/.uuma-local/scholar-catalog-implementation-20261023/real-reading-compact-refs-v1/library/data/catalog.db?mode=ro', uri=True); cur = conn.cursor(); print('Units:', cur.execute(\"SELECT COUNT(*) FROM skeleton_units WHERE skeleton_id='skeleton_e87a79f2f1e6fc99acb67b4568757132'\").fetchone()[0]); print('Triplets:', cur.execute(\"SELECT COUNT(*) FROM skeleton_triplets st JOIN skeleton_units su ON st.unit_id=su.unit_id WHERE su.skeleton_id='skeleton_e87a79f2f1e6fc99acb67b4568757132'\").fetchone()[0]); print('Checkpoints:', cur.execute(\"SELECT COUNT(*) FROM skeleton_checkpoints WHERE status='SUCCEEDED'\").fetchone()[0])"
   ```
   *Expected*: `Units: 85`, `Triplets: 347`, `Checkpoints: 340`
5. **Run Core Contract Tests in RSTV4**:
   ```powershell
   cd C:\Users\Alandelone\CodeSpace_Local\RSTV4
   pytest tests/test_skeleton_contract.py tests/test_catalog_skeleton.py
   ```
