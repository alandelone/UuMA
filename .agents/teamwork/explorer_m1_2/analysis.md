# Analysis: Global Semantic Discovery — Candidate Semantic Relation Proposals (W20)

**Author:** explorer_m1_2 (teamwork_explorer)  
**Date:** 2026-11-04  
**Target Milestone:** Delivery 2 (Global Semantic Discovery), Work Item W20  
**Repository Paths:**
- UuMA: `C:\Users\Alandelone\CodeSpace_Local\UuMA\`
- RSTV4: `C:\Users\Alandelone\CodeSpace_Local\RSTV4\`

---

## 1. Executive Summary

This investigation examines the requirements, architecture, implementation status, and verification strategy for **W20 (Evidence-Backed Semantic Relation Proposals)** within Delivery 2 (Global Semantic Discovery).

Key findings:
1. **Core Implementation Complete & Verified**: The core candidate graph indexing (`src/rstv4/catalog_candidate_index.py`), retrieval integration (`src/rstv4/catalog_content_retrieval.py`), human proposal/review links (`src/rstv4/catalog_candidate_links.py`), FastMCP content tools (`src/rstv4/catalog_content_tools.py`), and worker background execution (`src/rstv4/catalog_reading_worker.py`) are fully implemented in RSTV4.
2. **All 34 Related Tests Passing**: The 7 focused candidate index tests in `test_catalog_candidate_index.py`, 16 tests in `test_catalog_candidate_links.py`, 4 tests in `test_catalog_candidate_links_web.py`, 3 tests in `test_catalog_content_tools.py`, and 4 tests in `test_catalog_content_worker_batch.py` all pass cleanly with zero failures.
3. **Strict Policy Compliance**:
   - Incremental nearest-neighbor candidate graph computes top-20 nearest neighbors using NumPy float32 matrix blocks in bounded 32-anchor batches.
   - Zero runtime pairwise rescoring during user queries: queries read precomputed SQLite rows only, with zero vector loading or NumPy matrix operations.
   - Evidence citation binds located source passages from both sides of the proposal, deduplicating distinct paper IDs (`paper_ids` set) without Cartesian inflation.
   - Non-mutating proposal policy strictly enforced: proposals remain in `status='CANDIDATE'`, `relation='UNRESOLVED_SIMILARITY'`, `automatically_applied=False`, and `applied_merges=0`. Canonical database `catalog.db` is read-only during indexing and querying.
4. **Key Finding & Recommendation for Worker**:
   - **Environment Requirement**: The default `.venv` in RSTV4 lacks `numpy==1.26.4`. The worker must be executed using the verified isolated child interpreter (`C:\Users\Alandelone\CodeSpace_Local\RSTV4\.uuma-local\python\catalog-content-791032a82ebd\Scripts\python.exe`) or have NumPy installed into the primary environment.
   - **Artifact Path Reconciliation**: `PROJECT.md` line 60 specifies `data/artifacts/catalog-candidate-index/candidate.sqlite`, whereas `CatalogContentRetrieval` currently creates candidate tables inside `data/artifacts/catalog-content-index/vectors.sqlite`. This architectural difference is analyzed below with recommendations.

---

## 2. Requirement Analysis & Architectural Trace

### 2.1 Candidate Graph & SQLite Storage

#### File Locations
- Core Candidate Index: `C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_candidate_index.py`
- Retrieval Engine: `C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_content_retrieval.py`
- Human Links & W16 Integration: `C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_candidate_links.py`

#### Database Schema in Candidate Cache
The candidate cache uses two tables:

```sql
CREATE TABLE IF NOT EXISTS candidate_scopes (
    model_key TEXT,
    scope_key TEXT,
    keys_json TEXT,
    PRIMARY KEY(model_key, scope_key)
);

CREATE TABLE IF NOT EXISTS candidate_anchors (
    model_key TEXT,
    text_sha256 TEXT,
    scope_key TEXT,
    neighbors_json TEXT,
    updated_order INTEGER,
    PRIMARY KEY(model_key, text_sha256)
);
```

- **`model_key`**: SHA-256 digest of `{'version': VERSION, 'identity': identity}` where `VERSION = 'catalog-candidate-neighbors-v1'`. It cryptographically binds the BGE-M3 service generation and candidate algorithm version. If the embedding service restarts with a new generation ID or the candidate algorithm version changes, old cache rows become inactive and are not relabeled.
- **`scope_key`**: SHA-256 digest of `sorted(set(active_keys))`. Represents the exact corpus of Theme texts eligible for comparison.
- **`keys_json`**: Canonical JSON list of active `text_sha256` keys.
- **`neighbors_json`**: Canonical JSON serialized list of `[neighbor_text_sha256, score]` tuples (up to 20 neighbors), sorted by descending similarity score and ascending text digest for deterministic ordering.
- **`updated_order`**: Monotonically increasing sequence integer. Each updated anchor receives `last + i + 1`, ensuring fair round-robin scheduling across changing corpora.

#### Artifact Path Distinction
- In `PROJECT.md` line 60:
  `- **Output Artifacts**: data/artifacts/catalog-content-index/vectors.sqlite, data/artifacts/catalog-candidate-index/candidate.sqlite.`
- In `CatalogContentRetrieval.__init__`:
  `self.cache = self.root / 'data/artifacts/catalog-content-index/vectors.sqlite'`
  Candidate tables are currently written into `self.cache` (`vectors.sqlite`).
- In `test_catalog_candidate_index.py`:
  Direct unit tests explicitly instantiate `cache = tmp_path / 'candidate.sqlite'`.

---

### 2.2 Top-20 Nearest-Neighbor Matrix Computation

In `src/rstv4/catalog_candidate_index.py`:

1. **Parameters & Batching**:
   - `NEIGHBORS = 20`: Candidate suggestion scope, not exhaustive enumeration or label pruning.
   - `max_anchors = 32`: Default batch limit (bounded between 1 and 128). In `catalog_reading_worker.py`, `content_index_tick` invokes indexing with batch size 4 for embedding, which transitions to candidate aggregation.
2. **Incremental Neighbor Preservation**:
   - If an anchor previously had neighbors in `rows`, and all its previous neighbors remain in the current active text set:
     - The existing neighbor list is preserved: `preserved[anchor] = neighbors`.
     - Comparison is evaluated ONLY against newly added texts: `compare = tuple(sorted(active_set - prior - {anchor}))`.
     - Total pair comparisons during corpus growth is strictly less than $N \times (N-1)$.
   - If ANY previous neighbor was removed (or no prior scope exists):
     - A full rescan is triggered for that anchor: `compare = tuple(active)` and `preserved[anchor] = []`.
3. **NumPy Float32 Matrix Block Acceleration**:
   - Anchors with identical `compare` targets are grouped:
     ```python
     matrix = np.asarray([vectors[text] for text in compare], dtype=np.float32)
     queries = np.asarray([vectors[text] for text in group], dtype=np.float32)
     scores = np.clip(queries @ matrix.T, -1., 1.)
     ```
   - Self-similarity diagonal suppression: `scores[position, positions[anchor]] = -np.inf`.
   - Deterministic tie-breaking: `indices = np.argsort(-scores[position], kind='stable')[:NEIGHBORS]`.
   - Merging with preserved scores:
     ```python
     best = {text: score for text, score in preserved[anchor] if text in active_set}
     best.update((compare[int(i)], float(scores[position, i])) for i in indices if compare[int(i)] != anchor)
     updates[anchor] = sorted(best.items(), key=lambda item: (-item[1], item[0]))[:NEIGHBORS]
     ```
4. **Source Fence Guard**:
   - `ensure_current()` is invoked before committing to ensure the underlying Catalog snapshot fingerprint did not mutate during numeric computation.

---

### 2.3 Zero Runtime Pairwise Rescoring During User Queries

In `src/rstv4/catalog_content_retrieval.py`:

1. **Query Entry**: `candidate_relations(limit=20, min_similarity=0.75, offset=0, evidence_offset=0, evidence_limit=4)` calls `candidate_context(min_similarity=min_similarity)`.
2. **Stored Row Lookup**:
   - `candidate_context()` calls `state(self.cache, identity, [...])`.
   - `state()` executes a read-only query against `candidate_anchors WHERE model_key=?`.
   - **No vector embeddings are loaded into memory** (`self._vectors()` is never called).
   - **No NumPy matrix multiplications or rescoring occur** (`queries @ matrix.T` is never called).
3. **Edge Assembly**:
   - Pre-calculated neighbor pairs `(text, other, score)` from SQLite are filtered against `min_similarity`.
   - Self-similarity edges `(text, text, 1.0)` are included only if the identical text appears in multiple distinct Theme groups.
4. **Verification Evidence**:
   - `test_candidate_query_reads_cache_without_loading_vectors_or_numeric_rescoring` monkeypatches `index._vectors` and `np.asarray` to raise an `AssertionError` if invoked during `index.candidate_relations()`. The test passes, proving zero runtime vector loading and zero runtime scoring.

---

### 2.4 Evidence Binding & Distinct Paper Counts

1. **Two-Sided Evidence Representation**:
   - Proposals bind two distinct Theme instances from different Theme groups: `left[0]['theme']['group_id'] != right[0]['theme']['group_id']`.
   - Both sides' labels and definitions are exposed in `theme_previews`:
     `[{'theme_id': left_id, 'label': left_label, 'definition': left_def}, {'theme_id': right_id, 'label': right_label, 'definition': right_def}]`.
   - `require_documents(conn, documents, physical=True)` in `catalog_candidate_links.py` verifies:
     `if len(themes) != 2: raise ValueError('Candidate relationship must retain both distinct original Themes')`
2. **Located Evidence Citation**:
   - Every citation in `evidence` retains:
     - `paper_id` & `title`
     - `file_version_id` & `pdf_sha256`
     - `parse_run_id`
     - `page_number`, `section`, `block_id`, `block_content_digest`
     - `start`, `end`, and exact quote string `text`
     - `theme` object (`theme_id`, `observation_id`, `label`, `definition`, `review`)
3. **Deduplicated Distinct Paper Counts**:
   - As observations from both sides are collected:
     ```python
     for item in left + right:
         pair['evidence'][item['document_id']] = item
         pair['paper_ids'].add(item['paper_id'])
     ```
   - `item['paper_count'] = len(item['paper_ids'])` where `paper_ids` is a Python `set`.
   - Total distinct paper count reflects true unique paper IDs, preventing Cartesian explosion or duplicate counts across multiple blocks.

---

### 2.5 Non-Mutating Proposal Policy & W16 Review Workflow

1. **Unresolved State Invariant**:
   - Query results return items with:
     - `status: 'CANDIDATE'`
     - `relation: 'UNRESOLVED_SIMILARITY'`
     - `automatically_applied: False`
     - `scientific_acceptance: False`
     - `applied_merges: 0`
   - Canonical `catalog.db` tables (`papers`, `document_blocks`, `catalog_themes`, etc.) are never mutated by candidate indexing or retrieval.
2. **Human Proposal Generation (`CandidateLinks.propose`)**:
   - Stored in `catalog_candidate_link_proposals` and `catalog_theme_links`.
   - Requires explicit human request (`suggestion_id`, `expected_source_fingerprint`, `relation: 'RELATED'|'ALIAS'|'MERGE'`, `rationale`, `request_id`).
   - Validates that the physical PDF bytes on disk match `pdf_sha256` and parse run.
   - Resulting record remains `status='CANDIDATE'`.
3. **Human Review Lifecycle (`CandidateLinks.review` & W16 Integration)**:
   - Uses `CatalogUnderstanding.review()` with `kind='LINK'`.
   - Fenced by `expected_revision`.
   - Supports state transitions: `CANDIDATE` -> `ACCEPTED` -> `REJECTED`, or compensating reversal back to `CANDIDATE`.
   - Acceptance causes `_groups()` in `CatalogUnderstanding` to map alias themes together for aggregation while preserving 100% of the original labels, definitions, and observation audit records.
   - Physical PDF guard: if the physical PDF on disk is tampered with or altered after the proposal, `require_documents(..., physical=True)` blocks acceptance with `ValueError` while permitting reversal to `REJECTED`.

---

## 3. Test Review & Verification Analysis

### 3.1 Review of `tests/test_catalog_candidate_index.py`

The test suite contains 7 focused tests:

| # | Test Name | Purpose / Assertion | Status |
|---|-----------|---------------------|--------|
| 1 | `test_bounded_candidate_batches_resume_to_exact_nearest_neighbor_graph` | Verifies batching (`max_anchors=3`), partial resume, comparisons count, exactness against brute-force reference matrix, and zero-op idempotency on second run. | PASS (0.24s) |
| 2 | `test_new_texts_reuse_prior_comparisons_and_removed_neighbor_is_refilled` | Verifies incremental additions compare only new texts ($< N(N-1)$ comparisons), and deleting a neighbor forces an accurate refill. | PASS (0.42s) |
| 3 | `test_candidate_model_generation_and_source_fence_do_not_relabel_old_cache` | Verifies cache invalidation when model generation changes (`generation='two'`) and source change mid-aggregation raises exception without corrupting cache. | PASS (0.08s) |
| 4 | `test_candidate_query_reads_cache_without_loading_vectors_or_numeric_rescoring` | Monkeypatches `_vectors` and `np.asarray` to raise `AssertionError`; asserts `candidate_relations` succeeds without loading vectors or computing matrix products. | PASS (0.35s) |
| 5 | `test_fair_anchor_order_advances_under_repeated_scope_growth` | Incrementally adds texts across 10 iterations; asserts `updated_order` sequence advances fairly so old anchors are not starved. | PASS (0.31s) |
| 6 | `test_candidate_cache_changes_no_canonical_tables` | Asserts `catalog.db` contains zero `candidate_%` tables and file bytes remain byte-identical before and after indexing. | PASS (0.28s) |
| 7 | `test_crossing_end_of_window_publishes_inflight_vectors_but_defers_new_aggregation` | Simulates night window boundary closure during in-flight embedding; asserts in-flight vectors are saved but aggregation is deferred. | PASS (0.32s) |

### 3.2 Review of Supporting Test Suites

In addition to `test_catalog_candidate_index.py`, 4 related test suites were verified:

1. **`tests/test_catalog_candidate_links.py`** (16 tests, PASS):
   - Tests source-bound idempotent proposals.
   - Tests `ALIAS`, `MERGE`, and `RELATED` review transitions.
   - Tests compensating reversals preserving all original labels.
   - Tests physical source tampering rejection.
2. **`tests/test_catalog_candidate_links_web.py`** (4 tests, PASS):
   - Tests REST API endpoints `/api/catalog/understanding/content/candidates` and `/relationships`.
3. **`tests/test_catalog_content_tools.py`** (3 tests, PASS):
   - Tests FastMCP tool `get_catalog_theme_candidates`.
   - Asserts bounded transport previews adhere to `MAX_RESPONSE_CHARACTERS` (8000 chars).
   - Asserts proposals maintain `applied_merges=0` and `status='CANDIDATE'`.
4. **`tests/test_catalog_content_worker_batch.py`** (4 tests, PASS):
   - Tests worker `content_index_tick` under CPU budget (`batch_size=4`).
   - Tests daytime window exclusion (`WAITING_FOR_NIGHT_OR_FOREGROUND`).
   - Tests cooldown interval management (5s active, 300s idle, 60s window closed).

---

## 4. Execution Environment & Worker Strategy

### 4.1 Python Runtime & Dependency Environment

The standard virtual environment at `C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv` does NOT contain `numpy`. Attempting to run `pytest` or `catalog_reading_worker.py` with that interpreter produces:
`ModuleNotFoundError: No module named 'numpy'`

An isolated child runtime was previously prepared at:
`C:\Users\Alandelone\CodeSpace_Local\RSTV4\.uuma-local\python\catalog-content-791032a82ebd\Scripts\python.exe`
(documented in `content-numeric-runtime-v308/receipt.json` and `docs/operations/scholar-catalog-semantic-retrieval-2026-10-29.md`). It incorporates official PyPI `numpy==1.26.4` and references the donor site packages via `site.addsitedir`.

### 4.2 Background Worker Execution Flow

In `src/rstv4/catalog_reading_worker.py`:
1. Worker loop runs: `self.discover()` -> `self.run_once()` -> `self.content_index_tick()`.
2. `content_index_tick()` checks:
   - `os.environ.get('RSTV4_CATALOG_CONTENT_INDEX') == '1'`
   - `time.monotonic() >= self._content_index_due`
   - `reading_policy.night_window_open()` (00:00–08:00 Asia/Kuala_Lumpur)
   - Foreground reading pending: yields if foreground jobs exist
3. Invokes `index.refresh_batch(batch_size=4)`.
4. `refresh_batch()` in `CatalogContentRetrieval`:
   - Acquires `instance_lock(self.root, 'catalog-content-index', '1')` (non-blocking; returns `BUSY` on contention).
   - Embeds missing text chunks (up to 4 at a time).
   - When all eligible texts are embedded, executes candidate aggregation:
     `self._refresh_candidates(snapshot, identity, vectors, manual_requested=False)`
     which delegates to `catalog_candidate_index.refresh(..., max_anchors=32)`.
5. Worker updates `_content_index_due`:
   - Useful progress (`embedded` or `aggregated_anchors`): +5 seconds.
   - No work needed: +300 seconds.
   - Day window / outside night: +60 seconds.
   - Error caught: logs `UNAVAILABLE` and defers for +60 seconds without crashing the reading worker.

---

## 5. Recommendations & Strategy for W20 Delivery Worker

### Recommendation 1: Artifact Cache Location Alignment
- **Observation**: `PROJECT.md` contract lists `data/artifacts/catalog-candidate-index/candidate.sqlite`, but `CatalogContentRetrieval` writes candidate tables into `self.cache` (`data/artifacts/catalog-content-index/vectors.sqlite`).
- **Options for Implementer**:
  - *Option A (Contract Alignment)*: Add a `self.candidate_cache = self.root / 'data/artifacts/catalog-candidate-index/candidate.sqlite'` property to `CatalogContentRetrieval` and pass it to `catalog_candidate_index.refresh()` and `state()`. This separates embedding vectors from the candidate neighbor graph.
  - *Option B (Contract Clarification)*: If retaining single-cache consolidation under `vectors.sqlite` is preferred to avoid managing two SQLite connections, update `PROJECT.md` interface contracts to reflect that candidate tables reside within `vectors.sqlite`.
  - *Explorer Assessment*: Option A is cleaner and strictly satisfies both `PROJECT.md` line 60 and E2E acceptance criteria.

### Recommendation 2: Worker Python Interpreter Configuration
- **Observation**: `start-catalog-reading-worker.ps1` takes `-Python $Python`. If invoked with `.venv/Scripts/python.exe`, candidate indexing fails due to missing `numpy`.
- **Recommendation for Worker**:
  - Ensure the worker execution command explicitly passes:
    `-Python "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.uuma-local\python\catalog-content-791032a82ebd\Scripts\python.exe"`
  - Alternatively, execute `uv pip install numpy==1.26.4` (or `pip install numpy==1.26.4`) in `C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv` to align the default `.venv` with `pyproject.toml` line 14.

### Recommendation 3: Night Window & CPU Budget Verification
- **Observation**: Automated candidate aggregation requires `RSTV4_CATALOG_CONTENT_INDEX=1` and `00:00-08:00 Asia/Kuala_Lumpur`.
- **Recommendation for Worker**:
  - In non-night hours or during automated test validation, explicit manual calls (`index.refresh_batch(manual_requested=True)` or API `POST /api/catalog/understanding/content/index`) must be used to advance the index.
  - Keep `batch_size=4` for text embeddings and `max_anchors=32` for candidate aggregation to respect CPU resource bounds.
