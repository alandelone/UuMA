# Comprehensive Codebase Analysis: Scholar Catalog Deliveries 2, 3, and 4

**Date:** 2026-11-04  
**Investigator:** explorer_1 (Teamwork Explorer)  
**Primary Working Directory:** `C:\Users\Alandelone\CodeSpace_Local\UuMA\`  
**Governing Documents:**
- `docs/operations/scholar-catalog-complete-work-plan-2026-11-04-with-agent-execution-layer.md`
- `docs/operations/scholar-catalog-agent-execution/board.md`
- `docs/operations/scholar-catalog-agent-execution/first-journey-receipt-20261104.json`
- `docs/operations/scholar-catalog-agent-execution/held-jobs-triage.md`

---

## 1. Executive Summary & Architectural Topography

### 1.1 UuMA vs. RSTV4 Relationship
A critical discovery in this investigation is the architectural segregation between UuMA and RSTV4:
1. **UuMA (`C:\Users\Alandelone\CodeSpace_Local\UuMA`)**:
   - The local-first control plane for Hermes agents (`Brainstormer`, `Forge`, `Honc`, `Librarian`, `Scholar`, `Wisdom-Oldman`, `Yonc`).
   - Owns orchestration, session lifecycle, agent observatory (`src/uuma/observatory/`), agent-to-agent protocol (A2A), and centralized audit logging (`uuma.db`).
   - `src/uuma/observatory/adapters/scholar.py` acts as UuMA's view adapter into Scholar, connecting directly to `C:/Users/Alandelone/CodeSpace_Local/RSTV4/data/catalog.db` to inspect papers, PDF verification states, and pipeline queues.
   - `src/uuma/kag_bridge.py` and `scripts/check-scholar-graph-connector.py` maintain the client-side probe and SSH forwarding for `ScholarFieldKG` (port 8892/8887 on `alandelone-server-001`).
   - `.uuma-local/scholar-catalog-implementation-20261023/` contains 2,100 operational files, execution scripts, candidate releases, receipts, and preflight test fixtures developed during the implementation sprints.

2. **RSTV4 (`C:\Users\Alandelone\CodeSpace_Local\RSTV4`)**:
   - Scholar agent's isolated research operating system and authoritative database owner.
   - Owns the canonical `catalog.db` (Schema 22, 100 MB, 3,177 papers, 1,197 visible, 726 verified).
   - Contains all production code for semantic retrieval (`catalog_content_retrieval.py`, `catalog_embeddings.py`), PaperSkeleton modules (`catalog_skeleton_views.py`, `catalog_deep.py`, `located_deep.py`), review workflows (`catalog_theme_corrections.py`, `catalog_review_workflow.py`), MCP servers (`catalog_mcp.py`, `mcp_server.py`), and historical adoption controller (`catalog_history_adoption.py`).

---

## 2. Delivery 2: Global Semantic Discovery (W19–W21)

### 2.1 Implementation Status
- **Execution Board State:** `RUNTIME_VERIFIED` / Operational.
- **Test Suite Status:** 15 retrieval tests passed in `test_catalog_content_retrieval.py`; 7 candidate tests passed in `test_catalog_candidate_index.py`; 3 tool integration tests passed in `test_catalog_content_tools.py`. Total 25 tests verified.
- **External Dependency Probe:** Live BGE-M3 service on `alandelone-server-001` probed and verified (`ready=True`, `model=bge-m3`, `dimensions=1024`, `backend=onnxruntime`, `device=cpu`).

### 2.2 Component & Schema Analysis
1. **Vector & Embedding Storage (`src/rstv4/catalog_embeddings.py`)**:
   - `ScholarEmbeddings`: Communicates with `alandelone-server-001` via SSH standard input (no research text in command-line arguments or environment variables).
   - Authenticates against `SCHOLAR_EMBEDDING_TOKEN_FILE` on the server.
   - Computes L2-normalized 1024-dimensional dense vectors (`normalized()` enforces finite direction and unit length).
   - Batches strictly bounded between 1 and 16 texts, max 8,000 characters per text.

2. **Hybrid Search & Lexical/Dense Fusion (`src/rstv4/catalog_content_retrieval.py`)**:
   - **Vector Cache:** Stored in SQLite at `data/artifacts/catalog-content-index/vectors.sqlite`. Tables:
     - `vectors(text_sha256 TEXT, model_identity TEXT, vector_json TEXT, PRIMARY KEY(text_sha256, model_identity))`
     - `metadata(key TEXT PRIMARY KEY, value_json TEXT)`
     *(Note: Neither SQLite FTS5 nor sqlite-vec virtual tables are used for paper vectors. Vectors are stored as serialized JSON strings and decoded for in-memory cosine comparison; lexical search is in-memory BM25 with exact tokenization, length normalization factor 1.2, and stop-word filtering).*
   - **Text Chunking:** `chunks(text, size=1600, overlap=200)` preserves complete codepoints and exact source offsets.
   - **Hybrid Fusion Algorithm:** Reciprocal Rank Fusion (RRF) combining BM25 lexical rank and cosine semantic rank:
     $$\text{RRF Score}(d) = \sum_{m \in \{\text{lexical}, \text{dense}\}} \frac{1}{60 + \text{rank}_m(d)}$$
   - **Honest Coverage Reporting:** Query response returns `mode: 'HYBRID'` or `'LEXICAL_ONLY_INDEX_NEEDED'`. Includes `semantic_index` payload reporting `eligible_passages`, `indexed_passages`, `complete`, `corpus_complete`, `pending_sources`, `paused_paper_ids`, and `source_fingerprint`.
   - **Match Basis:** Matches clearly distinguish `match_basis: ['SEMANTIC']` (similarity $\ge 0.35$), `['TEXT']` (lexical score $> 0$), or both `['SEMANTIC', 'TEXT']`.
   - **Night Window Restriction:** Automatic indexing jobs execute only when `night_window_open()` is true (00:00–08:00 Asia/Kuala_Lumpur) unless explicitly bypassed via `request_refresh(..., manual_requested=True)`.

3. **Evidence Quotation Binding**:
   - Every returned passage item carries `block_id`, `page_number`, `section`, `start`, `end`, `block_content_digest`, and exact verbatim `quote`.

4. **Candidate Semantic Relation Proposals (`src/rstv4/catalog_candidate_index.py`, `catalog_candidate_links.py`)**:
   - Bounded pairwise nearest-neighbor cache over Theme definitions (`candidate_relations`).
   - Displays supporting evidence quotes from both sides (`evidence` array with `evidence_offset` and `evidence_limit`).
   - Distinct paper count aggregation: `paper_ids` tracks matched papers; `paper_count = len(paper_ids)`. Counts across Themes overlap and are never falsely summed as unique totals.
   - Explicitly records `applied_merges: 0`—candidate similarities never automatically mutate knowledge or merge concepts without review.

5. **Scholar Entry Points, CLI, HTTP & MCP Tools (`src/rstv4/catalog_mcp.py`, `catalog_content_tools.py`, `catalog_web.py`)**:
   - HTTP UI/API: `rstv4/catalog_web.py` runs on port 8875 (`/api/content/search`, `/api/content/candidates`).
   - FastMCP Server: `rstv4/mcp_server.py` (`rstv4-mcp` CLI entry point). When environment variable `RSTV4_CATALOG_GLOBAL_TOOLS=1` is set, mounts:
     - `query_catalog_content`: Full-text passage search with hybrid basis.
     - `get_catalog_theme_candidates`: Semantic similarity candidate inspection.
     - `query_catalog_understanding`: Open multi-theme search with ANY/ALL filters and unique paper counts.
     - `get_catalog_understanding`: Section-paginated paper understanding card and evidence quotes.
     - `get_catalog_reading_status`: Bounded execution overview.
     - `get_catalog_skeleton_views`: Immutable Skeleton view history.
     - Reading control & manual priority tools (`request_catalog_initial_reading`, `request_catalog_deep_reading`, `retry_catalog_initial_reading`, `control_catalog_reading`).

6. **W16 Review Mapping Hooks (`src/rstv4/catalog_theme_corrections.py`, `catalog_review_workflow.py`)**:
   - `catalog_theme_corrections` table records reversible human edits and restorations (`EDIT` / `RESTORE`).
   - Revision-fenced: requires matching `expected_revision` and `expected_review_revision`.
   - Connects candidate Themes to controlled vocabulary in `research_fields` and `topics` without destroying machine-authored observations.

---

## 3. Delivery 3: PaperSkeleton Modules (W22–W27)

### 3.1 Implementation Status
- **Execution Board State:**
  - W22: `BLOCKED (H)` — Distinct held deep-role approval for v419 (awaiting user decision).
  - W23: `BLOCKED` on W22.
  - W24: `PRESERVED` — Complete original L1–L4 source coverage ready.
  - W25: `PRESERVED` — Derived whole-paper content and writing-structure views ready.
  - W26: `RUNTIME_VERIFIED` — Separate purpose/value judgments operational in `catalog_reading_judgments`.
  - W27: `RUNTIME_VERIFIED` — Cross-view and source-version reuse contracts active.

### 3.2 Component & Schema Analysis
1. **L1–L4 PaperSkeleton Framework (`src/rstv4/located_deep.py`, `catalog_deep.py`)**:
   - **Layer 1:** Atomic propositions, entities, qualifications, source spans (`layer1_json`).
   - **Layer 2:** Logical, evidential, and causal relations (`layer2_json`).
   - **Layer 3:** Argumentative intent (`layer3_json`).
   - **Layer 4:** Macro writing roles (`layer4_json`, `layer4` column).
   - Persisted in `catalog.db` across:
     - `paper_skeletons`: Stores `skeleton_id`, `paper_version_id`, `content_digest`, `version`.
     - `skeleton_units`: Stores sequence index, raw text, section, page, layer 1-4 JSONs.
     - `skeleton_checkpoints`: Section-level and layer-level execution checkpoints.
     - `skeleton_source_outlines`: Preserved hierarchical headings and block geometry.

2. **Whole-Paper Content View & Writing Structure View (`src/rstv4/catalog_skeleton_views.py`)**:
   - Pipeline version: `VIEW_VERSION = "paperskeleton-content-and-purpose-v2-themes"`.
   - Content tasks: `skeleton_view_part`, `skeleton_view_digest`, `skeleton_view_final`, `skeleton_theme_role`.
   - Table: `catalog_skeleton_content_views(view_id, skeleton_id, job_id, source_digest, content_json, contracts_json, created_at)`.
   - Derives 22 dimensions (research problem, claims, technical/research methods, data, evaluation, findings, limitations/gaps, argument flow, writing architecture, etc.) strictly bound to authentic Skeleton unit IDs and source locations.
   - Publishes Themes into `catalog_skeleton_theme_observations`.

3. **Purpose & Value Evaluators (`src/rstv4/catalog_skeleton_views.py`, `catalog_reading.py`)**:
   - Task: `skeleton_purpose`.
   - Table: `catalog_skeleton_purpose_judgments(judgment_id, view_id, job_id, purpose_json, judgment_json, contract_json, created_at)`.
   - Evaluates completed content against declared research purpose (`purpose_json`) without modifying paper's content authority.
   - Separates recommendation from execution grant: recommending deep reading or citation expansion does NOT auto-queue runs.

4. **Cache Freshness & Invalidation Contracts**:
   - `snapshot(conn, source_job_id)` re-proves the exact native version against original model receipts using `replay_from_receipts`.
   - When PDF SHA256, parse run ID, or profile changes, `require_parse_source` and `parse_identity_is_current` invalidate derived views. Stale views remain in audit history but are excluded from active eligibility.

5. **Investigation of the v419 Sample**:
   - Pinned location: `.uuma-local/scholar-catalog-implementation-20261023/new-role-recovery-proposal-v419/`.
   - Sample paper: `paper_dd83af8026e39dd2a2e9316622a7ca49`.
   - Job: `skeletonviewjob_1216bde784964dc42990bbd92b55cd7431a23a60a43d94a05fe1bd58c6ec81e6`.
   - Failed Call: `catalogdeepmodelcall_3098dded1bb69f1f48bc449897135f18eaa4bce2c2c86bd69324212650b6d96a` (`gemini-3.6-flash`, task `skeleton_theme_role_json_recovery`, Theme: `Private Blockchain Governance and Trade-offs`).
   - Prior grant `v329` was already consumed and cannot authorize a second attempt.
   - Proposal `proposal.json` is `PREPARED_AWAITING_NEW_EXPLICIT_APPROVAL` with `maximum_additional_model_requests: 1`.
   - Software-only synthetic proof exists in `releases/distinct-role-proof-v565/` (`test_distinct_role_proof_v566.py`), but production execution is strictly blocked at the user review boundary (W22/W23).

---

## 4. Delivery 4: Portable Archive, Export/Import, & Migration (W28–W30, W32–W34)

### 4.1 Implementation Status
- **Execution Board State:**
  - W28 (Portable Source Location): `RUNTIME_VERIFIED`.
  - W29 (FULL Evidence Archive): `DEFERRED` (awaiting Delivery 3 full Skeleton completion).
  - W30 (Adoption & Reversal): `DEFERRED` (controller logic verified in software fixtures; awaiting actual FULL carrier).
  - W32 (User Journeys): First Journey `ACCEPTED`; Full Journey awaits Delivery 4.
  - W33 (FieldKG Runtime Check): `RUNTIME_VERIFIED` (`ScholarFieldKG` online on port 8892/8887).
  - W34 (Release Closure): `PENDING`.

### 4.2 Component & Schema Analysis
1. **Portable Source Location Handling (`src/rstv4/paper_sources.py`, `catalog_registered_sources.py`)**:
   - `require_pdf_source`: Reads PDF bytes directly from `source_file_versions.storage_path`, verifies `%PDF-` header, size in bytes, and SHA256 digest.
   - Relocation behavior: Verified in `.uuma-local/scholar-catalog-implementation-20261023/test_relocated_fulltext_guard_v665.py`. When original workstation paths are modified to point to relocated retained bytes, the guard successfully verifies the PDF, while tampered bytes are rejected with `Original parsed PDF changed`.

2. **Portable Archive Creation (`.uuma-local/.../archive_finished_skeleton_evidence_v546.py`)**:
   - Captures consistent database snapshot, stage manifest (`stage-manifest.json`), operation registries, physical full PDF, and original parser markdown/JSON artifacts.
   - Preflight checks enforce `PRAGMA foreign_key_check` and `verify_finished_record`.

3. **Controller History Adoption & Compensating Reversal (`src/rstv4/catalog_history_adoption.py`)**:
   - `prepare_adoption(source, job_ids, ...)`: Verifies completed `SKELETON_VIEW` and `SKELETON_PURPOSE` jobs, captures verified transport origin proof (`capture_verified_transport_origin`), and produces a sealed `Admission`.
   - `record_adoption(conn, admission)`: Inserts records inside an owned transaction into a nonempty target database. Verifies `proof["scopes"]` fingerprints. Enforces idempotency (replaying same request ID is a safe no-op). Detects conflicting overlapping adoptions. Emits `CATALOG_HISTORY_ADOPTED` event.
   - `reverse_adoption(conn, adoption_request_id, ...)`: Compensating reversal. Emits `CATALOG_HISTORY_ADOPTION_REVERSED` event. Does NOT delete or overwrite imported records; preserves audit trail and marks adoption reversed.
   - Verified in `.uuma-local/.../test_full_transfer_v284.py`.

4. **FieldKG Runtime Health (W33)**:
   - Verified via `ensure_knowledge_graph('scholar')` and `scripts/check-scholar-graph-connector.py`.
   - Connects to `ScholarFieldKG` on `alandelone-server-001` via SSH local port 8892 / 8887. Verified non-destructive: no local store recreation or remigration permitted.

---

## 5. Existing Test Suite Status & Verification Matrix

### 5.1 Test Files by Delivery Area
| Delivery | Scope | Primary Test Files | Test Count / Status |
| :--- | :--- | :--- | :--- |
| **Delivery 2** | Full-text retrieval | `RSTV4/tests/test_catalog_content_retrieval.py` | 15 tests (ALL GREEN) |
| | Candidate indexing | `RSTV4/tests/test_catalog_candidate_index.py` | 7 tests |
| | Content MCP tools | `RSTV4/tests/test_catalog_content_tools.py` | 3 tests |
| | Web & candidate links | `RSTV4/tests/test_catalog_content_web.py`, `test_catalog_candidate_links.py` | Tested |
| | Theme review (W16) | `RSTV4/tests/test_catalog_theme_corrections.py`, `test_catalog_review_workflow.py` | 40 tests |
| **Delivery 3** | L1–L4 Skeleton blocks | 68 `RSTV4/tests/test_skeleton_*.py` files | Extensive unit coverage |
| | Content & purpose views | `RSTV4/tests/test_catalog_skeleton.py`, `test_catalog_deep.py` | Tested |
| | v419 Proof | `.uuma-local/.../test_distinct_role_proof_v566.py`, `test_distinct_role_submit_once_v560.py` | Fixture verified |
| | Role recovery | `RSTV4/tests/test_skeleton_role_recovery.py` | 6 tests |
| **Delivery 4** | Relocated source guard | `.uuma-local/.../test_relocated_fulltext_guard_v665.py` | 1 test (PASSED) |
| | Adoption & reversal | `.uuma-local/.../test_full_transfer_v284.py`, `RSTV4/tests/test_catalog_history_adoption.py` | Tested |
| | Schema 21 transfer | `.uuma-local/.../test_schema21_transfer_v475.py`, `test_integrated_controller_v497.py` | Tested |
| | FieldKG connector | `UuMA/tests/test_scholar_graph_connector.py` | 3 tests |

### 5.2 Test Fixtures & Databases
1. **Canonical Production Database**: `C:/Users/Alandelone/CodeSpace_Local/RSTV4/data/catalog.db` (Schema 22, 100 MB).
2. **First Journey Accepted Sample**: `paper_dd83af8026e39dd2a2e9316622a7ca49` (85 blocks, 14 Themes).
3. **Synthetic / Rehearsal Databases**:
   - `C:/Users/Alandelone/CodeSpace_Local/RSTV4/data/catalog-initial-patch-rehearsal-v200.db` (23 MB).
   - `C:/Users/Alandelone/CodeSpace_Local/RSTV4/data/catalog-initial-preview-rehearsal-v188.db` (22 MB).
4. **Validation Artifacts**:
   - `C:/Users/Alandelone/CodeSpace_Local/RSTV4/.rstv4-local/skeleton-validation/20260930/` (`native-baseline.json`, `native-baseline.calls.jsonl`).
   - `C:/Users/Alandelone/CodeSpace_Local/UuMA/test-fixtures/scholar-complex-materials/` (`software-only-figure.svg`, `software-only-table.csv`).
   - `.uuma-local/scholar-catalog-implementation-20261023/new-role-recovery-proposal-v419/`.
