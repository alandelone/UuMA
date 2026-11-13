# Dispatch: challenger_m3_1 (Milestone M3 Adversarial Challenger 1)

## Role & Working Directory
- Role: Challenger (teamwork_challenger)
- Working Directory: C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\challenger_m3_1\
- Parent: orchestrator_3 (Conversation ID: 5b985bcb-fa1f-4334-be69-f733a855a15d)

## Input Information
Read before challenging:
1. `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `C:\Users\Alandelone\CodeSpace_Local\UuMA\PROJECT.md`
3. `C:\Users\Alandelone\CodeSpace_Local\UuMA\TEST_READY.md`
4. `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\worker_m3\handoff.md`

## Challenge Tasks
1. Stress-test W28: Attempt corrupted PDF magic bytes (`b"%NOTPDF"`), zero-byte files, and single-byte SHA-256 digest mismatches on relocated sources; verify immediate fail-closed rejection.
2. Stress-test W29: Attempt archive extraction without WAL truncation; verify checksum mismatches or integrity errors.
3. Stress-test W30: Attempt concurrent or duplicate history adoption into non-empty target; verify collision detection and idempotent reversal.
4. Stress-test W33: Port unreachable / connection reset simulation on ports 8892 and 8887; verify fail-closed status=`BLOCKED` without corrupting local stores.
5. Report test results in `handoff.md` with explicit verdict: **APPROVE** or **REQUEST_CHANGES**.

## 2026-11-04T12:01:12Z
You are challenger_m3_1. Your task is to adversarially challenge and stress-test Milestone M3 (Delivery 4: Final Portable Delivery: archive, import, and handover, W28–W34).

Your working directory is: C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\challenger_m3_1\
Your parent conversation ID is: 5b985bcb-fa1f-4334-be69-f733a855a15d

Read instructions from:
1. C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\challenger_m3_1\DISPATCH.md
2. C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\ORIGINAL_REQUEST.md
3. C:\Users\Alandelone\CodeSpace_Local\UuMA\PROJECT.md
4. C:\Users\Alandelone\CodeSpace_Local\UuMA\TEST_READY.md
5. C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\worker_m3\handoff.md

Stress-test:
- Corrupted PDF magic bytes (b"%NOTPDF"), zero-byte files, and single-byte SHA-256 digest mismatches on relocated sources (verify immediate fail-closed rejection).
- Archive extraction without WAL truncation (verify checksum mismatches or integrity errors).
- Concurrent or duplicate history adoption into non-empty target (verify collision detection and idempotent reversal).
- Port unreachable / connection reset simulation on ports 8892 and 8887 (verify fail-closed status=BLOCKED).
- Write your complete handoff report to C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\challenger_m3_1\handoff.md with an explicit verdict: APPROVE or REQUEST_CHANGES.
- Send a message to parent (5b985bcb-fa1f-4334-be69-f733a855a15d) upon completion.
