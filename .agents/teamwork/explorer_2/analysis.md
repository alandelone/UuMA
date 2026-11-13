# Scholar Catalog Delivery 1 Baseline and Operational Constraints Investigation Report

**Author:** explorer_2 (teamwork_explorer)  
**Date:** 2026-11-04 (Asia/Kuala_Lumpur)  
**Workspace:** `C:\Users\Alandelone\CodeSpace_Local\UuMA\`  
**Governing Context:** `ORIGINAL_REQUEST.md`, `mission_status.json`, `active-session/HANDOFF.md`, `docs/operations/scholar-catalog-complete-work-plan-2026-11-04-with-agent-execution-layer.md` (§9), `docs/operations/scholar-catalog-agent-execution/board.md`

---

## Executive Summary

Delivery 1 (Usable Initial-Reading Catalog) has been verified as **ACCEPTED and OPERATIONAL**. The active reading engine is `catalog-48cece41023e` (supervised worker pair PID 68680 / 77376), running against canonical database `C:\Users\Alandelone\CodeSpace_Local\RSTV4\data\catalog.db` with an immutable pre-activation backup. The first user journey is formally accepted under receipt `first-journey-receipt-20261104.json`. 

The operational environment and runtime dependencies for advancing into Delivery 2 (Global Semantic Discovery, W19–W21) are fully online and verified:
- **BGE-M3 Embedding Service**: Online on `alandelone-server-001` (1024 dimensions, onnxruntime, CPU) via SSH proxy.
- **FieldKG Knowledge Runtime**: Fully operational on port 8892 (Bridge) and port 8887 (OpenSPG server, project 2 / `ScholarFieldKG`), with `ensure_knowledge_graph('scholar')` returning `ready=True, graph='ScholarFieldKG', recovered=False`.
- **Database Partitioning & Concurrency Guardrails**: Under §9 "分层分权，严禁全员并发裸写", production writes are strictly segregated by domain owner (`catalog.db` for Scholar Catalog, `wisdom.db` for Wisdom knowledge, `uuma.db` for session control plane). Concurrent production writes across work packages are strictly forbidden.
- **Night Window Enforcement**: Automatic reading/parsing/indexing is gated to 00:00–08:00 Asia/Kuala_Lumpur (`RSTV4/src/rstv4/reading_policy.py`). Manual priority requests bypass this window only when recorded with `user_requested: true`.
- **v419 Single-Call Retry Boundary (W22)**: A distinct Class M/H user decision boundary is maintained. The v419 retry remains held/blocked for Delivery 3 and does not block Delivery 2.

---

## 1. Delivery 1 Completion and Baseline State

### 1.1 First Journey Acceptance Receipt
Analysis of `docs/operations/scholar-catalog-agent-execution/first-journey-receipt-20261104.json`:
- **Journey**: `W32_first_delivery_usable_initial_catalog`
- **Status**: `ACCEPTED`
- **Sample Paper ID**: `paper_dd83af8026e39dd2a2e9316622a7ca49`
- **Run ID**: `understanding_3c325480eadd87c3249d5ddd09615894fca1dcc5b73c323a4fa2b7dc40402b9f`
- **Judgment ID**: `readingjudgment_d4aea750de4db1decc612642e04081650bab7bf2cbc419f3bdfb953a5c3e6fa0`
- **Document Blocks Verified**: 85 blocks
- **Content Card Structure**: 12 verified keys (`author_contribution`, `dimensions`, `evidence_quotes`, `limitations`, `local_consolidation`, `materials`, `method`, `part_previews`, `question`, `reading_coverage`, `results`, `themes`)
- **Author Contribution Preview**: *"Synthesizes multi-level integration pathways between decentralized multi-agent systems and blockchain..."*
- **Theme Analysis**: 14 total Themes (5 `CENTRAL`, 9 `SUBSTANTIAL`), no passing mentions misrepresented as main topics
- **Reading Disposition**: 2 concrete deep-read reasons citing `system_architecture` and `evaluation`
- **Distinct Counting**: `distinct_counting_verified: true`
- **Release Engine**: `catalog-48cece41023e`

### 1.2 UuMA Session and Pipeline Gate State
- **`mission_status.json`**:
  - `stage`: `verification` (allowed stages: `discovery` -> `design` -> `execution` -> `verification` -> `complete`)
  - `gate.current`: `stage-gates/04-verification-report.md`
  - `gate.status`: `pending_review`
  - `gate.blocked_by`: `null`
  - Invariant: `mission_status.json` is the sole source of truth for pipeline progression; stage transitions require Orchestrator or explicit user review boundary approval.
- **`active-session/HANDOFF.md`**:
  - Documents Delivery 1 acceptance and operational status under §9 principles.
  - W01: Reconciled scheduled digest recovery v653 (`night-digest-admission-v653.json`, Event 1784 SUCCESS).
  - W02: Activated combined Reading repair release `catalog-48cece41023e` via `activate_combined_reading_v664.py`. Preflight clean, database backed up to `combined-reading-activation-v664/catalog-before.db` (SHA256: `30dd73444d...`), active worker pair PID 68680 / 77376.
  - W06: Triaged all 32 `NEEDS_HUMAN` jobs into 10 explicit error signatures in `held-jobs-triage.md`.
  - W07: Verified full-text readiness gate on real and relocated PDF (`test_relocated_fulltext_guard_v665.py` PASSED).
  - W08–W11: Verified pipeline & scheduling policies (40 tests passed in `test_catalog_understanding.py`, `test_catalog_theme_corrections.py`, `test_catalog_reading_overview.py`).
  - W12–W18: Verified Catalog UI, multi-Themes, disposition, and distinct counts on real database.
  - W19–W21: Verified semantic retrieval and tools (25 tests passed); live BGE-M3 service on `alandelone-server-001` probed.
  - W32: Accepted First User Journey.
  - W33: Probed live FieldKG knowledge runtime (`ready=True`, `graph=ScholarFieldKG`).

### 1.3 Live Queue Inventory in `catalog.db`
Direct SQLite read-only inspection of `C:\Users\Alandelone\CodeSpace_Local\RSTV4\data\catalog.db` reveals:
- Total Papers: **3,177**
- `catalog_reading_jobs` (173 total):
  - `SUCCEEDED`: **3**
  - `READY`: **137** (eligible for progression under night policy)
  - `RESOURCE_WAIT`: **1**
  - `NEEDS_HUMAN`: **32** (triaged, non-blocking to the 137 READY jobs)
- `catalog_reading_judgments`: 3
- `catalog_understanding_runs`: 3
- `catalog_themes`: 39
- `catalog_theme_observations`: 39
- `catalog_theme_mappings`: 0 (proposals remain candidate until reviewed under W16)
- `catalog_candidate_link_proposals`: 0
- `catalog_skeleton_content_views`: 0 (Delivery 3 scope)
- `paper_skeletons`: 0 (Delivery 3 scope)

### 1.4 Starting State for Delivery 2 (Global Semantic Discovery)
Delivery 2 (W19–W21) builds directly on top of Delivery 1:
1. **W19 (Full-Text Semantic Retrieval & Index Coverage)**: Core BGE-M3 integration exists in `RSTV4/src/rstv4/catalog_embeddings.py`. 15 retrieval tests already passed. Requires bounding retrieval queries to eligible parsed full text and reporting honest coverage states (`indexed`, `pending`, `stale`, `unavailable`).
2. **W20 (Evidence-Backed Semantic Relation Proposals)**: 7 candidate index tests passed. Generates two-sided candidate proposals without automatically applying merges or claims, routing review through W16.
3. **W21 (Scholar Tool and Entry Integration)**: Connects canonical Catalog records to Scholar tools/MCP without changing database identity or restarting the shared gateway.

---

## 2. Operational and Database Constraints

### 2.1 Database Paths, Schemas, and Domain Ownership
Inspection confirms strict domain isolation with no shared SQLite files across hosts:

| Database | Canonical Path | Size | Schema / Purpose | Sole Authority / Designated Owner |
| :--- | :--- | :---: | :--- | :--- |
| **`catalog.db`** | `C:\Users\Alandelone\CodeSpace_Local\RSTV4\data\catalog.db` | ~100.6 MB | 127 tables: `papers`, `catalog_reading_jobs`, `catalog_understanding_runs`, `catalog_themes`, `catalog_reading_judgments`, `fieldkg_*`, `skeleton_*` | Sole editable authority for Scholar Catalog. Dedicated Reading worker (`catalog-48cece41023e`) and designated WP operators. |
| **`wisdom.db`** | `C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\wisdom.db` | ~479 KB | 37 tables: `claims`, `chunks`, `evidence`, `knowledge_events`, `knowledge_fts`, `conflicts`, `gaps` | Wisdom-Oldman knowledge base. New claims remain candidates; only Orchestrator/user review may apply, reject, or reverse. |
| **`uuma.db`** | `C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\uuma.db` | ~2.31 GB | 18 tables: `agents`, `events`, `repo_session_events`, `commerce_tasks`, `commerce_commands`, `operations` | UuMA local-first control plane state, agent lifecycle, session audit. |

**Prohibitions Enforced**:
- Never repurpose Hermes `state.db` or join `uuma.db`, `wisdom.db`, and `catalog.db` schemas.
- Keep knowledge record types distinct; preserve append-only history via supersession or compensating reversal.
- Knowledge MCP operations must remain semantic and backend-neutral; raw SQLite APIs are never exposed.

### 2.2 §9 "分层分权，严禁全员并发裸写" Constraints
Detailed analysis of Section 9 of the work plan:
1. **Designated Writers and Owners**:
   - Every work item (W01–W34) has exactly **one accountable work package owner** (WP-A through WP-G). Collaborators cannot independently accept or write outside their assigned scope.
   - Cross-package changes require a formal request specifying `needed interface`, `reason`, `proposed owner`, `impact`, and `required acceptance`.
   - Shared database migrations, generated schemas, public contracts, and service scripts require a single appointed editor.
2. **Write Serialization & Transactional Boundaries**:
   - Production gate (§9.4.6): Pre-read actual process/task and source hashes immediately before any authorized write.
   - Require transactional idle boundaries, unique worker ownership, backup/rollback receipts, and idempotent readback.
   - Any stale precondition blocks the write pending a fresh plan.
3. **Approval Classification**:
   - **Class R (Read-Only)**: Inspect code, historical receipts, status. Permitted without extra gate.
   - **Class L (Isolated Development)**: Changes in isolated worktree, local test fixtures, draft documentation. Requires user resumption authorization.
   - **Class O (Operational Write)**: Switch Reading release, admit jobs, touch production queues/stores, restart worker. Requires explicit operational scope authorization, fresh preconditions, single operator, and rollback plan.
   - **Class M (External Model Request)**: Real LLM call / replay. Requires approved budget/policy and distinct approval (e.g., v419).
   - **Class H (Human Scientific / Scope Decision)**: Accept scientific semantics, Theme merges, permanent DEFER, or Goal closure. Requires direct user decision.
   - Rule: Class R or L access must **never** be treated as permission for Class O, M, or H.
4. **Worktree and Branch Isolation**:
   - One isolated git worktree/branch per work package.
   - Prevents git conflict chaos, concurrent file locks, and unintentional production pollution.
   - Orchestrator maintains central integration queue and executes bounded verification before merging.

### 2.3 00:00–08:00 Asia/Kuala_Lumpur Night Window Constraint
Defined and enforced in `c:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\reading_policy.py`:
- `TIMEZONE = "Asia/Kuala_Lumpur"` (UTC+08:00)
- `WINDOW_START_HOUR = 0`, `WINDOW_END_HOUR = 8`
- `AUTOMATIC_WORK_TYPES = frozenset({"SCREEN", "PARSE_PDF", "QUICK_READ", "SKELETON", "ASSESS"})`
- **Gating Mechanism**:
  ```python
  def night_window_open(now: datetime | None = None) -> bool:
      return WINDOW_START_HOUR <= local_time(now).hour < WINDOW_END_HOUR

  def admitted(job: Mapping, now: datetime | None = None) -> bool:
      return (
          job.get("job_type") not in AUTOMATIC_WORK_TYPES
          or explicit_manual(job)
          or night_window_open(now)
      )
  ```
- **Fair Resource Sharing**:
  - Bulk automatic reading, parsing, and semantic indexing run strictly between 00:00 and 08:00 MYT.
  - Daytime bulk admissions are blocked.
  - **Manual Priority Override**: A request bypasses the night window if and only if `input_json.user_requested == True` (`explicit_manual(job)`). Manual requests take priority at a safe work boundary (`foreground_reading_pending()`).
  - System recommendation does NOT equal user consent or execution grant.

### 2.4 FieldKG Runtime Configuration and Connectivity
FieldKG connects Scholar research data to OpenSPG/KAG graph structures.
- **Topology (`deploy/production-topology.json`)**:
  - Server: `alandelone-server-001`
  - Workstation Local SSH Forwards: Ports **8887** and **8892**
  - OpenSPG Server Port: **8887**
  - Scholar FieldKG Bridge Port: **8892**
  - Namespace: `ScholarFieldKG`
  - Project ID: `2`
- **Live Connectivity Verification**:
  1. `http://127.0.0.1:8892/health`:
     - Returned HTTP 200: `{'ready': True, 'runtime': 'OpenSPG/KAG', 'namespace': 'ScholarFieldKG', 'project_id': '2', 'host_addr': 'http://127.0.0.1:8887'}`
  2. `http://127.0.0.1:8887/public/v1/project`:
     - Returned HTTP 200: Lists Project 1 (`Uuma`) and Project 2 (`ScholarFieldKG`).
  3. Python verification via `uuma.knowledge_runtime.ensure_knowledge_graph('scholar')`:
     - Executed successfully, returning: `{'ready': True, 'graph': 'ScholarFieldKG', 'recovered': False}`.
- **Non-Destructive Invariant**:
  - Never remigrate FieldKG, recreate local graph stores, reindex unrelated graphs, or restart shared services as routine verification.

### 2.5 v419 Single-Call Retry Approval Requirement (W22)
- **Origin of v419**:
  - Pertains to job `skeletonviewjob_1216bde784964dc42990bbd92b55cd7431a23a60a43d94a05fe1bd58c6ec81e6` on the genuine original PaperSkeleton acceptance sample paper, which failed with `"Model output is not a JSON object"`.
- **Authorization Context**:
  - The previous one-off authorization (`v329`) was consumed and cannot authorize this different failure.
  - Classified under Class M (external model call) and Class H (human decision).
  - General plan approval, Goal resumption, or task assignment does **not** authorize v419.
- **User Decision Boundary**:
  - Approval or declination must be an authentic, distinct, direct user decision tied to the exact original proposal and scope.
  - If approved: at most the single authorized call is executed, its result authenticated, and the original job continued under normal validation.
  - If declined: disposition is durably recorded (`BLOCKED`), no unapproved calls are made, and final disposition is discussed rather than fabricating completion.
- **Sequencing & Independence**:
  - W22 is deferred until Delivery 3 (PaperSkeleton Deep Analysis).
  - It does **not** block Delivery 1 or Delivery 2.

---

## 3. Findings Matrix

| Domain | Observation / Verified Evidence | Operational Implication for Delivery 2 |
| :--- | :--- | :--- |
| **Delivery 1 State** | `first-journey-receipt-20261104.json` ACCEPTED; Engine `catalog-48cece41023e` active (PID 68680/77376). 3 SUCCEEDED, 137 READY, 32 triaged NEEDS_HUMAN. | Solid, verified baseline. Delivery 2 can proceed immediately without waiting for Delivery 3 deep reads or complete backlog clearance. |
| **Pipeline Stage** | `mission_status.json`: `verification`, gate `stage-gates/04-verification-report.md` (pending_review). | Preserve verification stage and pending review status; do not advance pipeline gate without Orchestrator/user review. |
| **Database Authority** | `catalog.db` (~100.6 MB) sole editor is Scholar worker; `wisdom.db` (~479 KB) owned by Wisdom; `uuma.db` (~2.31 GB) owned by control plane. | Strict serialization; no concurrent writes across work packages; use isolated worktrees and branch merge queues. |
| **Night Policy** | `reading_policy.py`: 00:00–08:00 Asia/Kuala_Lumpur window enforced for automatic jobs. Manual priority requires `user_requested: true`. | Delivery 2 batch indexing must be gated to the night window or run against existing parsed full-text with bounded sample queries. |
| **Embedding Service** | BGE-M3 online on `alandelone-server-001` (1024 dim, onnxruntime, CPU) via SSH stdin pipe. | Ready for W19 semantic queries; generation tokens and source guards prevent stale embeddings. |
| **FieldKG Runtime** | Ports 8892 (bridge) and 8887 (OpenSPG) HTTP 200; `ensure_knowledge_graph('scholar')` returns `ready=True, recovered=False`. | W33 healthy; no remigration or graph store rebuilds permitted. |
| **v419 Boundary** | W22 is `BLOCKED (H)` awaiting user decision for single-call retry. Scoped to Delivery 3. | Completely decoupled from Delivery 2; keep blocked until Delivery 3 is reached. |

---

## 4. Conclusion & Recommendations for Delivery 2

1. **Baseline is Sound**: Delivery 1 meets all acceptance criteria. The 137 READY reading jobs and 3 SUCCEEDED sample papers provide genuine full-text source evidence for semantic discovery.
2. **Delivery 2 Architecture**:
   - WP-D owns W19, W20, and W21.
   - W19 will index eligible located passages and candidate labels using BGE-M3 under the approved night/resource policy.
   - W20 will compute bounded candidate nearest neighbors with two-sided evidence citations, routing human reviews to W16.
   - W21 will verify the Scholar entry point against canonical `catalog.db` records.
3. **Execution Safety**:
   - Keep WP-D changes in an isolated branch/worktree.
   - Follow Class R/L boundaries during preparation; do not initiate unbounded model calls or concurrent production writes.
   - Respect the 00:00–08:00 Asia/Kuala_Lumpur batch processing window.
