# Project: Scholar Catalog Delivery Advancement (Deliveries 2, 3, 4)

## Architecture
- **Local-First Control Plane (UuMA)**: Owns session lifecycle, stage gates (`mission_status.json`), orchestration metadata (`.agents/teamwork/`), observatory adapters (`src/uuma/observatory/`), knowledge runtime bridges (`src/uuma/knowledge_runtime.py`), and staging test harnesses (`.uuma-local/scholar-catalog-implementation-20261023/`).
- **Research OS & Database Engine (RSTV4)**: Owns canonical SQLite databases (`C:/Users/Alandelone/CodeSpace_Local/RSTV4/data/catalog.db`), reading policy (`reading_policy.py`), content indexing (`catalog_content_retrieval.py`, `catalog_candidate_index.py`), FastMCP tools (`catalog_content_tools.py`), PaperSkeleton models and views (`catalog_skeleton_views.py`), and adoption/reversal controller (`catalog_history_adoption.py`).
- **External Model & Knowledge Services**:
  - `BGE-M3` 1024-dim embedding server on `alandelone-server-001:8893` (accessible via SSH tunnel or direct bind).
  - `FieldKG` knowledge graph runtime on ports 8892 (bridge HTTP endpoint) and 8887 (OpenSPG backend) serving `ScholarFieldKG` (Project ID 2).
- **Execution Constraints (§9 & Governance)**:
  - Strict serialization of writes to `catalog.db` and `wisdom.db` through designated single-process controllers.
  - Night reading window (00:00–08:00 Asia/Kuala_Lumpur) strictly enforced for automatic batch processing.
  - Isolated git worktrees / branches per work package.
  - User decision boundary: v419 single-call retry proposal held at W22 awaiting direct explicit user approval.

---

## Feature Inventory
Every feature identified during the Survey phase is enumerated below with its assigned milestone.

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F01 | Full-Text Chunking & Dense Embeddings (W19) | 1600-codepoint/200-overlap chunking, BGE-M3 1024-dim embedding, SQLite vector cache in `vectors.sqlite`. | M1 (Delivery 2) | W19 / survey |
| F02 | Hybrid Search via RRF & Source Fencing (W19) | Combines BM25 lexical recall and BGE-M3 cosine similarity via Reciprocal Rank Fusion; validates source PDF checksum to prevent in-flight tampering. | M1 (Delivery 2) | W19 / survey |
| F03 | Honest Retrieval Coverage Reporting (W19) | Accurate metadata reporting of indexing state (`eligible_passages`, `indexed_passages`, `complete`, `pending_sources`, `paused_paper_ids`). | M1 (Delivery 2) | W19 / survey |
| F04 | Candidate Semantic Relation Matrix (W20) | Top-20 nearest-neighbor candidate pairs using NumPy 1.26.4 matrix blocks; aggregates distinct paper counts without runtime pair rescoring. | M1 (Delivery 2) | W20 / survey |
| F05 | Non-Mutating Proposal Evidence (W20) | Cites located supporting quotations from both source papers; keeps proposals in `UNRESOLVED_SIMILARITY` with `applied_merges=0`. | M1 (Delivery 2) | W20 / survey |
| F06 | Scholar FastMCP Tools (W21) | Exposes `query_catalog_content` and `get_catalog_theme_candidates` with bounded transport previews and exact quote preservation. | M1 (Delivery 2) | W21 / survey |
| F07 | W16 Theme Mapping & Revision Fencing (W21) | Integrates human-reviewed Theme corrections and restorations (`catalog_theme_corrections`) with revision token validation. | M1 (Delivery 2) | W21 / survey |
| F08 | v419 Retry Decision Boundary (W22) | Pinned single-call retry proposal for deep-role failure held at `NEEDS_HUMAN` awaiting explicit user decision. | M2 (Delivery 3) | W22 / survey |
| F09 | Authorized Admission or Decline Recording (W23) | Executes at most one authorized replacement call if approved; durably records decline if rejected; zero unapproved calls. | M2 (Delivery 3) | W23 / survey |
| F10 | Genuine L1–L4 Source Coverage (W24) | Full 4-layer coverage (L1 propositions, L2 relations, L3 atom intents, L4 macro roles) across all 85 blocks of sample `paper_dd83af8026e3`. | M2 (Delivery 3) | W24 / survey |
| F11 | 22-Dimension Content & Structure Views (W25) | Constructs whole-paper content views across 22 dimensions and writing-structure views citing authentic Skeleton units and source spans. | M2 (Delivery 3) | W25 / survey |
| F12 | Decoupled Purpose & Value Evaluations (W26) | Purpose and value judgments evaluate declared research purpose against exact content evidence; preserves initial-only validity. | M2 (Delivery 3) | W26 / survey |
| F13 | Freshness & Version Replay Contracts (W27) | Cross-view invalidation: source generation changes invalidate derived views without overwriting history; replay from verified model receipts. | M2 (Delivery 3) | W27 / survey |
| F14 | Portable Relocated Source Handling (W28) | Relocated PDF handling verifies retained bytes via `%PDF-` header, SHA-256 digest, and MinerU manifest when workstation paths are absent. | M3 (Delivery 4) | W28 / survey |
| F15 | Complete Authentic FULL Evidence Archive (W29) | Packaging carrier generating sealed ZIP archive containing full database snapshot, stage manifest, operation registries, and raw PDF bytes. | M3 (Delivery 4) | W29 / survey |
| F16 | Non-Empty Target History Adoption & Reversal (W30) | Controller-owned append-only adoption (`CATALOG_HISTORY_ADOPTED`) and compensating reversal (`CATALOG_HISTORY_ADOPTION_REVERSED`) with WAL rollback. | M3 (Delivery 4) | W30 / survey |
| F17 | Final Full Delivery User Journey (W32) | End-to-end traversal across UI, API, and tool interfaces validating seamless retrieval, skeleton inspection, and export adoption. | M3 (Delivery 4) | W32 / survey |
| F18 | FieldKG Health & Connectivity (W33) | Connectivity and schema readback checks on ports 8892/8887 to `ScholarFieldKG` without recreating local stores. | M3 (Delivery 4) | W33 / survey |
| F19 | Release Closure & Handover Checklist (W34) | 34-item ledger reconciliation accounting for every work item (W01–W34) with verified live evidence or explicit user disposition. | M3 (Delivery 4) | W34 / survey |
| F20 | E2E Acceptance Test Suite Infrastructure | Multi-tier (Tiers 1-4) opaque-box test suite verifying requirements from `ORIGINAL_REQUEST.md` independently of internal modules. | E2E-TEST | prompt / reqs |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Delivery 2: Global Semantic Discovery | W19, W20, W21 (F01–F07) | Delivery 1 Accepted Baseline | PLANNED |
| M2 | Delivery 3: PaperSkeleton Deep Analysis | W22, W23, W24, W25, W26, W27 (F08–F13) | M1, User boundary at W22 | PLANNED |
| M3 | Delivery 4: Final Portable Delivery & Handover | W28, W29, W30, W32, W33, W34 (F14–F19) | M2, M1 | PLANNED |
| E2E-TEST | E2E Testing Track | Requirement-driven test suite (Tiers 1–4, F20) | none (parallel track) | PLANNED |

---

## Interface Contracts

### 1. Delivery 1 Baseline ↔ Delivery 2 (Global Semantic Discovery)
- **Input**: `catalog.db` tables `papers`, `catalog_reading_jobs`, `document_blocks`.
- **Output Artifacts**: `data/artifacts/catalog-content-index/vectors.sqlite`, `data/artifacts/catalog-candidate-index/candidate.sqlite`.
- **Integrity**: Delivery 2 reads canonical tables read-only; writes only to isolated artifact SQLite caches. No schema mutations or record updates to `catalog.db`.

### 2. Delivery 2 ↔ Delivery 3 (PaperSkeleton Deep Analysis)
- **Shared Entities**: `paper_id`, `document_blocks`, `themes` (`catalog_skeleton_content_views`).
- **Query Entry**: FastMCP tool `query_catalog_content(paper_id, query, limit=5)` returns exact quotes with block numbers matching L1–L4 units.
- **Fencing**: Source modifications trigger invalidation token in derived views.

### 3. Delivery 3 ↔ Delivery 4 (Portable Delivery & Archive)
- **Input for Archive**: Complete database state including verified 85 blocks of sample `paper_dd83af8026e3`, 22-dimension content views, purpose judgments, and physical PDF.
- **Archive Carrier**: Manifest `stage-manifest.json` sealing SHA-256 hashes of all component artifacts.
- **Adoption**: Target database receives records via `adopt_completed_catalog_history_v1` without overwriting existing non-empty owner records.

### 4. FieldKG & Embedding Runtime Contracts
- **BGE-M3**: Port 8893 (1024 dim L2-normalized vectors).
- **FieldKG Bridge**: HTTP Port 8892 (`/health` -> `ready=True`, `/query` -> graph responses).
- **FieldKG OpenSPG**: HTTP Port 8887 (`/public/v1/project` -> Project 2 `ScholarFieldKG`).

---

## Code Layout

### UuMA (Local-First Control Plane)
- `src/uuma/observatory/adapters/scholar.py`: Scholar adapter for observatory.
- `src/uuma/knowledge_runtime.py`: FieldKG runtime discovery and probe.
- `src/uuma/session/`: Session and gate lifecycle management.
- `.uuma-local/scholar-catalog-implementation-20261023/`: Staged verification scripts, receipts, and proposals.
- `.agents/teamwork/`: Orchestration and agent metadata.

### RSTV4 (Scholar Research Operating System)
- `src/rstv4/reading_policy.py`: Night reading window and job admission guard.
- `src/rstv4/catalog_embeddings.py`: BGE-M3 client and normalization.
- `src/rstv4/catalog_content_retrieval.py`: Hybrid BM25+dense RRF search and vector cache.
- `src/rstv4/catalog_candidate_index.py`: Candidate relation graph and distinct paper count.
- `src/rstv4/catalog_content_tools.py`: FastMCP tools for content and theme queries.
- `src/rstv4/catalog_skeleton_views.py`: PaperSkeleton L1–L4 views and purpose judgments.
- `src/rstv4/catalog_history_adoption.py`: History adoption and compensating reversal.
- `tests/test_catalog_content_retrieval.py`: Tests for hybrid search.
- `tests/test_catalog_candidate_index.py`: Tests for candidate relation index.
- `tests/test_catalog_content_tools.py`: Tests for FastMCP tools.
- `tests/test_catalog_deep.py` & `tests/test_catalog_skeleton.py`: Tests for PaperSkeleton.
- `tests/test_full_transfer_v284.py`: Tests for adoption and rollback.

### Exclusive File Ownership Boundaries
- **M1 (Delivery 2 Worker)**: Owns `src/rstv4/catalog_content_retrieval.py`, `src/rstv4/catalog_candidate_index.py`, `src/rstv4/catalog_content_tools.py`, `tests/test_catalog_content_retrieval.py`, `tests/test_catalog_candidate_index.py`, `tests/test_catalog_content_tools.py`.
- **M2 (Delivery 3 Worker)**: Owns `src/rstv4/catalog_skeleton_views.py`, `src/rstv4/catalog_skeleton_themes.py`, `tests/test_catalog_deep.py`, `tests/test_catalog_skeleton.py`.
- **M3 (Delivery 4 Worker)**: Owns `src/rstv4/catalog_history_adoption.py`, `src/rstv4/paper_sources.py`, `.uuma-local/.../archive_finished_skeleton_evidence_v546.py`, `tests/test_full_transfer_v284.py`.
- **E2E Testing Track**: Owns `tests/e2e_scholar_catalog/` (test harness and test suites exclusively).
