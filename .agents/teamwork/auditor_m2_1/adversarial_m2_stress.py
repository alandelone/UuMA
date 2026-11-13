"""Adversarial stress-testing of Milestone M2 assumptions and boundaries."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
import json
import pytest
from pathlib import Path

# Add RSTV4 src to path
RSTV4_SRC = Path(r"C:\Users\Alandelone\CodeSpace_Local\RSTV4\src")
if str(RSTV4_SRC) not in sys.path:
    sys.path.insert(0, str(RSTV4_SRC))

UUMA_IMPL = Path(r"C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-implementation-20261023")
if str(UUMA_IMPL) not in sys.path:
    sys.path.insert(0, str(UUMA_IMPL))

def test_v419_fail_closed_adversarial():
    print("--- Stress Test 1: v419 Submit-Once Fail-Closed Boundary ---")
    import distinct_role_submit_once_v559 as v559

    # Scenario 1: Default unpinned call must raise PermissionError
    try:
        v559.submit_once()
        print("  [FAIL] submit_once() did not raise PermissionError!")
        assert False
    except PermissionError as e:
        print(f"  [PASS] submit_once() raised PermissionError as expected: {e}")

    # Scenario 2: Attempting to bypass with old approval SHA
    old_pin = v559.DIRECT_HUMAN_APPROVAL_SHA256
    try:
        v559.DIRECT_HUMAN_APPROVAL_SHA256 = v559.OLD_APPROVAL_SHA
        try:
            v559.submit_once()
            print("  [FAIL] submit_once() with OLD_APPROVAL_SHA did not raise PermissionError!")
            assert False
        except PermissionError as e:
            print(f"  [PASS] submit_once() with OLD_APPROVAL_SHA raised PermissionError: {e}")
    finally:
        v559.DIRECT_HUMAN_APPROVAL_SHA256 = old_pin

    # Scenario 3: Attempting with random fake 64-char hex string
    try:
        v559.DIRECT_HUMAN_APPROVAL_SHA256 = "0" * 64
        try:
            v559.submit_once()
            print("  [FAIL] submit_once() with fake hex did not raise error!")
            assert False
        except (PermissionError, FileNotFoundError) as e:
            print(f"  [PASS] submit_once() with fake hex raised {type(e).__name__}: {e}")
    finally:
        v559.DIRECT_HUMAN_APPROVAL_SHA256 = old_pin

def test_snapshot_tamper_detection():
    print("\n--- Stress Test 2: snapshot() Tamper & Invalidation Detection ---")
    from rstv4.catalog_skeleton_views import snapshot

    db_path = Path(r"C:\Users\Alandelone\CodeSpace_Local\RSTV4\data\catalog.db")
    deep_job = "catalogdeepjob_8cf7ed4c1163eb1ac1ee4f5871af9780721529e21efc9bd995877735395340cc"

    # Connect read-only to real database
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    # Valid snapshot
    snap = snapshot(conn, deep_job)
    print(f"  [PASS] Valid snapshot returned {len(snap['units'])} units, digest={snap['source_digest'][:30]}...")

    # Scenario 1: Non-existent job
    try:
        snapshot(conn, "catalogdeepjob_non_existent")
        print("  [FAIL] Non-existent job did not raise ValueError!")
        assert False
    except ValueError as e:
        print(f"  [PASS] Non-existent job correctly raised ValueError: {e}")

    conn.close()

    # Scenario 2: Tampered unit in an in-memory clone of DB
    # Dump DB to memory and corrupt one unit
    disk_conn = sqlite3.connect(db_path)
    mem_conn = sqlite3.connect(":memory:")
    disk_conn.backup(mem_conn)
    disk_conn.close()
    mem_conn.row_factory = sqlite3.Row

    # Modify raw_text of unit 0
    mem_conn.execute("UPDATE skeleton_units SET raw_text='TAMPERED CONTENT' WHERE seq_idx=0")
    mem_conn.commit()

    try:
        snapshot(mem_conn, deep_job)
        print("  [FAIL] Tampered unit text did not raise ValueError!")
        assert False
    except ValueError as e:
        print(f"  [PASS] Tampered unit text correctly detected: {e}")

    # Scenario 3: Missing checkpoint
    # Restore unit 0, delete one checkpoint
    disk_conn = sqlite3.connect(db_path)
    mem_conn = sqlite3.connect(":memory:")
    disk_conn.backup(mem_conn)
    disk_conn.close()
    mem_conn.row_factory = sqlite3.Row

    mem_conn.execute("DELETE FROM skeleton_checkpoints WHERE checkpoint_id=(SELECT checkpoint_id FROM skeleton_checkpoints LIMIT 1)")
    mem_conn.commit()

    try:
        snapshot(mem_conn, deep_job)
        print("  [FAIL] Missing checkpoint did not raise ValueError!")
        assert False
    except ValueError as e:
        print(f"  [PASS] Missing checkpoint correctly detected: {e}")

    mem_conn.close()

def run_all_stress():
    test_v419_fail_closed_adversarial()
    test_snapshot_tamper_detection()
    print("\n=== ALL ADVERSARIAL STRESS TESTS COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    run_all_stress()
