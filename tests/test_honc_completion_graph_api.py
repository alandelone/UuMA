"""Exercise real Yonc API against an isolated database; never touch production tasks."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from uuma.honc.graph_client import GraphExecutionClient
from uuma.honc.life_context import LifeContextBroker
from uuma.honc.work_completion import WorkCompletion


def test_authenticated_host_ticks_real_graph_api_with_idempotent_receipt(tmp_path, monkeypatch):
    graph_root = Path(__file__).parents[2] / "yonc-graph"
    if not (graph_root / "graph_app/api.py").is_file():
        pytest.skip("Installed Yonc Graph source is needed for this integration test")
    monkeypatch.syspath_prepend(str(graph_root))
    from graph_app.api import create_app
    from graph_app.schema_v2 import ensure_v2_schema

    app = create_app(tmp_path / "graph.sqlite3")
    # Initialize only this test database. Do not enter frontend builder/watcher lifespan.
    engine = app.state.session_factory.kw["bind"]
    ensure_v2_schema(engine)
    api = TestClient(app)
    response = api.post(
        "/api/v2/nodes",
        json={
            "title": "隔离测试任务",
            "work_type": "ACTION",
            "done_when": "已完成指定测试",
            "stage": "EXECUTION",
            "status": "DOING",
        },
    )
    assert response.status_code == 201, response.text
    node_id = response.json()["node"]["id"]
    other = api.post(
        "/api/v2/nodes",
        json={
            "title": "保持未完成的任务",
            "work_type": "ACTION",
            "done_when": "保持不变",
            "stage": "EXECUTION",
            "status": "DOING",
        },
    ).json()["node"]
    health = api.get("/api/v2/health").json()
    http_requests = []

    def transport(request):
        http_requests.append((request.method, request.url.path))
        result = api.request(
            request.method, request.url.path, content=request.content, headers=dict(request.headers)
        )
        return httpx.Response(result.status_code, json=result.json())

    client = GraphExecutionClient(
        "http://isolated",
        database_id=health["database_id"],
        client=httpx.Client(transport=httpx.MockTransport(transport)),
    )
    root = Path(__file__).parents[1]
    plugin_path = root / "integrations/hermes/honc_life/__init__.py"
    spec = importlib.util.spec_from_file_location("isolated_honc_completion_host", plugin_path)
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    config = {
        "owner_id": "owner",
        "profile": "honc",
        "database_path": str(tmp_path / "honc.db"),
        "delivery_binding": {"platform": "telegram", "chat_id": "chat"},
    }
    broker = LifeContextBroker(config)
    monkeypatch.setattr(plugin, "_CONFIG", config)
    monkeypatch.setattr(plugin, "_BROKER", broker)
    monkeypatch.setattr(plugin, "_WORK", WorkCompletion(broker.store.ledger, client))
    monkeypatch.setattr(plugin, "_profile", lambda: "honc")
    env = {
        "HERMES_SESSION_USER_ID": "owner",
        "HERMES_SESSION_CHAT_ID": "chat",
        "HERMES_SESSION_PLATFORM": "telegram",
        "HERMES_SESSION_MESSAGE_ID": "1",
    }
    monkeypatch.setitem(
        sys.modules,
        "gateway.session_context",
        SimpleNamespace(get_session_env=lambda key: env.get(key, "")),
    )
    source = SimpleNamespace(
        profile="honc",
        chat_type="dm",
        user_id="owner",
        chat_id="chat",
        platform=SimpleNamespace(value="telegram"),
        is_bot=False,
    )
    gateway = SimpleNamespace(_is_user_authorized_for_source=lambda *a, **kw: True)
    event = SimpleNamespace(
        source=source, text="今天完成了隔离测试任务", message_id="1", internal=False
    )
    plugin._pre_gateway_dispatch(event=event, gateway=gateway)
    result = plugin._pre_llm_call(
        platform="telegram",
        session_id="s",
        turn_id="t",
        sender_id="owner",
        chat_id="chat",
        user_message=event.text,
    )
    context = json.loads(result["context"].split("\n", 1)[1])
    assert context["work_completion"]["status"] == "VERIFIED", context
    operation = context["work_completion"]["operation_id"]
    assert api.get(f"/api/v2/nodes/{node_id}").json()["status"] == "DONE"
    assert api.get(f"/api/v2/nodes/{other['id']}").json()["status"] == "DOING"
    receipt = api.get(f"/api/v2/execution/receipts/{operation}").json()["receipt"]
    assert receipt["action"] == "done" and not receipt["is_undone"]
    assert receipt["decision_origin"]["source_event_id"] == "telegram:chat:1"
    assert receipt["decision_origin"]["evidence_kind"] == "user_completion_report"
    reply = plugin._work_output(session_id="s", turn_id="t", response_text="untrusted model reply")
    assert "勾选完成" in reply and "读回确认" in reply
    plugin._close(session_id="s", turn_id="t")
    assert not plugin._WORK_RESULTS
    version = api.get("/api/v2/health").json()["graph_version"]
    replay = plugin._WORK.report(
        text=event.text, owner_id="owner", session_id="s", source_event_id="telegram:chat:1"
    )
    assert replay["graph_verified"]
    assert api.get("/api/v2/health").json()["graph_version"] == version
    assert sum(method == "POST" for method, path in http_requests) == 1
    assert (
        plugin._pre_tool_call(
            tool_name="mcp__honc_execution__honc_apply_completion",
            args={},
            session_id="s",
            turn_id="t",
        )["action"]
        == "block"
    )
    # A sender without the authenticated ingress proof cannot mark the other task done.
    source.user_id = "intruder"
    event.message_id, event.text = "2", "今天完成了保持未完成的任务"
    plugin._pre_gateway_dispatch(event=event, gateway=gateway)
    assert (
        plugin._pre_llm_call(
            platform="telegram",
            session_id="s",
            turn_id="u",
            sender_id="intruder",
            chat_id="chat",
            user_message=event.text,
        )
        is None
    )
    assert api.get(f"/api/v2/nodes/{other['id']}").json()["status"] == "DOING"
    api.close()
    engine.dispose()
