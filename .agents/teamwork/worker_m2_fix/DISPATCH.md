# Dispatch: worker_m2_fix (Remediation for Milestone M2 Iteration 1)

## Role & Working Directory
- Role: Worker (teamwork_worker)
- Working Directory: C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\worker_m2_fix\
- Parent: orchestrator_3 (Conversation ID: 5b985bcb-fa1f-4334-be69-f733a855a15d)

## Input Information
Read before work:
1. `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\PROJECT.md`
3. `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\TEST_READY.md`
4. `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\reviewer_m2_1\handoff.md` (Verbatim review feedback and error logs)

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Remediation Tasks

1. **Fix Ruff I001 Import Violations in Tests**:
   - In `C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_deep.py` and `C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_skeleton.py`, imports are un-sorted.
   - Run `ruff check --select I --fix tests/test_catalog_deep.py tests/test_catalog_skeleton.py` (or manually organize imports according to PEP 8 / ruff rules).
   - Verify that running:
     `& "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\ruff.exe" check src/rstv4/catalog_skeleton_views.py src/rstv4/catalog_skeleton_themes.py tests/test_catalog_deep.py tests/test_catalog_skeleton.py`
     exits with code 0 and prints "All checks passed!".

2. **Clean Scratch `.py` Files from `.agents/teamwork/`**:
   - The `.agents/teamwork/` folder must contain ONLY metadata markdown files (`.md`).
   - Remove any temporary/scratch `.py` files left in `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\worker_m2\` (such as `sync_m2.py`, `test_m2.py`, etc.).
   - Ensure your own directory `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\worker_m2_fix\` contains ONLY `.md` files.

3. **Re-Run Full Test Verification**:
   - In RSTV4: `pytest tests/test_skeleton_contract.py tests/test_catalog_skeleton.py tests/test_catalog_deep.py` (all 24 pass).
   - In UuMA: `python tests/e2e_scholar_catalog/run_e2e_tests.py --tier all` (all 50 pass).
   - Re-verify database `PRAGMA foreign_key_check` is empty and v419 remains held at `NEEDS_HUMAN` (fencing token 211).

4. **Output Requirements**:
   - Write your complete handoff report to `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\worker_m2_fix\handoff.md` with verbatim ruff output, test outputs, and layout verification.
   - Send a message to parent (`5b985bcb-fa1f-4334-be69-f733a855a15d`) upon completion.


## 2026-11-04T11:23:10Z
You are worker_m2_fix. Your task is to perform targeted remediation on Milestone M2 following reviewer_m2_1's REQUEST_CHANGES verdict.

Your working directory is: C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\worker_m2_fix\
Your parent conversation ID is: 5b985bcb-fa1f-4334-be69-f733a855a15d

Read instructions from:
1. C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\worker_m2_fix\DISPATCH.md
2. C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\reviewer_m2_1\handoff.md
3. C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\ORIGINAL_REQUEST.md
4. C:\Users\Alandelone\CodeSpace_Local\UuMA\PROJECT.md
5. C:\Users\Alandelone\CodeSpace_Local\UuMA\TEST_READY.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Tasks:
1. Fix Ruff I001 import order in RSTV4 test files: C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_deep.py and tests\test_catalog_skeleton.py so that `ruff check` on all 4 owned files passes cleanly with exit code 0.
2. Clean up scratch .py files left in C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\worker_m2\ so that .agents/teamwork/ contains strictly metadata markdown files only. Ensure no .py files exist in your own directory.
3. Re-run RSTV4 tests (24/24 pass) and UuMA E2E tests (50/50 pass).
4. Write your complete handoff report to C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\worker_m2_fix\handoff.md following the Handoff Protocol.
5. Send a message to parent (5b985bcb-fa1f-4334-be69-f733a855a15d) upon completion.
