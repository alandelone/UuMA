# Forensic Audit Report: Milestone M1 (Delivery 2 — Global Semantic Discovery)

**Agent**: `auditor_m1_1` (forensic_auditor)  
**Parent Agent**: `orchestrator_2` (`4c361d1e-a20f-4ba4-b1ff-f1cd6b7d8128`)  
**Target Work Product**: Milestone M1 (Delivery 2 — Global Semantic Discovery: W19, W20, W21)  
**Integrity Mode**: Development Mode (as specified in `ORIGINAL_REQUEST.md`)  
**Verdict**: **CLEAN**  

---

## 1. Observation

### 1.1 Canonical Database Invariance & Read-Only Fencing
- **Baseline SHA-256 Hash**:
  `EECA6B97FB4E1D20D33D8480C196561DCA9EAE35605DEBA7F8E56DE0E6B63C65`
- **Pre-Test Run Hash Verification**:
  ```powershell
  Get-FileHash 'C:\Users\Alandelone\CodeSpace_Local\RSTV4\data\catalog.db' -Algorithm SHA256
  ```
  Result:
  ```
  Algorithm : SHA256
  Hash      : EECA6B97FB4E1D20D33D8480C196561DCA9EAE35605DEBA7F8E56DE0E6B63C65
  Path      : C:\Users\Alandelone\CodeSpace_Local\RSTV4\data\catalog.db
  ```
- **Post-Test Run Hash Verification**:
  ```powershell
  Get-FileHash 'C:\Users\Alandelone\CodeSpace_Local\RSTV4\data\catalog.db' -Algorithm SHA256
  ```
  Result:
  ```
  Algorithm : SHA256
  Hash      : EECA6B97FB4E1D20D33D8480C196561DCA9EAE35605DEBA7F8E56DE0E6B63C65
  Path      : C:\Users\Alandelone\CodeSpace_Local\RSTV4\data\catalog.db
  ```
- **Read-Only SQLite Protection in `src/rstv4/catalog_content_retrieval.py`** (lines 35–40):
  ```python
  def connection(path):
      conn = sqlite3.connect(Path(path).resolve(strict=True).as_uri() + '?mode=ro', uri=True)
      conn.row_factory = sqlite3.Row
      conn.execute('PRAGMA query_only=ON')
      conn.execute('BEGIN')
      return conn
  ```
  Database connection is strictly locked with URI `?mode=ro` and `PRAGMA query_only=ON`.

### 1.2 Algorithmic Authenticity (BM25, Cosine Similarity, RRF, NumPy)
- In `src/rstv4/catalog_candidate_index.py` (lines 91–108):
  - True matrix dot product calculation:
    ```python
    matrix = np.asarray([vectors[text] for text in compare], dtype=np.float32)
    queries = np.asarray([vectors[text] for text in group], dtype=np.float32)
    scores = np.clip(queries @ matrix.T, -1., 1.)
    ```
  - Numerical checks: `if not np.isfinite(scores).all(): raise ValueError(...)`.
  - Self-exclusion: `scores[position, positions[anchor]] = -np.inf`.
  - Stable sort and Top-K extraction: `indices = np.argsort(-scores[position], kind='stable')[:NEIGHBORS]`.
- In `src/rstv4/catalog_content_retrieval.py` (lines 313–335):
  - Standard BM25 calculation:
    `length_factor = 1.2 * (.25 + .75 * sum(tokens.values()) / max(1, average_length))`
    `lexical[key] = sum(math.log(1 + (len(docs) - frequencies[t] + .5) / (frequencies[t] + .5)) * tokens[t] * 2.2 / (tokens[t] + length_factor) for t in terms if tokens[t])`
  - Dense cosine similarity: `sum(a * b for a, b in zip(query_vector, vector))`.
  - Reciprocal Rank Fusion (RRF): `ranks[key] = ranks.get(key, 0) + 1 / (60 + rank)` with standard constant $k=60$.
  - 0 hardcoded strings, 0 facade return values, and 0 dummy calculation bypasses.

### 1.3 Proposal Non-Mutation
- In `src/rstv4/catalog_content_retrieval.py` (lines 405, 449–451):
  - `status: 'CANDIDATE'`
  - `relation: 'UNRESOLVED_SIMILARITY'`
  - `applied_merges: 0`
  - `automatically_applied: False`
  - `scientific_acceptance: False`
- In `src/rstv4/catalog_content_tools.py` (lines 73–80):
  - Docstring and schema explicitly require:
    `"UNRESOLVED_SIMILARITY is not equivalence. This never applies a merge, accepts a claim, creates a research Field, indexes sources or starts deep reading."`
  - Candidate responses return two-sided evidence previews without executing any database writes or merges.

### 1.4 Governance, Policy & Work Isolation (§9)
- Single-writer serialization via `instance_lock` in `src/rstv4/catalog_content_retrieval.py`:
  `with instance_lock(self.root, 'catalog-content-index', '1'): ...`
  `with instance_lock(self.root, 'catalog-content-request', digest(request_id)): ...`
- Night window enforcement in `src/rstv4/reading_policy.py`:
  `TIMEZONE = "Asia/Kuala_Lumpur"`, `WINDOW_START_HOUR = 0`, `WINDOW_END_HOUR = 8`.
  `night_window_open()` gates automatic background index runs unless `manual_requested=True`.
- Workspace isolation:
  - All worker modifications were confined strictly to the designated files:
    `src/rstv4/catalog_content_retrieval.py`, `src/rstv4/catalog_candidate_index.py`, `src/rstv4/catalog_content_tools.py`, `tests/test_catalog_content_retrieval.py`, `tests/test_catalog_candidate_index.py`, `tests/test_catalog_content_tools.py`.
  - No source or test files exist in `.agents/teamwork/`.

### 1.5 Independent Test Execution & Linting
- **Independent Pytest Run**:
  Command:
  ```powershell
  & "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -m pytest `
    tests/test_catalog_content_retrieval.py `
    tests/test_catalog_candidate_index.py `
    tests/test_catalog_content_tools.py `
    tests/test_catalog_candidate_links.py `
    tests/test_catalog_theme_corrections.py `
    tests/test_catalog_content_worker_batch.py -v
  ```
  Result:
  `======================= 67 passed, 2 warnings in 22.46s =======================`
  - `tests/test_catalog_content_retrieval.py`: 16 passed
  - `tests/test_catalog_candidate_index.py`: 7 passed
  - `tests/test_catalog_content_tools.py`: 5 passed
  - `tests/test_catalog_candidate_links.py`: 16 passed
  - `tests/test_catalog_theme_corrections.py`: 19 passed
  - `tests/test_catalog_content_worker_batch.py`: 4 passed
- **Ruff Lint Check**:
  Command:
  ```powershell
  & "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -m ruff check `
    src/rstv4/catalog_content_retrieval.py `
    src/rstv4/catalog_candidate_index.py `
    src/rstv4/catalog_content_tools.py `
    tests/test_catalog_content_retrieval.py `
    tests/test_catalog_candidate_index.py `
    tests/test_catalog_content_tools.py
  ```
  Result: `All checks passed!` (0 lint errors).

---

## 2. Logic Chain

1. **Database Immutability Verified**: The SHA-256 hash of `C:\Users\Alandelone\CodeSpace_Local\RSTV4\data\catalog.db` was checked before and after all 67 tests were executed. The hash matched `EECA6B97FB4E1D20D33D8480C196561DCA9EAE35605DEBA7F8E56DE0E6B63C65` bit-for-bit. Read-only flags (`?mode=ro` and `PRAGMA query_only=ON`) guarantee that catalog retrieval cannot write to `catalog.db`.
2. **Authentic Computation Verified**: Inspection of `catalog_candidate_index.py` and `catalog_content_retrieval.py` confirms genuine NumPy matrix multiplications (`queries @ matrix.T`), mathematical Reciprocal Rank Fusion ($1/(60+rank)$), and standard BM25 calculations. No canned mock values or dummy facades bypass algorithmic logic.
3. **Non-Mutating Proposals Confirmed**: All candidate relations maintain `status='CANDIDATE'`, `relation='UNRESOLVED_SIMILARITY'`, `automatically_applied=False`, and `applied_merges=0`. Tool handlers expose bounded evidence without mutating canonical entities.
4. **Governance Conformance (§9)**: Single-writer serialization is enforced via `instance_lock`, night window bounds (00:00–08:00 Asia/Kuala_Lumpur) gate automatic batch indexing, and workspace file discipline was strictly maintained.
5. **Phase 2 Mode Flagging**: In Development Mode (stipulated by `ORIGINAL_REQUEST.md` line 8), code reuse of `numpy` and standard packages is fully authorized. The implementation contains 0 hardcoded test results, 0 facades, and 0 fabricated artifacts.

---

## 3. Caveats

- **Full Corpus Batch Run**: Full background indexing of all 21,403 passages in the corpus is not executed during this audit run; per §9 and `reading_policy.py`, full automatic batch runs occur during the scheduled night window (00:00–08:00 Asia/Kuala_Lumpur). The algorithm and window enforcement have been verified via tests.
- **Remote Model Service**: Tests utilize deterministic vector adapters (`Embeddings` fixture) to verify mathematical retrieval and fencing without requiring live network access to `alandelone-server-001:8893`. The production client `ScholarEmbeddings` was inspected and verified for SSH stdin isolation and timeout contracts.

---

## 4. Conclusion

**Verdict: CLEAN**

Milestone M1 (Delivery 2 — Global Semantic Discovery: W19, W20, W21) strictly complies with all integrity rules, governance constraints (§9), and architectural requirements:
- Zero hardcoded test results or facade shortcuts detected.
- Canonical database `catalog.db` remained completely unmodified (`EECA6B97FB4E1D20D33D8480C196561DCA9EAE35605DEBA7F8E56DE0E6B63C65`).
- Candidate relations are strictly non-mutating proposals with `applied_merges=0`.
- All 67 automated tests pass and ruff lint reports 0 errors.

---

## 5. Verification Method

To reproduce and independently confirm this audit:

1. **Verify Database Invariant**:
   ```powershell
   Get-FileHash 'C:\Users\Alandelone\CodeSpace_Local\RSTV4\data\catalog.db' -Algorithm SHA256
   ```
   *Expected*: `EECA6B97FB4E1D20D33D8480C196561DCA9EAE35605DEBA7F8E56DE0E6B63C65`.

2. **Execute Full Test Suite**:
   ```powershell
   & "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -m pytest `
     "C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_content_retrieval.py" `
     "C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_candidate_index.py" `
     "C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_content_tools.py" `
     "C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_candidate_links.py" `
     "C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_theme_corrections.py" `
     "C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_content_worker_batch.py" -v
   ```
   *Expected*: `67 passed in ~22s`.

3. **Execute Lint Check**:
   ```powershell
   & "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -m ruff check `
     "C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_content_retrieval.py" `
     "C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_candidate_index.py" `
     "C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_content_tools.py"
   ```
   *Expected*: `All checks passed!`.
