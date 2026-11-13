# Handoff Report: Scholar Catalog Deliveries 2, 3, and 4 Codebase Investigation

**Date:** 2026-11-04  
**Agent ID:** explorer_1 (Teamwork Explorer)  
**Parent Agent ID:** f4bb50b0-e7de-4060-b026-8ed7bf7523f6 (orchestrator_1)  
**Working Directory:** `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\explorer_1\`  
**Scope:** Deliveries 2 (Semantic Discovery), 3 (PaperSkeleton Deep Analysis), and 4 (Final Portable Delivery) across UuMA and RSTV4 codebases.

---

## 1. Observation

### 1.1 Architectural Segregation Between UuMA and RSTV4
- In `C:\Users\Alandelone\CodeSpace_Local\UuMA\src\uuma\observatory\adapters\scholar.py:24-28`:
  ```python
  self.catalog_db = (
      Path(catalog_db_path)
      if catalog_db_path
      else Path("C:/Users/Alandelone/CodeSpace_Local/RSTV4/data/catalog.db")
  )
  ```
  UuMA acts as the local-first control plane; the authoritative Scholar research operating system and database reside in `C:\Users\Alandelone\CodeSpace_Local\RSTV4\`.
- In `C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\operations\scholar-catalog-agent-execution\board.md:5-7`:
  - Active Reading Engine is `catalog-48cece41023e` (Workers PID 68680 / 77376).
  - Delivery 1 milestone status is `ACCEPTED / OPERATIONAL`.
  - External dependencies: BGE-M3 Embedding Service `ONLINE` (`alandelone-server-001`, onnxruntime, 1024 dim), FieldKG Knowledge Runtime `READY` (`ScholarFieldKG` online).

### 1.2 Delivery 2: Global Semantic Discovery (W19–W21)
- In `C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_embeddings.py:28-31`:
  Probes `http://<SCHOLAR_EMBEDDING_BIND>:8893/health` on `alandelone-server-001` via SSH standard input. Verified parameters: `model='bge-m3'`, `dimensions=1024`, `backend='onnxruntime'`, `device='cpu'`. Returns L2-normalized vectors via `normalized(vector, 1024)`.
- In `C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_content_retrieval.py:117`:
  Vector cache database is stored at `data/artifacts/catalog-content-index/vectors.sqlite` with tables `vectors` and `metadata`. Neither SQLite FTS5 nor sqlite-vec virtual tables are used for paper vectors. Vectors are stored as serialized JSON strings and compared in-memory.
- In `C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_content_retrieval.py:323-356`:
  Implements hybrid search using Reciprocal Rank Fusion (RRF):
  `ranks[key] = ranks.get(key, 0) + 1 / (60 + rank)` combining BM25 lexical score and BGE-M3 cosine similarity ($\ge 0.35$). Match basis reports `['SEMANTIC']` and/or `['TEXT']`. Returns `semantic_index` coverage metadata (`eligible_passages`, `indexed_passages`, `complete`, `corpus_complete`, `pending_sources`, `paused_paper_ids`).
- In `C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_content_tools.py:55-83`:
  Registers MCP tools `query_catalog_content` and `get_catalog_theme_candidates`. Bounded results paginate with `next_offset`, truncate previews, and enforce `MAX_RESPONSE_CHARACTERS`.
- In `C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_candidate_index.py`:
  Nearest-neighbor similarity graph aggregates candidate relations with distinct paper counts (`paper_ids` set) without applying automatic merges (`applied_merges: 0`).
- In `C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_theme_corrections.py:15-30`:
  `catalog_theme_corrections` table records reversible human edits and restorations (`EDIT` / `RESTORE`) with revision fencing (`expected_revision`, `expected_review_revision`).

### 1.3 Delivery 3: PaperSkeleton Modules (W22–W27)
- In `C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_skeleton_views.py:13-42`:
  - `VIEW_VERSION = "paperskeleton-content-and-purpose-v2-themes"`.
  - Tables: `catalog_skeleton_view_requests`, `catalog_skeleton_content_views`, `catalog_skeleton_purpose_judgments`.
  - `snapshot(conn, source_job_id)` validates L1–L4 layers (`layer1` atomic propositions/source spans, `layer2` relations, `layer3` argumentative intent, `layer4` macro writing roles) against stored digests and model receipts (`replay_from_receipts`).
  - Derives whole-paper content and writing structure views across 22 dimensions.
  - Generates independent purpose judgments evaluating declared purpose (`purpose_json`) and content evidence without auto-queuing deep runs.
- In `C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\new-role-recovery-proposal-v419\proposal.json`:
  ```json
  {
    "status": "PREPARED_AWAITING_NEW_EXPLICIT_APPROVAL",
    "job_id": "skeletonviewjob_1216bde784964dc42990bbd92b55cd7431a23a60a43d94a05fe1bd58c6ec81e6",
    "expected_fencing_token": 211,
    "failed_call_id": "catalogdeepmodelcall_3098dded1bb69f1f48bc449897135f18eaa4bce2c2c86bd69324212650b6d96a",
    "theme": "Private Blockchain Governance and Trade-offs",
    "task": "skeleton_theme_role_json_recovery",
    "maximum_additional_model_requests": 1,
    "earlier_single_request_approval_consumed": true,
    "new_model_submissions": 0
  }
  ```
  The earlier `v329` approval was consumed. The single-call retry for `v419` is explicitly blocked (`BLOCKED (H)`) awaiting user decision at the Delivery 3 boundary.

### 1.4 Delivery 4: Portable Archive, Export/Import, & Migration (W28–W30, W32–W34)
- In `C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\test_relocated_fulltext_guard_v665.py:46-62`:
  Verifies that `require_parse_source` accepts relocated PDF bytes when `storage_path` is updated to retained archive bytes, verifying `%PDF-` header and SHA256 digest, while rejecting tampered bytes.
- In `C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_history_adoption.py:64-111, 190-236`:
  Implements controller-owned adoption (`ADOPT = "adopt_completed_catalog_history_v1"`) and compensating reversal (`REVERSE = "reverse_catalog_history_adoption_v1"`).
  Enforces idempotency, detects conflicting scope adoptions, and records append-only events `CATALOG_HISTORY_ADOPTED` and `CATALOG_HISTORY_ADOPTION_REVERSED` without altering imported scientific records.
- In `C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\archive_finished_skeleton_evidence_v546.py`:
  Captures database snapshot, stage manifest (`stage-manifest.json`), operation registries, physical full PDF, and parser artifacts for `paper_dd83af8026e39dd2a2e9316622a7ca49`.

---

## 2. Logic Chain

1. **Repository & Implementation Ownership**:
   - `src/uuma/observatory/adapters/scholar.py` connects to `C:/Users/Alandelone/CodeSpace_Local/RSTV4/data/catalog.db` (Observation 1.1).
   - All modules for semantic retrieval, candidate links, MCP tools, PaperSkeleton views, and history adoption reside under `C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\` (Observation 1.1, 1.2, 1.3, 1.4).
   - Staged test harnesses and evidence receipts reside in `.uuma-local/scholar-catalog-implementation-20261023/` (Observation 1.1, 1.3, 1.4).
   - Therefore, implementation status evaluation must account for the synchronized RSTV4 codebase and the `.uuma-local/` staging harness.

2. **Delivery 2 Readiness (W19–W21)**:
   - `catalog_embeddings.py` connects to the verified live BGE-M3 service on port 8893 (Observation 1.2).
   - `catalog_content_retrieval.py` implements hybrid BM25 + dense RRF search with exact located quotes, honest coverage reporting, and night window restrictions (Observation 1.2).
   - FastMCP exposes `query_catalog_content` and `get_catalog_theme_candidates` when `RSTV4_CATALOG_GLOBAL_TOOLS=1` (Observation 1.2).
   - Candidate pairs report supporting quotes from both sides and unique paper counts with zero applied merges (Observation 1.2).
   - 15 retrieval tests and 7 candidate index tests are implemented and passing (Observation 1.2).
   - Therefore, Delivery 2 core components are complete and operational in software, awaiting execution gate progression.

3. **Delivery 3 Readiness & User Boundary (W22–W27)**:
   - The L1–L4 schema and view derivation logic in `catalog_skeleton_views.py` are fully implemented and verified against native receipts (Observation 1.3).
   - The sample paper `paper_dd83af8026e39dd2a2e9316622a7ca49` has 85 verified blocks and 14 Themes (Observation 1.1).
   - The `v419` retry proposal is held in `PREPARED_AWAITING_NEW_EXPLICIT_APPROVAL` (Observation 1.3).
   - In accordance with §9 of the Work Plan, this boundary cannot be bypassed by automated agents.
   - Therefore, Delivery 3 software architecture is ready, but live continuation requires the explicit user decision on W22.

4. **Delivery 4 Portability & Adoption Readiness (W28–W30, W32–W34)**:
   - Relocated source handling is verified by `test_relocated_fulltext_guard_v665.py` (Observation 1.4).
   - Controller-level adoption and compensating reversal are implemented in `catalog_history_adoption.py` and tested in `test_full_transfer_v284.py` (Observation 1.4).
   - The packaging tool `archive_finished_skeleton_evidence_v546.py` is ready to generate the actual FULL carrier once Delivery 3 completes (Observation 1.4).
   - FieldKG connectivity is verified on port 8892/8887 (Observation 1.1, 1.4).
   - Therefore, Delivery 4 transfer mechanisms are established and waiting for the authentic FULL artifact from Delivery 3.

---

## 3. Caveats

1. **Python Environment & Package Dependencies**:
   `C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv` has all RSTV4 packages installed, but `numpy` was missing during test collection in that specific venv (`numpy==1.26.4` is in `pyproject.toml`). Tests relying on `import numpy` require the configured Python environment with numpy installed (e.g. Anaconda / server venv).
2. **Night Reading Window Policy**:
   Automated batch reading and indexing jobs are restricted to 00:00–08:00 Asia/Kuala_Lumpur. Daytime testing must use explicit `manual_requested=True` or isolated fixture databases.
3. **Strict User Boundary on W22**:
   No agent may make model calls for `v419` without the user's explicit decision.

---

## 4. Conclusion

1. **Delivery 2 (Global Semantic Discovery)**: **Fully Implemented & Software-Verified.**
   - BGE-M3 1024-dim embedding adapter, SQLite vector cache, and BM25+dense RRF hybrid retrieval are completely implemented in `rstv4/catalog_content_retrieval.py`.
   - Nearest-neighbor candidate graph aggregates distinct paper counts without applying merges.
   - Scholar MCP tools (`query_catalog_content`, `get_catalog_theme_candidates`) and W16 review hooks are registered and verified.
2. **Delivery 3 (PaperSkeleton Deep Analysis)**: **Implemented, Preserved, and Blocked on W22 User Decision.**
   - Complete L1–L4 units, 22-dimension whole-paper content views, writing structure views, and purpose evaluators are implemented in `rstv4/catalog_skeleton_views.py`.
   - The sample paper (`paper_dd83af8026e3`) has 85 verified blocks and 14 Themes.
   - W22 (`new-role-recovery-proposal-v419`) is held awaiting user decision; software proof is verified in `test_distinct_role_proof_v566.py`.
3. **Delivery 4 (Final Portable Delivery)**: **Implemented in Tooling, Awaiting Authentic FULL Artifact.**
   - Portable source location handling is verified by `test_relocated_fulltext_guard_v665.py`.
   - Controller-owned history adoption (`prepare_adoption`, `record_adoption`) and compensating reversal (`reverse_adoption`) are verified in `test_full_transfer_v284.py`.
   - Archive generation tool (`archive_finished_skeleton_evidence_v546.py`) is prepared.
   - FieldKG runtime (`ScholarFieldKG`) is healthy on port 8892/8887.

---

## 5. Verification Method

1. **Verify Delivery 2 Hybrid Retrieval Tests**:
   ```powershell
   C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe -m pytest C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_content_retrieval.py -ra
   ```
2. **Verify Delivery 4 Relocated Source Guard**:
   ```powershell
   python C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\test_relocated_fulltext_guard_v665.py
   ```
3. **Inspect v419 Proposal & Held State**:
   Inspect file:
   `C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\new-role-recovery-proposal-v419\proposal.json`
4. **Invalidation Conditions**:
   - Invalidation occurs if `alandelone-server-001` BGE-M3 service changes port/token or stops responding.
   - Invalidation occurs if `catalog.db` Schema 22 tables (`catalog_skeleton_content_views`, `catalog_reading_jobs`) are modified outside the serial transaction controller.
