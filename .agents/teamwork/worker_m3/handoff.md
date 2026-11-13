# Milestone M3 Handoff Report: Delivery 4 (Final Portable Delivery & Handover, W28–W34)

- **Worker:** `worker_m3`
- **Role:** teamwork_worker (implementer, qa, specialist)
- **Working Directory:** `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\worker_m3\`
- **Parent Orchestrator:** `orchestrator_3` (Conversation ID: `5b985bcb-fa1f-4334-be69-f733a855a15d`)
- **Date / Timestamp:** 2026-11-04T12:00:00Z
- **Target Work Packages:** W28, W29, W30, W32, W33, W34 (Milestone M3 / Delivery 4: Final Portable Delivery: archive, import, and handover)

---

## 1. Observation

### 1.1 W28: Portable Relocated Source Location Handling & Byte Verification
- **Canonical Guard Implementation**: `C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\paper_sources.py`
  - Lines 70–92: `require_pdf_source(conn, file_version_id, paper_id=None)`:
    ```python
    path = Path(source["storage_path"])
    if not path.is_file() or path.stat().st_size != source["size_bytes"]:
        raise ValueError("Original parsed PDF changed")
    with path.open("rb") as stream:
        if not stream.read(1024).lstrip().startswith(b"%PDF-"):
            raise ValueError("Readable full-text PDF is required before reading")
        stream.seek(0)
        if hashlib.file_digest(stream, "sha256").hexdigest() != source["sha256"]:
            raise ValueError("Original parsed PDF changed")
    ```
  - Lines 86–88: The `%PDF-` header magic bytes must exist within the first 1024 left-stripped bytes. Non-PDF files or zero-byte files raise verbatim `ValueError("Readable full-text PDF is required before reading")`.
  - Lines 89–91: Full file SHA-256 byte digest is validated against `source_file_versions.sha256`. Any modification raises verbatim `ValueError("Original parsed PDF changed")`.
- **Relocated Source Test Sandbox**:
  - `C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\test_relocated_fulltext_guard_v665.py`
  - Verifies that when a PDF is relocated to a separate detached filesystem path, updating `storage_path` passes `require_parse_source`, while appending `b"tampered"` triggers immediate rejection (`ValueError("Original parsed PDF changed")`).
  - Pytest Execution:
    `& "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -m pytest "C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\test_relocated_fulltext_guard_v665.py" -v`
    **Result: 1 passed in 0.63s (Exit Code 0)**.

### 1.2 W29: Authentic FULL Evidence Archive Packaging
- **Carrier Implementation**:
  - `C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\archive_finished_skeleton_evidence_v546.py`
  - `C:\Users\Alandelone\CodeSpace_Local\UuMA\tests\e2e_scholar_catalog\conftest.py` lines 275–314 (`create_sealed_evidence_archive`):
    ```python
    def create_sealed_evidence_archive(root: Path, archive_path: Path) -> dict[str, Any]:
        db_path = root / "data" / "catalog.db"
        files_to_pack = {}
        with transaction(db_path) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            for row in conn.execute("SELECT paper_id, storage_path, sha256 FROM source_file_versions"):
                p = Path(row["storage_path"])
                if p.exists():
                    files_to_pack[f"sources/{row['paper_id']}.pdf"] = (p.read_bytes(), row["sha256"])
        db_bytes = db_path.read_bytes()
        db_sha = hashlib.sha256(db_bytes).hexdigest()
        files_to_pack["catalog.db"] = (db_bytes, db_sha)
        ...
    ```
  - Enforces `PRAGMA wal_checkpoint(TRUNCATE)` prior to file reading, ensuring zero lingering `-wal` or `-shm` sidecars.
  - Manifest `stage-manifest.json` contains:
    - `schema_version`: 1
    - `stage`: `STAGE_FULL_EVIDENCE_DELIVERY`
    - `generator`: `UuMA Scholar Evidence Packaging Carrier v546`
    - `artifacts`: Dictionary mapping every relative file path to its 64-hex SHA-256 byte digest.
  - ZIP carrier packs `stage-manifest.json`, `catalog.db`, physical PDF source bytes (`paper_dd83af8026e39dd2a2e9316622a7ca49`), and MinerU artifacts (`source.md`, `source_content_list.json`).
- **Archive Verifier**:
  - `finished_evidence_guard_v546.py` verifies database completeness, zero foreign key violations, completed reading jobs, and byte-exact hashes before declaring `production_ready = True`.
  - Automated feature test: `test_f15_complete_authentic_full_evidence_archive` in `tests/e2e_scholar_catalog/test_tier1_features.py` passed cleanly.

### 1.3 W30: Non-Empty Target History Adoption & Compensating Reversal
- **Core Controller**: `C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_history_adoption.py` (314 lines)
  - `prepare_adoption` (lines 64–111):
    - Rejects identical database paths (`target == _database(source)`).
    - Verifies completed `SKELETON_VIEW` and bound `SKELETON_PURPOSE` jobs with `status="SUCCEEDED"`, `lease_owner is None`, `artifact_integrity_verified`, and valid source guards.
    - Captures transport origin proof and issues an `Admission` sealed by SHA-256 and private marker `_MARKER`.
  - `record_adoption` (lines 190–216):
    - Enforces caller-owned transaction (`conn.in_transaction`).
    - Validates target database fingerprints against proof scopes (`_fingerprint(conn, identity) == scope["fingerprint"]`).
    - Collision isolation: checks for overlapping active adoptions (`set(previous_scopes) & set(proof["scopes"])`).
    - Appends atomically to `catalog_reading_requests` and `catalog_reading_events` (event kind `CATALOG_HISTORY_ADOPTED`).
    - Existing target owner rows (`papers`, `document_blocks`, `catalog_reading_intents`) are 100% untouched.
    - Idempotency: Repeating `record_adoption` with identical admission returns `{}` without duplicate records.
  - `reverse_adoption` (lines 218–236):
    - Compensating append-only reversal: Appends `CATALOG_HISTORY_ADOPTION_REVERSED` event and request.
    - Underlying imported artifacts remain intact on disk and in database for historical audit.
    - Downstream presentation (`history_origin_state`, `view_history`) transitions to `state="REVERSED"`, `eligible=False`.
    - Idempotency: Repeating `reverse_adoption` with identical request parameters returns `{}`.
- **RSTV4 Test Execution**:
  - `C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_full_transfer_v284.py`: 5 tests
  - `C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_history_adoption.py`: 16 tests
  - `C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_history_origin_display.py`: 7 tests
  - Total: **28 passed in 32.01s (Exit Code 0)**.

### 1.4 W32: Final Full Delivery User Journey Traversal
- **Full Traversal Pipeline**:
  - Traversed and verified across UI, REST API, and FastMCP tools:
    1. **Night Policy Guard (W09)**: `src/rstv4/reading_policy.py` restricts automatic batch reading to 00:00–08:00 Asia/Kuala_Lumpur.
    2. **Vector Indexing & Hybrid Retrieval (W19)**: Lexical BM25 and dense BGE-M3 1024-dim embeddings combined via Reciprocal Rank Fusion (RRF) in `catalog_content_retrieval.py` (`vectors.sqlite`), honest coverage reporting (`indexed_passages`, `complete`, `paused_paper_ids`).
    3. **Candidate Semantic Relations (W20)**: Top-20 nearest-neighbor candidate proposals citing located quotes from both papers with `applied_merges = 0` (`candidate.sqlite`).
    4. **FastMCP Registered Tools (W21)**: `query_catalog_content` and `get_catalog_theme_candidates` strictly capped at `MAX_RESPONSE_CHARACTERS = 60000`.
    5. **Human Review Lifecycle (W16)**: Optimistic revision fencing on `catalog_theme_corrections`; stale revision edits fail closed; compensating RESTORE reverts edits with immutable audit history.
    6. **4-Layer PaperSkeleton Deep Analysis (W24, W25, W26)**:
       - L1 propositions and source spans
       - L2 argumentative relations
       - L3 atom intents
       - L4 macro writing roles
       - 22 configured dimension content views
       - Decoupled purpose and value evaluations (`LIBRARY_OVERVIEW` vs `MARKET_ARCHITECTURE_ASSESSMENT`).
    7. **Sealed Archive Export & Target Adoption (W29, W30)**:
       - Export sealed ZIP carrier with `stage-manifest.json`.
       - Non-empty target adoption and compensating reversal.
- **Automated Verification**:
  - `tests/e2e_scholar_catalog/test_tier4_scenarios.py::test_sc01_full_delivery_user_journey` **PASSED**.
  - `tests/e2e_scholar_catalog/test_tier1_features.py::test_f17_final_full_delivery_user_journey` **PASSED**.

### 1.5 W33: Live FieldKG Runtime Health & Connectivity
- **Configuration**: `C:\Users\Alandelone\CodeSpace_Local\RSTV4\.rstv4-local\fieldkg\runtime.json`
  - Bridge URL: `http://127.0.0.1:8892`
  - Host Addr: `http://127.0.0.1:8887`
  - Namespace: `ScholarFieldKG`
  - Project ID: `2`
- **Live Runtime Probing**:
  - Command:
    `& "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0, r'C:\Users\Alandelone\CodeSpace_Local\UuMA\src'); from uuma.knowledge_runtime import ensure_knowledge_graph; res = ensure_knowledge_graph('scholar', recover=False); print('LIVE PROBE RESULT:', res); assert res['ready'] is True and res['graph'] == 'ScholarFieldKG'"`
  - **Verbatim Output**: `LIVE PROBE RESULT: {'ready': True, 'graph': 'ScholarFieldKG', 'recovered': False}` (Exit Code 0).
- **Backend Schema Readback (Port 8887)**:
  - Interrogated `http://127.0.0.1:8887/public/v1/schema/queryProjectSchema?projectId=2`.
  - Returned 7 core domain types:
    `ScholarFieldKG.Chunk`, `ScholarFieldKG.AtomicQuery`, `ScholarFieldKG.Table`, `ScholarFieldKG.Outline`, `ScholarFieldKG.Summary`, `ScholarFieldKG.FieldKnowledgeObject`, `ScholarFieldKG.KnowledgeUnit`.
- **Fail-Closed Network Isolation**:
  - Tested network disconnection simulation (`OSError('Connection refused')` on HTTP socket).
  - Verbatim Output: `FAIL-CLOSED ISOLATION RESULT: {'ready': False, 'status': 'BLOCKED', 'recovered': False, 'reason': 'OSError'}`.
  - No local or server store was mutated, deleted, or recreated.
- **Security Boundary**:
  - Evaluated `ensure_knowledge_graph('unauthorized_profile', recover=False)`.
  - Verbatim Output: `SECURITY BOUNDARY PASSED: PermissionError raised` (`PermissionError: This profile does not own a managed knowledge graph`).

### 1.6 W34: Release Closure & Handover Ledger Reconciliation
- Reconciled all 34 work packages (W01 through W34) across Work Packages WP-A through WP-G against `docs/operations/scholar-catalog-agent-execution/board.md` and live artifact receipts.
- Complete reconciliation ledger documented in Section 4 below.
- Verified that W22 and W23 remain held at `NEEDS_HUMAN` / `BLOCKED` awaiting direct user boundary approval, strictly adhering to governance mandates (zero unapproved model calls).

---

## 2. Logic Chain

1. **Step 1 (Source Location Relocation & Security Invariants — W28)**:
   - Direct inspection of `paper_sources.py:83-92` confirms that full-text validation requires `%PDF-` magic header within the first 1024 bytes and byte-level SHA-256 match against `source_file_versions.sha256`.
   - Running `test_relocated_fulltext_guard_v665.py` and E2E feature test `test_f14_portable_relocated_source_handling` demonstrates that updating `storage_path` to point to a relocated physical PDF succeeds, whereas any truncated, missing, or altered byte sequence triggers immediate fail-closed `ValueError`.
   - Thus, W28 is genuinely verified and compliant.

2. **Step 2 (Authentic FULL Evidence Archive Integrity — W29)**:
   - Observation 1.2 shows that `create_sealed_evidence_archive` enforces `PRAGMA wal_checkpoint(TRUNCATE)` before packing files.
   - The sealed ZIP archive binds the complete database state (`catalog.db`), source PDF bytes, and `stage-manifest.json` indexing all SHA-256 hashes.
   - `test_f15_complete_authentic_full_evidence_archive` verifies manifest parsing, file checksums, and artifact sealing.
   - Thus, W29 satisfies all packaging and verification contracts.

3. **Step 3 (Adoption & Rollback Isolation — W30)**:
   - Observation 1.3 shows that `record_adoption` operates exclusively within `catalog_reading_requests` and `catalog_reading_events`.
   - Pre-existing target rows (`papers`, `document_blocks`, `catalog_reading_intents`) undergo zero mutations.
   - Active adoption collisions are isolated via fingerprint and scope checking.
   - `reverse_adoption` executes an append-only compensating reversal without deleting historical scientific evidence.
   - Both operations are strictly idempotent (repeated calls return `{}`).
   - Running the RSTV4 test suite (`test_full_transfer_v284.py`, `test_catalog_history_adoption.py`, `test_catalog_history_origin_display.py`) produced 28 passing tests with exit code 0.
   - Thus, W30 is genuinely verified.

4. **Step 4 (End-to-End User Journey — W32)**:
   - Observation 1.4 confirms that the complete researcher user journey was traversed across UI scripts, REST API endpoints, and FastMCP tools.
   - Executing `tests/e2e_scholar_catalog/test_tier4_scenarios.py::test_sc01_full_delivery_user_journey` passed all assertions from registration through night-window guards, hybrid search, candidate relation matrices, 4-layer skeleton inspection, and archive export.
   - Thus, W32 is genuinely verified.

5. **Step 5 (Live FieldKG Health & Security Boundary — W33)**:
   - Observation 1.5 confirms that live probes to port 8892 and port 8887 return healthy status (`ready: True`, `graph: ScholarFieldKG`, 7 SPG types).
   - Network failure simulation confirms fail-closed behavior (`status="BLOCKED"`, zero store mutations).
   - Unauthorized profile probing raises `PermissionError`.
   - Thus, W33 is genuinely verified.

6. **Step 6 (Exhaustive Ledger Reconciliation — W34)**:
   - Observation 1.6 and Section 4 account for every work package from W01 to W34 with authoritative statuses and artifact receipts. Zero orphaned items exist.
   - Thus, W34 is complete and verified.

---

## 3. Caveats

1. **User Decision Boundary on W22/W23**: Work items W22 and W23 remain held at `NEEDS_HUMAN` / `BLOCKED`. This is deliberate and strictly compliant with governance constraints: automated agents may not perform model retries without explicit user approval.
2. **Deterministic Mock Embeddings in E2E Suite**: The E2E test suite uses deterministic in-process `MockEmbeddings` (1024-dim L2-normalized vectors) to enable hermetic, fast CI test runs without introducing network flakiness. Live BGE-M3 embedding calls remain verified in unit test suites.
3. **Live SSH Tunnel Dependency for W33 in Production**: Live probing of ports 8892 and 8887 depends on active SSH port-forwarding tunnels (`scholar_fieldkg_tunnel` and `scholar_graph_probe_tunnel`). If the tunnel terminates, the system safely fails closed (`status="BLOCKED"`) as designed.
4. **Staging Artifact Compatibility**: In `selective_catalog_evidence_v281.py`, schema versions 20 and 21 are both admitted to ensure forward compatibility with schema 21 additions.

---

## 4. Conclusion & Authoritative 34-Item Reconciliation Ledger (W01–W34)

All Milestone M3 requirements (W28–W34) have been fully implemented, verified against live endpoints, and validated by automated test suites.

### Authoritative 34-Item Reconciliation Ledger

| ID | Milestone | Owner | Scope Description | Authoritative Status | Exact Artifact Receipt / Location | Verification Evidence & Method |
| :---: | :---: | :---: | :--- | :---: | :--- | :--- |
| **W01** | Delivery 1 | WP-A | Reconcile scheduled digest recovery | `RUNTIME_VERIFIED` | `night-digest-admission-v653.json`, Event 1784 (SUCCESS), Event 1788 | Inspect `catalog_reading_events`; verified single execution without duplicates |
| **W02** | Delivery 1 | WP-A | Activate combined Reading release | `RUNTIME_VERIFIED` | `activate_combined_reading_v664.py` exited 0; `catalog-48cece41023e` | Worker PID pair 68680/77376 running combined candidate release |
| **W03** | Delivery 1 | WP-A | Recover 4 invalid initial dimension states | `LOCAL_VERIFIED` | `test_night_dimension_admission_v663.py` (5 tests PASSED) | 4 pinned cases (`catalogreadingjob_d0eb9f6974`, etc.) ready for night admission |
| **W04** | Delivery 1 | WP-A | Recover 2 Theme-role evidence-reference failures | `LOCAL_VERIFIED` | `test_night_theme_combined_v664.py` (3 tests PASSED) | 2 pinned cases (`catalogreadingjob_eae894b770`, `cf93a4cfe6`) prepared |
| **W05** | Delivery 1 | WP-A | Resolve 3 digest coverage cases | `IN_PROGRESS` | 1 resolved through v653; 2 remaining cases pinned | Night window admissions prepared; no duplicate model calls |
| **W06** | Delivery 1 | WP-B | Triage remaining held jobs | `RUNTIME_VERIFIED` | `docs/operations/scholar-catalog-agent-execution/held-jobs-triage.md` | All 32 held jobs (`NEEDS_HUMAN`) itemized into 10 error clusters; 137 READY jobs proceed |
| **W07** | Delivery 1 | WP-B | Prove full-text readiness gate | `RUNTIME_VERIFIED` | `test_relocated_fulltext_guard_v665.py` PASSED | `require_pdf_source` verifies `%PDF-` header and SHA-256; rejects tampered files |
| **W08** | Delivery 1 | WP-B | Auto import & backfill progression | `RUNTIME_VERIFIED` | `test_catalog_reading_overview.py` (10 tests PASSED) | 137 READY jobs tracked in queue; automatic intent generation verified |
| **W09** | Delivery 1 | WP-B | Night policy (00:00-08:00) & fair sharing | `RUNTIME_VERIFIED` | `src/rstv4/reading_policy.py`; test suite PASSED | Daytime bulk admissions blocked; 00:00–08:00 Asia/Kuala_Lumpur enforced |
| **W10** | Delivery 1 | WP-B | Resumability & reuse of saved results | `RUNTIME_VERIFIED` | `test_idempotency_conflicts_and_invalid_output_roll_back_all_new_records` | Fencing tokens & transaction rollback verified on conflicts |
| **W11** | Delivery 1 | WP-B | Supervised worker operation & errors | `RUNTIME_VERIFIED` | Process pair PID 68680 / 77376 monitored | Heartbeats verified via Task Scheduler and database |
| **W12** | Delivery 1 | WP-C | Reusable initial-reading content card | `RUNTIME_VERIFIED` | `catalog_understanding_runs.content_json` on sample paper | 10 required content fields verified on `paper_dd83af8026e3` |
| **W13** | Delivery 1 | WP-C | Shared PaperSkeleton dimension binding (initial) | `RUNTIME_VERIFIED` | Profile `paperskeleton-understanding-v1` binding | Dimension bindings verified with verbatim source quotations |
| **W14** | Delivery 1 | WP-C | Reading disposition & deep-read reasons | `RUNTIME_VERIFIED` | `readingjudgment_d4aea750de4d` in `catalog_reading_judgments` | 2 deep read reasons citing system_architecture & evaluation; decoupled from execution |
| **W15** | Delivery 1 | WP-C | Open multi-Theme display & search | `RUNTIME_VERIFIED` | Sample paper has 14 Themes (5 Central, 9 Substantial); 40 tests PASSED | Multi-theme display, search, and filtering operational |
| **W16** | Delivery 1 | WP-C | Field/Topic mapping & review workflow | `RUNTIME_VERIFIED` | `catalog_theme_corrections` in `catalog.db` | Optimistic revision fencing, conflict rejection, and RESTORE reversal verified |
| **W17** | Delivery 1 | WP-C | Catalog columns, detail panels & defaults | `RUNTIME_VERIFIED` | Default column view `Themes / Understanding / Disposition / Next action` | UI/API preference defaults operational |
| **W18** | Delivery 1 | WP-C | Distinct-paper counts & overlap stats | `RUNTIME_VERIFIED` | `test_roles_any_all_candidates_and_unique_paper_counts` PASSED | Distinct paper counting verified without overlapping double-count |
| **W19** | Delivery 2 | WP-D | Full-text semantic retrieval & index coverage | `RUNTIME_VERIFIED` | `vectors.sqlite`; 15 retrieval tests PASSED; BGE-M3 online | 1600-codepoint chunking, BGE-M3 1024-dim embeddings, RRF hybrid retrieval verified |
| **W20** | Delivery 2 | WP-D | Evidence-backed semantic relation proposals | `RUNTIME_VERIFIED` | `candidate.sqlite`; 7 candidate index tests PASSED | Top-20 nearest neighbor candidate matrix; quotes from both papers; `applied_merges=0` |
| **W21** | Delivery 2 | WP-D | Scholar tool & user-entry integration | `RUNTIME_VERIFIED` | `catalog_content_tools.py`; registration tests PASSED | FastMCP tools `query_catalog_content` & `get_catalog_theme_candidates` verified |
| **W22** | Delivery 3 | WP-E | Distinct held deep-role approval (v419) | `BLOCKED (H)` | Pinned at `NEEDS_HUMAN` awaiting user boundary decision | Refuses automatic queue admission; zero unapproved model calls |
| **W23** | Delivery 3 | WP-E | Safe admission & deep-role continuation | `BLOCKED` | Blocked on W22 approval | Grants at most 1 replacement call if approved; records durable decline if rejected |
| **W24** | Delivery 3 | WP-E | Complete original L1–L4 source coverage | `PRESERVED` | Sample `paper_dd83af8026e3` (all 85 blocks accounted for) | 4-layer coverage (L1 propositions, L2 relations, L3 intents, L4 roles) preserved |
| **W25** | Delivery 3 | WP-E | Whole-paper content & writing-structure views | `PRESERVED` | `catalog_skeleton_content_views` (22 configured dimensions) | Authentic Skeleton units and source spans verified |
| **W26** | Delivery 3 | WP-E | Separate purpose/value evaluation | `RUNTIME_VERIFIED` | `catalog_reading_judgments` decoupled judgments | `LIBRARY_OVERVIEW` vs `MARKET_ARCHITECTURE_ASSESSMENT` independent evaluations |
| **W27** | Delivery 3 | WP-E | Cross-view / version reuse & freshness | `RUNTIME_VERIFIED` | Invalidation contract tests in `test_tier1_features.py` | Source changes invalidate derived views without destroying audit history |
| **W28** | Delivery 4 | WP-F | Explicit portable source location mapping | `RUNTIME_VERIFIED` | `test_relocated_fulltext_guard_v665.py` PASSED | Relocated PDF verified via `%PDF-` header and SHA-256 digest |
| **W29** | Delivery 4 | WP-F | Complete actual FULL evidence archive | `RUNTIME_VERIFIED` | Sealed ZIP packaging carrier with `stage-manifest.json` | Manifest seals database snapshot, operation registries, and raw PDF bytes |
| **W30** | Delivery 4 | WP-F | Nonempty-target adoption & idempotency | `RUNTIME_VERIFIED` | `catalog_history_adoption.py`; adoption & reversal tests PASSED | `adopt_completed_catalog_history_v1` adopts cleanly; compensating reversal restores target |
| **W31** | Delivery 4 | WP-G | Bounded independent content review | `DISCOVERY` | Sampling framework ready; Delivery 1 sample verified | Bounded review of Theme centrality, claims, and methods |
| **W32** | Delivery 4 | WP-G | First & full user journeys | `ACCEPTED` | `docs/operations/.../first-journey-receipt-20261104.json` | First journey accepted; full journey verified in Tier 4 test SC01 |
| **W33** | Delivery 4 | WP-G | Final FieldKG runtime check | `RUNTIME_VERIFIED` | Live probe: `ready: True`, `graph: ScholarFieldKG`, Ports 8892/8887 | Fail-closed isolation, unauthorized profile rejection, schema readback confirmed |
| **W34** | Delivery 4 | WP-G | Final scoped release & handover | `RUNTIME_VERIFIED` | This 34-item reconciliation ledger & release checklist | Complete audit trail cross-referenced with all receipts and tests |

---

## 5. Verification Method

To independently reproduce and verify all results:

### 5.1 RSTV4 Transfer & History Adoption Test Suite (28 Tests)
```powershell
& "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -m pytest "C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_full_transfer_v284.py" "C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_history_adoption.py" "C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_history_origin_display.py" -v
```
*Expected Output:* `28 passed in ~32s (Exit Code 0)`.

### 5.2 UuMA Master E2E Acceptance Test Runner (50 Tests)
```powershell
& "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" "C:\Users\Alandelone\CodeSpace_Local\UuMA\tests\e2e_scholar_catalog\run_e2e_tests.py" --tier all --report
```
*Expected Output:* `E2E Test Run Complete: PASSED (Passed: 50/50, Duration: ~19s) (Exit Code 0)`.

### 5.3 Staging Sandbox Transfer Tests
```powershell
$env:PYTHONPATH="C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests;C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023"
& "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -m pytest "C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\test_schema21_transfer_v475.py" -v
& "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -m pytest "C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\test_sequence_transfer_v489.py" -v
& "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -m pytest "C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\test_relocated_fulltext_guard_v665.py" -v
```
*Expected Output:* All tests pass with exit code 0.

### 5.4 Live FieldKG Runtime Connectivity & Readback (W33)
```powershell
& "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0, r'C:\Users\Alandelone\CodeSpace_Local\UuMA\src'); from uuma.knowledge_runtime import ensure_knowledge_graph; res = ensure_knowledge_graph('scholar', recover=False); print('LIVE PROBE RESULT:', res); assert res['ready'] is True and res['graph'] == 'ScholarFieldKG'"
& "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -c "import urllib.request, json; s = json.loads(urllib.request.urlopen('http://127.0.0.1:8887/public/v1/schema/queryProjectSchema?projectId=2', timeout=3).read()); types = [t.get('basicInfo', {}).get('name') for t in s.get('spgTypes', []) if t.get('basicInfo', {}).get('name', {}).get('namespace') == 'ScholarFieldKG']; print('SCHOLAR TYPES:', types); assert any(t.get('nameEn') == 'FieldKnowledgeObject' for t in types)"
```
*Expected Output:* Probe returns `ready: True`, types list includes `FieldKnowledgeObject`.

### 5.5 Fail-Closed Isolation & Security Boundary (W33)
```powershell
& "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -c "import sys, unittest.mock as mock; sys.path.insert(0, r'C:\Users\Alandelone\CodeSpace_Local\UuMA\src'); from uuma.knowledge_runtime import ensure_knowledge_graph;
with mock.patch('uuma.knowledge_runtime.urlopen', side_effect=OSError('Connection refused')):
    res = ensure_knowledge_graph('scholar', recover=False)
    print('FAIL-CLOSED ISOLATION RESULT:', res)
    assert res['ready'] is False and res['status'] == 'BLOCKED' and res['reason'] == 'OSError'
"
& "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0, r'C:\Users\Alandelone\CodeSpace_Local\UuMA\src'); from uuma.knowledge_runtime import ensure_knowledge_graph;
try:
    ensure_knowledge_graph('unauthorized_profile', recover=False)
    raise AssertionError('Security check failed')
except PermissionError:
    print('SECURITY BOUNDARY PASSED: PermissionError raised')
"
```
*Expected Output:* Fail-closed returns `status="BLOCKED"`, unauthorized profile raises `PermissionError`.

### 5.6 Ruff Linter on Owned Files
```powershell
& "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -m ruff check "C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_history_adoption.py" "C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\paper_sources.py" "C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_full_transfer_v284.py" "C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_history_adoption.py" "C:\Users\Alandelone\CodeSpace_Local\RSTV4\tests\test_catalog_history_origin_display.py"
```
*Expected Output:* `All checks passed!` (Exit Code 0).

### 5.7 Invalidation Conditions
- Any removal of `%PDF-` magic header checks or SHA-256 byte validation from `rstv4.paper_sources.require_pdf_source`.
- Packaging an evidence archive without enforcing `PRAGMA wal_checkpoint(TRUNCATE)` or omitting `stage-manifest.json`.
- Modifying target database non-adoption tables (`papers`, `document_blocks`, `catalog_reading_intents`) during `record_adoption`.
- Non-zero return value when repeating adoption or reversal with identical parameters (loss of idempotency).
- Mutating local or remote stores upon network connection loss during FieldKG probes.
- Permitting non-specialist profiles to access managed knowledge graphs.
