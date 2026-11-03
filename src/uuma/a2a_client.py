"""A2A SDK wire types over authenticated, administrator-bound endpoints."""

from __future__ import annotations

import json
import os
from urllib.parse import urlsplit

from .control_client import ControlClient, credential


def _transport_endpoint(endpoint: str) -> str:
    """Apply administrator-configured loopback SSH forwards, preserving agent paths."""
    configured = os.environ.get("UUMA_A2A_LOOPBACK_FORWARDS", "").strip()
    if not configured:
        return endpoint
    forwards = json.loads(configured)
    if not isinstance(forwards, dict) or len(forwards) > 16:
        raise ValueError("A2A loopback forwards must be an origin map")
    for origin, target in forwards.items():
        for value in (origin, target):
            if not isinstance(value, str):
                raise TypeError("A2A loopback origins must be strings")
            parsed = urlsplit(value)
            if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
                    or not parsed.port or parsed.username or parsed.password
                    or parsed.path or parsed.query or parsed.fragment):
                raise ValueError("A2A forwards require explicit HTTP loopback origins and ports")
    parsed = urlsplit(endpoint)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    target = forwards.get(origin)
    if target is None:
        return endpoint
    if parsed.query or parsed.fragment:
        raise ValueError("A2A endpoint cannot contain a query or fragment")
    return target + parsed.path


def call(binding: dict, method: str, params: dict, request_id: str):
    identity, token = credential()
    if identity != "orchestrator":
        raise PermissionError("Execution dispatch requires the control identity")
    result = ControlClient(_transport_endpoint(binding["endpoint"]), identity, token).request(
        "POST",
        "/rpc",
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        },
        extra_headers={"A2A-Version": "1.0"},
    )
    if "error" in result:
        raise RuntimeError(f"A2A request was rejected: {result['error'].get('code')}")
    return result["result"]


def send_run(binding: dict, run: dict):
    from a2a.types.a2a_pb2 import Message, Part, Role, SendMessageRequest
    from google.protobuf.json_format import MessageToDict

    epoch = int(run["execution_epoch"])
    message_id = f"uuma:{run['run_id']}:{epoch}"
    request = SendMessageRequest(
        message=Message(
            message_id=message_id,
            role=Role.ROLE_USER,
            parts=[Part(text="Execute the existing authorized UuMA contract")],
        ),
        metadata={"uuma_run_id": run["run_id"], "execution_epoch": epoch},
    )
    request.configuration.return_immediately = True
    return call(binding, "SendMessage", MessageToDict(request), message_id)


def send_knowledge_consultation(binding: dict, receipt: dict):
    """Dispatch only the server-registered Wisdom child with Brainstormer's identity."""
    from a2a.types.a2a_pb2 import Message, Part, Role, SendMessageRequest
    from google.protobuf.json_format import MessageToDict

    from .wisdom_consultation import CONTRACT_VERSION

    identity, token = credential()
    if (
        identity != "brainstormer" or binding.get("agent_id") != "wisdom-oldman"
        or receipt.get("contract_version") != CONTRACT_VERSION
        or receipt.get("requester") != identity
        or receipt.get("responder") != "wisdom-oldman"
    ):
        raise PermissionError("This path permits only a registered Brainstormer -> Wisdom question")
    epoch = int(receipt["execution_epoch"])
    message_id = f"uuma:{receipt['run_id']}:{epoch}"
    request = SendMessageRequest(
        message=Message(
            message_id=message_id, role=Role.ROLE_USER,
            parts=[Part(text="Answer the existing bounded Wisdom knowledge consultation")],
        ),
        metadata={"uuma_run_id": receipt["run_id"], "execution_epoch": epoch},
    )
    request.configuration.return_immediately = True
    result = ControlClient(binding["endpoint"], identity, token).request(
        "POST", "/rpc",
        {"jsonrpc": "2.0", "id": message_id, "method": "SendMessage",
         "params": MessageToDict(request)},
        extra_headers={"A2A-Version": "1.0"},
    )
    if "error" in result:
        raise RuntimeError(f"Consultation dispatch was rejected: {result['error'].get('code')}")
    return result["result"]
