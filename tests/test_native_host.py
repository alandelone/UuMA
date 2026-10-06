from __future__ import annotations

import io
import json
import struct

import pytest

from uuma.commerce_control import CommerceControlStore
from uuma.commerce_store import CommerceStore
from uuma.native_host.host import (
    MAX_MESSAGE_BYTES,
    NativeHost,
    NativeMessagingError,
    read_message,
    write_message,
)


def _pack(msg: dict) -> bytes:
    data = json.dumps(msg).encode("utf-8")
    return struct.pack("<I", len(data)) + data


def test_read_and_write_roundtrips_length_prefixed_messages():
    buf = io.BytesIO()
    test_msg = {"action": "ping", "request_id": "req_1"}
    write_message(test_msg, buf)

    buf.seek(0)
    read_back = read_message(buf)
    assert read_back == test_msg


def test_outbound_message_over_1mb_rejected():
    buf = io.BytesIO()
    huge_msg = {"huge": "x" * (MAX_MESSAGE_BYTES + 10)}
    with pytest.raises(NativeMessagingError, match="exceeds 1 MiB limit"):
        write_message(huge_msg, buf)


def test_native_host_origin_validation(tmp_path):
    control_store = CommerceControlStore(tmp_path / "control.db")
    commerce_store = CommerceStore(tmp_path / "lab.db", tmp_path / "archive")

    host = NativeHost(
        allowed_origin="chrome-extension://knldjmfmopnflpmmkcfjedmhhajpkgcl/",
        control_store=control_store,
        commerce_store=commerce_store,
    )

    # Valid origin
    res = host.handle_request({
        "action": "ping",
        "request_id": "req_val",
        "origin": "chrome-extension://knldjmfmopnflpmmkcfjedmhhajpkgcl",
    })
    assert res["success"] is True
    assert res["result"]["pong"] is True

    # Invalid origin
    res_bad = host.handle_request({
        "action": "ping",
        "request_id": "req_bad",
        "origin": "chrome-extension://malicious_extension_id",
    })
    assert res_bad["success"] is False
    assert "Unauthorized origin" in res_bad["error"]


def test_native_host_claim_and_renew_command(tmp_path):
    control_store = CommerceControlStore(tmp_path / "control.db")
    commerce_store = CommerceStore(tmp_path / "lab.db", tmp_path / "archive")

    control_store.create_task(platform="shopee", account_id="user_test")

    host = NativeHost(
        control_store=control_store,
        commerce_store=commerce_store,
    )

    # Claim command
    claim_res = host.handle_request({
        "action": "claim_command",
        "request_id": "req_claim",
        "payload": {"ttl_seconds": 60},
    })
    assert claim_res["success"] is True
    cmd = claim_res["result"]["command"]
    assert cmd["action"] == "EXTRACT"
    assert cmd["fencing_token"] == 1

    # Renew lease
    renew_res = host.handle_request({
        "action": "renew_lease",
        "request_id": "req_renew",
        "payload": {
            "task_id": cmd["task_id"],
            "lease_token": cmd["lease_token"],
            "fencing_token": cmd["fencing_token"],
            "ttl_seconds": 60,
        },
    })
    assert renew_res["success"] is True
    assert renew_res["result"]["task_id"] == cmd["task_id"]


def test_native_host_get_stored_order_ids_and_ingest_counts(tmp_path):
    control_store = CommerceControlStore(tmp_path / "control.db")
    commerce_store = CommerceStore(tmp_path / "lab.db", tmp_path / "archive")

    host = NativeHost(
        control_store=control_store,
        commerce_store=commerce_store,
    )

    # 1. Initially empty
    res_empty = host.handle_request({
        "action": "get_stored_order_ids",
        "request_id": "req_ids_1",
        "payload": {"platform": "shopee"},
    })
    assert res_empty["success"] is True
    assert res_empty["result"]["count"] == 0
    assert res_empty["result"]["order_ids"] == []

    # 2. Ingest first batch (2 orders)
    batch_1 = {
        "batch_id": "b_1",
        "platform": "shopee",
        "account_id": "user1",
        "orders": [
            {"order_id": "ord_101", "total_amount": 50.0, "status": "Completed", "items": [{"product_name": "Item A"}]},
            {"order_id": "ord_102", "total_amount": 30.0, "status": "Completed", "items": [{"product_name": "Item B"}]},
        ],
    }
    ingest_1 = host.handle_request({
        "action": "submit_batch",
        "request_id": "req_ingest_1",
        "payload": batch_1,
    })
    assert ingest_1["success"] is True
    assert ingest_1["result"]["new_orders_count"] == 2
    assert ingest_1["result"]["existing_orders_count"] == 0
    assert ingest_1["result"]["total_stored_orders"] == 2
    assert set(ingest_1["result"]["new_order_ids"]) == {"ord_101", "ord_102"}

    # 3. Query stored order IDs
    res_ids = host.handle_request({
        "action": "get_stored_order_ids",
        "request_id": "req_ids_2",
        "payload": {"platform": "shopee"},
    })
    assert res_ids["success"] is True
    assert res_ids["result"]["count"] == 2
    assert set(res_ids["result"]["order_ids"]) == {"ord_101", "ord_102"}

    # 4. Ingest second batch with 1 existing and 1 new order
    batch_2 = {
        "batch_id": "b_2",
        "platform": "shopee",
        "account_id": "user1",
        "orders": [
            {"order_id": "ord_101", "total_amount": 50.0, "status": "Completed", "items": [{"product_name": "Item A"}]},
            {"order_id": "ord_103", "total_amount": 90.0, "status": "Completed", "items": [{"product_name": "Item C"}]},
        ],
    }
    ingest_2 = host.handle_request({
        "action": "submit_batch",
        "request_id": "req_ingest_2",
        "payload": batch_2,
    })
    assert ingest_2["success"] is True
    assert ingest_2["result"]["new_orders_count"] == 1
    assert ingest_2["result"]["existing_orders_count"] == 1
    assert ingest_2["result"]["total_stored_orders"] == 3
    assert ingest_2["result"]["new_order_ids"] == ["ord_103"]

