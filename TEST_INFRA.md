# E2E Test Infra: Scholar Catalog Deliveries 2, 3, and 4 (W19–W34)

## 1. Test Philosophy & Design Principles
- **Requirement-Driven & Opaque-Box**: Test scenarios are derived directly from user requirements (`ORIGINAL_REQUEST.md`), interface specifications (`PROJECT.md`), and research operating system governance contracts. Tests interact strictly with public entrypoints, FastMCP tool interfaces, HTTP endpoints, and canonical database contracts, remaining independent of internal implementation mechanics.
- **Fail-Closed Security & Governance**: Verification suites enforce §9 governance rules: strict serialization of production database writes, strict 00:00–08:00 Asia/Kuala_Lumpur night reading window enforcement for automated batch operations, explicit user approval boundaries (v419 single-call retry proposal held at W22), and hash-verified source immutability.
- **Progressive Testability**: Verification checks provide early, deterministic pass/fail signals for each delivery milestone without assuming or requiring features from subsequent milestones.
- **Hermetic Isolation & Clean State**: Every test executes within an isolated filesystem sandbox (`tmp_path`) with independent SQLite instances, ensuring zero inter-test coupling, zero side-effects on live databases (`catalog.db`, `wisdom.db`), and complete order-independence.

---

## 2. Methodology

| Methodology | Application in Scholar Catalog E2E Testing |
|---|---|
| **Category-Partition Method** | Systematic decomposition of functional input domains into orthogonal equivalence partitions: search queries (`empty`, `whitespace`, `unicode/cjk`, `long passage`), PDF sources (`intact`, `header corrupted`, `checksum altered`, `quarantined`, `relocated`), execution timing (`daytime`, `night window`, `manual override`), and revision tokens (`initial 0`, `monotonic sequence`, `stale conflict`). |
| **Boundary Value Analysis (BVA)** | Precise stress testing around boundary conditions: night window boundary timestamps (23:59:59 MYT vs 00:00:00 MYT, 07:59:59 MYT vs 08:00:00 MYT), text chunking limits (1600 codepoints with 200 overlap), transport payload fences (`MAX_RESPONSE_CHARACTERS` = 60,000), candidate nearest-neighbor top-20 cutoffs, and 0/1/many distinct paper aggregations. |
| **Pairwise (Combinatorial) Testing** | Systematic verification of 2-way interactions across system boundaries: semantic search combined with open theme candidates; human theme corrections combined with candidate relation proposals; L1–L4 PaperSkeleton views combined with evidence archive export; relocated source handling combined with non-empty target adoption and compensating reversal. |
| **Real-World Workload Testing** | End-to-end multi-step workflow simulation modeling genuine researcher user journeys: from PDF ingestion and night initial reading, to semantic discovery, deep skeleton analysis, purpose evaluation, portable archive creation, and foreign catalog adoption with conflict isolation. |

---

## 3. Feature Inventory & Coverage Mapping

The test suite provides comprehensive coverage across all features F01–F19 defined in `PROJECT.md`.

| # | Feature | Scope / Requirement | Milestone | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|---|---|---|:---:|:---:|:---:|:---:|
| **F01** | Full-Text Chunking & Dense Embeddings | 1600-codepoint/200-overlap chunking, BGE-M3 1024-dim dense embeddings, SQLite vector cache in `vectors.sqlite`. | M1 (W19) | F01 | B08 | PW01 | SC01 |
| **F02** | Hybrid Search via RRF & Source Fencing | Combines BM25 lexical recall and BGE-M3 cosine similarity via Reciprocal Rank Fusion; validates source PDF checksum to prevent in-flight tampering. | M1 (W19) | F02 | B03 | PW01, PW05 | SC01 |
| **F03** | Honest Retrieval Coverage Reporting | Accurate metadata reporting of indexing state (`eligible_passages`, `indexed_passages`, `complete`, `pending_sources`, `paused_paper_ids`). | M1 (W19) | F03 | B01 | PW05 | SC01 |
| **F04** | Candidate Semantic Relation Matrix | Top-20 nearest-neighbor candidate pairs using vector blocks; aggregates distinct paper counts without runtime rescoring. | M1 (W20) | F04 | B07 | PW01, PW02, PW06 | SC01, SC02 |
| **F05** | Non-Mutating Proposal Evidence | Cites located supporting quotations from both source papers; proposals stay in `UNRESOLVED_SIMILARITY` with `applied_merges=0`. | M1 (W20) | F05 | B07 | PW02, PW06 | SC01, SC02 |
| **F06** | Scholar FastMCP Tools | Exposes `query_catalog_content` and `get_catalog_theme_candidates` with bounded transport previews and exact quote preservation. | M1 (W21) | F06 | B07 | PW06 | SC01 |
| **F07** | W16 Theme Mapping & Revision Fencing | Integrates human-reviewed Theme corrections and restorations (`catalog_theme_corrections`) with revision token validation. | M1 (W21) | F07 | B09 | PW02 | SC02 |
| **F08** | v419 Retry Decision Boundary | Pinned single-call retry proposal for deep-role failure held at `NEEDS_HUMAN` awaiting explicit user decision. | M2 (W22) | F08 | B02 | - | SC02 |
| **F09** | Authorized Admission or Decline Recording | Executes at most one authorized replacement call if approved; durably records decline if rejected; zero unapproved calls. | M2 (W23) | F09 | B02 | - | SC02 |
| **F10** | Genuine L1–L4 Source Coverage | Full 4-layer coverage (L1 propositions, L2 relations, L3 atom intents, L4 macro roles) across all 85 blocks without substituting simplified samples. | M2 (W24) | F10 | B08 | PW03 | SC01 |
| **F11** | 22-Dimension Content & Structure Views | Constructs whole-paper content views across 22 dimensions and writing-structure views citing authentic Skeleton units and source spans. | M2 (W25) | F11 | B08 | PW03 | SC01 |
| **F12** | Decoupled Purpose & Value Evaluations | Purpose and value judgments evaluate declared research purpose against exact content evidence; preserves initial-only validity. | M2 (W26) | F12 | B02 | PW07 | SC01 |
| **F13** | Freshness & Version Replay Contracts | Cross-view invalidation: source generation changes invalidate derived views without overwriting history; replay from verified model receipts. | M2 (W27) | F13 | B03 | PW05 | SC03 |
| **F14** | Portable Relocated Source Handling | Relocated PDF handling verifies retained bytes via `%PDF-` header, SHA-256 digest, and MinerU manifest when workstation paths are absent. | M3 (W28) | F14 | B03, B04 | PW04 | SC03 |
| **F15** | Complete Authentic FULL Evidence Archive | Packaging carrier generating sealed ZIP archive containing full database snapshot, stage manifest, operation registries, and raw PDF bytes. | M3 (W29) | F15 | B04 | PW03 | SC01, SC03 |
| **F16** | Non-Empty Target History Adoption & Reversal | Controller-owned append-only adoption (`CATALOG_HISTORY_ADOPTED`) and compensating reversal (`CATALOG_HISTORY_ADOPTION_REVERSED`) with WAL rollback. | M3 (W30) | F16 | B05, B10 | PW04, PW07 | SC01, SC03 |
| **F17** | Final Full Delivery User Journey | End-to-end traversal across UI, API, and tool interfaces validating seamless retrieval, skeleton inspection, and export adoption. | M3 (W32) | F17 | B01, B07 | PW01–PW07 | SC01 |
| **F18** | FieldKG Health & Connectivity | Connectivity and schema readback checks on ports 8892/8887 to `ScholarFieldKG` without recreating local stores. | M3 (W33) | F18 | B02 | - | SC04 |
| **F19** | Release Closure & Handover Checklist | 34-item ledger reconciliation accounting for every work item (W01–W34) with verified live evidence or explicit user disposition. | M3 (W34) | F19 | - | - | SC04 |

---

## 4. Test Architecture & Directory Layout

```text
tests/e2e_scholar_catalog/
├── __init__.py                     # Package marker
├── conftest.py                     # Deterministic fixtures, isolated catalog sandboxes, mock embeddings
├── test_tier1_features.py          # Tier 1: Happy-path feature coverage for F01–F19 (19 tests)
├── test_tier2_boundaries.py        # Tier 2: Boundary value analysis & corner case stress (10 tests)
├── test_tier3_combinations.py      # Tier 3: Pairwise cross-feature interaction suites (7 tests)
├── test_tier4_scenarios.py         # Tier 4: Real-world researcher user journeys (4 tests)
└── run_e2e_tests.py                # Standalone master runner with CLI options and JSON/MD report generation
```

### Shared Fixture Infrastructure (`conftest.py`)
- `mock_embeddings`: Deterministic L2-normalized 1024-dimensional embedding provider conforming to BGE-M3 interface contracts.
- `catalog_sandbox`: Hermetic temporary catalog root with fully initialized database schema (`papers`, `source_file_versions`, `parse_runs`, `document_blocks`, `catalog_reading_jobs`, `catalog_theme_observations`, `catalog_theme_corrections`, `catalog_skeleton_content_views`, `catalog_skeleton_purpose_judgments`).
- `sample_pdf_factory`: Generates valid `%PDF-1.4` files with exact SHA-256 digests and registered catalog entries.
- `archive_builder`: Programmatic generator of authentic sealed ZIP evidence archives with SHA-256 stage manifests.

---

## 5. Tier Definitions & Coverage Thresholds

| Tier | Focus | Test Count | Assertion Threshold | Exit Condition |
|---|---|:---:|:---:|---|
| **Tier 1: Feature Coverage** | Happy-path isolation tests for F01–F19 across Deliveries 2, 3, and 4 | 19 | $\ge 1$ comprehensive test per feature | 100% Pass |
| **Tier 2: Boundary & Corner Cases** | Negative testing, corrupted bytes, boundary times, transport limits, collision safety | 10 | Strict failure closing & error verification | 100% Pass |
| **Tier 3: Cross-Feature Combinations** | Pairwise interactions across architectural and pipeline seams | 7 | End-to-end data integrity across seams | 100% Pass |
| **Tier 4: Real-World Scenarios** | Full researcher lifecycles, human-in-the-loop review, disaster recovery, and audit | 4 | Complete operational journeys verified | 100% Pass |
| **Total Suite** | Complete opaque-box verification of Deliveries 2, 3, and 4 | **40** | **Comprehensive requirement coverage** | **All 40 Pass** |

---

## 6. Test Runner Instructions

### Master Test Runner
Execute all tiers with summary reporting:
```powershell
python -m pytest tests/e2e_scholar_catalog/ -v
```
Or via the standalone runner:
```powershell
python tests/e2e_scholar_catalog/run_e2e_tests.py --tier all --report
```

### Running Individual Tiers
```powershell
# Tier 1 only (Feature Coverage)
python -m pytest tests/e2e_scholar_catalog/test_tier1_features.py -v

# Tier 2 only (Boundary & Corner Cases)
python -m pytest tests/e2e_scholar_catalog/test_tier2_boundaries.py -v

# Tier 3 only (Cross-Feature Combinations)
python -m pytest tests/e2e_scholar_catalog/test_tier3_combinations.py -v

# Tier 4 only (Real-World Application Scenarios)
python -m pytest tests/e2e_scholar_catalog/test_tier4_scenarios.py -v
```

### Pass/Fail Semantics
- Exit code `0`: All assertions passed across all executed tiers.
- Exit code `1`: One or more assertions failed, or an unexpected runtime exception occurred.
