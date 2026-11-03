import sqlite3

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from uuma.librarian_inventory_capture import capture_inventory_plan
from uuma.librarian_inventory_plan import plan_inventory


@pytest.fixture
def public_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=3072).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def test_grants_required_before_any_capture(tmp_path, public_key):
    root = tmp_path / "project"
    root.mkdir()
    (root / "a").write_text("one")
    plan = plan_inventory(root, "project")
    queue = tmp_path / "queue"
    with pytest.raises(ValueError, match="ungranted"):
        capture_inventory_plan(plan, queue, "device", "2026-10-31", public_key,
                               granted_sources=set())
    assert not queue.exists()


def test_real_encrypted_capture_and_partial_inventory(tmp_path, public_key):
    root = tmp_path / "project"
    root.mkdir()
    (root / "a").write_text("one")
    (root / "b").write_text("two")
    plan = plan_inventory(root, "project", shard_files=1)
    grants = {s["source_id"] for s in plan["shards"]}
    result = capture_inventory_plan(plan, tmp_path / "queue", "device", "2026-10-31",
                                    public_key, granted_sources=grants)
    assert result["capture_coverage"] == "COMPLETE_OBSERVED_INVENTORY"
    assert len(result["shards"]) == 2
    plan["inventory_status"] = "PARTIAL"
    assert capture_inventory_plan(plan, tmp_path / "queue", "device", "2026-10-31",
                                  public_key, granted_sources=grants)["capture_coverage"] == "PARTIAL"


def test_sqlite_wal_is_covered_by_online_snapshot(tmp_path, public_key):
    root = tmp_path / "project"
    root.mkdir()
    db = sqlite3.connect(root / "live.db")
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE test (value TEXT)")
        db.execute("INSERT INTO test VALUES ('current')")
        db.commit()
        plan = plan_inventory(root, "project", shard_files=1)
        result = capture_inventory_plan(plan, tmp_path / "queue", "device", "2026-10-31",
                                        public_key,
                                        granted_sources={s["source_id"] for s in plan["shards"]})
        assert result["capture_coverage"] == "COMPLETE_OBSERVED_INVENTORY"
        assert any(path.endswith("-wal") for path in result["sqlite_sidecars_covered_by_online_snapshot"])
    finally:
        db.close()


def test_path_escape_rejected_before_capture(tmp_path, public_key):
    root = tmp_path / "project"
    root.mkdir()
    (root / "a").write_text("one")
    plan = plan_inventory(root, "project")
    plan["shards"][0]["relative_paths"][0] = "../outside"
    with pytest.raises(ValueError, match="path"):
        capture_inventory_plan(plan, tmp_path / "queue", "device", "2026-10-31", public_key,
                               granted_sources={"project-p00001"})
    assert not (tmp_path / "queue").exists()


def test_failed_sqlite_snapshot_does_not_claim_sidecars(tmp_path, public_key):
    root = tmp_path / "project"
    root.mkdir()
    database = root / "live.db"
    database.write_bytes(b"SQLite format 3\x00" + b"invalid")
    (root / "live.db-wal").write_bytes(b"pending")
    plan = plan_inventory(root, "project")
    result = capture_inventory_plan(plan, tmp_path / "queue", "device", "2026-10-31", public_key,
                                    granted_sources={"project-p00001"})
    assert result["capture_coverage"] == "PARTIAL"
    assert result["sqlite_sidecars_covered_by_online_snapshot"] == []
    assert len(result["sqlite_sidecars_without_snapshot"]) == 1


def test_capture_delivers_each_shard_with_session_transport(tmp_path, public_key, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    (root / "a").write_text("one")
    (root / "b").write_text("two")
    plan = plan_inventory(root, "project", shard_files=1)
    calls = []

    def deliver(queue, batch_id, *, host, identity_file, use_sessions, bytes_per_second):
        calls.append((queue, batch_id, host, identity_file, use_sessions, bytes_per_second))
        return {"delivery_state": "DELIVERED"}

    monkeypatch.setattr("uuma.librarian_inventory_capture.deliver_queued_batch", deliver)
    key_path = tmp_path / "device-key"
    result = capture_inventory_plan(
        plan, tmp_path / "queue", "device", "2026-10-31", public_key,
        granted_sources={s["source_id"] for s in plan["shards"]},
        host="server", identity_file=key_path, bytes_per_second=262144,
    )
    assert len(calls) == 2
    assert all(call[2:] == ("server", key_path, True, 262144) for call in calls)
    assert all(shard["delivery"]["delivery_state"] == "DELIVERED" for shard in result["shards"])
