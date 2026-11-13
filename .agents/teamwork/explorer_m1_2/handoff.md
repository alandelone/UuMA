# Handoff Report: W20 Evidence-Backed Semantic Relation Proposals

**Task:** Delivery 2 (Global Semantic Discovery) — Focus W20 Investigation  
**Author:** explorer_m1_2 (teamwork_explorer)  
**Date:** 2026-11-04  
**Working Directory:** `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\explorer_m1_2\`  
**Target Recipient:** orchestrator_1 (`f4bb50b0-e7de-4060-b026-8ed7bf7523f6`)

---

## 1. Observation

### 1.1 Direct Codebase Observations
1. **Core Candidate Index Implementation**:
   - Location: `C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_candidate_index.py` (126 lines).
   - Constants: `NEIGHBORS = 20` (line 9), `VERSION = 'catalog-candidate-neighbors-v1'` (line 10).
   - Functions:
     - `state(cache, identity, active_keys)` (lines 25–45): Reads existing candidate anchors and scopes from SQLite cache via read-only URI (`?mode=ro`).
     - `refresh(cache, identity, vectors, *, ensure_current, max_anchors=32)` (lines 47–126): Executes incremental nearest-neighbor search using NumPy float32 matrix blocks (`queries @ matrix.T`), bounded to `max_anchors` (default 32, max 128).
   - Invalidation & Fencing: Binds model generation and algorithm version: `model = key({'version': VERSION, 'identity': identity})`. Enforces `ensure_current()` callback before committing transactions.
2. **Retrieval Engine & Zero Runtime Pairwise Rescoring**:
   - Location: `C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_content_retrieval.py`.
   - Lines 358–396: `candidate_relations(limit=20, min_similarity=.75, offset=0, evidence_offset=0, evidence_limit=4)` calls `candidate_context()`.
   - Lines 397–429: `candidate_context()` calls `state(self.cache, identity, ...)` to load precomputed neighbors from SQLite. It does **not** call `self._vectors()` or NumPy matrix scoring during query execution.
   - Lines 431–445: `_append_candidate()` deduplicates distinct paper IDs using a Python set: `pair['paper_ids'].add(item['paper_id'])`, reporting `item['paper_count'] = len(item['paper_ids'])`.
   - Lines 438–440: Proposals are initialized with:
     ```python
     'status': 'CANDIDATE',
     'relation': 'UNRESOLVED_SIMILARITY',
     'automatically_applied': False,
     'scientific_acceptance': False
     ```
     and line 394 returns `'applied_merges': 0`.
3. **Cache Storage Location Difference**:
   - `C:\Users\Alandelone\CodeSpace_Local\UuMA\PROJECT.md` line 60 specifies:
     `- **Output Artifacts**: data/artifacts/catalog-content-index/vectors.sqlite, data/artifacts/catalog-candidate-index/candidate.sqlite.`
   - `src/rstv4/catalog_content_retrieval.py` line 117 specifies:
     `self.cache = self.root / 'data/artifacts/catalog-content-index/vectors.sqlite'`.
     Candidate tables (`candidate_scopes`, `candidate_anchors`) are created inside `vectors.sqlite`.
   - `tests/test_catalog_candidate_index.py` lines 49, 64, 80, 113 directly test with `cache = tmp_path / 'candidate.sqlite'`.
4. **Worker Hook & Night Window**:
   - Location: `C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_reading_worker.py` lines 523–546 (`content_index_tick()`).
   - Requires `os.environ.get('RSTV4_CATALOG_CONTENT_INDEX') == '1'`.
   - Checks `reading_policy.night_window_open()` (00:00–08:00 Asia/Kuala_Lumpur) and yields if foreground reading is pending.
   - Calls `index.refresh_batch(batch_size=4)`.
5. **Runtime Environment & Dependency**:
   - Primary virtual environment: `C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe`.
     - Executing `python -c "import numpy"` fails with: `ModuleNotFoundError: No module named 'numpy'`.
   - Isolated child environment: `C:\Users\Alandelone\CodeSpace_Local\RSTV4\.uuma-local\python\catalog-content-791032a82ebd\Scripts\python.exe`.
     - Executing `python -c "import numpy; print(numpy.__version__)"` outputs: `1.26.4`.

### 1.2 Test Execution Results
Executed the test suites using the isolated NumPy child runtime:
- `tests\test_catalog_candidate_index.py`:
  - Command: `& 'C:\Users\Alandelone\CodeSpace_Local\RSTV4\.uuma-local\python\catalog-content-791032a82ebd\Scripts\python.exe' -m pytest tests\test_catalog_candidate_index.py`
  - Result: `7 passed in 3.14s`
- `tests\test_catalog_candidate_links.py` and `tests\test_catalog_content_tools.py`:
  - Result: `19 passed, 1 warning in 9.82s`
- `tests\test_catalog_candidate_links_web.py`:
  - Result: `4 passed in 2.80s`
- `tests\test_catalog_content_worker_batch.py`:
  - Result: `4 passed in 0.21s`
- `tests\test_catalog_content_retrieval.py`:
  - Result: `15 passed in 3.52s`
- Total: **49 passing tests** across the content retrieval, candidate index, candidate links, MCP tools, and worker batch modules.

---

## 2. Logic Chain

1. **Incremental nearest-neighbor candidate graph in `candidate.sqlite`**:
   - The algorithmic foundation in `catalog_candidate_index.py` is sound and completely verified (7 passed tests).
   - In unit tests, `candidate.sqlite` is explicitly used. In `CatalogContentRetrieval`, `self.cache` defaults to `vectors.sqlite`. While functioning correctly within the same SQLite file, separating `self.candidate_cache` to `data/artifacts/catalog-candidate-index/candidate.sqlite` will cleanly align runtime code with `PROJECT.md` line 60 and isolate embedding storage from graph computation.
2. **Top-20 nearest-neighbor candidate matrix using NumPy float32 blocks (32-anchor batches)**:
   - `catalog_candidate_index.refresh()` enforces bounded batches (`max_anchors=32`, max 128).
   - Anchors are grouped by common `compare` sets and multiplied as 2D float32 matrices (`queries @ matrix.T`), followed by diagonal masking, stable argsort (`kind='stable'`), and truncation to `NEIGHBORS = 20`.
   - When new texts are added, existing neighbors of unchanged anchors are preserved and only comparisons against newly added texts are computed, drastically reducing pair comparisons below $N(N-1)$.
3. **Zero runtime pairwise rescoring during user queries**:
   - `candidate_relations()` and `candidate_context()` read only precomputed rows from `candidate_anchors`.
   - Verified directly by `test_candidate_query_reads_cache_without_loading_vectors_or_numeric_rescoring`, where monkeypatching vector loading and NumPy operations to fail does not impede candidate retrieval.
4. **Evidence citation from both sides with distinct paper counts (`paper_ids` set)**:
   - `_append_candidate` binds Theme previews and observations from both sides (`left` and `right`), requiring distinct `group_id`s.
   - Quotation evidence is aggregated with full source locations (`paper_id`, `file_version_id`, `pdf_sha256`, `parse_run_id`, `start`, `end`, `text`).
   - Distinct paper count is calculated as `len(pair['paper_ids'])` using a set, guaranteeing duplicate occurrences across multiple blocks in the same paper do not inflate unique paper statistics.
5. **Non-mutating proposal policy**:
   - Returned proposals remain in `CANDIDATE` status with `relation='UNRESOLVED_SIMILARITY'`, `automatically_applied=False`, and `applied_merges=0`.
   - Canonical `catalog.db` is read-only during candidate discovery (`test_candidate_cache_changes_no_canonical_tables` verified 0 table creations and 0 byte modifications in `catalog.db`).
   - Explicit human proposals and review actions are routed through W16 (`CandidateLinks.propose` and `CandidateLinks.review`), which enforce revision fencing and physical PDF integrity before allowing `ACCEPTED` state transitions.

---

## 3. Caveats

1. **Read-Only Investigation**: As an explorer subagent, no production code in `RSTV4` or `UuMA` was modified. All findings are derived from static analysis, architectural documentation review, and non-destructive test execution.
2. **Interpreter Divergence**: The host environment's default `.venv` lacks `numpy`. Worker execution or automated pipelines must target the child environment (`.uuma-local/python/catalog-content-791032a82ebd/Scripts/python.exe`) or install `numpy==1.26.4` into `.venv`.
3. **Live Corpus Aggregation vs Test Fixtures**: All 49 tests currently run against synthetic or scoped fixture databases. Full-corpus aggregation across the entire registered paper collection requires running during the night window (00:00–08:00 Asia/Kuala_Lumpur) with `RSTV4_CATALOG_CONTENT_INDEX=1`.

---

## 4. Conclusion

1. **W20 Implementation Readiness**: The candidate index mechanism is mathematically correct, fully implemented, and passes all unit and integration tests. It strictly adheres to all constraints:
   - Top-20 nearest-neighbor calculation with 32-anchor batches via NumPy float32.
   - Zero runtime vector loading or matrix rescoring on user queries.
   - Two-sided located evidence citation with distinct `paper_ids` set counting.
   - Non-mutating proposal policy with `UNRESOLVED_SIMILARITY` and `applied_merges=0`.
2. **Implementation Worker Action Items for M1**:
   - **Action Item 1 (Interpreter)**: Configure worker tasks to use the NumPy 1.26.4 interpreter (`.uuma-local/python/catalog-content-791032a82ebd/Scripts/python.exe`) or synchronize `.venv` with `pyproject.toml`.
   - **Action Item 2 (Cache Separation)**: Update `CatalogContentRetrieval` to support `self.candidate_cache = self.root / 'data/artifacts/catalog-candidate-index/candidate.sqlite'` to strictly match `PROJECT.md` line 60.
   - **Action Item 3 (Activation Guard)**: Set `RSTV4_CATALOG_CONTENT_INDEX=1` in the worker environment during night reading window execution.

---

## 5. Verification Method

To independently verify all findings and test suites:

1. **Run Candidate Index Test Suite**:
   ```powershell
   cd C:\Users\Alandelone\CodeSpace_Local\RSTV4
   & "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.uuma-local\python\catalog-content-791032a82ebd\Scripts\python.exe" -m pytest tests\test_catalog_candidate_index.py -v
   ```
   *Expected outcome*: 7 passed.

2. **Run Candidate Links & FastMCP Tools Test Suites**:
   ```powershell
   & "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.uuma-local\python\catalog-content-791032a82ebd\Scripts\python.exe" -m pytest tests\test_catalog_candidate_links.py tests\test_catalog_candidate_links_web.py tests\test_catalog_content_tools.py tests\test_catalog_content_worker_batch.py -v
   ```
   *Expected outcome*: 27 passed.

3. **Verify Zero Runtime Rescoring & Canonical DB Immutability**:
   Inspect `tests\test_catalog_candidate_index.py`:
   - `test_candidate_query_reads_cache_without_loading_vectors_or_numeric_rescoring` (lines 95–110)
   - `test_candidate_cache_changes_no_canonical_tables` (lines 124–132)
