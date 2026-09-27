"""Chrome Native Messaging host protocol implementation."""

from __future__ import annotations

import json
import os
import struct
import sys
from typing import Any, BinaryIO

from uuma.commerce_control import CommerceControlStore
from uuma.commerce_store import CommerceStore

PROTOCOL_VERSION = "1.0"
MAX_MESSAGE_BYTES = 1024 * 1024  # 1 MiB Chrome Native Messaging limit
DEFAULT_ALLOWED_ORIGIN = "chrome-extension://knldjmfmopnflpmmkcfjedmhhajpkgcl/"


class NativeMessagingError(ValueError):
    pass


def read_message(stream: BinaryIO) -> dict[str, Any] | None:
    """Reads a 32-bit length-prefixed JSON message from the binary stream."""
    raw_length = stream.read(4)
    if not raw_length:
        return None
    if len(raw_length) < 4:
        raise NativeMessagingError(f"Incomplete length prefix: expected 4 bytes, got {len(raw_length)}.")

    (message_length,) = struct.unpack("<I", raw_length)
    if message_length == 0:
        return {}
    if message_length > MAX_MESSAGE_BYTES * 10:  # Allow inbound up to 10MB, outbound is capped at 1MB
        raise NativeMessagingError(f"Inbound message too large: {message_length} bytes.")

    raw_message = stream.read(message_length)
    if len(raw_message) < message_length:
        raise NativeMessagingError(
            f"Incomplete message body: expected {message_length} bytes, got {len(raw_message)}."
        )

    try:
        decoded = raw_message.decode("utf-8")
        return json.loads(decoded)
    except Exception as exc:
        raise NativeMessagingError(f"Failed to decode JSON message: {exc}") from exc


def write_message(message: dict[str, Any], stream: BinaryIO) -> None:
    """Writes a 32-bit length-prefixed JSON message to the binary stream, enforcing the 1 MiB limit."""
    serialized = json.dumps(message, ensure_ascii=False).encode("utf-8")
    if len(serialized) > MAX_MESSAGE_BYTES:
        raise NativeMessagingError(
            f"Outbound message exceeds 1 MiB limit: {len(serialized)} bytes > {MAX_MESSAGE_BYTES}."
        )

    length_prefix = struct.pack("<I", len(serialized))
    stream.write(length_prefix)
    stream.write(serialized)
    stream.flush()


class NativeHost:
    def __init__(
        self,
        in_stream: BinaryIO | None = None,
        out_stream: BinaryIO | None = None,
        allowed_origin: str | None = None,
        control_store: CommerceControlStore | None = None,
        commerce_store: CommerceStore | None = None,
    ):
        self.in_stream = in_stream or sys.stdin.buffer
        self.out_stream = out_stream or sys.stdout.buffer
        self.allowed_origin = allowed_origin or os.environ.get("UUMA_ALLOWED_ORIGIN", DEFAULT_ALLOWED_ORIGIN)
        self.control_store = control_store or CommerceControlStore()
        self.commerce_store = commerce_store or CommerceStore()
        self.worker_id = f"native_host_{os.getpid()}"

    def validate_origin(self, origin: str) -> bool:
        if not self.allowed_origin:
            return True
        return origin.strip().rstrip("/") == self.allowed_origin.strip().rstrip("/")

    def handle_request(self, req: dict[str, Any]) -> dict[str, Any]:
        req_id = req.get("request_id", "")
        action = str(req.get("action", "")).strip().lower()
        payload = req.get("payload", {})

        # Origin validation if supplied
        origin = req.get("origin")
        if origin and not self.validate_origin(origin):
            return {
                "protocol_version": PROTOCOL_VERSION,
                "request_id": req_id,
                "success": False,
                "error": f"Unauthorized origin: '{origin}'.",
            }

        try:
            if action == "ping":
                result = {"pong": True, "worker_id": self.worker_id}
            elif action == "claim_command":
                ttl = int(payload.get("ttl_seconds", 60))
                cmd = self.control_store.claim_command(self.worker_id, ttl_seconds=ttl)
                result = {"claimed": cmd is not None, "command": cmd}
            elif action == "renew_lease":
                task_id = payload["task_id"]
                lease_token = payload["lease_token"]
                fencing_token = int(payload["fencing_token"])
                ttl = int(payload.get("ttl_seconds", 60))
                result = self.control_store.renew_lease(
                    task_id, lease_token, fencing_token, ttl_seconds=ttl
                )
            elif action in {"submit_batch", "extract_orders"}:
                result = self.commerce_store.ingest_batch(payload)
            elif action == "report_checkpoint":
                task_id = payload["task_id"]
                lease_token = payload["lease_token"]
                fencing_token = int(payload["fencing_token"])
                checkpoint = payload.get("checkpoint", {})
                status = payload.get("status")
                result = self.control_store.report_checkpoint(
                    task_id, lease_token, fencing_token, checkpoint, status=status
                )
            elif action == "get_task_status":
                task_id = payload["task_id"]
                result = self.control_store.get_task_status(task_id)
            elif action in {"create_task", "start_task"}:
                platform = payload.get("platform", "shopee")
                account_id = payload.get("account_id", "default_user")
                max_orders = int(payload.get("max_orders", 100)) if payload.get("max_orders") else None
                task_id = payload.get("task_id")
                result = self.control_store.create_task(
                    platform=platform,
                    account_id=account_id,
                    max_orders=max_orders,
                    task_id=task_id,
                )
            else:
                return {
                    "protocol_version": PROTOCOL_VERSION,
                    "request_id": req_id,
                    "success": False,
                    "error": f"Unknown action: '{action}'.",
                }

            return {
                "protocol_version": PROTOCOL_VERSION,
                "request_id": req_id,
                "success": True,
                "result": result,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "protocol_version": PROTOCOL_VERSION,
                "request_id": req_id,
                "success": False,
                "error": str(exc),
            }

    def run_loop(self) -> None:
        """Processes messages sequentially until EOF on in_stream."""
        while True:
            try:
                msg = read_message(self.in_stream)
                if msg is None:
                    # Clean EOF
                    break
                response = self.handle_request(msg)
                write_message(response, self.out_stream)
            except (KeyboardInterrupt, SystemExit):
                break
            except Exception as exc:  # noqa: BLE001
                err_resp = {
                    "protocol_version": PROTOCOL_VERSION,
                    "success": False,
                    "error": str(exc),
                }
                try:
                    write_message(err_resp, self.out_stream)
                except Exception:  # noqa: BLE001
                    break
