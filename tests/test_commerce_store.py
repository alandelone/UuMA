from __future__ import annotations

import json
from pathlib import Path

import pytest

from uuma.commerce_store import CommerceStore


@pytest.fixture
def commerce_store(tmp_path):
    db_path = tmp_path / "test_lab.db"
    archive_dir = tmp_path / "commerce_archive"
    return CommerceStore(db_path, archive_dir)


def test_batch_ingestion_and_idempotent_replay(commerce_store):
    batch = {
        "batch_id": "batch_shopee_001",
        "task_id": "task_100",
        "platform": "shopee",
        "account_id": "user_my",
        "orders": [
            {
                "order_id": "ord_101",
                "status": "Completed",
                "total_amount": 150.50,
                "currency": "MYR",
                "items": [
                    {
                        "product_id": "p_01",
                        "sku_id": "sku_01_red",
                        "product_name": "ESP32-S3 Dev Board",
                        "variant_name": "N16R8",
                        "quantity": 2.0,
                        "unit_price": 45.0,
                        "line_total": 90.0,
                        "ai_category_suggestion": "electronics",
                        "ai_ownership_suggestion": "self",
                    },
                    {
                        "product_id": "p_02",
                        "sku_id": "sku_02_usb",
                        "product_name": "Type-C Cable",
                        "quantity": 3.0,
                        "unit_price": 20.16,
                        "line_total": 60.50,
                        "ai_category_suggestion": "consumable",
                        "ai_ownership_suggestion": "self",
                    },
                ],
            }
        ],
    }

    receipt = commerce_store.ingest_batch(batch)
    assert receipt["batch_id"] == "batch_shopee_001"
    assert receipt["receipt_status"] == "NEW_ACK"
    assert receipt["order_count"] == 1
    assert receipt["line_count"] == 2

    # Verify immutable archive file was written
    archive_file = Path(receipt["archive_path"])
    assert archive_file.exists()
    saved_data = json.loads(archive_file.read_text(encoding="utf-8"))
    assert saved_data["batch_id"] == "batch_shopee_001"

    # Idempotent replay: submitting the exact same batch returns EXISTING_ACK
    replay_receipt = commerce_store.ingest_batch(batch)
    assert replay_receipt["receipt_status"] == "EXISTING_ACK"
    assert replay_receipt["payload_hash"] == receipt["payload_hash"]


def test_batch_conflict_on_different_payload(commerce_store):
    batch1 = {
        "batch_id": "batch_conflict_001",
        "task_id": "task_101",
        "orders": [{"order_id": "ord_1", "total_amount": 10.0, "items": []}],
    }
    commerce_store.ingest_batch(batch1)

    # Same batch_id, different content
    batch2 = {
        "batch_id": "batch_conflict_001",
        "task_id": "task_101",
        "orders": [{"order_id": "ord_1", "total_amount": 20.0, "items": []}],
    }
    with pytest.raises(ValueError, match="already exists with a different payload hash"):
        commerce_store.ingest_batch(batch2)


def test_candidate_collision_flagged_for_identity_review(commerce_store):
    # Two identical items in the same order with identical product_id, sku_id, and variant
    batch = {
        "batch_id": "batch_collision_001",
        "task_id": "task_collision",
        "orders": [
            {
                "order_id": "ord_collision",
                "items": [
                    {
                        "product_id": "p_same",
                        "sku_id": "sku_same",
                        "product_name": "Sensor Mod",
                        "variant_name": "v1",
                        "quantity": 1.0,
                    },
                    {
                        "product_id": "p_same",
                        "sku_id": "sku_same",
                        "product_name": "Sensor Mod Duplicate",
                        "variant_name": "v1",
                        "quantity": 1.0,
                    },
                ],
            }
        ],
    }
    commerce_store.ingest_batch(batch)

    lines = commerce_store.list_order_lines(order_id="ord_collision")
    assert len(lines) == 2
    # The second duplicate candidate key should be marked pending_identity_review
    statuses = [l["review_status"] for l in lines]
    assert "pending_identity_review" in statuses
