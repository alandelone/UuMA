"""A2A SDK wire types over authenticated, administrator-bound endpoints."""

from __future__ import annotations

from .control_client import ControlClient, credential


def call(binding: dict, method: str, params: dict, request_id: str):
    identity, token = credential()
    if identity != "orchestrator":
        raise PermissionError("Execution dispatch requires the control identity")
    result = ControlClient(binding["endpoint"], identity, token).request(
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
