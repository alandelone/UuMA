from starlette.testclient import TestClient

from uuma.auth import TokenRegistry
from uuma.node_journal import NodeJournal
from uuma.workstation_node import create_app


def test_one_workstation_port_hosts_a2a_and_identity_scoped_desktop_mcp(tmp_path):
    tokens = TokenRegistry(tmp_path / "tokens.json")
    credentials = tokens.initialize()
    app = create_app(object(), NodeJournal(tmp_path / "node.db"), tokens, {})
    with TestClient(app) as client:
        assert client.get("/receipts").status_code == 403
        assert client.post("/mcp/chatgpt/", json={}).status_code == 403
        assert client.post("/mcp/xhs/", json={}).status_code == 403
        headers = {"Authorization": "Bearer " + credentials["orchestrator"]}
        assert client.get("/receipts", headers=headers).status_code == 200
        headers = {"Authorization": "Bearer " + credentials["brainstormer"]}
        assert client.post("/mcp/xhs/", headers=headers, json={}).status_code == 403


def test_brainstormer_chatgpt_tools_route_through_workstation_semantic_prefix(tmp_path, monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    from mcp.types import CallToolResult, TextContent, Tool

    from uuma import remote_mcp

    calls = []

    class Session:
        async def list_tools(self):
            return SimpleNamespace(tools=[Tool(
                name="chatgpt_status", description="Read consultation progress",
                inputSchema={"type": "object", "properties": {"request_id": {"type": "string"}}},
            )])

        async def call_tool(self, name, arguments):
            calls.append((remote_mcp.CALLER.get(), name, arguments))
            return CallToolResult(content=[TextContent(type="text", text='{"status":"QUEUED"}')])

    @asynccontextmanager
    async def owner_session(service):
        assert service == "chatgpt"
        assert remote_mcp.CALLER.get() == "brainstormer"
        yield Session()

    monkeypatch.setattr(remote_mcp, "owner_session", owner_session)
    tokens = TokenRegistry(tmp_path / "tokens.json")
    credentials = tokens.initialize()
    app = create_app(object(), NodeJournal(tmp_path / "node.db"), tokens, {})
    headers = {
        "Authorization": "Bearer " + credentials["brainstormer"],
        "X-Uuma-Identity": "brainstormer",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-06-18",
    }
    with TestClient(app) as client:
        response = client.post("/mcp/chatgpt/", headers=headers, json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {},
        })
        assert response.status_code == 200, response.text
        assert response.json()["result"]["tools"][0]["name"] == "chatgpt_status"
        response = client.post("/mcp/chatgpt/", headers=headers, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "chatgpt_status", "arguments": {"request_id": "existing"}},
        })
        assert response.status_code == 200, response.text
        assert response.json()["result"].get("isError", False) is False
        assert calls == [("brainstormer", "chatgpt_status", {"request_id": "existing"})]


def test_server_chatgpt_stdio_uses_remote_transport_without_local_browser_or_database(monkeypatch):
    from uuma import mcp_chatgpt, remote_mcp

    monkeypatch.setenv("UUMA_REMOTE_MCP_URL", "http://127.0.0.1:8770/mcp")
    observed = []
    monkeypatch.setattr(remote_mcp, "run_stdio_proxy", lambda service: observed.append(service))

    def forbidden(*args, **kwargs):
        raise AssertionError("Remote ChatGPT entry must not initialize a local browser or account DB")

    monkeypatch.setattr(mcp_chatgpt.BridgeStore, "authorize", forbidden)
    monkeypatch.setattr(mcp_chatgpt, "_start_local_bridge", forbidden)
    mcp_chatgpt.main()
    assert observed == ["chatgpt"]
