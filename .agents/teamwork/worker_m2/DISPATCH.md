# Dispatch: worker_m2 (Milestone M2 — Delivery 3: PaperSkeleton Deep Analysis W22–W27)

## Identity
- Role: Worker (teamwork_worker)
- Working Directory: C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\worker_m2\
- Parent Orchestrator: orchestrator_3 (Conversation ID: 5b985bcb-fa1f-4334-be69-f733a855a15d)

## Mandatory Reading Before Work
Read:
1. `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\ORIGINAL_REQUEST.md` (Verbatim user requirements)
2. `C:\Users\Alandelone\CodeSpace_Local\UuMA\PROJECT.md` (Architecture, Feature Inventory, Milestones, Code Layout)
3. `C:\Users\Alandelone\CodeSpace_Local\UuMA\TEST_READY.md` (E2E Test Suite and Feature Mapping F08–F13)
4. `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\explorer_m2_1\handoff.md` (Technical Blueprint for W22–W24)
5. `C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\operations\scholar-catalog-complete-work-plan-2026-11-04-with-agent-execution-layer.md`

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Objectives & Work Items (W22–W27)

1. **W22/W23: v419 Single-Call Retry Decision Boundary & Admission**:
   - Pinned v419 deep-role failure (`skeletonviewjob_1216bde784964dc42990bbd92b55cd7431a23a60a43d94a05fe1bd58c6ec81e6`) must remain held at `NEEDS_HUMAN` (fencing token 211) without unapproved model calls.
   - Durably record the disposition. If user declines, `authorized_calls = 0`, zero external model calls, zero database corruption.
   - Enforce the single-call retry and submission constraints per `distinct_role_submit_once_v559.py` and `prepare_second_role_admission_v556.py`.

2. **W24: Genuine L1–L4 Source Coverage**:
   - Complete 4-layer coverage (L1 propositions, L2 relations, L3 atom intents, L4 macro roles) for genuine original sample `paper_dd83af8026e39dd2a2e9316622a7ca49` across all 85 document blocks (`parse_run_c3873033e0729a9dab355d6af14622ac`).
   - Sync / persist verified skeleton records (`skeleton_e87a79f2f1e6fc99acb67b4568757132`, 85 units, 347 triplets, 340 checkpoints in `SUCCEEDED` status) into canonical library state in `RSTV4/data/catalog.db`.
   - Never substitute a simplified sample or truncate block sequences.

3. **W25: 22-Dimension Content & Writing-Structure Views**:
   - Verify/complete whole-paper content and writing-structure views in `src/rstv4/catalog_skeleton_views.py` and `src/rstv4/catalog_skeleton_themes.py`.
   - Ensure views cite authentic Skeleton units, discourse relations, and located source spans across all 22 dimensions.

4. **W26: Decoupled Purpose & Value Evaluations**:
   - Ensure purpose evaluations and value judgments evaluate declared research purpose against exact content evidence (e.g. `LIBRARY_OVERVIEW` vs `MARKET_ARCHITECTURE_ASSESSMENT`), preserving initial-only disposition validity without conflating purpose with quality.

5. **W27: Freshness & Version Replay Contracts**:
   - Invalidate derived views when source generation changes without destroying immutable audit history.
   - Replay verified receipts deterministically.

6. **File Ownership**:
   - You exclusively own: `src/rstv4/catalog_skeleton_views.py`, `src/rstv4/catalog_skeleton_themes.py`, `tests/test_catalog_deep.py`, `tests/test_catalog_skeleton.py`.
   - Do NOT edit outside your ownership boundaries.

7. **Verification**:
   - Run tests in RSTV4: `pytest tests/test_skeleton_contract.py tests/test_catalog_skeleton.py tests/test_catalog_deep.py`
   - Run E2E M2 tests in UuMA: `python tests/e2e_scholar_catalog/run_e2e_tests.py --tier tier1` and `run_e2e_tests.py --tier tier2`
   - Run ruff linter: `ruff check` on modified files.
   - Document all commands, execution output, and verification results in `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\worker_m2\handoff.md`.

## 2026-11-04T10:47:34Z
[Message] timestamp=2026-11-04T10:47:34Z sender=5b985bcb-fa1f-4334-be69-f733a855a15d priority=MESSAGE_PRIORITY_HIGH
You are worker_m2, assigned to implement and verify Milestone M2 (Delivery 3: PaperSkeleton Deep Analysis, W22–W27).
Working directory: C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\worker_m2\
Parent conversation ID: 5b985bcb-fa1f-4334-be69-f733a855a15d
Core Tasks: W22–W27.
