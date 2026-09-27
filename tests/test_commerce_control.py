from __future__ import annotations

import pytest

from uuma.commerce_control import CommerceControlStore


@pytest.fixture
def control_store(tmp_path):
    db_path = tmp_path / "test_uuma.db"
    return CommerceControlStore(db_path)


def test_create_task_and_get_status(control_store):
    task = control_store.create_task(
        platform="shopee",
        account_id="user_my_123",
        date_range_start="2026-01-01",
        date_range_end="2026-06-30",
        max_orders=50,
    )
    assert task["platform"] == "shopee"
    assert task["account_id"] == "user_my_123"
    assert task["status"] == "QUEUED"
    assert task["fencing_token"] == 0

    status = control_store.get_task_status(task["task_id"])
    assert status["task_id"] == task["task_id"]
    assert status["status"] == "QUEUED"
    assert status["max_orders"] == 50


def test_claim_command_advances_fencing_and_lease(control_store):
    task = control_store.create_task(platform="shopee", account_id="user_test")
    task_id = task["task_id"]

    cmd = control_store.claim_command("worker_1", ttl_seconds=60)
    assert cmd is not None
    assert cmd["task_id"] == task_id
    assert cmd["action"] == "EXTRACT"
    assert cmd["fencing_token"] == 1
    assert cmd["lease_token"].startswith("lease_")

    # Task status should now be RUNNING
    updated = control_store.get_task(task_id)
    assert updated["status"] == "RUNNING"
    assert updated["fencing_token"] == 1
    assert updated["active_lease_token"] == cmd["lease_token"]


def test_stale_fencing_token_rejected(control_store):
    task = control_store.create_task(platform="shopee", account_id="user_test")
    task_id = task["task_id"]
    cmd = control_store.claim_command("worker_1", ttl_seconds=60)

    # Try updating with stale fencing token 0
    with pytest.raises(PermissionError, match="Stale fencing token"):
        control_store.update_task_status(
            task_id, "PAUSED", fencing_token=0, lease_token=cmd["lease_token"]
        )


def test_renew_lease_success_and_expiry(control_store):
    task = control_store.create_task(platform="shopee", account_id="user_test")
    task_id = task["task_id"]
    cmd = control_store.claim_command("worker_1", ttl_seconds=10)

    renewed = control_store.renew_lease(
        task_id, cmd["lease_token"], cmd["fencing_token"], ttl_seconds=120
    )
    assert renewed["task_id"] == task_id
    assert renewed["fencing_token"] == 1

    # Wrong lease token should fail
    with pytest.raises(PermissionError, match="Invalid or expired lease token"):
        control_store.renew_lease(task_id, "wrong_lease_token", 1)


def test_report_checkpoint_persists_progress_and_status(control_store):
    task = control_store.create_task(platform="shopee", account_id="user_test")
    task_id = task["task_id"]
    cmd = control_store.claim_command("worker_1", ttl_seconds=60)

    checkpoint = {"page": 2, "orders_synced": 40}
    updated = control_store.report_checkpoint(
        task_id, cmd["lease_token"], cmd["fencing_token"], checkpoint, status="RUNNING"
    )
    assert updated["last_checkpoint"]["page"] == 2
    assert updated["last_checkpoint"]["orders_synced"] == 40


def test_pause_resume_cancel_flow(control_store):
    task = control_store.create_task(platform="shopee", account_id="user_test")
    task_id = task["task_id"]
    control_store.claim_command("worker_1")

    # Pause
    paused = control_store.pause_task(task_id, reason="Hold for review")
    assert paused["status"] == "PAUSED"

    # Resume
    resumed = control_store.resume_task(task_id)
    assert resumed["status"] == "RUNNING"

    # Cancel
    cancelled = control_store.cancel_task(task_id, reason="User abort")
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["active_lease_token"] is None
