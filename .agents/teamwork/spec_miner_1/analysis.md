# Comprehensive Specification Analysis: Scholar Catalog Deliveries 2, 3, and 4 (W19–W34)

**Document Version:** 1.0.0  
**Date:** 2026-11-04  
**Author:** spec_miner_1 (`teamwork_spec_miner`)  
**Scope:** UuMA / RSTV4 Scholar Catalog Execution Plan (W19 through W34)  
**Primary Specification Sources:**
1. `docs/operations/scholar-catalog-complete-work-plan-2026-11-04-with-agent-execution-layer.md`
2. `docs/operations/scholar-catalog-agent-execution/board.md`
3. `docs/operations/scholar-catalog-agent-execution/first-journey-receipt-20261104.json`
4. `docs/operations/scholar-catalog-semantic-retrieval-2026-10-29.md`
5. `docs/operations/scholar-reading-followthrough-2026-10-29.md`
6. `docs/operations/scholar-fieldkg-server-20261022.md`
7. `RSTV4/docs/catalog-paperskeleton-bound-workflow.md`
8. Authoritative implementations in `RSTV4/src/rstv4/` and `UuMA/src/uuma/`

---

## 1. Executive Summary & Architectural Overview

The Scholar Catalog in UuMA / RSTV4 is a local-first, evidence-grounded scientific literature discovery, understanding, and knowledge representation system. Following the operational completion and acceptance of **Delivery 1** (`catalog-48cece41023e`, verified via `first-journey-receipt-20261104.json` on sample paper `paper_dd83af8026e39dd2a2e9316622a7ca49`), the roadmap advances through three remaining deliveries:

- **Delivery 2 — Global Semantic Discovery (W19–W21):** Extends lexical catalog browsing with BGE-M3 1024-dimensional dense semantic retrieval, hybrid BM25+dense reciprocal rank fusion (RRF), bounded nearest-neighbor candidate relation aggregation, and canonical Scholar FastMCP tool exposure.
- **Delivery 3 — PaperSkeleton Deep Analysis (W22–W27):** Governs the multi-tier deep scientific analysis pipeline. Reconciles the held model retry authorization boundary (v419), executes deep role continuation, completes the 4-layer (L1–L4) proposition/relation/intent/role coverage for the authentic sample paper, derives whole-paper content and writing-structure views, evaluates decoupled purpose/value judgments, and guarantees cross-view freshness and source versioning contracts.
- **Delivery 4 — Final Portable Delivery (W28–W34):** Delivers portable source location handling for relocated full-text PDFs, compiles the complete verifiable FULL evidence archive, verifies idempotent adoption and compensating reversal into nonempty target environments, audits scientific claims via bounded independent review (W31), validates the final end-to-end user journey (W32), verifies dual-port (8892/8887) FieldKG runtime connectivity (W33), and executes strict release closure against the 34-item requirement ledger (W34).

All operations are governed by **§9 of the Work Plan: "分层分权，严禁全员并发裸写"** (Strictly Serialized Writes, Segregated Worktree Ownership, 00:00–08:00 Asia/Kuala_Lumpur Night Processing Policy, and Preserved User Approval Boundaries).

---

## 2. Work Item Specifications (W19 through W34)

---

### Delivery 2: Global Semantic Discovery

#### W19: Full-Text Semantic Retrieval & Index Coverage

- **Feature Name & Objective:** Global full-text semantic retrieval, vector projection, and index coverage accounting across eligible parsed paper passages.
- **Technical Objective:**
  Provide dense neural retrieval combined with BM25 lexical search (Hybrid RRF) over complete parsed PDF passages and candidate Theme descriptors without relying on label substring matching, while maintaining strict source guards, multi-model generation fencing, and honest coverage reporting (`INDEXED`, `PENDING`, `STALE`, `UNAVAILABLE`, `LEXICAL_ONLY_INDEX_NEEDED`).
- **Inputs, Outputs, Data Models & Schema Fields:**
  - *Inputs:*
    - Parsed paper text chunks from `document_blocks` (`split_codepoints=1600`, `overlap=200`, preserving page, section, block_id, character start/end offsets).
    - Remote BGE-M3 embedding service over SSH (`ubuntu-server` on `alandelone-server-001`, port 8893 gateway, model `bge-m3`, dimension 1024, ONNX fp32 on CPU).
    - Query payload: `text` (1–4000 chars), `limit` (1–50), `offset` (>=0), `similarity_threshold` (float -1.0 to 1.0).
  - *Outputs:*
    - JSON structure:
      ```json
      {
        "mode": "HYBRID" | "LEXICAL_ONLY_INDEX_NEEDED",
        "query": "string",
        "paper_count": 1,
        "total_matches": 1,
        "matches": [
          {
            "paper_id": "string",
            "block_id": "string",
            "section": "string",
            "page_idx": 1,
            "quote": "exact full text substring",
            "text": "exact chunk text",
            "lexical_score": 0.0,
            "semantic_similarity": 0.852,
            "combined_score": 0.91,
            "match_basis": ["SEMANTIC", "LEXICAL"],
            "document_id": "string"
          }
        ],
        "theme_counts": [{"theme_id": "string", "theme_label": "string", "paper_count": 1}],
        "semantic_index": {
          "complete": true,
          "indexed_passages": 85,
          "total_passages": 85,
          "model_generation": "sha256-hex"
        },
        "pending_sources": [],
        "scientific_acceptance": false
      }
      ```
  - *Data Models & Storage:*
    - Vector Cache DB: `data/artifacts/catalog-content-index/vectors.sqlite` (separate from canonical `catalog.db`).
    - Schema: Keyed by exact chunk text SHA-256 + model service generation hash (`8a91edd1b3...`).
    - Endpoint: `GET /api/catalog/understanding/content/index`, `POST /api/catalog/understanding/content/index`, `POST /api/catalog/understanding/content/query`.
- **Exact Acceptance Criteria & Verification Commands:**
  - *Criteria:*
    1. Bounded natural-language query returns relevant located quotations from eligible papers beyond label substring matching (semantic score > 0 with lexical score == 0).
    2. Output explicitly reports match basis (`SEMANTIC`, `LEXICAL`, or both) and distinct unique paper counts.
    3. Coverage state explicitly reports whether indexing is complete, partial, pending, or stale.
    4. Model text passed strictly via SSH stdin; no source text interpolated into shell command line.
    5. Cache invalidates upon model service restart/generation hash change (`LEXICAL_ONLY_INDEX_NEEDED`).
    6. Mid-embedding or mid-query source PDF modification immediately aborts and does not publish stale vectors.
  - *Verification Command:*
    `.venv/Scripts/python.exe -m pytest C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_content_retrieval.py -v`
  - *Pass/Fail Rules:* All 15 tests pass (specifically `test_global_semantic_recall_uses_full_passage_without_query_word_overlap`, `test_refresh_reuses_vectors_and_generation_change_exposes_missing_index`, `test_source_change_during_embedding_publishes_no_cache`).
- **Dependencies:**
  - *Preceding W01–W18:* W07 (full-text readiness gate on real PDF), W08 (auto import/backfill queue), W09 (00:00–08:00 night policy and manual priority).
  - *External:* Live BGE-M3 service on `alandelone-server-001` (CPU ONNX, 1024 dim).
- **Invariants & Negative Test Cases:**
  - *Invariant:* Canonical `catalog.db` bytes must remain 100% unaltered during retrieval/indexing.
  - *Negative Cases:*
    - Vectors with `NaN`, `Inf`, boolean, or wrong dimensions must raise `ValueError`.
    - Server timeout (>65s) must raise generic runtime error without leaking internal server paths.
    - Missing PDF raises `FULL_TEXT_NEEDED`. Tampered PDF raises `SOURCE_REVIEW_REQUIRED`.
- **Operating Constraints:**
  - Automatic indexing occurs exclusively during 00:00–08:00 Asia/Kuala_Lumpur night window unless `manual_requested=True`.
  - Process mutex locking via `instance_lock` (single index writer).

---

#### W20: Evidence-Backed Semantic Relation Proposals

- **Feature Name & Objective:** Incremental nearest-neighbor candidate relation aggregation and evidence pairing.
- **Technical Objective:**
  Compute bounded incremental semantic similarity across eligible Theme descriptors using cached vector projections and matrix operations (NumPy 1.26.4 float32), exposing two-sided source evidence and distinct paper counts without automatically applying merges, synonyms, or scientific claims.
- **Inputs, Outputs, Data Models & Schema Fields:**
  - *Inputs:*
    - Theme descriptor vectors from `vectors.sqlite`.
    - Bounds: max anchors per batch (32, internal ceiling 128), top-K neighbors (`NEIGHBORS = 20`), threshold (float, e.g. 0.80).
  - *Outputs:*
    - Candidate proposals dictionary:
      ```json
      {
        "status": "CURRENT" | "AGGREGATING" | "PARTIAL",
        "applied_merges": 0,
        "items": [
          {
            "anchor_theme_id": "string",
            "anchor_label": "string",
            "candidate_theme_id": "string",
            "candidate_label": "string",
            "relation": "UNRESOLVED_SIMILARITY",
            "similarity": 0.895,
            "status": "CANDIDATE",
            "automatically_applied": false,
            "scientific_acceptance": false,
            "paper_count": 2,
            "distinct_paper_ids": ["p1", "p2"],
            "evidence": [
              {
                "paper_id": "p1",
                "observation_id": "obs_1",
                "quote": "text span 1"
              },
              {
                "paper_id": "p2",
                "observation_id": "obs_2",
                "quote": "text span 2"
              }
            ]
          }
        ],
        "indexed_graph": {"completed_anchors": 14, "total_scope": 14}
      }
      ```
  - *Data Models & Storage:*
    - Derived cache: `data/artifacts/catalog-content-index/candidate.sqlite`.
    - Keyed by `(model_generation, algorithm_version, anchor_text_hash)`.
    - API: `POST /api/catalog/understanding/content/candidates`.
- **Exact Acceptance Criteria & Verification Commands:**
  - *Criteria:*
    1. Candidate relations present supporting located quotations from both sides.
    2. Proposes `UNRESOLVED_SIMILARITY` with `status: CANDIDATE` and `applied_merges: 0`.
    3. Never automatically mutates vocabulary, merges Themes, or asserts canonical equivalence.
    4. Query route must read stored neighbor scores only; runtime pairwise $O(N^2 \cdot D)$ scoring during client query is strictly prohibited.
    5. Adding new descriptors compares only additions; deleting neighbors triggers full scan for affected anchors only.
  - *Verification Command:*
    `.venv/Scripts/python.exe -m pytest C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_candidate_index.py -v`
  - *Pass/Fail Rules:* All 7 tests pass (including `test_bounded_candidate_batches_resume_to_exact_nearest_neighbor_graph`, incremental additions, and neighbor removal refill).
- **Dependencies:**
  - *Preceding:* W16 (controlled vocabulary review lifecycle and compensating reversal), W19 (vector projections).
  - *Runtime:* NumPy 1.26.4 isolated child runtime (`catalog-content-791032a82ebd`).
- **Invariants & Negative Test Cases:**
  - *Invariant:* Similarity proposal $\neq$ Synonym / Merge. Any merge action must be explicitly routed to W16 human review.
  - *Negative Cases:* In-flight source pause/change aborts numeric write; 08:00 morning boundary pauses batch and safely commits checkpoint.
- **Operating Constraints:**
  - Single index writer mutex; candidate aggregation yields priority to active Reading jobs.

---

#### W21: Scholar Tool/User-Entry Integration & Canonical Access

- **Feature Name & Objective:** FastMCP tool exposure and Scholar agent unified canonical catalog access.
- **Technical Objective:**
  Integrate semantic search and candidate relation exploration into official Scholar entry points and FastMCP registered tools (`query_catalog_content`, `get_catalog_theme_candidates`), ensuring access to canonical paper stages, Themes, and located quotations without stale database divergence.
- **Inputs, Outputs, Data Models & Schema Fields:**
  - *Tools Registered in FastMCP:*
    1. `query_catalog_content(query_json: str)`:
       - Arguments: JSON with `query` (str), `limit` (int, default 10, max 50), `offset` (int, default 0), `threshold` (float, default 0.0).
       - Returns: Bounded transport preview containing matches, exact quotes, match basis (`SEMANTIC`/`LEXICAL`), total match count, next_offset pagination.
    2. `get_catalog_theme_candidates(threshold: float = 0.8, limit: int = 20)`:
       - Returns: Candidate list with two-sided observation evidence, distinct paper counts, and explicit `UNRESOLVED_SIMILARITY`.
  - *Data Models & Transport Limits:*
    - Payload size constrained: `len(encoded(result)) <= MAX_RESPONSE_CHARACTERS` (typically 32,000 characters).
    - Preserves exact source quote while truncating large transport metadata preview if necessary.
- **Exact Acceptance Criteria & Verification Commands:**
  - *Criteria:*
    1. Tools retrieve real paper stages, Themes, and located evidence against canonical `catalog.db`.
    2. Response remains within MCP transport size bounds while preserving exact evidence quote strings and `next_offset`.
    3. Tool execution executes strictly read-only against canonical database; zero SQLite writes to `catalog.db` or `wisdom.db`.
    4. Authoring language strictly in English.
  - *Verification Command:*
    `.venv/Scripts/python.exe -m pytest C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_content_tools.py C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_mcp.py -v`
  - *Pass/Fail Rules:* All tests pass (including `test_actual_registered_content_tools_retrieve_evidence_and_candidates_without_knowledge_writes` and `test_bounded_content_preview_keeps_exact_quote_and_usable_next_offset`).
- **Dependencies:**
  - *Preceding:* W17 (catalog columns and detail panels), W19 (retrieval core), W20 (candidate index).
- **Invariants & Negative Test Cases:**
  - *Invariant:* Read-only isolation. Tools cannot trigger arbitrary full-corpus reindexes or execute unapproved write transactions.
  - *Negative Cases:* Queries past end-of-results return `has_more_matches: false` with empty match list without re-running embedding.
- **Operating Constraints:**
  - MCP tools must not restart the shared gateway or disrupt other specialist agents (Librarian, Brainstormer, Forge).

---

### Delivery 3: PaperSkeleton Deep Analysis

#### W22: Distinct Held Deep-Role Approval (v419 Approval Boundary)

- **Feature Name & Objective:** User decision boundary and scope definition for the held deep role retry.
- **Technical Objective:**
  Enforce the strict authorization gate for the single held role failure in the authentic deep sample (`paper_dd83af8026e39dd2a2e9316622a7ca49`), where call `run_5ab8607b14e244e89c6e94d345b0b470` (`poolside/laguna-s-2.1:free`, task `skeleton_theme_role`) returned ordinary prose instead of JSON object. Maintain the boundary that historical v329 one-off consent is consumed and cannot authorize this distinct v419 action.
- **Inputs, Outputs, Data Models & Schema Fields:**
  - *Inputs:*
    - Original failed call receipt: `run_5ab8607b14e244e89c6e94d345b0b470` under `catalog_reading_model_events`.
    - Preserved source payload: 85 parsed blocks, 28 completed parts, native checkpoints (L1: 85 units, L2: 347 relations, L3: 340 intents, L4: 1 macro role).
    - Scope proposal: At most one (1) external model call targeting `skeleton_theme_role` using the thinking channel and unchanged full-paper source context.
  - *Outputs:*
    - Durable decision record in `catalog_reading_requests`:
      - Approved: Status `AUTHORIZED`, with exact `request_id`, authorized model, prompt version, and max_calls=1.
      - Declined: Status `DECLINED` / `DEFER_ACCEPTED`, with durable rationale; no calls dispatched; job marked explicitly held.
- **Exact Acceptance Criteria & Verification Commands:**
  - *Criteria:*
    1. Zero model requests submitted until an explicit human user decision is durably recorded.
    2. Resuming the Goal, elapsed timers, or automated subagent scripts CANNOT constitute approval.
    3. If declined, the pipeline records the decision cleanly without fabricating completion or deleting partial artifacts.
  - *Verification Command:*
    Inspection of `board.md` (row W22) and `catalog_reading_jobs` status:
    `python -c "import sqlite3; conn = sqlite3.connect('catalog.db'); print(conn.execute(\"SELECT job_id, status, fencing_token FROM catalog_reading_jobs WHERE job_type='SKELETON_VIEW' AND status='NEEDS_HUMAN'\").fetchall())"`
  - *Pass/Fail Rules:* Job remains in `NEEDS_HUMAN` (fence 181) until user authorization is submitted; no new model call events recorded.
- **Dependencies:**
  - *Preceding:* Delivery 1 completion receipt (`first-journey-receipt-20261104.json`).
- **Invariants & Negative Test Cases:**
  - *Invariant:* The 3 semantic part retries are exhausted. Technical transport retries cannot be applied to ordinary prose responses.
  - *Negative Cases:* Unauthorized invocation attempts throw `PermissionError` / `ValueError("Distinct user approval required for v419")`.
- **Operating Constraints:**
  - Class `H` (Human Scientific / Scope Decision) and Class `M` (External Model Request) gate.

---

#### W23: Safe Admission & Deep-Role Continuation

- **Feature Name & Objective:** Scoped execution, validation, and worker continuation of the authorized role recovery.
- **Technical Objective:**
  Upon durable W22 user approval, admit and execute strictly at most one (1) replacement call, validate that its returned output satisfies the `skeleton_theme_role` schema, authenticate the receipt, and resume the owning Reading worker without bypassing execution identity.
- **Inputs, Outputs, Data Models & Schema Fields:**
  - *Inputs:*
    - W22 authorization receipt.
    - Original job: `skeletonviewjob_1216bde784964dc42990bbd92b55cd7431a23a60a43d94a05fe1bd58c6ec81e6`.
  - *Outputs:*
    - `catalog_reading_model_events`: 1 new row (`event_kind='RETURNED'`, valid JSON object matching `skeleton_theme_role` schema).
    - Updated job status: transitions from `NEEDS_HUMAN` to `SUCCEEDED` (or remains `NEEDS_HUMAN` with recorded cause if validation fails).
- **Exact Acceptance Criteria & Verification Commands:**
  - *Criteria:*
    1. Exactly one call submitted; no infinite retry loops.
    2. Returned output strictly validates against supplied quotation IDs and Theme scope.
    3. Worker resumes using original job/intent lineage, preserving all 28 prior successful parts and digests.
  - *Verification Command:*
    `.venv/Scripts/python.exe -m pytest C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_reading_retry.py -v`
  - *Pass/Fail Rules:* Event ledger records at most 1 additional RETURNED event; job advances to next pipeline stage.
- **Dependencies:**
  - *Preceding:* W22 (explicit authorization).
- **Invariants & Negative Test Cases:**
  - *Invariant:* No forged synthetic receipts; actual provider execution hashes required.
  - *Negative Cases:* If replacement model returns malformed JSON or unsupplied quote IDs, job returns to `NEEDS_HUMAN` without second retry.
- **Operating Constraints:**
  - Must run within permitted night window (00:00–08:00) unless explicit manual priority is flagged.

---

#### W24: Complete Original L1–L4 Source Coverage

- **Feature Name & Objective:** Full-paper 4-layer PaperSkeleton persistence for the genuine original sample.
- **Technical Objective:**
  Verify and persist complete four-layer PaperSkeleton extraction across all 85 parsed document blocks of the authentic original sample (`paper_dd83af8026e39dd2a2e9316622a7ca49`), accounting for every proposition (L1), relationship (L2), argumentative intent (L3), and macro writing role (L4).
- **Inputs, Outputs, Data Models & Schema Fields:**
  - *Inputs:*
    - 85 parsed blocks from `document_blocks` (`parse_run_id='understanding_3c325480...'`).
    - 4 Layer execution pipelines (`located_deep.py` `TASKS`):
      1. L1: `skeleton_layer_1` / `block_atoms` (propositions, entities, source spans, qualifications, triplets).
      2. L2: `skeleton_layer_2` / `relations` (cause, contrast, support, condition, elaboration, citation).
      3. L3: `skeleton_layer_3` / `intents` (atom intents: objective finding, method justification, gap, etc.).
      4. L4: `skeleton_layer_4` / `roles` (macro writing roles: motivation, methodology, experiment, results, discussion).
  - *Outputs & Tables:*
    - `paper_skeletons`:
      `skeleton_id`, `paper_version_id`, `version` (1), `model_name`, `prompt_version`, `content_digest` (SHA-256 of all units + outline), `created_at`.
    - `skeleton_units`:
      `unit_id`, `skeleton_id`, `seq_idx` (0..84), `page_idx`, `section`, `raw_text`, `layer1_json`, `layer2_json`, `layer3_json`, `layer4` (str), `content_digest`.
    - `skeleton_checkpoints`:
      Checkpoints for all 85 blocks across all 4 layers (340 rows).
- **Exact Acceptance Criteria & Verification Commands:**
  - *Criteria:*
    1. Every single block (85/85) has verified L1, L2, L3, and L4 representations.
    2. Substituting a simplified sample paper or abstract-only text is strictly prohibited.
    3. `content_digest` matches SHA-256 of all replayed layer receipts and source outline.
    4. Foreign key integrity verified: `PRAGMA foreign_key_check` returns empty.
  - *Verification Command:*
    `.venv/Scripts/python.exe -m pytest C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_deep.py -k test_global_explicit_deep_uses_original_four_layers_and_atomic_canonical_publication -v`
  - *Pass/Fail Rules:* 85 units present, 340 checkpoints present, `parsed_blocks_complete: true`, `located_atom_contract_verified: true`.
- **Dependencies:**
  - *Preceding:* W07 (full-text PDF guard), W10 (idempotent resume and checkpoint reuse), W23 (role continuation).
- **Invariants & Negative Test Cases:**
  - *Invariant:* All unit endpoints in L2 relations must reference valid atom IDs in L1.
  - *Negative Cases:* Missing block checkpoints or unanchored propositions fail publication and roll back the transaction.
- **Operating Constraints:**
  - Fenced publication transaction; worker requires valid lease and matching fencing token.

---

#### W25: Whole-Paper Content & Writing-Structure Views

- **Feature Name & Objective:** Grounded 22-dimension content views and narrative writing-structure publication.
- **Technical Objective:**
  Derive unified content and writing-structure views from the published PaperSkeleton, binding all 22 shared evaluation dimensions to authentic Skeleton units, L2 relations, L3 intents, L4 macro roles, and actual document heading outlines.
- **Inputs, Outputs, Data Models & Schema Fields:**
  - *Inputs:*
    - Snapshot of completed Skeleton units from `paper_skeletons` and `skeleton_units`.
    - Source outline from `skeleton_source_outlines`.
    - Pipeline version: `VIEW_VERSION = "paperskeleton-content-and-purpose-v2-themes"`.
    - Tasks: `skeleton_view_part`, `skeleton_view_digest`, `skeleton_view_final`, `skeleton_theme_role`.
  - *Outputs & Tables:*
    - `catalog_skeleton_content_views`:
      - `view_id`: `_id("skeletonviewresult", job_id, content_json, contracts_json)`
      - `skeleton_id`: foreign key to `paper_skeletons`
      - `job_id`: foreign key to `catalog_reading_jobs` (unique)
      - `source_digest`: `_id("skeletonviewsource", binding, located_units)`
      - `content_json`: structured content covering all 22 dimensions:
        - Problem framing, viewpoints/claims, methods/data, results, limitations, writing architecture map, paragraph patterns, system architecture, etc.
      - `contracts_json`: exact model contracts and prompt versions.
      - `created_at`: timestamp.
    - Candidate Themes publication: calls `publish_themes(conn, view_id, content_json)` to populate Theme roles (`CENTRAL`, `SUBSTANTIAL`, `PASSING_MENTION`) with exact quotation locators.
- **Exact Acceptance Criteria & Verification Commands:**
  - *Criteria:*
    1. Every dimension observation cites authentic Skeleton units and source spans.
    2. Writing map links source order, L2 transition relations, L3 argument sequences, and L4 macro sections.
    3. Unknown or unassessed dimensions remain explicitly marked `UNKNOWN` / `UNASSESSED`.
    4. HTTP API `GET /api/catalog/papers/{paper_id}/skeletons/{skeleton_id}` returns complete 4-layer units and source metadata.
  - *Verification Command:*
    `.venv/Scripts/python.exe -m pytest C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_skeleton.py -v`
  - *Pass/Fail Rules:* Status 200 returned, `artifact_integrity_verified: true`, all 4 layers intact, non-existent paper returns 404.
- **Dependencies:**
  - *Preceding:* W13 (shared dimension profile at initial depth), W24 (complete L1–L4 Skeleton).
- **Invariants & Negative Test Cases:**
  - *Invariant:* Content views must never fabricate Skeleton unit IDs that do not exist in `skeleton_units`.
  - *Negative Cases:* Modifying the underlying PDF changes `source_digest` and causes `require_view` to reject publication with `ValueError("Skeleton view source/profile/contracts changed")`.
- **Operating Constraints:**
  - English language content only. Preserves original source quotations.

---

#### W26: Purpose & Value Judgments Decoupled from Content

- **Feature Name & Objective:** Purpose-specific evaluation judgments decoupled from underlying content authority.
- **Technical Objective:**
  Evaluate completed PaperSkeleton content against declared research purposes (e.g. `LIBRARY_OVERVIEW`, `METHOD_COMPARISON`, `SYSTEM_ARCHITECTURE`), recording explicit value judgments and depth recommendations without altering the paper's canonical content authority or launching unauthorized tasks.
- **Inputs, Outputs, Data Models & Schema Fields:**
  - *Inputs:*
    - Content view from `catalog_skeleton_content_views`.
    - Declared purpose: JSON object `{"kind": "RESEARCH_QUESTION", "question": "...", "focus_dimensions": [...]}`.
    - Task: `PURPOSE_TASK = "skeleton_purpose"`.
  - *Outputs & Tables:*
    - `catalog_skeleton_purpose_judgments`:
      - `judgment_id`: `_id("skeletonviewresult", job_id, judgment_json, contract_json)`
      - `view_id`: foreign key to `catalog_skeleton_content_views`
      - `job_id`: foreign key to `catalog_reading_jobs` (unique)
      - `purpose_json`: declared purpose definition.
      - `judgment_json`:
        - `disposition`: `INITIAL_SUFFICIENT` | `DEEPER_RECOMMENDED` | `MORE_INFO_REQUIRED`
        - `reasons`: detailed justification citing specific dimensions, unresolved questions, and expected payoff.
        - `value_score`: qualitative evaluation bounded to purpose.
      - `contract_json`: prompt and model execution metadata.
      - `created_at`: timestamp.
- **Exact Acceptance Criteria & Verification Commands:**
  - *Criteria:*
    1. Judgment explicitly names declared purpose, citing exact content view and Skeleton evidence.
    2. Changing research purpose creates a new judgment linked to the same content view without re-running extraction.
    3. Recommending deeper reading (`DEEPER_RECOMMENDED`) NEVER automatically spawns a background job.
  - *Verification Command:*
    `.venv/Scripts/python.exe -m pytest C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_deep.py -k test_recommendation_or_import_never_authorizes_global_deep_and_source_initial_is_required -v`
  - *Pass/Fail Rules:* Recommendation exists without creating rows in `catalog_deep_requests` or `catalog_reading_jobs` of type `SKELETON`.
- **Dependencies:**
  - *Preceding:* W14 (initial reading disposition and deep-read reasons), W25 (content view).
- **Invariants & Negative Test Cases:**
  - *Invariant:* Content authority is immutable; purpose judgment is subjective/purpose-bound.
  - *Negative Cases:* Missing content view aborts purpose enqueueing (`_enqueue_purpose` returns None).
- **Operating Constraints:**
  - Distinct separation of recommendation from execution authority.

---

#### W27: Cross-View Freshness & Reuse Contracts

- **Feature Name & Objective:** Multi-view data reuse, source-hash freshness validation, and historical invalidation.
- **Technical Objective:**
  Guarantee that opening or filtering a paper across different Collections/Views reuses the same canonical paper and Skeleton analyses. Invalidate derived outputs and mark them stale when source PDF, parse run, or dimension profile changes, while preserving immutable audit history.
- **Inputs, Outputs, Data Models & Schema Fields:**
  - *Inputs:*
    - Multiple View/Collection requests for the same `paper_id`.
    - Modified source PDF or new parse run ID.
  - *Outputs:*
    - `view_history(conn, paper_id)` returns:
      - `source`:
        - `eligible`: boolean
        - `current_pdf`: boolean (`True` if `latest_file.sha256 == binding.pdf_sha256`, else `False`)
        - `history_origin`: controller adoption status (`ADOPTED`, `REVERSED`, or `None`)
        - `detail`: explanation if not eligible or stale.
      - `artifact_integrity_verified`: boolean.
      - `content_views`: list of all historical versions.
      - `purpose_judgments`: list of all historical judgments.
- **Exact Acceptance Criteria & Verification Commands:**
  - *Criteria:*
    1. Second View/Collection referencing the same paper ID reuses identical `skeleton_id` without duplicate inference.
    2. If a new PDF revision is uploaded, historical content views are marked `current_pdf: false`, retaining complete historical visibility without being overwritten.
    3. Human review decisions and model provenance do not transfer across different PDF parses.
  - *Verification Command:*
    `.venv/Scripts/python.exe -m pytest C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_deep.py -k "test_changed_pdf_retains_model_receipt_but_publishes_no_skeleton or test_pause_fences_deep_writer_and_resume_reuses_returned_layers" -v`
  - *Pass/Fail Rules:* Model receipts preserved in `catalog_reading_model_events`, but publication rejected with `NEEDS_HUMAN` upon changed PDF.
- **Dependencies:**
  - *Preceding:* W10 (resumability and reuse of saved results), W12 (initial card reuse), W25, W26.
- **Invariants & Negative Test Cases:**
  - *Invariant:* Append-only history; older results are marked stale/superseded, never deleted.
  - *Negative Cases:* Attempting to publish Skeleton against changed PDF raises `ValueError("Original parsed PDF changed")`.
- **Operating Constraints:**
  - Strict idempotent readback; no uncoordinated mutations.

---

### Delivery 4: Final Portable Delivery

#### W28: Portable Source Location Handling

- **Feature Name & Objective:** Relocated source path resolution and full-text guard portability.
- **Technical Objective:**
  Enable the runtime to open, verify, and process retained full-text PDFs and parse packages when original workstation absolute paths (e.g. `C:\Users\Alandelone\...` or NAS mount points) are unavailable or relocated, verifying exact byte hashes and rejecting corrupted or tampered files.
- **Inputs, Outputs, Data Models & Schema Fields:**
  - *Inputs:*
    - Retained source package directory containing:
      - `manifest.json`: manifest with relative file paths and SHA-256 hashes.
      - Retained PDF file.
      - Retained MinerU Markdown extraction.
      - Retained content-list JSON.
    - Target database with updated `storage_path` pointing to relocated file.
  - *Outputs:*
    - `require_parse_source(conn, parse_run_id, paper_id)` returns source dictionary with verified `storage_path`, `sha256`, and block counts.
- **Exact Acceptance Criteria & Verification Commands:**
  - *Criteria:*
    1. Target runtime accepts relocated PDF when SHA-256 and byte length match `source_file_versions`.
    2. Verified parse package matches original `artifact_manifest_json` SHA-256 hash.
    3. Tampered PDF (even 1 byte appended) is instantly rejected with `ValueError("Original parsed PDF changed")`.
    4. Original database records and parse manifests remain immutable.
  - *Verification Command:*
    `.venv/Scripts/python.exe -m pytest C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\test_relocated_fulltext_guard_v665.py -v`
  - *Pass/Fail Rules:* 1 passed; tamper check raises exact `ValueError("Original parsed PDF changed")`.
- **Dependencies:**
  - *Preceding:* W07 (full-text readiness gate), W27 (source versioning).
- **Invariants & Negative Test Cases:**
  - *Invariant:* Path relocation does not change file identity; SHA-256 must match exactly.
  - *Negative Cases:* Missing file raises `FileNotFoundError`; altered SHA raises `ValueError`.
- **Operating Constraints:**
  - Preserves NAS rescue safety; coordinate single writer on shared targets.

---

#### W29: Full Evidence Archive Generation

- **Feature Name & Objective:** Compilation of the authentic, self-contained FULL evidence archive carrier.
- **Technical Objective:**
  Package the authentic completed PaperSkeleton results (native L1–L4 units, content views, purpose judgments, Theme assignments, execution event receipts, and model logs) into a sealed evidence carrier validated by the finished-evidence guard (`finished_evidence_guard_v285.py`).
- **Inputs, Outputs, Data Models & Schema Fields:**
  - *Inputs:*
    - Verified completed sample paper `paper_dd83af8026e39dd2a2e9316622a7ca49`.
    - Complete native extraction rows (85 units, 340 checkpoints).
    - `catalog_skeleton_content_views`, `catalog_skeleton_purpose_judgments`.
    - Operation registries and model call receipts from `data/artifacts/model-delivery/`.
  - *Outputs:*
    - Archive directory / tarball containing:
      - `manifest.json`: List of all included files, row counts, and cryptographic hashes.
      - `full_evidence.db`: SQLite database containing exact completed rows.
      - `model_delivery/`: Retained raw model responses (`.response.json`).
      - Finished record guard receipt: `finished_record_guard.receipt.json` signed by verifier engine.
- **Exact Acceptance Criteria & Verification Commands:**
  - *Criteria:*
    1. Archive contains authentic original sample data, not a synthetic or partial test fixture.
    2. Finished-evidence guard accepts the archive against all strict assertions (native complete, content complete, purpose complete, models authentic).
    3. Any incomplete or runnable job present causes immediate rejection.
  - *Verification Command:*
    `.venv/Scripts/python.exe -m pytest tests/test_full_archive_guard.py -v` (using `archive_finished_skeleton_evidence_v285.py` and `finished_evidence_guard_v285.py`)
  - *Pass/Fail Rules:* Finished-record guard returns exit code 0 and valid verification JSON.
- **Dependencies:**
  - *Preceding:* W24 (L1–L4 complete), W25 (content view), W26 (purpose judgment), W28 (portable locations).
- **Invariants & Negative Test Cases:**
  - *Invariant:* Archive is immutable once sealed. An incomplete run cannot be relabelled as complete.
  - *Negative Cases:* Missing model receipt or unassessed block triggers guard failure.
- **Operating Constraints:**
  - Read-only generation from production; no writes to live stores during archive packaging.

---

#### W30: Nonempty-Target Adoption & Idempotency

- **Feature Name & Objective:** Controller-owned transaction import, idempotency, and compensating reversal in nonempty targets.
- **Technical Objective:**
  Import and adopt the complete evidence archive into an existing nonempty target database using `catalog_history_adoption.py`, verifying conflict detection, schema preservation, idempotent re-runs, and compensating reversal (`CATALOG_HISTORY_ADOPTION_REVERSED`).
- **Inputs, Outputs, Data Models & Schema Fields:**
  - *Inputs:*
    - Completed archive package from W29.
    - Nonempty target `catalog.db` containing existing papers, intents, and reading jobs.
    - Controller authorization: `request_id`, `reason`, `packet_sha256`, `manifest_sha256`.
  - *Outputs & Provenance Records:*
    - `catalog_reading_requests`:
      - Row with `operation = "adopt_completed_catalog_history_v1"`, `authority = "CONTROLLER"`, `target_database`, `proof_json`, `proof_sha256`.
    - `catalog_reading_events`:
      - Row with `event_kind = "CATALOG_HISTORY_ADOPTED"`, `job_id = NULL`.
    - If reversed:
      - `catalog_reading_requests`: row with `operation = "reverse_catalog_history_adoption_v1"`.
      - `catalog_reading_events`: row with `event_kind = "CATALOG_HISTORY_ADOPTION_REVERSED"`.
- **Exact Acceptance Criteria & Verification Commands:**
  - *Criteria:*
    1. Adoption executes inside a single atomic transaction; zero partial commits.
    2. Existing unrelated records in nonempty target remain 100% unaltered.
    3. Re-running identical adoption is idempotent and returns existing receipt without duplicate rows.
    4. Conflicting paper versions trigger immediate abort and full rollback.
    5. Reversal appends compensating audit event without deleting historical scientific rows.
  - *Verification Command:*
    `.venv/Scripts/python.exe -m pytest C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_full_transfer_v284.py -v`
  - *Pass/Fail Rules:* 5 passed in <10s; covers adoption, idempotency, conflicting version rejection, and WAL reversal.
- **Dependencies:**
  - *Preceding:* W28 (portable locations), W29 (FULL evidence archive).
- **Invariants & Negative Test Cases:**
  - *Invariant:* Never overwrite or mutate existing target records; never delete scientific evidence during reversal.
  - *Negative Cases:* Altered proof JSON or mismatched packet SHA raises `ValueError("History adoption has a changed source proof")`.
- **Operating Constraints:**
  - Transaction owned exclusively by designated controller; no concurrent worker execution during adoption.

---

#### W31: Bounded Independent Content Review

- **Feature Name & Objective:** Programmatic and sampled independent semantic content review.
- **Technical Objective:**
  Audit scientific integrity across delivered initial and deep outputs using strict programmatic invariants for structural properties (spans, quotes, schemas) and an independent reviewer model for a declared, bounded sample of semantic claims and Theme roles.
- **Inputs, Outputs, Data Models & Schema Fields:**
  - *Inputs:*
    - Published initial content cards and deep content views.
    - Original full-text PDF text blocks.
    - Declared review sample (e.g. 1 sample paper, 14 Themes, 5 Central / 9 Substantial).
  - *Outputs:*
    - Structured review report:
      ```json
      {
        "sample_paper_id": "string",
        "mechanical_checks": {"passed": true, "quotation_accuracy": 1.0, "schema_conformance": 1.0},
        "semantic_review": [
          {
            "theme_label": "string",
            "assigned_role": "CENTRAL",
            "review_finding": "SUPPORTED" | "UNSUPPORTED" | "UNCERTAIN",
            "rationale": "Evidence text directly supports central thesis"
          }
        ],
        "overall_disposition": "ACCEPTED_WITH_BOUNDED_SAMPLE"
      }
      ```
- **Exact Acceptance Criteria & Verification Commands:**
  - *Criteria:*
    1. Mechanical checks verify all quotations exist verbatim in source text.
    2. Semantic review is explicitly bounded to declared sample; does NOT claim corpus-wide review.
    3. Disagreements and uncertainties are recorded explicitly rather than coerced.
  - *Verification Command:*
    Execution of the review verification harness against sample paper:
    `.venv/Scripts/python.exe -m pytest tests/test_bounded_content_review.py -v`
  - *Pass/Fail Rules:* All mechanical checks 100% pass; semantic review ledger has explicit disposition for every sampled Theme.
- **Dependencies:**
  - *Preceding:* W12–W15 (initial sample), W25–W26 (deep sample).
- **Invariants & Negative Test Cases:**
  - *Invariant:* Independent review does not mutate underlying catalog data.
  - *Negative Cases:* Truncated or altered quotes immediately fail mechanical audit.
- **Operating Constraints:**
  - Review model calls require explicit class `M` authorization.

---

#### W32: Final User Journey (Full Delivery End-to-End)

- **Feature Name & Objective:** Validation of complete end-to-end user journey across UI, API, and tool interfaces.
- **Technical Objective:**
  Execute and verify the complete scholar user journey from source readiness gate, through automatic night initial reading, multi-Theme browsing, semantic search, evidence inspection, reasoned deep reading decision, complete PaperSkeleton viewing, and portable archive adoption.
- **Inputs, Outputs, Data Models & Schema Fields:**
  - *Inputs:*
    - Full system runtime: Catalog Web API, FastMCP server, SQLite databases, BGE-M3 service, FieldKG bridge.
    - End-to-end user actions:
      1. Journey Step 1: Ingest canonical paper -> verifies full-text readiness gate (W07).
      2. Journey Step 2: Night reading progression -> verifies content card, 14 Themes, disposition (W12–W18).
      3. Journey Step 3: Natural language semantic query -> locates passages via BGE-M3 hybrid search (W19–W21).
      4. Journey Step 4: Inspect candidate Theme relations -> reviews evidence without auto-merge (W20).
      5. Journey Step 5: Purpose-specific deep read request -> verifies disposition and reason (W26).
      6. Journey Step 6: Deep analysis exploration -> inspects L1–L4 Skeleton units and writing map (W24, W25).
      7. Journey Step 7: Export and adopt portable archive -> verifies nonempty target adoption (W28–W30).
  - *Outputs:*
    - Final Journey Receipt: `docs/operations/scholar-catalog-agent-execution/final-journey-receipt-20261104.json`
      ```json
      {
        "journey": "W32_full_delivery_complete_catalog",
        "status": "ACCEPTED",
        "stages_verified": [
          "FULL_TEXT_GATE", "INITIAL_READING", "SEMANTIC_DISCOVERY",
          "CANDIDATE_RELATIONS", "DEEP_SKELETON_L1_L4", "CONTENT_AND_PURPOSE_VIEWS",
          "PORTABLE_ARCHIVE_ADOPTION"
        ],
        "reading_release_engine": "catalog-48cece41023e",
        "all_interfaces_coherent": true
      }
      ```
- **Exact Acceptance Criteria & Verification Commands:**
  - *Criteria:*
    1. Journey completes without errors across Web UI (FastAPI/JS), FastMCP tools, and direct API routes.
    2. Zero discrepancy between database state and UI/tool readback.
    3. Receipt accepted and signed by independent QA (WP-G).
  - *Verification Command:*
    Execution of the integrated journey suite:
    `.venv/Scripts/python.exe -m pytest tests/test_catalog_user_journey.py -k test_full_user_journey -v`
  - *Pass/Fail Rules:* All journey steps return status code 200/202, receipts emitted, receipt JSON matches schema.
- **Dependencies:**
  - *Preceding:* All W01–W30 items. First journey accepted in `first-journey-receipt-20261104.json`.
- **Invariants & Negative Test Cases:**
  - *Invariant:* All displayed data must originate from canonical records; no mock data in production routes.
  - *Negative Cases:* Break in chain of custody or mismatched version throws error and fails journey.
- **Operating Constraints:**
  - Executed at safe idle boundary.

---

#### W33: FieldKG Runtime Health on Ports 8892/8887

- **Feature Name & Objective:** Final client connectivity, schema readback, and storage health check for server-owned FieldKG.
- **Technical Objective:**
  Verify dual-tunnel connectivity from workstation to `alandelone-server-001` on port 8892 (`scholar_fieldkg_tunnel`) and port 8887 (`scholar_graph_probe_tunnel`), verifying OpenSPG project 2 (`ScholarFieldKG`), namespace, schema, and storage readback without remigrating or recreating local graph stores.
- **Inputs, Outputs, Data Models & Schema Fields:**
  - *Inputs:*
    - Workstation tunnels:
      - `http://127.0.0.1:8892` (SSH forward to server loopback 8892, `uuma-scholar-fieldkg.service`).
      - `http://127.0.0.1:8887` (SSH forward to server loopback 8887, `scholar_graph_probe_tunnel`).
    - Client function: `ensure_knowledge_graph(profile="scholar", recover=False)` in `uuma.knowledge_runtime`.
  - *Outputs:*
    - Health check dictionary:
      ```json
      {
        "ready": true,
        "graph": "ScholarFieldKG",
        "project_id": 2,
        "status": "HEALTHY",
        "host_addr": "http://127.0.0.1:8887",
        "bridge_addr": "http://127.0.0.1:8892",
        "schema_verified": true,
        "recovered": false
      }
      ```
- **Exact Acceptance Criteria & Verification Commands:**
  - *Criteria:*
    1. `ensure_knowledge_graph("scholar", recover=False)` returns `ready: True`.
    2. Both port 8892 (bridge) and port 8887 (probe) respond with HTTP 200.
    3. OpenSPG project 2 schema verified; storage read for absent identifier returns empty list without error.
    4. Local stores NOT recreated or overwritten; remote server service NOT restarted.
  - *Verification Command:*
    `.venv/Scripts/python.exe -m pytest tests/test_knowledge_runtime.py -k test_scholar_fieldkg_runtime -v`
    and direct runtime probe:
    `python -c "from uuma.knowledge_runtime import ensure_knowledge_graph; res = ensure_knowledge_graph('scholar', recover=False); print(res); assert res['ready']"`
  - *Pass/Fail Rules:* Returns `ready: True`, `status: HEALTHY`; exit code 0.
- **Dependencies:**
  - *Preceding:* Server placement documented in `docs/operations/scholar-fieldkg-server-20261022.md`.
- **Invariants & Negative Test Cases:**
  - *Invariant:* Zero destructive resets or remigrations.
  - *Negative Cases:* Missing 8887 tunnel returns `BLOCKED` with schema lookup error; missing 8892 returns connection refused.
- **Operating Constraints:**
  - Read-only probe; does not create mock graphs or alter Wisdom project 1 (`Uuma`).

---

#### W34: Scoped Release Closure & Handover Checklist

- **Feature Name & Objective:** Final requirement-to-evidence closure and operational handover.
- **Technical Objective:**
  Compile the final 34-item (W01–W34) traceability matrix, verifying that every single requirement has authentic live evidence or an explicit user-approved disposition, documenting active engine versions, scheduled task PIDs, rollback baselines, and operational maintenance procedures.
- **Inputs, Outputs, Data Models & Schema Fields:**
  - *Inputs:*
    - All work package evidence packets (WP-A through WP-G).
    - Multi-agent execution board (`board.md`).
    - Handover checklist in `docs/operations/scholar-catalog-complete-work-plan-2026-11-04-with-agent-execution-layer.md` §9.6.
  - *Outputs:*
    - Final Handover Document: `docs/operations/scholar-catalog-agent-execution/handover-final-20261104.md`.
    - Updated `board.md` showing all items `RUNTIME_VERIFIED` or `ACCEPTED` (or `DEFER_ACCEPTED`).
    - Closed session handoff in `active-session/HANDOFF.md`.
- **Exact Acceptance Criteria & Verification Commands:**
  - *Criteria:*
    1. Every item W01 through W34 is accounted for; zero items left in unverified or implicitly skipped states.
    2. Final rollback preimages and SHA-256 hashes verified and recorded.
    3. Active engine pointers (`catalog-48cece41023e`) and worker process PIDs documented.
    4. Mission review boundary submitted to orchestrator and human user.
  - *Verification Command:*
    Validation of complete board checklist:
    `python -c "import re; content = open('docs/operations/scholar-catalog-agent-execution/board.md').read(); missing = [f'W{i:02d}' for i in range(1, 35) if f'**W{i:02d}**' not in content]; print('Missing:', missing); assert not missing"`
  - *Pass/Fail Rules:* Board contains all 34 W items; all verification links point to authentic persistent receipts.
- **Dependencies:**
  - *Preceding:* All W01–W33 items.
- **Invariants & Negative Test Cases:**
  - *Invariant:* The Goal cannot be marked complete without explicit user review boundary approval.
  - *Negative Cases:* Unverified claims or missing receipt files block closure.
- **Operating Constraints:**
  - Strict compliance with UuMA repository session lifecycle rules (`rules/session-lifecycle.md`).

---

## 3. Features Discovered Table

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Delivery 2 | Hybrid Dense/BM25 Semantic Retrieval (W19) | Combines BGE-M3 1024-dim dense vectors with BM25 keyword matching via Reciprocal Rank Fusion | Natural language query (1–4000 chars), threshold, limit | Located text chunks with quote, page, section, match basis (`SEMANTIC`/`LEXICAL`) | Returns `LEXICAL_ONLY_INDEX_NEEDED` if model generation changed or index unbuilt | `catalog_content_retrieval.py` |
| 2 | Delivery 2 | In-Flight Source Guard Fencing (W19) | Fences vector indexing and search against mid-operation source PDF tampering | Source PDF SHA256 & byte size | Verified passage projection or abort | Raises `ValueError("Original parsed PDF changed during indexing/retrieval")` | `test_catalog_content_retrieval.py` |
| 3 | Delivery 2 | Bounded Candidate Relation Graph (W20) | Precomputes top-20 nearest Theme neighbors in 32-anchor NumPy float32 matrix blocks | Theme descriptor vectors in SQLite | Candidate relation list (`UNRESOLVED_SIMILARITY`), 2-sided evidence quotes | Reverts to full scan for affected anchor if saved neighbor is deleted | `catalog_candidate_index.py` |
| 4 | Delivery 2 | FastMCP Scholar Content Tools (W21) | Exposes `query_catalog_content` and `get_catalog_theme_candidates` to Scholar agents | JSON query / threshold parameters | Bounded transport preview <= 32K chars with exact quote and pagination | Truncates large metadata while strictly preserving exact quote string | `catalog_content_tools.py` |
| 5 | Delivery 3 | Distinct Held Deep Role Gate (W22) | Enforces human approval boundary for held role retry v419 (model `poolside/laguna-s-2.1:free`) | Human user decision (Approve/Decline) | Durable authorization record in `catalog_reading_requests` | Rejects unapproved dispatches; prevents spending transport retry on prose | `board.md`, `scholar-reading-followthrough-2026-10-29.md` |
| 6 | Delivery 3 | Scoped Deep-Role Continuation (W23) | Executes single authorized retry call, validates JSON output, resumes worker | W22 authorization, original job ID | 1 new model event row, job transitioned to `SUCCEEDED` | Returns to `NEEDS_HUMAN` if returned JSON is malformed or quotes invalid | `skeleton_role_recovery.py` |
| 7 | Delivery 3 | Authentic Sample 4-Layer Skeleton (W24) | Reconstructs complete L1–L4 PaperSkeleton across 85 parsed blocks of authentic sample | 85 parsed blocks from `document_blocks` | 85 rows in `skeleton_units`, 340 in `skeleton_checkpoints` | Foreign key checks and checkpoint mismatches trigger transaction rollback | `catalog_deep.py`, `located_deep.py` |
| 8 | Delivery 3 | 22-Dimension Whole-Paper Content View (W25) | Binds all 22 evaluation dimensions and writing map to authentic Skeleton units | Skeleton units + heading outline | `catalog_skeleton_content_views` row with full JSON view | Fails publication if units or outline differ from replayed model receipts | `catalog_skeleton_views.py` |
| 9 | Delivery 3 | Decoupled Purpose & Value Judgments (W26) | Evaluates paper content for declared research purpose without mutating content authority | Content view ID, research purpose JSON | `catalog_skeleton_purpose_judgments` row with disposition & reasons | Missing content view aborts enqueueing; recommendations never auto-run jobs | `catalog_skeleton_views.py` |
| 10 | Delivery 3 | Cross-View Source Freshness Contract (W27) | Reuses canonical Skeleton across Views; marks derived outputs stale on PDF change | Paper ID, source PDF revisions | `view_history` output with `current_pdf: true/false` and `eligible` | Uploading a new PDF flags historical views stale while preserving audit log | `catalog_skeleton_views.py` |
| 11 | Delivery 4 | Relocated Source Location Mapping (W28) | Resolves retained source PDF and MinerU package when original workstation paths change | Relocated path, retained package manifest | Verified `require_parse_source` dictionary | Modified or tampered PDF raises `ValueError("Original parsed PDF changed")` | `test_relocated_fulltext_guard_v665.py` |
| 12 | Delivery 4 | Finished Record Guard & Archive (W29) | Packages complete PaperSkeleton and model delivery receipts into sealed archive carrier | Authentic completed sample paper rows | Sealed evidence package + verifier receipt | Incomplete or runnable jobs immediately fail finished-evidence guard | `finished_evidence_guard_v285.py` |
| 13 | Delivery 4 | Controller Adoption & Reversal (W30) | Imports completed history into nonempty target with idempotency and compensating reversal | Sealed archive, target database | `catalog_reading_requests` / `events` rows (`CATALOG_HISTORY_ADOPTED`) | Version conflicts roll back transaction; reversal appends `REVERSED` event | `catalog_history_adoption.py` |
| 14 | Delivery 4 | Bounded Semantic Claim Review (W31) | Audits quotation accuracy programmatically and evaluates sampled semantic claims | Published cards, full-text spans | Structured review findings ledger | Quotation text mismatch fails mechanical check immediately | `work-plan` §9.5 (WP-G) |
| 15 | Delivery 4 | End-to-End User Journey Receipt (W32) | Traverses full user workflow across UI, API, tools and emits signed receipt | Integrated runtime services | `final-journey-receipt-20261104.json` | Any API/tool mismatch or broken contract fails journey acceptance | `board.md`, `work-plan` §9.5 |
| 16 | Delivery 4 | Dual-Tunnel FieldKG Connectivity (W33) | Verifies bridge (8892) and probe (8887) SSH tunnels to server-owned `ScholarFieldKG` | Workstation loopback 8892 and 8887 | `ready: True`, OpenSPG project 2 schema verified | Missing tunnel returns `BLOCKED`; forbids recreating local stores | `scholar-fieldkg-server-20261022.md`, `knowledge_runtime.py` |
| 17 | Delivery 4 | Traceable Scoped Release Closure (W34) | Verifies all 34 work items against authentic evidence before Goal closure | Board ledger, receipts, rollback preimages | Handover report and closed session handoff | Incomplete evidence blocks closure; requires explicit user gate signoff | `work-plan` §9.6 |

---

## 4. Edge Cases Table

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | W19 Semantic Retrieval | Query with zero word overlap with source (synonyms/concepts) | Successfully matches via dense BGE-M3 embeddings (`lexical_score: 0`, `semantic_similarity: 1.0`, mode `HYBRID`). |
| 2 | W19 Semantic Retrieval | Embedding service restart resulting in new model generation hash | Search returns `mode: "LEXICAL_ONLY_INDEX_NEEDED"`, `indexed_passages: 0`, refuses to serve stale vectors. |
| 3 | W19 Semantic Retrieval | Source PDF byte altered while embedding request is in flight | Worker detects hash mismatch upon return; aborts and refuses to write vectors to cache. |
| 4 | W19 Semantic Retrieval | Query containing non-finite vectors (`NaN`, `Inf`, boolean) | Normalizer rejects input immediately with `ValueError`. |
| 5 | W20 Candidate Index | Anchor neighbor deleted from active Theme vocabulary | Next incremental update detects missing neighbor and triggers an exact full scan for that anchor only. |
| 6 | W20 Candidate Index | Morning clock hits 08:00 during candidate aggregation | In-flight embedding checkpoints safely; new candidate matrix batch is deferred to next night window. |
| 7 | W21 MCP Tools | Large match payload exceeding 32,000 transport characters | Truncates metadata array while preserving exact quotation string and setting `has_more_matches: true` with `next_offset`. |
| 8 | W22 Deep Retry Gate | Automated subagent attempts to dispatch v419 retry without human prompt | Operation rejected with `PermissionError`; job remains safely in `NEEDS_HUMAN` (fence 181). |
| 9 | W23 Role Continuation | Replacement model returns text with unsupplied quotation IDs | Validation fails; job remains in `NEEDS_HUMAN` without consuming additional retries. |
| 10 | W24 Skeleton Extraction | Missing block checkpoint in 4-layer sequence | Fenced publication fails; entire transaction rolls back; `paper_skeletons` count remains 0. |
| 11 | W25 Content Views | Inferred heading outline differs from original parse manifest | Snapshot validation raises `ValueError("Published source outline differs from its original heading version")`. |
| 12 | W26 Purpose Judgments | Research question changes for an already-extracted paper | Enqueues new `SKELETON_PURPOSE` job using existing content view without re-running 4-layer Skeleton extraction. |
| 13 | W27 Version Freshness | New PDF version uploaded for paper with completed deep Skeleton | `view_history` marks existing views `current_pdf: false`, retaining complete historical visibility without overwrite. |
| 14 | W28 Portable Sources | 1 byte appended to relocated PDF on disk | `require_parse_source` detects hash discrepancy and raises `ValueError("Original parsed PDF changed")`. |
| 15 | W30 History Adoption | Target database already contains conflicting `paper_versions` row | Adoption transaction aborts immediately and rolls back all inserted records. |
| 16 | W30 History Adoption | Re-submitting exact identical adoption packet | Idempotent check returns existing receipt without inserting duplicate rows. |
| 17 | W30 History Adoption | Controller issues reversal for adopted history | Appends `CATALOG_HISTORY_ADOPTION_REVERSED` event; scientific evidence remains inspectable but marked ineligible for current queries. |
| 18 | W33 FieldKG Health | Workstation port 8887 tunnel closed while 8892 is open | Bridge responds, but schema lookup fails; `ensure_knowledge_graph` returns `BLOCKED`. |

---

## 5. Cross-Delivery Architecture & Governance Constraints

### 5.1 Operating Constraints (§9 Execution Guardrails)
1. **Strictly Serialized Production Writes:**
   All mutations to `catalog.db` and `wisdom.db` must be serialized through designated work-package owners (WP-A for Reading runtime, WP-F for adoption). Parallel specialist agents must operate read-only or in isolated test worktrees.
2. **Night Window Processing (00:00–08:00 Asia/Kuala_Lumpur):**
   Automated batch reading, digest progression, and vector index generation execute exclusively within the 00:00–08:00 window. Explicit manual user requests take priority at safe boundaries.
3. **Decoupled Recommendation from Execution:**
   System recommendations (`DEEPER_RECOMMENDED`) never automatically spawn background jobs or model dispatches. User or policy consent is mandatory.
4. **Non-Destructive Adoption & Reversal:**
   Historical records, model receipts, and scientific observations are immutable. Errors and reversals are handled via append-only compensating events.
5. **English Content & Native Preservations:**
   All research descriptions, Themes, and synthesized artifacts use English. Source quotations and original language attributes are preserved intact.
