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
