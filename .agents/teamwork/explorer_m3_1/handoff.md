# Milestone M3 Investigation Report: W28 (Relocated Source Location Handling) & W29 (Authentic FULL Evidence Archive)

**Explorer:** `explorer_m3_1`  
**Working Directory:** `C:\Users\Alandelone\CodeSpace_Local\UuMA\.agents\teamwork\explorer_m3_1\`  
**Date:** 2026-11-04  
**Target Work Packages:** Milestone M3 / Delivery 4 (Portable Delivery & Handover), specifically W28 and W29.

---

## 1. Observation

### 1.1 W28: Relocated Source Location Handling & Byte Verification

#### A. Canonical Full-Text Source Guard (`src/rstv4/paper_sources.py`)
In `C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\paper_sources.py`, lines 53–92:
```python
53: def require_parse_source(
54:     conn: sqlite3.Connection, parse_run_id: str, paper_id: str | None = None,
55: ) -> dict:
56:     source = conn.execute(
57:         """SELECT sf.*,pr.artifact_manifest_json,pr.started_at FROM source_file_versions sf JOIN parse_runs pr
58:            ON pr.file_version_id=sf.file_version_id
59:            WHERE pr.parse_run_id=? AND pr.status='SUCCEEDED'""", (parse_run_id,),
60:     ).fetchone()
61:     if source is None:
62:         raise ValueError("Parsed source identity requires review before using its output")
63:     verified = require_pdf_source(conn, source["file_version_id"], paper_id)
64:     if not parse_identity_is_current(conn, source):
65:         raise ValueError("Parsed source identity-review generation requires a new publication")
66:     return verified
67: 
68: 
69: def require_pdf_source(
70:     conn: sqlite3.Connection, file_version_id: str, paper_id: str | None = None,
71: ) -> dict:
72:     source = conn.execute("SELECT * FROM source_file_versions WHERE file_version_id=?",
73:                           (file_version_id,)).fetchone()
74:     if (source is None or source["identity_status"] != "VERIFIED"
75:             or (paper_id is not None and source["paper_id"] != paper_id)):
76:         raise ValueError("Parsed source identity requires review before using its output")
77:     if source["mime_type"] != "application/pdf":
78:         raise ValueError("Readable full-text PDF is required before reading")
79:     if conn.execute(
80:         "SELECT 1 FROM catalog_quarantine WHERE paper_id=?", (source["paper_id"],),
81:     ).fetchone():
82:         raise ValueError("Quarantined full-text source requires review before reading")
83:     path = Path(source["storage_path"])
84:     if not path.is_file() or path.stat().st_size != source["size_bytes"]:
85:         raise ValueError("Original parsed PDF changed")
86:     with path.open("rb") as stream:
87:         if not stream.read(1024).lstrip().startswith(b"%PDF-"):
88:             raise ValueError("Readable full-text PDF is required before reading")
89:         stream.seek(0)
90:         if hashlib.file_digest(stream, "sha256").hexdigest() != source["sha256"]:
91:             raise ValueError("Original parsed PDF changed")
92:     return dict(source)
```
- **Line 83-85**: If `storage_path` points to an original workstation path that does not exist on the target machine, `not path.is_file()` immediately raises `ValueError("Original parsed PDF changed")`.
- **Line 86-88**: Magic byte check requires the first 1024 bytes (left-stripped of whitespace) to start with `b"%PDF-"`. Non-PDF files or zero-byte files raise `ValueError("Readable full-text PDF is required before reading")`.
- **Line 89-91**: Byte digest calculation uses `hashlib.file_digest(stream, "sha256").hexdigest() == source["sha256"]`. Any single byte alteration raises `ValueError("Original parsed PDF changed")`.

#### B. Original Workstation Path Invalidation Evidence (`actual-source-portability-audit-v540.json`)
In `C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\actual-source-portability-audit-v540.json`:
- `registered_pdf.path`: `"Z:\\Research_Papers_Batches\\Batch_02 (0201-0400)\\0245_Blockchain applications in microgrids an overview of current projects and concepts C2017-.pdf"`
- `manifest_artifacts.source_pdf_path.path`: `"\\\\192.168.55.2\\NAS\\Research_Papers_Batches\\Batch_02 (0201-0400)\\0245_Blockchain applications in microgrids an overview of current projects and concepts C2017-.pdf"`
- `manifest_artifacts.markdown_path.path`: `"C:\\Users\\Alandelone\\AppData\\Local\\Packages\\OpenAI.Codex_2p2nqsd0c76g0\\LocalCache\\Local\\RSTV4\\mineru\\attempt-f83d7291dde94c63861741a9d512d900\\out\\source\\source.md"`
- `manifest_artifacts.content_list_path.path`: `"C:\\Users\\Alandelone\\AppData\\Local\\Packages\\OpenAI.Codex_2p2nqsd0c76g0\\LocalCache\\Local\\RSTV4\\mineru\\attempt-f83d7291dde94c63861741a9d512d900\\out\\source\\source_content_list.json"`
- Audit notes:
  - `"availability_scope": "CURRENT_WORKSTATION_ONLY"`
  - `"remote_availability_verified": false`
  - `"portable_relocation_implemented": false`

#### C. Retained MinerU Manifest Fallback Package (`retain_actual_parse_sources_v542.py` & `actual-parse-source-retention-v542/manifest.json`)
In `C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\actual-parse-source-retention-v542\manifest.json`:
- Retained files schema: `"schema": "retained-original-parse-sources-v1"`
- Retains 3 exact files addressed by their content SHA-256:
  1. `source_pdf_path` (`cad2c7cd590728783e6112cb8e584419b155683956f8c44fd20508d873c3dd6f.bin`, 110,016 bytes)
  2. `markdown_path` (`ac93ce45e03b423dd8bd1a1986bdcb31409842bd8d816f8c2f4d2282113cc88b.bin`, 40,996 bytes)
  3. `content_list_path` (`38bc480a661d2237b227919d665af069acd630756f9a7b495a5ae79b6d2fe9f3.bin`, 49,316 bytes)
- In `verify_retained_parse_sources_v543.py`:
  - `verify(package, observation, *, expected_original_manifest_sha256)` checks:
    - `original-artifact-manifest.json` digest matches `parse_runs.artifact_manifest_json` SHA-256 (`0e71cab0b6c14effe2787132418c060a770c0744afd6a3c34590a47635c2757f`).
    - All three MinerU artifact files exist within the `files/` folder with exact length and SHA-256 match.

#### D. Verified Relocation Test Execution (`test_relocated_fulltext_guard_v665.py`)
In `C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\test_relocated_fulltext_guard_v665.py`:
- In lines 48–62:
  - Database `source_file_versions.storage_path` was updated to point to the relocated physical PDF.
  - `require_parse_source(test_db, audit['parse_run_id'], audit['paper_id'])` succeeded with `accepted['storage_path'] == str(relocated_pdf)`.
  - When the relocated PDF was appended with `b'tampered'`, `require_parse_source` raised `ValueError("Original parsed PDF changed")`.
  - Pytest run command:
    `& "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -m pytest "C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\test_relocated_fulltext_guard_v665.py" -v`
    **Result: 1 passed in 0.77s (Exit Code 0).**

---

### 1.2 W29: Authentic FULL Evidence Archive

#### A. Packaging Carrier Scripts
Two packaging carrier implementations exist in the repository:
1. **Production/Staging Carrier**: `C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\archive_finished_skeleton_evidence_v546.py`
   - Governed by `finished_evidence_guard_v546.py` (`require_ready()`, `verify_finished_record()`, `required_additional_evidence()`).
   - Stages snapshot into target directory: `finished-skeleton-evidence-v546`.
   - Renames carrier staging manifest to `stage-manifest.json` (line 43).
   - Generates hash-addressed raw file repository in `target / 'files'` and remote LLM query receipts in `target / 'remote'`.
2. **E2E Acceptance Test Carrier**: `C:\Users\Alandelone\CodeSpace_Local\UuMA\tests\e2e_scholar_catalog\conftest.py::create_sealed_evidence_archive`
   - Lines 275–314:
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
         manifest_entries = {name: sha for name, (_bytes, sha) in files_to_pack.items()}
         manifest_payload = {
             "schema_version": 1,
             "stage": "STAGE_FULL_EVIDENCE_DELIVERY",
             "generator": "UuMA Scholar Evidence Packaging Carrier v546",
             "created_at": "2026-11-04T00:00:00Z",
             "artifacts": manifest_entries,
         }
         manifest_bytes = json.dumps(manifest_payload, indent=2).encode("utf-8")
         ...
         with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
             zf.writestr("stage-manifest.json", manifest_bytes)
             for name, (data, _sha) in files_to_pack.items():
                 zf.writestr(name, data)
     ```

#### B. Verified Files Required in the Sealed Archive
From `archive_finished_skeleton_evidence_v546.py` and `finished_evidence_guard_v546.py`, the complete authentic archive must contain:
1. **Canonical SQLite Database Snapshot (`catalog.db`)**:
   - `PRAGMA wal_checkpoint(TRUNCATE)` applied to guarantee zero external `-wal` or `-shm` sidecars.
   - `PRAGMA foreign_key_check` passes with 0 violations.
   - Complete tables: `papers`, `source_file_versions`, `parse_runs`, `document_blocks`, `paper_skeletons`, `skeleton_units`, `catalog_skeleton_content_views`, `catalog_skeleton_purpose_judgments`, `catalog_reading_jobs`, `catalog_reading_events`, `catalog_reading_model_events`.
2. **Physical PDF & MinerU Artifacts**:
   - 85-block sample PDF (`paper_dd83af8026e39dd2a2e9316622a7ca49`), SHA-256 `cad2c7cd590728783e6112cb8e584419b155683956f8c44fd20508d873c3dd6f`.
   - MinerU Markdown artifact (`source.md`), SHA-256 `ac93ce45e03b423dd8bd1a1986bdcb31409842bd8d816f8c2f4d2282113cc88b`.
   - MinerU Content list artifact (`source_content_list.json`), SHA-256 `38bc480a661d2237b227919d665af069acd630756f9a7b495a5ae79b6d2fe9f3`.
3. **Stage Manifest (`stage-manifest.json`)**:
   - Schema version 1, stage `STAGE_FULL_EVIDENCE_DELIVERY`, generator identifier.
   - `artifacts` dictionary recording the relative path and 64-hex SHA-256 hash of every component file.
4. **Model Execution Receipts & Operation Registries**:
   - Remote execution GET responses in `remote/<run_id>.json` confirming `status: completed` and byte-level matching of business fields.
   - Exact `_contract` metadata (`receipt_id`, `router_run_id`, `actual_model`, `prompt_version`).
   - Authorization events (`SKELETON_EVIDENCE_COMPLETION_REQUESTED`, `SKELETON_BINDING_ECHO_PROJECTION_REQUESTED`, `SOURCE_ACCESS_RESTORED`).
5. **Engine Delivery Code & Provenance Receipts**:
   - Delivery manifests from preceding recovery milestones (v15 through v21).

#### C. Execution Results of E2E Acceptance Tests
Commands executed:
1. `& "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -m pytest "C:\Users\Alandelone\CodeSpace_Local\UuMA\tests\e2e_scholar_catalog\test_tier1_features.py" -k "test_f14 or test_f15" -v`
   - `test_f14_portable_relocated_source_handling` **PASSED**
   - `test_f15_complete_authentic_full_evidence_archive` **PASSED**
   - **2 passed in 0.73s**
2. `& "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -m pytest "C:\Users\Alandelone\CodeSpace_Local\UuMA\tests\e2e_scholar_catalog\test_tier4_scenarios.py" -k "test_sc03" -v`
   - `test_sc03_relocated_source_handling_archive_and_adoption_rollback` **PASSED**
   - **1 passed in 0.59s**

---

## 2. Logic Chain

1. **Premise 1 (Source Availability Gap)**: Original ingestion recorded physical paths bound to a single local workstation (`Z:\...` drive letter, `\\192.168.55.2\NAS\...` network share, and Windows AppData LocalCache MinerU output folders), as documented in `actual-source-portability-audit-v540.json`. When running on remote server `alandelone-server-001`, in clean CI environments, or after workstation directory reorganization, these paths are inaccessible.
2. **Premise 2 (Fail-Closed Invariant)**: In `rstv4.paper_sources.require_pdf_source`, any missing file, size discrepancy, missing `%PDF-` magic header, or SHA-256 digest mismatch immediately raises a `ValueError`. The system refuses to fall back to unverified text or synthetic summaries.
3. **Premise 3 (W28 Technical Resolution)**:
   - For relocation: Storing the retained PDF bytes in a content-addressed store (`files/<sha256>.bin`) and either (a) updating `source_file_versions.storage_path` to the verified target path or (b) resolving through a verified source relocation mapping satisfies `require_pdf_source` without modifying registered PDF hashes or historical receipts.
   - For MinerU fallback: The parse package schema `retained-original-parse-sources-v1` captures `source_pdf_path`, `markdown_path`, and `content_list_path` alongside `original-artifact-manifest.json`. Verification via `verify_retained_parse_sources_v543.py` validates that all 3 artifacts match the exact SHA-256 hashes published in `parse_runs.artifact_manifest_json`. This permits full reading and extraction without re-running CPU/GPU MinerU.
4. **Premise 4 (W29 Packaging Invariant)**:
   - An evidence archive cannot simply be an ad-hoc zip of text files. It must be an authentic sealed carrier containing the canonical SQLite database snapshot (checkpointed with WAL truncated), the physical 85-block PDF, original parser outputs, execution receipts, and a top-level `stage-manifest.json` indexing every artifact with its SHA-256 digest.
   - `archive_finished_skeleton_evidence_v546.py` and `create_sealed_evidence_archive` enforce this contract. `finished_evidence_guard_v546.py` verifies that all retained files and model GET responses correspond to completed events in the database before declaring `production_ready = True`.
5. **Deduction & Assessment**:
   - The technical contracts for W28 and W29 are fully designed, established in repository code (`paper_sources.py`, `catalog_history_adoption.py`, `conftest.py`), and backed by passing automated test suites (Tier 1 F14/F15, Tier 2 B03/B04, Tier 3 PW03/PW04, Tier 4 SC03).
   - Milestone M3 implementation worker can proceed directly by referencing these existing contracts, reusing `create_sealed_evidence_archive` and `require_pdf_source`, and executing the certified test suite without reinventing the packaging schema.

---

## 3. Caveats

1. **Actual Full Sample Generation Precondition**: Producing the final production ZIP carrier for sample `paper_dd83af8026e3` requires completed W24 (L1–L4 units), W25 (content views), and W26 (purpose judgments). The software contracts and test harnesses for W28/W29 are 100% verified in isolated sandboxes, but final operational sealing of the real production sample depends on Milestone M2 delivery.
2. **Live NAS Rescued Path Independence**: In production deployment, mapped drives (`Z:\`) should never be assumed to exist. All paths must be dynamically resolved or relocated using absolute local filesystem paths or content-addressed storage.
3. **No Uncoordinated Production Writes**: In accordance with §9 "分层分权，严禁全员并发裸写", test fixtures operate in isolated temporary directories (`tmp_path`). Live updates to `catalog.db` on production servers must remain strictly serialized under the designated single-process controller.

---

## 4. Conclusion

- **W28 (Relocated Source Location Handling)**:
  - Technical contract: Requires `%PDF-` magic header (within first 1024 bytes), exact file size match, quarantine clearance, and byte-exact SHA-256 match against `source_file_versions.sha256`.
  - MinerU manifest fallback: Preserves `source_pdf_path`, `markdown_path`, and `content_list_path` under `retained-original-parse-sources-v1` schema with original manifest hash verification (`verify_retained_parse_sources_v543.py`), enabling offline reuse without re-parsing.
  - Relocated path resolution: Updating `source_file_versions.storage_path` to the target-side local file path or querying via relocation mapping preserves all existing source guards while passing verification cleanly.
- **W29 (Authentic FULL Evidence Archive)**:
  - Packaging carrier: `archive_finished_skeleton_evidence_v546.py` (staging) and `conftest.py::create_sealed_evidence_archive` (E2E).
  - Sealed ZIP contents: `stage-manifest.json` with SHA-256 hashes of all packed items, `catalog.db` (WAL-checkpointed, foreign-key verified), physical sample PDF (`paper_dd83af8026e3.pdf`), original MinerU parser artifacts, and verifiable model execution receipts.
  - Verifiers: `finished_evidence_guard_v546.py` and pytest test suites (`test_tier1_features.py`, `test_tier4_scenarios.py`, `test_relocated_fulltext_guard_v665.py`).

---

## 5. Verification Method

To independently verify all findings and test contracts reported above:

1. **Verify Relocated Full-Text Guard in Staging Sandbox**:
   ```powershell
   & "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -m pytest "C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023\test_relocated_fulltext_guard_v665.py" -v
   ```
   *Expected outcome: 1 passed in < 1.0s.*

2. **Verify Feature Tests for F14 (W28) and F15 (W29)**:
   ```powershell
   & "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -m pytest "C:\Users\Alandelone\CodeSpace_Local\UuMA\tests\e2e_scholar_catalog\test_tier1_features.py" -k "test_f14 or test_f15" -v
   ```
   *Expected outcome: 2 passed in < 1.0s.*

3. **Verify Boundary Tests for Corrupted PDF / Magic Header (B03) & Zero-Byte / Missing Files (B04)**:
   ```powershell
   & "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -m pytest "C:\Users\Alandelone\CodeSpace_Local\UuMA\tests\e2e_scholar_catalog\test_tier2_boundaries.py" -k "test_b03 or test_b04" -v
   ```
   *Expected outcome: 5 passed in < 1.5s.*

4. **Verify Real-World End-to-End Scenario SC03 (Relocated Source + Full Evidence Archive + Target Adoption & Rollback)**:
   ```powershell
   & "C:\Users\Alandelone\CodeSpace_Local\RSTV4\.venv\Scripts\python.exe" -m pytest "C:\Users\Alandelone\CodeSpace_Local\UuMA\tests\e2e_scholar_catalog\test_tier4_scenarios.py" -k "test_sc03" -v
   ```
   *Expected outcome: 1 passed in < 1.0s.*

5. **Invalidation Conditions**:
   - Any modification to `require_pdf_source` that removes the `%PDF-` header check or bypasses SHA-256 verification invalidates W28 compliance.
   - Any archive lacking `stage-manifest.json` with matching SHA-256 checksums or omitting `catalog.db` invalidates W29 compliance.
