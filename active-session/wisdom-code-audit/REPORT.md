# Wisdom-Oldman implementation audit — 2026-09-09

Resolution status: all six confirmed findings were fixed in production code and promoted into
`tests/test_wisdom_code_audit_regressions.py`. Focused test and final verification evidence appears
below. No live databases, external network, credentials, Docker recovery, or live KAG model calls
were used.

## Evidence

- Existing knowledge regression suites: 13 passed.
- Additional contract probes: 6 failed, each at the intended behavior assertion (no fixture/setup failures).
- Probe artifact: active-session/wisdom-code-audit/test_contract_probes.py.
- Run with repository Python: python -m pytest active-session/wisdom-code-audit/test_contract_probes.py -q --tb=short.
- These deliberately expose unfixed defects; production code and existing assertions were not changed.

Resolution verification:

- Original audit probes: 6 passed after repair.
- Production regression tests for the same contracts: 6 passed.
- Focused Wisdom suite: 19 passed.
- Full UuMA suite: 95 passed with one existing third-party Pydantic warning.
- Full source and test lint: passed.

## Confirmed findings

1. **P1 — Replacement content is absent from supersession review snapshots.**
   knowledge_service.py:838 previews only the operation target, while :990 reads and accepts a second record, the replacement. apply_patch at :548 checks only previewed records. Reproduction: propose A -> B; independently modify candidate B; apply the original supersession proposal. It succeeds and accepts changed B instead of raising StaleKnowledgeError. Capture both records in the review diff and stale checks, including the replacement's actual accepted status transition.

2. **P1 — Reversal breaks accepted relation dependencies.**
   knowledge_service.py:616-637 checks/restores only directly changed records. Reproduction: approve entities A and B; approve relation A -> B; reverse A's original acceptance. A returns to CANDIDATE while its relation remains ACCEPTED and graph_neighborhood still returns it. Refuse reversal while accepted dependents exist or include explicit dependent changes in a reviewable reversal.

3. **P1 — A process interruption strands projection jobs.**
   knowledge_store.py:605 selects only PENDING/FAILED; kag_adapter.py marks RUNNING before applying. Reproduction: persist RUNNING, reopen the store, create a new projection worker, sync. Result: processed=0 and lag=1. No lease/reclaim path is present in this worker. Add recoverable ownership/lease handling and replay-safe backend writes; avoid blindly reclaiming legitimately active jobs.

4. **P1 — Fallback answers discard applicable conditions and known conflicts.**
   kag_adapter.py:509 copies claim statements; :565 hardcodes an empty conflict list. Reproduction: two accepted battery lifetime claims with temperature=25 C and discharge_rate=0.5 C plus an explicit unresolved conflict. Offline answer lists 1000 and 200 cycles, drops both qualifiers, and returns conflicts=[]. The degraded-runtime label does not preserve the missing scientific context. Join relevant qualifiers/conflicts and retain evidence stance in output.

5. **P2 — Research budgets are recorded but not enforced.**
   knowledge_service.py:484-508 and knowledge_models.py:325 onward accept counters without tier-limit transitions. Reproduction: QUICK ACTIVE run updated to 601 seconds, 11 sources, 50001 tokens remains ACTIVE. The documented limits are 600 seconds, 10 sources and 50000 tokens. This proves missing state enforcement; no autonomous scheduler was exercised. Enforce limits in the execution path as well as persisted state, with actual usage accounting.

6. **P2 — Extraction cannot reach document chunks after the first 100.**
   knowledge_construction.py:37 always selects the document prefix, clamps max_chunks to 100, and provides no offset/cursor. Reproduction: ingest 136 chunks; request extraction twice at max_chunks=100. Only the same 100 unique chunks are requested; the remaining 36 are unreachable through this document extraction API. Add explicit pagination/progress and distinguish batch completion from document completion.

## Additional implementation limitation from inspection

The real KAG bridge retrieve branches (kag_bridge.py:470 onward) return answer/references plus one summarized SEMANTIC step. They do not populate structured conditions, conflicts, satisfaction rationale or remaining gaps. The adapter defaults these fields instead of reconstructing them from canonical state. This is a missing output-contract integration, not evidence that every model-generated answer is false. Live retrieval fidelity and source support still require separate end-to-end evaluation.

## Resolution

- Supersession review freezes both affected claims and rejects either snapshot when stale.
- Reversal validates the resulting dependency graph before changing canonical records.
- Projection workers leave active `RUNNING` jobs alone and reclaim them after a 15-minute lease.
- Answers restore canonical qualifiers, conflicts, gaps, and evidence stance/rationale.
- Research-run writes enforce the documented budget tiers and record the exhaustion reason.
- Construction supports cursor pagination through every document chunk.

These audited contracts are now implemented. Live OpenSPG answer quality remains an operational
evaluation concern. The mission stays at its existing verification/user-review boundary.
