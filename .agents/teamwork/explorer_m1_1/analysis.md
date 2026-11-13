# Technical Analysis: Global Semantic Discovery (W19)

**Date**: 2026-11-04  
**Author**: `explorer_m1_1` (Teamwork Explorer)  
**Milestone**: M1 (Delivery 2 — Global Semantic Discovery)  
**Work Package Focus**: W19 (Full-Text Semantic Retrieval & Index Coverage)  
**Target Repositories**: `C:\Users\Alandelone\CodeSpace_Local\RSTV4\` and `C:\Users\Alandelone\CodeSpace_Local\UuMA\`

---

## 1. Executive Summary

Milestone M1 (Delivery 2) delivers Global Semantic Discovery across the Scholar research catalog. Task W19 requires verified full-text semantic retrieval, hybrid search (BM25 + BGE-M3 dense vectors via Reciprocal Rank Fusion), strict source-fencing against physical PDF modification, honest coverage reporting, and exact passage quotations with block-level citations.

### Core Discoveries:
1. **Production Code Completeness**: The core modules `src/rstv4/catalog_embeddings.py` and `src/rstv4/catalog_content_retrieval.py` are structurally complete, implementing chunking, vector caching, BM25 + dense RRF, source-fencing, honest coverage reporting, and block citations.
2. **Live External Services Online**: The remote BGE-M3 embedding service on `alandelone-server-001:8893` was directly probed via SSH `ubuntu-server`. It is healthy, returning 1024-dim L2-normalized vectors under active generation `e38579a56b80a37bf51106e3ce4e1b77441b8baa5462b74a5a1025afc65b8b9a`.
3. **Live Catalog Health**: In the production `catalog.db`, 21,403 eligible passages exist across parsed papers, 609 passages are currently indexed in `data/artifacts/catalog-content-index/vectors.sqlite`, and live queries execute successfully in `HYBRID` mode.
4. **Environment Gap Identified (The Blocker)**: Running `pytest tests/test_catalog_content_retrieval.py` failed 6 out of 15 tests with `ModuleNotFoundError: No module named 'numpy'` in `src/rstv4/catalog_candidate_index.py:49`. Although `pyproject.toml` pins `"numpy==1.26.4"`, NumPy is missing from the active virtual environment `C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv`.
5. **Verification of the Fix**: Providing `numpy==1.26.4` (using the verified offline wheel already retained in `UuMA\.uuma-local\...`) immediately resolves all 6 test failures, resulting in **15/15 tests passing cleanly**.

---

## 2. In-Depth Technical Architecture (W19 Requirements)

### 2.1 Chunking & Text Representation
- **Location**: `src/rstv4/catalog_content_retrieval.py:43-50`, `chunks(text, size=1600, overlap=200)`
- **Specification**:
  - Size: 1,600 Unicode codepoints.
  - Overlap: 200 Unicode codepoints (stride = 1,400 codepoints).
  - Codepoint-exact slicing: `yield start, min(len(text), start + size), text[start:end]`.
  - Full-text coverage: handles oversized blocks without truncation or gaps.
  - Multi-byte / Unicode safety: verified in `test_chunking_preserves_all_unicode_offsets_and_overlap` with multi-byte emoji and Asian characters (`太阳 energy 🚀\n` * 900), guaranteeing `covered == set(range(len(text)))`.
- **Entity Ingestion**:
  - `PASSAGE`: Block text from `document_blocks` (`parse_run_id`), preserving `page_number`, `section`, `block_id`, `block_content_digest`.
  - `THEME`: `theme['label'] + '\n' + theme['definition']` from `catalog_understanding`, indexing candidate and accepted themes independently of passages.

### 2.2 BGE-M3 Dense Embeddings & Isolated Vector Cache
- **Embedding Client**: `src/rstv4/catalog_embeddings.py:ScholarEmbeddings`
  - Transport: SSH stdlib subprocess to `ubuntu-server` (`alandelone-server-001`).
  - Privacy guard: Research text travels strictly via `stdin` (never interpolated into command-line arguments).
  - Remote service: `http://localhost:8893/v1/embeddings` using bearer token from `~/.local/share/uuma/production/scholar-fieldkg/embedding.env`.
  - Model contract: `bge-m3`, dimensions: 1024, backend: `onnxruntime`, device: `cpu`.
  - L2-normalization: `normalized(vector, dimensions)` calculates $v / \|v\|_2$.
  - Service generation binding: Remote script verifies process PID and start time:
    $$\text{generation} = \text{SHA256}(\text{boot\_id} + \text{pid} + \text{stat.starttime})$$
    A server reboot or process restart alters the generation token, immediately preventing silent reuse of vectors from an unverified encoder.
- **SQLite Vector Cache**:
  - Location: `data/artifacts/catalog-content-index/vectors.sqlite`
  - Schema:
    - `vectors(text_sha256 TEXT NOT NULL, model_identity TEXT NOT NULL, vector_json TEXT NOT NULL, PRIMARY KEY(text_sha256, model_identity))`
    - `metadata(key TEXT PRIMARY KEY, value_json TEXT NOT NULL)`
  - Authority Boundary: The vector cache is an isolated, non-authoritative projection. It contains zero scientific claims and can be wiped or reconstructed at any time from `catalog.db` + BGE-M3.

### 2.3 BM25 + Dense Hybrid Search via Reciprocal Rank Fusion (RRF)
- **Lexical Component (BM25 Variant)**:
  - Tokenization: lowercase word regex `\w+` excluding `STOP_WORDS`.
  - Document frequency: `frequencies = {term: sum(term in tokens for tokens in tokenized.values())}`.
  - Length penalty: `length_factor = 1.2 * (0.25 + 0.75 * len(tokens) / average_length)`.
  - BM25 score:
    $$\text{lexical}(d) = \sum_{t \in Q} \ln\left(1 + \frac{N - n_t + 0.5}{n_t + 0.5}\right) \cdot \frac{tf(t, d) \cdot 2.2}{tf(t, d) + length\_factor}$$
- **Dense Component (Cosine Similarity)**:
  - Unit L2-normalized query vector $q$ and passage vector $v$:
    $$\text{dense}(d) = q \cdot v = \sum_{i=1}^{1024} q_i v_i$$
- **Reciprocal Rank Fusion ($k = 60$)**:
  - Ranks sorted independently:
    - Lexical: descending by score for $\text{score} > 0$.
    - Dense: descending by score for $\text{similarity} \ge min\_similarity$ (default $0.35$).
  - Combined RRF score:
    $$RRF(d) = \sum_{S \in \{\text{lexical}, \text{dense}\}} \frac{1}{60 + rank_S(d)}$$
  - Tie-breaking: sorted by $(-RRF(d), \text{document\_id})$.
  - Match basis classification:
    - `['SEMANTIC']` if dense score $\ge min\_similarity$.
    - `['TEXT']` if lexical score $> 0$.
    - `['SEMANTIC', 'TEXT']` if both criteria are satisfied.
  - Enables zero-keyword semantic recall (e.g., matching conceptual synonyms when query words do not literally appear in the text).

### 2.4 In-Flight Source-Fencing
- **Physical Verification**: `require_parse_source(conn, parse_run_id, paper_id)` reads physical PDF bytes:
  - Header check: validates starts with `%PDF-`.
  - Integrity digest: calculates SHA-256 of file bytes and asserts exact match against `source_file_versions.sha256`.
  - Mismatch or missing file: quarantined into `pending_sources` with stage `SOURCE_REVIEW_REQUIRED`.
- **Pre-Embedding Snapshot**: `snapshot = self.snapshot()` computes `fingerprint` over all valid document IDs, pending stages, and paused paper IDs.
- **Mid-Embedding Validation**: After receiving vectors from the encoder, `_refresh_locked()` takes a second snapshot. If `current['fingerprint'] != snapshot['fingerprint']`, the entire batch is discarded and `ValueError('Catalog source changed during indexing; nothing published')` is raised.
- **Mid-Query Validation**: In `search()`, `self._assert_current(snapshot)` verifies that the snapshot fingerprint did not drift during embedding or ranking; otherwise raises `ValueError`.

### 2.5 Honest Coverage Reporting
- **Inventory Metrics in `status()` & `search()`**:
  - `eligible_passages`: Count of passages extracted from latest valid parsed PDFs.
  - `indexed_passages`: Count of eligible passages with current vectors in `vectors.sqlite`.
  - `eligible_index_complete`: Boolean (`indexed_passages == eligible_passages`).
  - `corpus_complete`: Boolean (`eligible_index_complete and not pending_sources`). Requires all papers in the catalog to have valid full text and parsing.
  - `mode`: `'HYBRID'` if vectors exist, otherwise `'LEXICAL_ONLY_INDEX_NEEDED'`.
  - `scientific_acceptance`: Invariant `False` attached to all retrieval results.
- **Pending Stages Categorization**:
  1. `FULL_TEXT_NEEDED`: Paper record exists in `papers`, but no `source_file_versions` registered.
  2. `FULL_TEXT_OR_PARSE_NEEDED`: File version registered, but no successful parse in `parse_runs`.
  3. `SOURCE_REVIEW_REQUIRED`: Physical PDF missing, corrupted, unreadable, or SHA-256 mismatch.
  4. `USABLE_PARSED_TEXT_NEEDED`: Parse run succeeded, but produced zero non-empty document blocks.
  5. `indexing_paused_paper_ids`: Explicitly paused in `catalog_reading_intents` (`PAUSED` or `STOPPED`).

### 2.6 Exact Passage Quotation & Block Citations
Every match in `search()['matches']` yields:
- `quote`: exact chunk substring `d['text']`.
- `paper_id`: canonical paper ID.
- `title`: title from `papers`.
- `block_id`: source block ID (e.g. `p1-b1`, `block_004`).
- `page_number`: physical page number.
- `section`: parsed section heading.
- `start` / `end`: exact codepoint offsets within the source block.
- `block_content_digest`: content hash of the original block.
- `pdf_sha256`: SHA-256 digest of the source PDF.
- `parse_run_id` & `file_version_id`: provenance tokens.

---

## 3. Test Suite Review & Diagnosis

### 3.1 Test Coverage Inventory (`tests/test_catalog_content_retrieval.py`)
The suite consists of 15 tests:

| # | Test Name | Target Behavior | Status in RSTV4 `.venv` |
|---|---|---|:---:|
| 1 | `test_global_semantic_recall_uses_full_passage_without_query_word_overlap` | Semantic recall with 0 lexical overlap, RRF scoring, located quotes | **FAIL** (`ModuleNotFoundError: numpy`) |
| 2 | `test_refresh_reuses_vectors_and_generation_change_exposes_missing_index` | Vector cache reuse, model generation invalidation, honest fallback | **FAIL** (`ModuleNotFoundError: numpy`) |
| 3 | `test_automatic_indexing_waits_for_night_before_service_or_cache_access` | Night window policy (00:00–08:00 MYT), manual bypass | **FAIL** (`ModuleNotFoundError: numpy`) |
| 4 | `test_partial_index_reports_real_coverage_and_candidates_do_not_apply_merges` | Bounded batch indexing, partial status reporting, no auto-merges | **FAIL** (`ModuleNotFoundError: numpy`) |
| 5 | `test_changed_original_pdf_excludes_old_index_and_reports_source_problem` | Source fencing: tampered PDF excluded, `SOURCE_REVIEW_REQUIRED` | **FAIL** (`ModuleNotFoundError: numpy`) |
| 6 | `test_source_change_during_embedding_publishes_no_cache` | Mid-call PDF change halts cache publication, raises ValueError | **PASS** |
| 7 | `test_source_change_during_query_cannot_return_obsolete_evidence` | Mid-query PDF change raises ValueError, rejects stale results | **FAIL** (`ModuleNotFoundError: numpy`) |
| 8 | `test_chunking_preserves_all_unicode_offsets_and_overlap` | 1600/200 chunking over multi-byte Unicode and emoji | **PASS** |
| 9–13 | `test_invalid_vectors_are_never_usable` (5 parametrized cases) | Rejection of `[0., 0.]`, `bool`, `NaN`, `Inf`, wrong dimensions | **PASS** |
| 14 | `test_server_transport_keeps_research_text_out_of_arguments_and_checks_identity` | SSH transport sends text only via stdin, checks server identity | **PASS** |
| 15 | `test_server_timeout_has_a_bounded_public_error` | Subprocess timeout maps to bounded error without leaking paths | **PASS** |

### 3.2 Root Cause Analysis of Failures
- **Call Chain**:
  `index.refresh_batch(manual_requested=True)`  
  $\to$ `self._refresh_locked()` (`catalog_content_retrieval.py:224`)  
  $\to$ `self._refresh_candidates()` (`catalog_content_retrieval.py:162`)  
  $\to$ `refresh()` (`catalog_candidate_index.py:49`)  
  $\to$ `import numpy as np` $\to$ **`ModuleNotFoundError: No module named 'numpy'`**
- **Dependency Contract**:
  - `RSTV4/pyproject.toml` declares `"numpy==1.26.4"` under `dependencies`.
  - Historical notes (`docs/operations/scholar-catalog-semantic-retrieval-2026-10-29.md` §47) confirm NumPy was intentionally added for the matrix multiplication nearest-neighbor index.
  - The local offline wheel `numpy-1.26.4-cp311-win_amd64.whl` (SHA256 `cd25bcecc4974d09257ffcd1f098ee778f7834c3ad767fe5db785be9a4aa9cb2`) is stored at `C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\content-numeric-runtime-v308\numpy-1.26.4-cp311-cp311-win_amd64.whl`.
  - When tested in an isolated environment with `numpy 1.26.4`, **all 15 tests passed in 3.95s**.

---

## 4. Worker Execution & Verification Strategy for W19

### 4.1 Worker Execution Architecture
The reading worker (`src/rstv4/catalog_reading_worker.py`) incorporates `content_index_tick()` to interleave indexing between reading checkpoints:

```
[Reading Worker Loop: run_forever()]
       │
       ▼
 1. discover()        --> Scan and enqueue new papers
       │
       ▼
 2. run_once()        --> Process foreground reading job (QUICK_READ)
       │
       ▼
 3. content_index_tick()
       ├── Guard 1: RSTV4_CATALOG_CONTENT_INDEX == '1' (disabled by default)
       ├── Guard 2: Cooldown check (_content_index_due)
       ├── Guard 3: Night window open (00:00–08:00 MYT)?
       │             └─ If closed: sets cooldown +60s, returns WAITING_FOR_NIGHT
       ├── Guard 4: Foreground reading pending?
       │             └─ If pending: indexing yields immediately
       ├── Execution: refresh_batch(batch_size=4)
       │             └─ CPU Budget: 4 texts per tick (bounded execution)
       ├── Schedule Next:
       │     ├─ Useful work (embedded > 0 or anchors > 0): cooldown +5s
       │     └─ Idle / Complete: cooldown +300s
       └─ Fault Tolerance:
             └─ Exception caught -> status = UNAVAILABLE, cooldown +60s
                 (Worker NEVER crashes from indexing failure)
```

### 4.2 Foreground Manual Execution
When triggered via CLI, Web API (`POST /api/catalog/understanding/content/index`), or FastMCP tool:
- Parameter `manual_requested=True` bypasses the night window.
- Parameter `batch_size` (up to 16) allows faster batch indexing.
- Cross-process concurrency is serialized via `instance_lock(root, 'catalog-content-index', '1')`.
- Request idempotency: writes `<digest(request_id)>.json` in `data/artifacts/catalog-content-index/requests/`.

### 4.3 Production Database Safety (§9 Governance)
- Read-only connection: `conn = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)`.
- Query-only enforcement: `conn.execute('PRAGMA query_only=ON')`.
- Zero writes to `catalog.db` or `wisdom.db`.
- All output written strictly to `data/artifacts/catalog-content-index/vectors.sqlite`.

---

## 5. Recommended Implementation & Enhancement Strategy for W19 Worker

As an Explorer agent under read-only constraints, the following concrete actions are recommended for the implementation worker:

### Step 1: Environment Baseline Correction
The implementing worker must ensure `numpy==1.26.4` is installed in `C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv`:
```powershell
# Offline install using verified local wheel:
& "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\pip.exe" install --no-index `
  "C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\content-numeric-runtime-v308\numpy-1.26.4-cp311-cp311-win_amd64.whl"
```
*Rationale*: Satisfies `pyproject.toml` dependency declaration and resolves all candidate index imports.

### Step 2: Verification of Core Test Suites
Run the full suite of M1 tests to establish clean baseline:
```powershell
$venv = "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe"
& $venv -m pytest C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_content_retrieval.py -ra
& $venv -m pytest C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_candidate_index.py -ra
& $venv -m pytest C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_content_tools.py -ra
& $venv -m pytest C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_content_worker_batch.py -ra
& $venv -m pytest C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_content_web.py -ra
```

### Step 3: Worker Night-Window Activation
To activate automatic background indexing in production:
1. Ensure the reading worker process is scheduled or run with environment variable:
   `$env:RSTV4_CATALOG_CONTENT_INDEX = "1"`
2. Verify that automatic batch indexing runs strictly within 00:00–08:00 Asia/Kuala_Lumpur, processing 4 texts per tick with 5s intervals during active work and 300s during idle.

### Step 4: Live Verification Against Canonical Records
1. Query current index status:
   ```python
   retrieval = CatalogContentRetrieval('C:/Users/Alandelone/CodeSpace_Local/RSTV4')
   status = retrieval.status()
   # Verify eligible_passages, indexed_passages, pending_sources
   ```
2. Run sample bounded natural-language queries (e.g. `deep learning representation learning` and a non-overlapping synonym query):
   - Confirm `mode == 'HYBRID'`
   - Confirm `match_basis` includes `['SEMANTIC']`
   - Confirm exact quotations and valid `block_id` citations
   - Confirm `scientific_acceptance == False`
