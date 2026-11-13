# Dispatch: worker_m3 (Milestone M3 — Delivery 4: Portable Delivery & Handover W28–W34)

## Identity
- Role: Worker (teamwork_worker)
- Working Directory: C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\worker_m3\
- Parent Orchestrator: orchestrator_3 (Conversation ID: 5b985bcb-fa1f-4334-be69-f733a855a15d)

## Mandatory Reading Before Work
Read:
1. `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\ORIGINAL_REQUEST.md` (Verbatim user requirements)
2. `C:\Users\Alandelone\CodeSpace_Local\UuMA\PROJECT.md` (Architecture, Feature Inventory, Milestones, Code Layout)
3. `C:\Users\Alandelone\CodeSpace_Local\UuMA\TEST_READY.md` (E2E Test Suite and Feature Mapping F14–F19)
4. `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\explorer_m3_1\handoff.md` (W28-W29 Technical Blueprint)
5. `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\explorer_m3_2\handoff.md` (W30, W32 Technical Blueprint)
6. `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\explorer_m3_3\handoff.md` (W33, W34 Technical Blueprint)
7. `C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\operations\scholar-catalog-complete-work-plan-2026-11-04-with-agent-execution-layer.md`

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Objectives & Work Items (W28–W34)

1. **W28 (Portable Relocated Source Location Handling)**:
   - Verify that relocated PDF source handling correctly reads and validates retained source bytes via `%PDF-` magic header and SHA-256 byte verification when original workstation paths are unavailable.
   - Verify fail-closed behavior on corrupted bytes or invalid headers.

2. **W29 (Authentic FULL Evidence Archive)**:
   - Produce/verify the complete authentic FULL evidence archive carrier containing sealed ZIP archive, `stage-manifest.json`, database snapshot, and raw PDF bytes.
   - Ensure WAL checkpoint (`PRAGMA wal_checkpoint(TRUNCATE)`) is enforced prior to packing.

3. **W30 (Non-Empty Target History Adoption & Compensating Reversal)**:
   - Verify append-only adoption (`CATALOG_HISTORY_ADOPTED`) into a non-empty target owner database without collision or mutation of existing target owner records.
   - Verify compensating reversal (`CATALOG_HISTORY_ADOPTION_REVERSED`) rolls back adopted events and presentation while keeping underlying historical receipts intact.
   - Verify strict idempotency for both adoption and reversal.

4. **W32 (Final Full Delivery User Journey)**:
   - Traverse the complete user journey across ingestion, night window guard, vector indexing, hybrid search, candidate relations, FastMCP tool payload bounds, 4-layer skeleton inspection, and export adoption.
   - Verify all steps pass cleanly.

5. **W33 (FieldKG Health & Connectivity)**:
   - Execute live connectivity and schema readback checks on ports 8892 and 8887 to `ScholarFieldKG` (Project 2).
   - Verify fail-closed network isolation (`status="BLOCKED"`) and unauthorized profile security barrier (`PermissionError`).

6. **W34 (Release Closure & Handover Checklist)**:
   - Reconcile all 34 work packages (W01 through W34) with authoritative statuses, artifact receipts, and verification evidence against `board.md`.
   - Produce the completed release closure and handover record.

7. **Verification & Tests**:
   - Run RSTV4 test suite: `pytest tests/test_full_transfer_v284.py tests/test_catalog_history_adoption.py tests/test_catalog_history_origin_display.py`
   - Run UuMA master E2E acceptance test runner: `python tests/e2e_scholar_catalog/run_e2e_tests.py --tier all --report` (all 50 tests pass).
   - Check ruff linter on owned files: exit code 0.
   - Ensure your working directory `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\worker_m3\` contains STRICTLY metadata `.md` files (zero `.py` scratch files).

8. **Output Requirements**:
   - Write your complete handoff report to `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\worker_m3\handoff.md` following the Handoff Protocol.
   - Send a message to parent (`5b985bcb-fa1f-4334-be69-f733a855a15d`) upon completion.


## 2026-11-04T11:48:53Z
You are worker_m3, assigned to implement and verify Milestone M3 (Delivery 4: Final Portable Delivery: archive, import, and handover, W28–W34).

Your working directory is: C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\worker_m3\
Your parent conversation ID is: 5b985bcb-fa1f-4334-be69-f733a855a15d
