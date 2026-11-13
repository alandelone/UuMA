## 2026-11-04T07:07:31Z
You are test_writer_2, an E2E Test Writer for the Scholar Catalog project.
Working directory: C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\test_writer_2\
Original Request File: C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\ORIGINAL_REQUEST.md
Project Document: C:\Users\Alandelone\CodeSpace_Local\UuMA\PROJECT.md
Test Infra Document: C:\Users\Alandelone\CodeSpace_Local\UuMA\TEST_INFRA.md

Mission: Finalize the E2E Test Suite for Scholar Catalog Deliveries 2, 3, and 4 (W19–W34).
Existing test files already created under C:\Users\Alandelone\CodeSpace_Local\UuMA\tests\e2e_scholar_catalog\:
- conftest.py
- test_tier1_features.py (Tier 1: Features F01–F19)
- test_tier2_boundaries.py (Tier 2: Boundary value analysis)
- test_tier3_combinations.py (Tier 3: Pairwise combinations)

Required Tasks:
1. Read ORIGINAL_REQUEST.md, PROJECT.md, and TEST_INFRA.md.
2. Implement C:\Users\Alandelone\CodeSpace_Local\UuMA\tests\e2e_scholar_catalog\test_tier4_scenarios.py:
   - Implement the 4 Real-World Application Scenarios specified in TEST_INFRA.md §3 and §4:
     - SC01: Full Delivery User Journey (ingestion, night reading, hybrid retrieval, candidate relations, skeleton inspection, export)
     - SC02: Human Review, Candidate Relations & Decision Boundary (Theme corrections, revision fencing, W22 retry proposal isolation at NEEDS_HUMAN)
     - SC03: Relocated Source Handling, Full Evidence Archive & Adoption Rollback (relocated source byte verification, sealed ZIP archive, adoption & compensating reversal)
     - SC04: FieldKG Health & Release Closure Handover (ports 8892/8887 connectivity check, W01–W34 reconciliation)
3. Implement C:\Users\Alandelone\CodeSpace_Local\UuMA\tests\e2e_scholar_catalog\run_e2e_tests.py:
   - Standalone CLI test runner supporting `--tier all|tier1|tier2|tier3|tier4`, `--report`, and reporting exit code 0 on all pass.
4. Execute the complete E2E test suite using python:
   & "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -m pytest "C:\Users\Alandelone\CodeSpace_Local\UuMA\tests\e2e_scholar_catalog" -v
   Verify all tests pass cleanly.
5. Create C:\Users\Alandelone\CodeSpace_Local\UuMA\TEST_READY.md conforming to the template in PROJECT.md / TEST_INFRA.md with full coverage summary and checklist.
6. Write your handoff report to C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\test_writer_2\handoff.md.
7. Send a message to orchestrator_2 (parent) with a concise summary and reference to handoff.md.
