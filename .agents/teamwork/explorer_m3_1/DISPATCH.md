# Dispatch: explorer_m3_1 (Milestone M3 Exploration: W28 & W29)

## Role & Working Directory
- Role: Explorer (teamwork_explorer)
- Working Directory: C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\explorer_m3_1\
- Parent: orchestrator_3 (Conversation ID: 5b985bcb-fa1f-4334-be69-f733a855a15d)

## Input Information
Read before exploration:
1. `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `C:\Users\Alandelone\CodeSpace_Local\UuMA\PROJECT.md`
3. `C:\Users\Alandelone\CodeSpace_Local\UuMA\TEST_READY.md`
4. `C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\operations\scholar-catalog-complete-work-plan-2026-11-04-with-agent-execution-layer.md`
5. Prior archive and source code in `RSTV4/src/rstv4/` and `UuMA/.uuma-local/`

## Investigation Scope
Investigate requirements and technical contracts for:
1. **W28: Relocated Source Location Handling**:
   - How does the system handle retained PDF source bytes when original workstation paths are unavailable?
   - Verify byte-exact verification via `%PDF-` header, SHA-256 digest, and MinerU manifest (`paper_sources.py`, `catalog_source_relocation`, etc.).
   - Identify how fallback / relocated search roots are registered and validated.
2. **W29: Authentic FULL Evidence Archive**:
   - What packaging carrier script exists (e.g. `archive_finished_skeleton_evidence_v546.py` or equivalent in UuMA staging)?
   - What files must be included in the sealed ZIP archive (canonical DB state, 85-block sample PDF, stage manifest, receipts)?
   - How does `stage-manifest.json` record SHA-256 hashes?
   - What verifier tool / tests validate archive integrity?

## Deliverables
Write your comprehensive investigation report to `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\explorer_m3_1\handoff.md` following the Handoff Protocol (Observation, Logic Chain, Caveats, Conclusion, Verification Commands).
Send a message to parent (`5b985bcb-fa1f-4334-be69-f733a855a15d`) upon completion.

## 2026-11-04T11:39:49Z
[Message] timestamp=2026-11-04T11:39:49Z sender=5b985bcb-fa1f-4334-be69-f733a855a15d priority=MESSAGE_PRIORITY_HIGH
Content: You are explorer_m3_1. Your task is to investigate Milestone M3 technical contracts for W28 (Relocated Source Location Handling) and W29 (Authentic FULL Evidence Archive).
