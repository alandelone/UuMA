# Changes Made for Milestone M1 (Delivery 2 — Global Semantic Discovery)

**Agent**: worker_m1 (teamwork_worker)  
**Milestone**: M1 (Delivery 2: Global Semantic Discovery — W19, W20, W21)  
**Date**: 2026-11-04  

---

## 1. Environment Synchronization
- **Installed Dependency**: `numpy==1.26.4` installed into `C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv` from verified offline wheel:
  `C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\content-numeric-runtime-v308\numpy-1.26.4-cp311-cp311-win_amd64.whl`
- **Result**: Synchronized RSTV4 virtual environment with `pyproject.toml` dependency requirements without internet access.

---

## 2. Code Modifications

### 2.1 `src/rstv4/catalog_candidate_index.py`
- **Path Support & Directory Auto-Creation**:
  - Added `from pathlib import Path`.
  - In `state(cache, identity, active_keys)`: Converted `cache = Path(cache)` to support both string and Path instances.
  - In `refresh(cache, identity, vectors, *, ensure_current, max_anchors=32)`: Converted `cache = Path(cache)` and added `cache.parent.mkdir(parents=True, exist_ok=True)` to prevent `sqlite3.OperationalError` when `candidate.sqlite` is initialized in an isolated directory.

### 2.2 `src/rstv4/catalog_content_retrieval.py`
- **Adherence to PROJECT.md line 60 for Candidate Cache Separation**:
  - Updated `CatalogContentRetrieval.__init__` to accept optional `candidate_cache` keyword argument:
    ```python
    self.cache = self.root / 'data/artifacts/catalog-content-index/vectors.sqlite'
    self.candidate_cache = (
        Path(candidate_cache).resolve()
        if candidate_cache is not None
        else (self.root / 'data/artifacts/catalog-candidate-index/candidate.sqlite')
    )
    ```
  - Redirected `_refresh_candidates()` to write candidate anchors and scopes into `self.candidate_cache` (`data/artifacts/catalog-candidate-index/candidate.sqlite`).
  - Redirected `candidate_context()` to read candidate state from `self.candidate_cache`.
- **Honest Coverage Reporting**:
  - In `status()`: Added explicit `'complete': indexed == len(passages)` alongside `'eligible_index_complete'`, guaranteeing honest and uniform reporting across metadata calls (`eligible_passages`, `indexed_passages`, `complete`, `pending_sources`, `paused_paper_ids`).
  - In `search()`: Added `'paused_paper_ids': snapshot['indexing_paused_paper_ids']` both at top-level and inside `'semantic_index'`.
  - In `candidate_relations()`: Added `'paused_paper_ids': snapshot['indexing_paused_paper_ids']` and confirmed strict reporting of `'applied_merges': 0` and `'relation': 'UNRESOLVED_SIMILARITY'`.

### 2.3 `tests/test_catalog_content_retrieval.py`
- Added integration test:
  - `test_candidate_cache_path_separation_and_override`: Verifies that default cache separation creates `vectors.sqlite` under `data/artifacts/catalog-content-index/` and `candidate.sqlite` under `data/artifacts/catalog-candidate-index/`, and that the `candidate_cache` constructor parameter cleanly overrides the destination.

### 2.4 `tests/test_catalog_content_tools.py`
- Added imports: `import pytest`, `from rstv4.catalog_understanding import CatalogUnderstanding`.
- Added required integration tests:
  - `test_content_tools_reflect_w16_theme_corrections_and_revision_fencing`:
    - Validates that initial candidate queries retrieve genuine machine observations.
    - Validates revision fencing on human EDIT: mismatched revision raises `ValueError("Theme correction revision changed")`.
    - Validates that genuine human EDIT (`store.correct_theme`) creates a new effective observation with status `ACCEPTED`.
    - Validates that after indexing, FastMCP `get_catalog_theme_candidates` surfaces the human-corrected theme label preview and observation ID.
    - Validates revision fencing on RESTORE: mismatched revision raises `ValueError`.
    - Validates that compensating RESTORE (`restore_revision=0`) restores the original machine observation, and FastMCP search results reflect the restored observation after indexing.
  - `test_bounded_candidate_previews_and_evidence_pagination`:
    - Validates bounded candidate preview truncation: `label_preview` truncated to $\le 200$ characters, evidence list capped at $\le 4$ items with `evidence_preview_truncated=True` and exact `evidence_total`.
    - Validates continuous `next_offset` pagination: 5 items across 3 pages (offsets 0, 2, 4) verify `next_offset` progression without item skipping or overlapping, terminating with `has_more=False` and `next_offset=None`.
    - Validates exact quotation preservation in search responses: quotes are never clipped or damaged during response transport bounding.

---

## 3. Database Invariant
- Pre-execution SHA-256: `EECA6B97FB4E1D20D33D8480C196561DCA9EAE35605DEBA7F8E56DE0E6B63C65`
- Post-execution SHA-256: `EECA6B97FB4E1D20D33D8480C196561DCA9EAE35605DEBA7F8E56DE0E6B63C65`
- **Result**: Invariant strictly maintained (0 mutations to `data/catalog.db`).
