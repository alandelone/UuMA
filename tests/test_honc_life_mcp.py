import asyncio
import json
from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP

from uuma.honc.life_mcp import register_life_tools
from uuma.honc.life_service import LifeService
from uuma.honc.life_store import LifeStore
from uuma.honc.store import HoncStore


def setup_tools(tmp_path, grants=()):
    now = datetime(2026, 10, 13, 12, tzinfo=UTC)
    service = LifeService(
        LifeStore(HoncStore(tmp_path / "honc.db")),
        owner_id="fixture-owner",
        profile="honc",
        session_id="fixture-session",
        clock=lambda: now,
    )
    receipt = service.receive_user_message(
        adapter_id="fixture-adapter",
        source_event_id="message",
        raw_content="今天状态很好",
        received_at=now,
        granted_operations=grants,
    )
    bound = service.bind_source(receipt["source_ref"])
    server = FastMCP("fixture-honc-existing-server")
    register_life_tools(server, lambda: bound)
    return server, receipt, bound


def call(server, name, arguments):
    result = asyncio.run(server.call_tool(name, arguments))
    # FastMCP returns content plus structured output for a declared result model.
    return result[1]


def test_registered_tools_exclude_identity_ingestion_and_delivery_capabilities(tmp_path):
    server, _, _ = setup_tools(tmp_path)
    tools = asyncio.run(server.list_tools())
    assert {tool.name for tool in tools} == {
        "honc_get_life_context",
        "honc_configure_habit",
        "honc_update_life_settings",
        "honc_record_habit",
        "honc_record_body",
        "honc_save_diary",
        "honc_correct_life_record",
        "honc_get_life_operation",
        "honc_get_life_history",
        "honc_record_anchor",
    }
    encoded = json.dumps([tool.inputSchema for tool in tools])
    for forbidden in (
        "user_id",
        "owner_id",
        "source_ref",
        "adapter_id",
        "delivery_target",
        "database_path",
    ):
        assert forbidden not in encoded
    context = call(server, "honc_get_life_context", {})
    assert context["status"] == "READ_OK" and context["data"]["request_refs"] == {}


def test_mcp_write_returns_committed_receipt_and_replay_identity(tmp_path):
    server, receipt, service = setup_tools(tmp_path, ("record_body",))
    request = {
        "request_ref": receipt["request_refs"]["record_body"],
        "source_quote": "今天状态很好",
        "observations": [{"description": "今天状态很好"}],
    }
    first = call(server, "honc_record_body", {"request": request})
    second = call(server, "honc_record_body", {"request": request})
    assert first["status"] == "APPLIED" and second["status"] == "ALREADY_APPLIED"
    assert first["records"] == second["records"] and first["operation_id"] == second["operation_id"]
    lookup = call(server, "honc_get_life_operation", {"operation_id": first["operation_id"]})
    assert lookup["records"] == first["records"]
    assert (
        service.get_history(record_id=first["records"][0]["id"]).data["records"][0]["kind"]
        == "body"
    )


def test_mcp_does_not_create_grants_from_model_supplied_request_reference(tmp_path):
    server, _, _ = setup_tools(tmp_path)
    response = call(
        server,
        "honc_record_body",
        {
            "request": {
                "request_ref": "model-invented",
                "source_quote": "今天状态很好",
                "observations": [{"description": "今天状态很好"}],
            }
        },
    )
    assert response["status"] == "FAILED" and response["records"] == []
