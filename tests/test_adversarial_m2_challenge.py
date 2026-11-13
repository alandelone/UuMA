"""Adversarial challenge and stress-test suite for Milestone M2 (Delivery 3: PaperSkeleton Deep Analysis).

Tests:
1. W22/W23: Fail-closed unauthorized submission, payload tampering, single-post attempt enforcement,
   and idempotency key handling on v419 recovery.
2. W24: 85-block coverage edge cases (gap detection, out-of-order sequence, non-existent block mapping,
   triplet join integrity, and foreign key enforcement).
3. W27: Freshness invalidation under byte mutations, magic byte corruption, and corrupted source hashes.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure UuMA, RSTV4, and .uuma-local scripts are importable
repo_root = Path(__file__).resolve().parents[1]
rstv4_root = repo_root.parent / "RSTV4"
uuma_local_v23 = repo_root / ".uuma-local" / "scholar-catalog-implementation-20261023"

for p in (repo_root / "src", rstv4_root / "src", uuma_local_v23):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import distinct_role_submit_once_v559
from rstv4.catalog_skeleton_views import require_parse_source, snapshot, view_history
from rstv4.paper_sources import require_pdf_source

CANONICAL_DB = rstv4_root / "data" / "catalog.db"
SAMPLE_PAPER = "paper_dd83af8026e39dd2a2e9316622a7ca49"
SAMPLE_SKEL = "skeleton_e87a79f2f1e6fc99acb67b4568757132"
SAMPLE_DEEP_JOB = "catalogdeepjob_8cf7ed4c1163eb1ac1ee4f5871af9780721529e21efc9bd995877735395340cc"
V419_VIEW_JOB = "skeletonviewjob_1216bde784964dc42990bbd92b55cd7431a23a60a43d94a05fe1bd58c6ec81e6"
V419_FAILED_CALL = "catalogdeepmodelcall_3098dded1bb69f1f48bc449897135f18eaa4bce2c2c86bd69324212650b6d96a"


@pytest.fixture
def isolated_db(tmp_path: Path):
    """Hermetic sandbox copy of the canonical catalog database."""
    if not CANONICAL_DB.exists():
        pytest.skip(f"Canonical catalog.db not found at {CANONICAL_DB}")
    sandbox_db = tmp_path / "catalog.db"
    shutil.copy2(CANONICAL_DB, sandbox_db)
    conn = sqlite3.connect(sandbox_db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn, sandbox_db
    conn.close()


@pytest.fixture
def isolated_pdf_sandbox(isolated_db, tmp_path: Path):
    """Hermetic sandbox with canonical catalog database and isolated PDF file copy."""
    conn, db_path = isolated_db
    row = conn.execute(
        """SELECT sf.storage_path, sf.sha256, sf.size_bytes, sf.file_version_id, pr.parse_run_id
           FROM source_file_versions sf JOIN parse_runs pr ON pr.file_version_id=sf.file_version_id
           WHERE sf.paper_id=?""",
        (SAMPLE_PAPER,),
    ).fetchone()
    if not row or not os.path.exists(row["storage_path"]):
        pytest.skip(f"Original source PDF for {SAMPLE_PAPER} not found on disk")
    
    pdf_copy = tmp_path / "source.pdf"
    shutil.copy2(row["storage_path"], pdf_copy)
    conn.execute(
        "UPDATE source_file_versions SET storage_path=? WHERE file_version_id=?",
        (str(pdf_copy), row["file_version_id"]),
    )
    conn.commit()
    yield conn, db_path, pdf_copy, dict(row)


# ==============================================================================
# SECTION 1: W22/W23 v419 Recovery Stress Tests
# ==============================================================================


def test_w22_unauthorized_pin_fails_closed_by_default():
    """Verify default DIRECT_HUMAN_APPROVAL_SHA256 is None and raises PermissionError."""
    assert distinct_role_submit_once_v559.DIRECT_HUMAN_APPROVAL_SHA256 is None
    with pytest.raises(PermissionError, match="Distinct direct human approval is not pinned"):
        distinct_role_submit_once_v559.submit_once()


@pytest.mark.parametrize(
    "invalid_pin",
    [
        12345678,
        "",
        "not-a-sha",
        "deadbeef" * 7,  # 56 chars, invalid length
        "g" * 64,         # 64 chars, invalid hex
        distinct_role_submit_once_v559.OLD_APPROVAL_SHA,  # Old consumed approval SHA
    ],
)
def test_w22_invalid_or_stale_approval_pin_fails_closed(invalid_pin):
    """Verify invalid pin formats and previous approval SHA fail closed with PermissionError."""
    with (
        patch.object(distinct_role_submit_once_v559, "DIRECT_HUMAN_APPROVAL_SHA256", invalid_pin),
        pytest.raises(PermissionError, match="Distinct direct human approval is not pinned"),
    ):
        distinct_role_submit_once_v559.submit_once()


def test_w22_approval_payload_and_evidence_tampering(tmp_path: Path):
    """Verify approval evidence tampering and scope deviations fail closed."""
    claim_dir = tmp_path / "approved-distinct-role-v419"
    claim_dir.mkdir(parents=True)
    approval_file = claim_dir / "human-approval.json"

    # Base valid structure matching exact scope
    valid_payload = {
        "scope": "distinct-role-v419",
        "job_id": distinct_role_submit_once_v559.JOB,
        "failed_call_id": distinct_role_submit_once_v559.FAILED,
        "expected_fencing_token": 211,
        "prompt_sha256": distinct_role_submit_once_v559.PROMPT_SHA,
        "maximum_additional_model_requests": 1,
        "channel": "thinking",
        "decision": "APPROVED",
        "human_reply_id": "fresh-valid-reply-001",
        "answer_verbatim": "Yes, approve exactly one replacement call.",
    }

    # Case 1: Pinned SHA does not match file bytes
    approval_file.write_text(json.dumps(valid_payload), encoding="utf-8")
    mismatched_sha = "0" * 64
    with (
        patch.object(distinct_role_submit_once_v559, "CLAIM_DIR", claim_dir),
        patch.object(distinct_role_submit_once_v559, "DIRECT_HUMAN_APPROVAL_SHA256", mismatched_sha),
        pytest.raises(PermissionError, match="Approval evidence does not match the direct human reply pin"),
    ):
        distinct_role_submit_once_v559.submit_once()

    # Case 2: Approval file payload tampered: maximum_additional_model_requests = 2
    tampered_payload = dict(valid_payload, maximum_additional_model_requests=2)
    raw = json.dumps(tampered_payload).encode("utf-8")
    approval_file.write_bytes(raw)
    pin = hashlib.sha256(raw).hexdigest()
    with (
        patch.object(distinct_role_submit_once_v559, "CLAIM_DIR", claim_dir),
        patch.object(distinct_role_submit_once_v559, "DIRECT_HUMAN_APPROVAL_SHA256", pin),
        pytest.raises(PermissionError, match="Approval differs from the exact distinct role proposal"),
    ):
        distinct_role_submit_once_v559.submit_once()

    # Case 3: Approval file payload tampered: decision = 'DECLINED'
    declined_payload = dict(valid_payload, decision="DECLINED")
    raw = json.dumps(declined_payload).encode("utf-8")
    approval_file.write_bytes(raw)
    pin = hashlib.sha256(raw).hexdigest()
    with (
        patch.object(distinct_role_submit_once_v559, "CLAIM_DIR", claim_dir),
        patch.object(distinct_role_submit_once_v559, "DIRECT_HUMAN_APPROVAL_SHA256", pin),
        pytest.raises(PermissionError, match="Approval differs from the exact distinct role proposal"),
    ):
        distinct_role_submit_once_v559.submit_once()


def test_w23_single_post_attempt_enforcement_and_idempotency(tmp_path: Path):
    """Verify single-post attempt enforcement (maximum_posts: 1) and repeated post prevention."""
    claim_dir = tmp_path / "approved-distinct-role-v419"
    claim_dir.mkdir(parents=True)
    approval_file = claim_dir / "human-approval.json"

    valid_payload = {
        "scope": "distinct-role-v419",
        "job_id": distinct_role_submit_once_v559.JOB,
        "failed_call_id": distinct_role_submit_once_v559.FAILED,
        "expected_fencing_token": 211,
        "prompt_sha256": distinct_role_submit_once_v559.PROMPT_SHA,
        "maximum_additional_model_requests": 1,
        "channel": "thinking",
        "decision": "APPROVED",
        "human_reply_id": "reply-user-auth-single-post-999",
        "answer_verbatim": "Approve single retry call.",
    }
    raw = json.dumps(valid_payload).encode("utf-8")
    approval_file.write_bytes(raw)
    pin = hashlib.sha256(raw).hexdigest()

    fake_operation_id = "rstv4-model-fake-operation-id-12345"
    mock_reserve = MagicMock(return_value={"status": "CLAIM_RESERVED_WITHOUT_AUTHORITY", "operation_id": fake_operation_id})

    # Pre-create single-post-attempt.json (simulating a prior run or crash)
    attempt_file = claim_dir / "single-post-attempt.json"
    attempt_file.write_text('{"maximum_posts": 1, "status": "PRIOR_ATTEMPT"}', encoding="utf-8")

    with (
        patch.object(distinct_role_submit_once_v559, "CLAIM_DIR", claim_dir),
        patch.object(distinct_role_submit_once_v559, "DIRECT_HUMAN_APPROVAL_SHA256", pin),
        patch.object(distinct_role_submit_once_v559, "reserve_once", mock_reserve),
        patch("urllib.request.urlopen") as mock_url,
    ):
        result = distinct_role_submit_once_v559.submit_once()
        # Verify reconciliation required and ZERO model posts issued
        assert result["status"] == "RECONCILIATION_REQUIRED"
        assert result["model_posts"] == 0
        mock_url.assert_not_called()


def test_w22_w23_canonical_held_state_verification(isolated_db):
    """Verify v419 recovery job in canonical catalog.db is pinned at NEEDS_HUMAN with zero unapproved calls."""
    conn, _ = isolated_db
    job = conn.execute(
        "SELECT job_id, status, fencing_token, last_error FROM catalog_reading_jobs WHERE job_id=?",
        (V419_VIEW_JOB,),
    ).fetchone()
    assert job is not None
    assert job["status"] == "NEEDS_HUMAN"
    assert job["fencing_token"] == 211
    assert job["last_error"] == "Model output is not a JSON object"

    # Verify the failed call has NO 'RETURNED' event
    failed_returned = conn.execute(
        "SELECT COUNT(*) FROM catalog_reading_model_events WHERE job_id=? AND call_id=? AND event_kind='RETURNED'",
        (V419_VIEW_JOB, V419_FAILED_CALL),
    ).fetchone()[0]
    assert failed_returned == 0

    # Verify the last model event for this job was event 1127 (WAITING_OR_FAILED) and zero events occurred after it
    latest_event = conn.execute(
        "SELECT event_seq, event_kind, call_id FROM catalog_reading_model_events WHERE job_id=? ORDER BY event_seq DESC LIMIT 1",
        (V419_VIEW_JOB,),
    ).fetchone()
    assert latest_event["event_seq"] == 1127
    assert latest_event["event_kind"] == "WAITING_OR_FAILED"
    assert latest_event["call_id"] == V419_FAILED_CALL


# ==============================================================================
# SECTION 2: W24 85-Block Coverage Edge Cases
# ==============================================================================


def test_w24_canonical_85_block_coverage_baseline(isolated_db):
    """Verify baseline sample paper has exactly 85 blocks, 85 units, 347 triplets, 340 checkpoints."""
    conn, _ = isolated_db
    units = conn.execute(
        "SELECT seq_idx, unit_id, layer4 FROM skeleton_units WHERE skeleton_id=? ORDER BY seq_idx",
        (SAMPLE_SKEL,),
    ).fetchall()
    assert len(units) == 85
    assert [u["seq_idx"] for u in units] == list(range(85))
    assert units[0]["layer4"] == "Front_Matter"
    assert units[-1]["layer4"] == "Global_Conclusion"

    triplet_count = conn.execute(
        "SELECT count(*) FROM skeleton_triplets st JOIN skeleton_units su ON st.unit_id=su.unit_id WHERE su.skeleton_id=?",
        (SAMPLE_SKEL,),
    ).fetchone()[0]
    assert triplet_count == 347

    checkpoints = conn.execute(
        "SELECT count(*), status FROM skeleton_checkpoints GROUP BY status"
    ).fetchall()
    assert (340, "SUCCEEDED") in [(r[0], r[1]) for r in checkpoints]

    # Baseline snapshot must succeed
    snap = snapshot(conn, SAMPLE_DEEP_JOB)
    assert len(snap["units"]) == 85
    assert snap["binding"]["skeleton_id"] == SAMPLE_SKEL


def test_w24_gap_detection_missing_unit_fails_closed(isolated_db):
    """Edge Case: Deleting a unit and its triplets causes snapshot() to detect coverage reduction."""
    conn, _ = isolated_db
    # First verify FK protects against direct unit deletion
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        conn.execute("DELETE FROM skeleton_units WHERE skeleton_id=? AND seq_idx=42", (SAMPLE_SKEL,))

    # When triplets are cleaned up and unit 42 is removed (leaving 84 units)
    u42 = conn.execute("SELECT unit_id FROM skeleton_units WHERE skeleton_id=? AND seq_idx=42", (SAMPLE_SKEL,)).fetchone()[0]
    conn.execute("DELETE FROM skeleton_triplets WHERE unit_id=?", (u42,))
    conn.execute("DELETE FROM skeleton_units WHERE unit_id=?", (u42,))
    conn.commit()

    with pytest.raises(ValueError, match="Published Skeleton unit coverage changed"):
        snapshot(conn, SAMPLE_DEEP_JOB)


def test_w24_gap_detection_missing_seq_idx_gap_fails_closed(isolated_db):
    """Edge Case: Renumbering a unit creates a sequence index gap (0..41, 43..85)."""
    conn, _ = isolated_db
    # Renumber unit 42 to 85 (creating gap at 42)
    conn.execute(
        "UPDATE skeleton_units SET seq_idx=85 WHERE skeleton_id=? AND seq_idx=42",
        (SAMPLE_SKEL,),
    )
    conn.commit()

    with pytest.raises(ValueError, match="Published Skeleton unit differs from the original located version"):
        snapshot(conn, SAMPLE_DEEP_JOB)


def test_w24_out_of_order_sequence_fails_closed(isolated_db):
    """Edge Case: Inverted / out-of-order sequence index between adjacent units."""
    conn, _ = isolated_db
    # Swap seq_idx of unit 10 and 11
    u10 = conn.execute("SELECT unit_id FROM skeleton_units WHERE skeleton_id=? AND seq_idx=10", (SAMPLE_SKEL,)).fetchone()[0]
    u11 = conn.execute("SELECT unit_id FROM skeleton_units WHERE skeleton_id=? AND seq_idx=11", (SAMPLE_SKEL,)).fetchone()[0]

    conn.execute("UPDATE skeleton_units SET seq_idx=999 WHERE unit_id=?", (u10,))
    conn.execute("UPDATE skeleton_units SET seq_idx=10 WHERE unit_id=?", (u11,))
    conn.execute("UPDATE skeleton_units SET seq_idx=11 WHERE unit_id=?", (u10,))
    conn.commit()

    with pytest.raises(ValueError, match="Published Skeleton unit differs from the original located version"):
        snapshot(conn, SAMPLE_DEEP_JOB)


def test_w24_non_existent_block_mapping_fails_closed(isolated_db):
    """Edge Case: Corrupting unit text/structure breaks alignment with block receipts."""
    conn, _ = isolated_db
    unit = conn.execute(
        "SELECT unit_id, raw_text FROM skeleton_units WHERE skeleton_id=? AND seq_idx=5",
        (SAMPLE_SKEL,),
    ).fetchone()

    # Mutate raw_text so it no longer matches original block receipt
    conn.execute(
        "UPDATE skeleton_units SET raw_text='Tampered text not in document_blocks' WHERE unit_id=?",
        (unit["unit_id"],),
    )
    conn.commit()

    with pytest.raises(ValueError, match="Published Skeleton unit differs from the original located version"):
        snapshot(conn, SAMPLE_DEEP_JOB)


def test_w24_triplet_join_integrity_and_fk_enforcement(isolated_db):
    """Edge Case: Triplet orphan prevention and Foreign Key constraint validation."""
    conn, _ = isolated_db

    # Baseline foreign key check
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    # Attempt inserting an orphan triplet referencing a non-existent unit_id
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        conn.execute(
            """INSERT INTO skeleton_triplets(triplet_id, unit_id, subject, predicate, object, content_digest)
               VALUES('orphan-triplet-999', 'nonexistent-unit-xyz', 'Subj', 'Pred', 'Obj', 'digest123')"""
        )

    # Attempt deleting a unit that has active triplets with FK enabled
    u0 = conn.execute("SELECT unit_id FROM skeleton_units WHERE skeleton_id=? AND seq_idx=0", (SAMPLE_SKEL,)).fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        conn.execute("DELETE FROM skeleton_units WHERE unit_id=?", (u0,))


# ==============================================================================
# SECTION 3: W27 Freshness Invalidation Under Mutations
# ==============================================================================


def test_w27_pdf_byte_mutation_invalidates_source(isolated_pdf_sandbox):
    """Verify modifying single PDF byte immediately invalidates require_pdf_source and require_parse_source."""
    conn, _, pdf_path, row = isolated_pdf_sandbox

    # Verify initial valid state
    source = require_pdf_source(conn, row["file_version_id"], SAMPLE_PAPER)
    assert source["sha256"] == row["sha256"]

    # Mutate 1 byte in the middle of the PDF
    original_bytes = pdf_path.read_bytes()
    mutated_bytes = bytearray(original_bytes)
    mutated_bytes[2000] = (mutated_bytes[2000] + 1) % 256
    pdf_path.write_bytes(mutated_bytes)

    with pytest.raises(ValueError, match="Original parsed PDF changed"):
        require_pdf_source(conn, row["file_version_id"], SAMPLE_PAPER)

    with pytest.raises(ValueError, match="Original parsed PDF changed"):
        require_parse_source(conn, row["parse_run_id"], SAMPLE_PAPER)

    # Restore original bytes: verification recovers cleanly
    pdf_path.write_bytes(original_bytes)
    recovered = require_pdf_source(conn, row["file_version_id"], SAMPLE_PAPER)
    assert recovered["sha256"] == row["sha256"]


def test_w27_pdf_magic_byte_corruption_invalidates_source(isolated_pdf_sandbox):
    """Verify corrupting %PDF- header magic bytes raises specific readable PDF error."""
    conn, _, pdf_path, row = isolated_pdf_sandbox
    original_bytes = pdf_path.read_bytes()

    # Corrupt header magic bytes
    corrupted_magic = b"NOTPDF" + original_bytes[6:]
    pdf_path.write_bytes(corrupted_magic)

    with pytest.raises(ValueError, match="Readable full-text PDF is required before reading"):
        require_pdf_source(conn, row["file_version_id"], SAMPLE_PAPER)

    # Restore original bytes
    pdf_path.write_bytes(original_bytes)


def test_w27_corrupted_source_hash_invalidates_source(isolated_pdf_sandbox):
    """Verify corrupting sha256 in source_file_versions causes immediate invalidation."""
    conn, _, _pdf_path, row = isolated_pdf_sandbox

    # Mutate sha256 in database
    conn.execute(
        "UPDATE source_file_versions SET sha256=? WHERE file_version_id=?",
        ("0" * 64, row["file_version_id"]),
    )
    conn.commit()

    with pytest.raises(ValueError, match="Original parsed PDF changed"):
        require_pdf_source(conn, row["file_version_id"], SAMPLE_PAPER)


def test_w27_cross_view_invalidation_preserves_immutable_history(isolated_pdf_sandbox):
    """Verify byte mutation invalidates request/view eligibility while preserving all historical records."""
    conn, _, pdf_path, _row = isolated_pdf_sandbox

    # Check baseline view history
    hist = view_history(conn, SAMPLE_PAPER)
    assert len(hist["requests"]) == 1
    req_before = hist["requests"][0]
    assert req_before["content_status"] == "NEEDS_HUMAN"
    assert req_before["content_eligible"] is True

    # Corrupt PDF bytes
    original_bytes = pdf_path.read_bytes()
    pdf_path.write_bytes(original_bytes[:5000])  # truncated bytes

    # Query view_history under corrupted source
    corrupted_hist = view_history(conn, SAMPLE_PAPER)
    # 1. Historical request records are NOT deleted
    assert len(corrupted_hist["requests"]) == len(hist["requests"])
    # 2. Content eligibility flips to False with error detail
    req_corrupted = corrupted_hist["requests"][0]
    assert req_corrupted["content_eligible"] is False
    assert "Original parsed PDF changed" in req_corrupted["content_detail"]

    # Restore original PDF bytes
    pdf_path.write_bytes(original_bytes)

    # Verification recovers cleanly
    restored_hist = view_history(conn, SAMPLE_PAPER)
    assert restored_hist["requests"][0]["content_eligible"] is True
