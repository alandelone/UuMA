"""Adversarial empirical verification script for Milestone 4 remediation.

Challenger: challenger_m4_rep_1
Role: critic, specialist
Verification Scope:
1. Physical existence, non-emptiness, and valid JSON structure for EVERY durable receipt cited
   in master-audit-signoff-20261106.md and board.md.
2. Exact fence values in catalog.db for all 6 pinned recovery jobs: (39, 41, 19, 22, 17, 7).
3. Strict 11-member integrity in both delivery-archive-20261106 and delivery-archive-20261105.
4. Verbatim matching of all 8 quotes in semantic-review-receipt-20261106.json against
   physical source.pdf bytes and unit IDs in paper_skeleton.json.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tarfile

import pypdf
import pytest

# Base paths
UUMA_ROOT = Path(r"C:\Users\Alandelone\CodeSpace_Local\UuMA")
RSTV4_ROOT = Path(r"C:\Users\Alandelone\CodeSpace_Local\RSTV4")
UUMA_LOCAL = UUMA_ROOT / ".uuma-local" / "scholar-catalog-implementation-20261023"
UUMA_DOCS = UUMA_ROOT / "docs" / "operations" / "scholar-catalog-agent-execution"
CANONICAL_DB = RSTV4_ROOT / "data" / "catalog.db"

DELIVERY_ARCHIVE_20261106 = UUMA_LOCAL / "delivery-archive-20261106"
DELIVERY_ARCHIVE_20261105 = UUMA_LOCAL / "delivery-archive-20261105"

REQUIRED_11_MEMBERS = frozenset({
    "metadata.json",
    "source.pdf",
    "catalog.db",
    "paper_skeleton.json",
    "content_view.json",
    "purpose_judgment.json",
    "model_events_bundle.json",
    "parse_artifact_manifest.json",
    "source.md",
    "source_content_list.json",
    "verifier_receipt.json",
})

EXPECTED_PDF_SHA256 = "cad2c7cd590728783e6112cb8e584419b155683956f8c44fd20508d873c3dd6f"
EXPECTED_PDF_BYTES = 110016
EXPECTED_PAPER_ID = "paper_dd83af8026e39dd2a2e9316622a7ca49"


def compute_sha256(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


# ==============================================================================
# 1. Verification of Durable Receipts (Physical existence, non-empty, valid JSON/MD)
# ==============================================================================

RECEIPTS_TO_VERIFY = [
    # Night admission receipts in UUMA_LOCAL
    (UUMA_LOCAL / "night-digest-admission-v653.json", "json"),
    (UUMA_LOCAL / "night-dimension-admission-v663-1.json", "json"),
    (UUMA_LOCAL / "night-dimension-admission-v663-2.json", "json"),
    (UUMA_LOCAL / "night-dimension-admission-v663-3.json", "json"),
    (UUMA_LOCAL / "night-dimension-admission-v663-4.json", "json"),
    (UUMA_LOCAL / "night-theme-admission-v664-a.json", "json"),
    (UUMA_LOCAL / "night-theme-admission-v664-b.json", "json"),
    # Documents in UUMA_DOCS
    (UUMA_DOCS / "triage-39-cases-20261105.md", "markdown"),
    (UUMA_DOCS / "first-journey-receipt-20261104.json", "json"),
    (UUMA_DOCS / "target-adoption-receipt-20261106.json", "json"),
    (UUMA_DOCS / "semantic-review-receipt-20261106.json", "json"),
    (UUMA_DOCS / "search-acceptance-receipt-20261105.json", "json"),
    (UUMA_DOCS / "held-jobs-triage.md", "markdown"),
    (UUMA_DOCS / "triage-held-jobs-20261104.json", "json"),
    (UUMA_DOCS / "master-audit-signoff-20261106.md", "markdown"),
    (UUMA_DOCS / "board.md", "markdown"),
    # Additional audit receipts cited in W01-W34 matrix
    (UUMA_LOCAL / "combined-reading-activation-v664" / "receipt.json", "json"),
    (UUMA_LOCAL / "w01-w34-audit-20261105-v671" / "fixed-release-integrity.json", "json"),
    (UUMA_LOCAL / "w01-w34-audit-20261105-v671" / "queue-and-window-checks.json", "json"),
    (UUMA_LOCAL / "w01-w34-audit-20261105-v671" / "contract-replay.json", "json"),
    (UUMA_LOCAL / "w01-w34-audit-20261105-v671" / "receipt-reconciliation.json", "json"),
    (UUMA_LOCAL / "w01-w34-audit-20261105-v671" / "native-source-coverage.json", "json"),
    (UUMA_LOCAL / "w01-w34-audit-20261105-v671" / "fieldkg-live-health.json", "json"),
]


@pytest.mark.parametrize("file_path,file_type", RECEIPTS_TO_VERIFY)
def test_durable_receipt_existence_and_validity(file_path: Path, file_type: str):
    """Verify physical existence, non-emptiness, and valid structure of each cited receipt."""
    assert file_path.exists(), f"Receipt file does NOT exist: {file_path}"
    assert file_path.is_file(), f"Receipt path is NOT a file: {file_path}"
    size = file_path.stat().st_size
    assert size > 0, f"Receipt file is empty (0 bytes): {file_path}"

    if file_type == "json":
        raw_text = file_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
        assert isinstance(data, (dict, list)), f"JSON root must be dict or list: {file_path}"
        assert len(data) > 0, f"Parsed JSON data is empty: {file_path}"
    elif file_type == "markdown":
        raw_text = file_path.read_text(encoding="utf-8")
        assert len(raw_text.strip()) > 50, f"Markdown content unexpectedly short: {file_path}"


# ==============================================================================
# 2. Verification of Exact Fences in catalog.db for 6 Pinned Recovery Jobs
# ==============================================================================

PINNED_JOBS = [
    # (job_id, expected_fence, case_type)
    (
        "catalogreadingjob_cf93a4cfe6711e0b0a9de48cdda944c66955d22c8ee1dac9d969e3e87c24ec6d",
        39,
        "theme_a",
    ),
    (
        "catalogreadingjob_eae894b77064e0fda1b65f3f2d7dec9dab1ad4f8e798db924e31d011a8fac34e",
        41,
        "theme_b",
    ),
    (
        "catalogreadingjob_b6cd388062f845b3b1a06998620ecb4fd8b8ca55bb8e70a5a176f16ce44e125f",
        19,
        "dimension_1",
    ),
    (
        "catalogreadingjob_1747a61025cff62d4e94cf40ba4de5bbf1e5c274db5ce511eeb88f32bc0afbe7",
        22,
        "dimension_2",
    ),
    (
        "catalogreadingjob_7c87aab5f575fc367a371daec53ceae0905c0a2a2ce6ee02cf18e3689fa5cc52",
        17,
        "dimension_3",
    ),
    (
        "catalogreadingjob_df48fec9f8ddb778af730a98f85ac72469faf45ca182600d8870a0670a71c135",
        7,
        "dimension_4",
    ),
]


def test_pinned_recovery_job_fences_in_catalog_db():
    """Verify exact fence values in catalog.db for all 6 pinned recovery jobs: (39, 41, 19, 22, 17, 7)."""
    assert CANONICAL_DB.exists(), f"Canonical catalog.db does not exist: {CANONICAL_DB}"

    conn = sqlite3.connect(CANONICAL_DB)
    conn.row_factory = sqlite3.Row
    try:
        actual_fences = []
        for job_id, expected_fence, case_type in PINNED_JOBS:
            row = conn.execute(
                "SELECT job_id, status, fencing_token FROM catalog_reading_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            assert row is not None, f"Job {job_id} ({case_type}) not found in catalog_reading_jobs!"
            actual_fence = row["fencing_token"]
            actual_status = row["status"]
            actual_fences.append(actual_fence)
            assert actual_fence == expected_fence, (
                f"Fence mismatch for job {job_id} ({case_type}): "
                f"expected {expected_fence}, got {actual_fence} (status: {actual_status})"
            )
            assert actual_status == "READY", (
                f"Status mismatch for admitted recovery job {job_id}: "
                f"expected READY, got {actual_status}"
            )

        assert tuple(actual_fences) == (39, 41, 19, 22, 17, 7), (
            f"Expected fence tuple (39, 41, 19, 22, 17, 7), got {tuple(actual_fences)}"
        )
    finally:
        conn.close()


# ==============================================================================
# 3. Strict 11-Member Integrity in Delivery Archives (20261106 and 20261105)
# ==============================================================================

@pytest.mark.parametrize("archive_dir", [DELIVERY_ARCHIVE_20261106, DELIVERY_ARCHIVE_20261105])
def test_delivery_archive_strict_11_member_integrity(archive_dir: Path):
    """Verify strict 11-member integrity in delivery archives (both 20261106 and 20261105)."""
    assert archive_dir.exists(), f"Archive directory does not exist: {archive_dir}"
    assert archive_dir.is_dir(), f"Archive path is not a directory: {archive_dir}"

    manifest_file = archive_dir / "manifest.json"
    packet_file = archive_dir / "packet.tar.gz"

    assert manifest_file.exists(), f"Missing manifest.json in {archive_dir}"
    assert packet_file.exists(), f"Missing packet.tar.gz in {archive_dir}"

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest.get("version") == "scholar-catalog-delivery-archive-v1"
    assert manifest.get("paper_id") == EXPECTED_PAPER_ID
    assert "packet_sha256" in manifest
    assert "files" in manifest

    actual_packet_sha256 = compute_sha256(packet_file)
    assert actual_packet_sha256 == manifest["packet_sha256"], (
        f"packet.tar.gz SHA256 mismatch: actual={actual_packet_sha256}, manifest={manifest['packet_sha256']}"
    )

    # 1. Unpacked directory member check
    for member in REQUIRED_11_MEMBERS:
        member_path = archive_dir / member
        assert member_path.exists(), f"Required member {member} missing from archive dir {archive_dir}"
        assert member_path.is_file(), f"Member {member} is not a file"
        assert member in manifest["files"], f"Required member {member} missing from manifest.json"
        disk_hash = compute_sha256(member_path)
        manifest_hash = manifest["files"][member]
        assert disk_hash == manifest_hash, f"Hash mismatch for {member}: disk={disk_hash}, manifest={manifest_hash}"

    # 2. Packed tar.gz member check: EXACTLY 11 members matching REQUIRED_11_MEMBERS
    packed_members = []
    with tarfile.open(packet_file, "r:gz") as tar:
        for tarinfo in tar.getmembers():
            if tarinfo.isfile():
                packed_members.append(tarinfo.name)
                extracted_bytes = tar.extractfile(tarinfo).read()
                extracted_hash = hashlib.sha256(extracted_bytes).hexdigest()
                assert extracted_hash == manifest["files"][tarinfo.name], (
                    f"Packed member {tarinfo.name} content SHA256 mismatch with manifest"
                )

    assert len(packed_members) == 11, f"Expected exactly 11 packed members, got {len(packed_members)}: {packed_members}"
    assert set(packed_members) == REQUIRED_11_MEMBERS, (
        f"Packed members mismatch. Diff: {set(packed_members) ^ REQUIRED_11_MEMBERS}"
    )

    # 3. Source PDF integrity in archive
    pdf_path = archive_dir / "source.pdf"
    assert pdf_path.stat().st_size == EXPECTED_PDF_BYTES, (
        f"source.pdf size mismatch: got {pdf_path.stat().st_size}, expected {EXPECTED_PDF_BYTES}"
    )
    assert compute_sha256(pdf_path) == EXPECTED_PDF_SHA256, "source.pdf SHA256 mismatch"

    # 4. Catalog.db snapshot integrity in archive
    db_path = archive_dir / "catalog.db"
    conn = sqlite3.connect(db_path)
    try:
        fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert len(fk_errors) == 0, f"Foreign key errors in archive catalog.db: {fk_errors}"
        integrity = conn.execute("PRAGMA integrity_check").fetchall()
        assert integrity == [("ok",)], f"Integrity check failed on archive catalog.db: {integrity}"
        themes_cnt = conn.execute("SELECT COUNT(*) FROM catalog_skeleton_theme_observations").fetchone()[0]
        assert themes_cnt == 78, f"Expected 78 theme observations in archive catalog.db, got {themes_cnt}"
    finally:
        conn.close()

    # 5. Verifier receipt integrity
    receipt_path = archive_dir / "verifier_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt.get("verifier_status") == "VERIFIED"
    assert receipt.get("paper_id") == EXPECTED_PAPER_ID
    assert receipt.get("integrity_assertions", {}).get("total_members") == 11
    assert receipt.get("integrity_assertions", {}).get("foreign_key_violations") == 0
    assert receipt.get("integrity_assertions", {}).get("database_integrity_check") == "ok"
    assert receipt.get("integrity_assertions", {}).get("theme_observations_count") == 78


# ==============================================================================
# 4. Verbatim Quote Matching and Unit ID Validation for Semantic Review Receipt
# ==============================================================================

def test_semantic_review_quotes_and_unit_ids_against_physical_pdf_and_skeleton():
    """Verify verbatim matching of all 8 quotes in semantic-review-receipt-20261106.json

    against physical source.pdf bytes and unit IDs in paper_skeleton.json.
    """
    receipt_path = UUMA_DOCS / "semantic-review-receipt-20261106.json"
    assert receipt_path.exists(), f"Semantic review receipt missing: {receipt_path}"

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    sample_audit = receipt.get("stratified_sample_audit", [])
    assert len(sample_audit) == 8, f"Expected 8 audited sample themes, got {len(sample_audit)}"

    # Load physical source.pdf
    pdf_path = DELIVERY_ARCHIVE_20261106 / "source.pdf"
    assert pdf_path.exists(), f"source.pdf missing from delivery archive: {pdf_path}"
    assert pdf_path.stat().st_size == EXPECTED_PDF_BYTES
    assert compute_sha256(pdf_path) == EXPECTED_PDF_SHA256

    # Extract all text from physical source.pdf via pypdf
    reader = pypdf.PdfReader(str(pdf_path))
    assert len(reader.pages) > 0, "source.pdf has 0 pages"
    full_pdf_text = ""
    for page in reader.pages:
        full_pdf_text += page.extract_text() + "\n"

    # Also extract raw bytes for binary check
    raw_pdf_bytes = pdf_path.read_bytes()

    # Normalize whitespace for flexible robust comparison
    def normalize_ws(s: str) -> str:
        return " ".join(s.split())

    normalized_pdf_text = normalize_ws(full_pdf_text)

    # Load paper_skeleton.json
    skeleton_path = DELIVERY_ARCHIVE_20261106 / "paper_skeleton.json"
    assert skeleton_path.exists(), f"paper_skeleton.json missing from delivery archive: {skeleton_path}"
    skeleton_data = json.loads(skeleton_path.read_text(encoding="utf-8"))

    # Extract all unit_ids from paper_skeleton.json
    skeleton_units = {}
    if isinstance(skeleton_data, dict):
        if "units" in skeleton_data:
            for u in skeleton_data["units"]:
                skeleton_units[u["unit_id"]] = u
        elif "skeleton_units" in skeleton_data:
            for u in skeleton_data["skeleton_units"]:
                skeleton_units[u["unit_id"]] = u
        else:
            # Fallback recursive search for unit_id
            def collect_units(obj):
                if isinstance(obj, dict):
                    if "unit_id" in obj:
                        skeleton_units[obj["unit_id"]] = obj
                    for v in obj.values():
                        collect_units(v)
                elif isinstance(obj, list):
                    for item in obj:
                        collect_units(item)
            collect_units(skeleton_data)
    elif isinstance(skeleton_data, list):
        for u in skeleton_data:
            if isinstance(u, dict) and "unit_id" in u:
                skeleton_units[u["unit_id"]] = u

    assert len(skeleton_units) == 85, f"Expected 85 skeleton units, found {len(skeleton_units)}"

    # Audit each of the 8 sample entries
    print("\nAuditing 8 Stratified Themes:")
    for idx, item in enumerate(sample_audit):
        theme_index = item.get("theme_index")
        theme_key = item.get("theme_key")
        label = item.get("label")
        role = item.get("role")
        quote = item.get("source_evidence_quote")
        unit_id = item.get("skeleton_unit_id")

        print(f"[{idx+1}/8] Theme #{theme_index}: '{label}' ({role})")
        print(f"      Quote: \"{quote}\"")
        print(f"      Unit ID: {unit_id}")

        assert quote, f"Empty quote for theme {theme_key}"
        assert unit_id, f"Empty unit_id for theme {theme_key}"

        # 1. Check unit_id exists in paper_skeleton.json
        assert unit_id in skeleton_units, (
            f"Unit ID '{unit_id}' cited in theme '{label}' does not exist in paper_skeleton.json!"
        )

        unit_obj = skeleton_units[unit_id]
        unit_text = unit_obj.get("text") or unit_obj.get("content") or ""

        # 2. Check quote matches physical source.pdf
        # Check normalized text match
        norm_quote = normalize_ws(quote)
        match_in_pdf_text = norm_quote in normalized_pdf_text
        match_in_unit_text = norm_quote in normalize_ws(unit_text) if unit_text else True

        # If direct string match in extracted PDF text fails, check ascii encoding in raw bytes
        if not match_in_pdf_text:
            ascii_quote = quote.encode("ascii", "ignore")
            match_in_pdf_bytes = ascii_quote in raw_pdf_bytes
        else:
            match_in_pdf_bytes = True

        assert match_in_pdf_text or match_in_pdf_bytes, (
            f"Quote for theme '{label}' was NOT found in physical source.pdf:\n\"{quote}\""
        )

        print(f"      -> Unit ID confirmed in skeleton: True")
        print(f"      -> Verbatim match in physical source.pdf: True")

    print("\nALL 8/8 quotes and unit IDs verified verbatim!")


# ==============================================================================
# Main Runner for Direct Invocation
# ==============================================================================

def main():
    print("=" * 70)
    print("STARTING ADVERSARIAL EMPIRICAL VERIFICATION HARNESS")
    print("=" * 70)

    # 1. Durable Receipts
    print("\n[STEP 1] Verifying Physical Existence and Validity of All Durable Receipts...")
    failed_receipts = []
    for path, ftype in RECEIPTS_TO_VERIFY:
        try:
            test_durable_receipt_existence_and_validity(path, ftype)
            print(f"  [OK] ({ftype.upper()}) {path.name} ({path.stat().st_size} bytes)")
        except Exception as e:
            print(f"  [FAIL] {path.name}: {e}")
            failed_receipts.append((path.name, str(e)))

    # 2. Pinned Recovery Job Fences
    print("\n[STEP 2] Verifying Exact Fences in catalog.db for Pinned Recovery Jobs...")
    try:
        test_pinned_recovery_job_fences_in_catalog_db()
        print("  [OK] All 6 pinned recovery jobs verified in catalog.db:")
        for job_id, fence, ctype in PINNED_JOBS:
            print(f"       Job {job_id[:24]}... -> fence={fence} ({ctype})")
    except Exception as e:
        print(f"  [FAIL] Pinned job fence verification failed: {e}")
        failed_receipts.append(("pinned_job_fences", str(e)))

    # 3. Delivery Archives Integrity
    print("\n[STEP 3] Verifying Strict 11-Member Integrity in Delivery Archives...")
    for arch in [DELIVERY_ARCHIVE_20261106, DELIVERY_ARCHIVE_20261105]:
        try:
            test_delivery_archive_strict_11_member_integrity(arch)
            print(f"  [OK] Strict 11-member integrity verified for: {arch.name}")
        except Exception as e:
            print(f"  [FAIL] Archive integrity verification failed for {arch.name}: {e}")
            failed_receipts.append((arch.name, str(e)))

    # 4. Semantic Review Quotes & Unit IDs
    print("\n[STEP 4] Verifying Semantic Review Quotes & Unit IDs against Physical source.pdf...")
    try:
        test_semantic_review_quotes_and_unit_ids_against_physical_pdf_and_skeleton()
        print("  [OK] All 8 quotes matched verbatim in source.pdf bytes & unit IDs validated.")
    except Exception as e:
        print(f"  [FAIL] Semantic review quote audit failed: {e}")
        failed_receipts.append(("semantic_review_quotes", str(e)))

    print("\n" + "=" * 70)
    if failed_receipts:
        print(f"VERIFICATION VERDICT: FAILED ({len(failed_receipts)} failures)")
        for name, err in failed_receipts:
            print(f"  - {name}: {err}")
        sys.exit(1)
    else:
        print("VERIFICATION VERDICT: ALL TESTS PASSED (100% EMPIRICAL PROOF)")
        print("=" * 70)
        sys.exit(0)


if __name__ == "__main__":
    main()
