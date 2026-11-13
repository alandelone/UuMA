# Detailed Investigation and Analysis: Milestone M1 (Delivery 2 — W21)
**Scope:** Scholar Tool & User Entry Point Integration (Focus: W21)  
**Investigator:** explorer_m1_3 (Teamwork Explorer)  
**Date:** 2026-11-04  
**Target Codebases:** `C:\Users\Alandelone\CodeSpace_Local\RSTV4\` and `C:\Users\Alandelone\CodeSpace_Local\UuMA\`

---

## 1. Executive Summary & Objective

In accordance with `ORIGINAL_REQUEST.md` (R1 / Acceptance Criteria W21) and `PROJECT.md` (F06 & F07), work package **W21** requires verifying and establishing the integration between the registered Scholar FastMCP tools and user entry points against canonical research records.

Specifically, the investigation evaluated:
1. FastMCP tools `query_catalog_content` and `get_catalog_theme_candidates` in `src/rstv4/catalog_content_tools.py` and their attachment in `src/rstv4/catalog_mcp.py`.
2. Retrieval of real paper stages, Themes, located evidence, and semantic search results against canonical records.
3. Bounded transport previews and exact quotation preservation (character limits, next_offset pagination, and non-clipping guarantees).
4. Full integration with W16 human-reviewed Theme mappings (`src/rstv4/catalog_theme_corrections.py`), revision token fencing (`expected_revision`, `expected_review_revision`), and reversible EDIT/RESTORE lifecycles.
5. Existing test coverage in `tests/test_catalog_content_tools.py` and formulation of an actionable worker execution and verification strategy without writing production code.

---

## 2. FastMCP Tool Architecture & Entry Point Integration

### 2.1 Attachment Guard & Read-Only Guarantees
- **File**: `C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_mcp.py` (`attach(root)` lines 29–46, `register_catalog_tools` lines 48–206).
- **Owner Resolution**: `attach(root)` requires an explicit root path containing `data/catalog.db`. It opens the database with `read_collection_db(db_path)` in read-only mode (`PRAGMA query_only=ON`) and verifies that `schema_version` equals `CATALOG_VERSION` (15).
- **Zero In-Flight Mutations**: Tool attachment instantiates `CatalogUnderstanding.__new__(CatalogUnderstanding)` and `CatalogReading.__new__(CatalogReading)` without calling initializing constructors (`__init__`), strictly preventing unintentional database migrations, lock contention, or write transactions during MCP startup.
- **Service Factory**: `register_content_tools(mcp, services)` in `src/rstv4/catalog_content_tools.py` binds to `services()`:
  ```python
  def content():
      store, _reading = services()
      return CatalogContentRetrieval(store.db_path.parent.parent)
  ```
  This resolves the root workspace directory from `store.db_path` dynamically, ensuring all 10 registered FastMCP tools operate on the exact same canonical database instance.

### 2.2 Tool 1: `query_catalog_content`
- **Location**: `src/rstv4/catalog_content_tools.py:60-70`.
- **Input Validation**: Validates arguments via Pydantic model `ContentQuery` (`src/rstv4/catalog_content_web.py:16-20`):
  - `query`: `str` (1 to 4,000 characters, strict)
  - `limit`: `int` (1 to 50, default 10, strict)
  - `min_similarity`: `float` (-1.0 to 1.0, default 0.35, strict, `allow_inf_nan=False`)
  - `offset`: `int` (0 to 1,000,000, default 0, strict)
- **Call Chain**:
  `query_catalog_content(query_json)` $\rightarrow$ `ContentQuery.model_validate_json(query_json)` $\rightarrow$ `CatalogContentRetrieval.search(**payload.model_dump())` $\rightarrow$ `bounded_result(..., candidates=False)`.
- **Search Execution**:
  1. Combines BM25 lexical ranking and dense BGE-M3 (1024-dim L2-normalized) cosine similarity via Reciprocal Rank Fusion ($1 / (60 + rank)$).
  2. Identifies matching basis honestly: `['SEMANTIC']`, `['TEXT']`, or `['SEMANTIC', 'TEXT']`.
  3. Returns coverage metadata:
     - `mode`: `'HYBRID'` (if embedding vectors exist) or `'LEXICAL_ONLY_INDEX_NEEDED'`.
     - `semantic_index`: reports `eligible_passages`, `indexed_passages`, `complete`, `corpus_complete`, and `source_fingerprint`.
     - `pending_sources`: lists papers awaiting full-text acquisition or parsing (`FULL_TEXT_NEEDED`, `FULL_TEXT_OR_PARSE_NEEDED`, `SOURCE_REVIEW_REQUIRED`, `USABLE_PARSED_TEXT_NEEDED`).
     - `theme_counts`: distinct paper counts aggregated by Theme `group_id` across matched papers.
     - `matches`: list of located passage objects with `quote`, `block_id`, `page_number`, `section`, `start`, `end`, `block_content_digest`, `rank_score`, and similarity metrics.

### 2.3 Tool 2: `get_catalog_theme_candidates`
- **Location**: `src/rstv4/catalog_content_tools.py:72-82`.
- **Input Validation**: Validates arguments via Pydantic model `ContentCandidates` (`src/rstv4/catalog_content_web.py:23-31`):
  - `limit`: `int` (1 to 100, default 20)
  - `min_similarity`: `float` (-1.0 to 1.0, default 0.75, `allow_inf_nan=False`)
  - `offset`: `int` (0 to 1,000,000, default 0)
  - `evidence_offset`: `int` (0 to 1,000,000, default 0)
  - `evidence_limit`: `int` (1 to 20, default 4)
  - `expected_source_fingerprint`: `str | None` (64-char hex)
  - `expected_proposal_id`: `str | None` (64-char hex)
- **Call Chain**:
  `get_catalog_theme_candidates(query_json)` $\rightarrow$ `ContentCandidates.model_validate_json(query_json)` $\rightarrow$ `CatalogContentRetrieval.candidate_relations(**payload.model_dump())` $\rightarrow$ `bounded_result(..., candidates=True)`.
- **Candidate Aggregation & Non-Mutating Guarantees**:
  1. Reads top-20 nearest-neighbor candidate pairs computed by `catalog_candidate_index.py` using NumPy 1.26.4 matrix blocks on SQLite vector cache (`candidate.sqlite`).
  2. Query time never loads raw vector payloads or recomputes pairwise cosine similarities ($O(N^2D)$ eliminated).
  3. Every proposal is returned with `status='CANDIDATE'`, `relation='UNRESOLVED_SIMILARITY'`, `applied_merges=0`, and `automatically_applied=False`.
  4. Retains authentic two-sided located source evidence citations (`theme_previews`, `evidence`, `paper_ids`, `paper_count`).

---

## 3. Bounded Transport Previews and Quotation Preservation

### 3.1 Bounding Implementation in `bounded_result`
Inspecting `src/rstv4/catalog_content_tools.py:11–53`:
```python
def bounded_result(result, *, candidates=False):
    value = deepcopy(result)
    for key, maximum in [('pending_sources', 20), ('theme_counts', 100), ('paper_ids', 100)]:
        if key in value:
            value[key + '_total'] = len(value[key])
            value[key + '_preview_truncated'] = len(value[key]) > maximum
            value[key] = value[key][:maximum]
    collection = 'items' if candidates else 'matches'
    if candidates:
        for pair in value['items']:
            evidence = pair['evidence']
            pair['evidence_total'] = pair.get('evidence_total', len(evidence))
            pair['evidence_preview_truncated'] = bool(pair.get('has_more_evidence')) or len(evidence) > 4
            pair['evidence'] = [{key: item[key] for key in (
                'document_id', 'paper_id', 'parse_run_id', 'file_version_id', 'pdf_sha256')}
                | {'theme_id': item['theme']['theme_id'],
                   'observation_id': item['theme']['observation_id'],
                   'label_preview': item['theme']['label'][:200]}
                for item in evidence[:4]]
            pair['paper_ids_preview_truncated'] = len(pair['paper_ids']) > 100
            pair['paper_ids'] = pair['paper_ids'][:100]
    else:
        for item in value['matches']:
            item.pop('text', None)  # Exact quote already carries the same complete passage.
    ...
```

### 3.2 Key Preservation and Bounding Mechanics
1. **Deduplication Without Loss**: In `query_catalog_content`, `item.pop('text', None)` is executed because `quote` already contains the full passage text. This prevents payload duplication while preserving the complete, untruncated quotation.
2. **Never Truncate Quotes in Place**: Individual quotes are never chopped, sliced, or clipped with an ellipsis (`...`). If the serialized JSON payload exceeds `MAX_RESPONSE_CHARACTERS`:
   ```python
   while len(encoded(value)) > MAX_RESPONSE_CHARACTERS and value[collection]:
       value[collection].pop()
       removed = True
   ```
   Trailing matches/items are removed in their entirety. The matches that remain are 100% complete.
3. **Paging Continuity**:
   - `has_more_matches` (or `has_more` for candidates) is set to `True` if matches were removed or if prior pages indicated more.
   - `next_offset` is computed as `value['offset'] + len(value[collection])`.
   - The client can supply `next_offset` in the subsequent call to retrieve the remaining matches.
4. **Character Limit Analysis (48K vs 32K)**:
   - In `catalog_mcp_views.py:7`, `MAX_RESPONSE_CHARACTERS = 48000`.
   - In the dispatch prompt, `"32K char limit, next_offset pagination"` is referenced as a target requirement.
   - Analysis: `test_bounded_content_preview_keeps_exact_quote_and_usable_next_offset` tests with an artificial 30,000-character quote. Under 48,000 characters, a single 30,000-character quote fits comfortably while two such quotes trigger truncation. Under a 32,000 limit, a single 30,000 quote plus JSON metadata would be close to the ceiling (around 31K).
   - Both 48,000 and 32,768 (32K) satisfy the architectural principle of bounded transport previews. The worker can parameterize or document this threshold if a strict 32K limit is required for specific Hermes FastMCP transport buffers.

---

## 4. Integration with W16 Human-Reviewed Theme Mappings & Revision Fencing

### 4.1 W16 Core: `catalog_theme_corrections.py`
The human correction workflow enforces four strict architectural principles:
1. **Immutable Historical Records**: Machine observations and published runs are never edited in place or deleted.
2. **Reversible Operations (EDIT / RESTORE)**:
   - `replace(store, *, observation_id, expected_revision, expected_review_revision, request_id, reason, actor, theme=None, restore_revision=None)`
   - When `theme` is provided: Operation is `'EDIT'`. Validates source evidence in `document_blocks`, registers the theme if new, creates a new `catalog_theme_observations` record with `effective_id`, records an automatic `'ACCEPTED'` review event, and logs an `'EDIT'` row in `catalog_theme_corrections`.
   - When `restore_revision` is provided: Operation is `'RESTORE'`. Reverts to an earlier revision (or `restore_revision=0` for the original machine observation) without erasing subsequent correction history.
3. **Optimistic Revision Token Fencing**:
   - `expected_revision`: Must match `head(conn, observation_id)['revision']`. Any concurrent or stale edit raises `ValueError("Theme correction revision changed")`.
   - `expected_review_revision`: Must match `store._review_state(conn, 'OBSERVATION', current['effective_observation_id'])['revision']`. Any concurrent review event raises `ValueError("Theme review revision changed")`.
4. **Idempotency**: Pinned `request_id` returns the existing result if called with identical payload; raises `ValueError` if reused with differing payload.

### 4.2 Projection Flow into Retrieval and FastMCP Tools
The call graph connecting W16 to W21 was traced end-to-end:
```text
catalog_theme_corrections.replace() [EDIT / RESTORE]
       │
       ▼
catalog_theme_corrections.project(conn, observation)
       │
       ▼
CatalogUnderstanding._paper(conn, paper_id, groups)
       │
       ├──► get_catalog_understanding(paper_id) FastMCP Tool
       │       └── Returns compact_paper with effective Theme labels & correction metadata
       │
       ▼
catalog_content_retrieval.current_documents(conn)
       │
       ├──► Passage & Theme Chunking (chunks(theme['label'] + '\n' + theme['definition']))
       │       └── Indexes the effective human-corrected Theme text into vector cache
       │
       ├──► query_catalog_content FastMCP Tool
       │       └── Retrieves located matches citing human-corrected Theme descriptors
       │
       ▼
catalog_content_retrieval.candidate_context()
       │
       ├──► catalog_candidate_index.state() [NumPy 1.26.4 top-20 cache]
       │
       ▼
get_catalog_theme_candidates FastMCP Tool
       └── Emits UNRESOLVED_SIMILARITY pairs reflecting effective Theme labels, IDs, & review states
```
- **Automatic Alignment**: Because `current_documents` invokes `CatalogUnderstanding._paper(..., snapshot_only=True)`, which applies `project(conn, dict(row))` from `catalog_theme_corrections.py`, any accepted human correction (EDIT or RESTORE) automatically updates the indexing corpus on the next `refresh_batch`.
- **Review Fencing on Links**: Candidate link proposals created via `CandidateLinks.propose()` are reviewed via `CandidateLinks.review()` $\rightarrow$ `CatalogUnderstanding.review(kind='LINK', ...)`. This requires `expected_revision` fencing and enforces physical PDF source checks (`require_link_sources(conn, object_id, physical=True)`) before acceptance.

---

## 5. Review of Existing Tests in `tests/test_catalog_content_tools.py`

### 5.1 Current Test Suite Execution Results
Running with the dedicated numeric runtime interpreter (`C:\Users\Alandelone\CodeSpace_Local\RSTV4\.uuma-local\python\catalog-content-791032a82ebd\Scripts\python.exe`):
```text
collected 3 items
tests\test_catalog_content_tools.py ... [100%]
3 passed, 1 warning in 2.58s
```
Related suites executed synchronously and verified:
- `tests/test_catalog_mcp.py`: 6 passed in 5.79s
- `tests/test_catalog_content_retrieval.py` + `tests/test_catalog_candidate_index.py`: 22 passed in 4.58s
- `tests/test_catalog_theme_corrections.py`: 19 passed in 8.10s
- `tests/test_catalog_candidate_links.py` + `tests/test_catalog_candidate_links_web.py`: 20 passed in 10.43s

### 5.2 Test Coverage Analysis & Gaps
While existing tests verify basic functionality, several critical integration contracts are not explicitly asserted in `test_catalog_content_tools.py`:

| Test / Contract | Current State in `test_catalog_content_tools.py` | Gap / Deficiency |
| :--- | :--- | :--- |
| **Read-Only / No DB Writes** | Verified: `service.db_path.read_bytes() == before` and `index.cache.read_bytes() == vectors` | Fully covered. |
| **Quote Preservation** | Verified: artificial 30K quote preserved without truncation; `bounded['has_more_matches']` asserted | Fully covered. |
| **Out-of-Range Offset** | Verified: `offset=10` returns empty matches and no re-indexing | Fully covered. |
| **W16 Correction Reflection** | **Missing**: Tools are only queried against initial machine observations | **Gap**: Does not test that an `EDIT` or `RESTORE` via `store.correct_theme()` updates the text retrieved by `query_catalog_content` and `get_catalog_theme_candidates`. |
| **W16 Revision Fencing in Tools Context** | **Missing**: Tool tests do not attempt stale correction operations | **Gap**: Stale `expected_revision` rejection is tested in `test_catalog_theme_corrections.py` but not integrated into the tool verification chain. |
| **Candidate Evidence Preview Truncation** | Partially tested: checks `candidate['evidence_total'] >= len(candidate['evidence'])` | **Gap**: Does not assert truncation of `label_preview` (capped at 200 chars), `evidence[:4]` capping, or `next_offset` pagination across candidate pairs. |
| **Lexical vs Hybrid Fallback** | Tested with mock embeddings | **Gap**: Does not verify honest fallback reporting when vectors are missing (`LEXICAL_ONLY_INDEX_NEEDED`). |

---

## 6. Actionable Worker Execution & Verification Strategy for W21

The M1 Worker is responsible for owning `catalog_content_tools.py` and `tests/test_catalog_content_tools.py`. The recommended strategy below provides concrete instructions, test specifications, and verification commands.

### 6.1 Proposed Test Enhancements for Worker
The worker should add two targeted integration tests to `tests/test_catalog_content_tools.py`:

#### Test 1: `test_content_tools_reflect_w16_theme_corrections_and_revision_fencing`
- **Objective**: Verify that FastMCP tools `query_catalog_content` and `get_catalog_theme_candidates` accurately reflect human corrections (EDIT / RESTORE) and respect revision fencing tokens.
- **Workflow**:
  1. Initialize standard test fixture with parsed paper `p1` and initial theme observation.
  2. Call `query_catalog_content` and `get_catalog_theme_candidates` to record baseline machine observation.
  3. Execute `store.correct_theme(observation_id=obs_id, expected_revision=0, expected_review_revision=0, theme={'label': 'Corrected High Performance Storage', 'definition': 'Human refined definition citing original blocks.', 'role': 'CENTRAL', 'evidence': [...]}, request_id='req-edit-1', actor='reviewer', reason='Corrected noisy label')`.
  4. Assert stale revision rejection: calling `store.correct_theme` again with `expected_revision=0` raises `ValueError("Theme correction revision changed")`.
  5. Run `index.refresh_batch(manual_requested=True)` to rebuild vector projection.
  6. Query FastMCP `query_catalog_content` for `'Corrected High Performance Storage'`:
     - Assert match is returned with exact quote.
     - Assert Theme label reflects the corrected string.
  7. Query FastMCP `get_catalog_theme_candidates`:
     - Assert candidate items cite the new `effective_observation_id` and corrected `label_preview`.
  8. Execute RESTORE correction: `store.correct_theme(..., restore_revision=0, expected_revision=1, expected_review_revision=1, request_id='req-restore-1', ...)`.
  9. Run `index.refresh_batch(manual_requested=True)` and verify FastMCP tools revert to the original observation.

#### Test 2: `test_bounded_candidate_previews_and_evidence_pagination`
- **Objective**: Verify candidate preview truncation (`label_preview` $\le$ 200 chars, `evidence` $\le$ 4, `paper_ids` $\le$ 100), `next_offset` pagination, and honest coverage state.
- **Workflow**:
  1. Mock or construct candidate relations with 6 evidence items and a 300-character label.
  2. Pass through `bounded_result(result, candidates=True)`.
  3. Assert `evidence_preview_truncated` is `True`, `len(pair['evidence']) == 4`, and `len(pair['evidence'][0]['label_preview']) <= 200`.
  4. Assert `next_offset` pagination correctly steps through items without skipping or dropping citations.

### 6.2 Worker Execution Guardrails & Constraints
1. **Dedicated Runtime Environment**:
   Always execute pytest and worker tasks using the NumPy 1.26.4 child venv:
   `C:\Users\Alandelone\CodeSpace_Local\RSTV4\.uuma-local\python\catalog-content-791032a82ebd\Scripts\python.exe`
   Do NOT use the system default Python (Python 3.12) as it lacks `numpy` and `pypdf`, causing collection errors.
2. **Read-Only Against Canonical Databases**:
   Ensure `catalog.db` SHA-256 remains unchanged during all test queries. Never execute `CREATE TABLE` or `INSERT` against canonical tables in query code.
3. **Character Budget Verification**:
   Maintain `len(encoded(result)) <= MAX_RESPONSE_CHARACTERS` (48,000) across all tool outputs. If 32,000 is desired for FastMCP transport compliance, configure or document it explicitly without silently clipping quotations.
