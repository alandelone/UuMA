"""Protocol regression checks without model calls or saved user configuration."""

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import httpx
import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient


@pytest.fixture
def gateway(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    (tmp_path / "settings.json").write_text(
        json.dumps({"port": 18782, "models": {"gemini-3.8-flash": "Fixture"}}), encoding="utf-8"
    )
    monkeypatch.setenv("CODEX_AGY_STATE", str(tmp_path))
    source = Path(__file__).resolve().parents[1] / "integrations/codex_antigravity/gateway.py"
    spec = importlib.util.spec_from_file_location("_gateway_input_tools_fixture", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tool(name: str = "read") -> dict:
    return {
        "type": "function",
        "name": name,
        "description": "Read an isolated fixture",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
    }


def test_local_auth_needs_no_openai_account(gateway: ModuleType, tmp_path: Path) -> None:
    gateway.AUTH = tmp_path / "absent-openai-auth.json"
    credential = "fixture-local-credential-" + "x" * 32
    (gateway.STATE / "gateway-token").write_text(credential, encoding="utf-8")

    def request_with(host: str, token: str) -> Request:
        return Request(
            {
                "type": "http",
                "client": (host, 1234),
                "headers": [
                    (b"authorization", ("Bearer " + token).encode()),
                ],
            }
        )

    assert gateway.authenticate(request_with("127.0.0.1", credential)) == "local"
    for host, token in [("203.0.113.10", credential), ("127.0.0.1", "incorrect")]:
        with pytest.raises(HTTPException):
            gateway.authenticate(request_with(host, token))
    assert not gateway.AUTH.exists()


def test_local_credential_never_reaches_openai_and_quota_stays_enforced(
    gateway: ModuleType,
    tmp_path: Path,
) -> None:
    gateway.AUTH = tmp_path / "openai-auth.json"
    gateway.AUTH.write_text(
        json.dumps(
            {
                "tokens": {
                    "access_token": "fixture-openai-token",
                    "account_id": "fixture-account",
                }
            }
        ),
        encoding="utf-8",
    )
    credential = "fixture-local-credential-" + "x" * 32
    (gateway.STATE / "gateway-token").write_text(credential, encoding="utf-8")
    seen = []

    def official(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.headers["authorization"] == "Bearer fixture-openai-token"
        assert credential not in str(request.headers)
        return httpx.Response(
            429,
            stream=httpx.ByteStream(b'{"error":{"message":"fixture quota exhausted"}}'),
            headers={"content-type": "application/json"},
        )

    with TestClient(gateway.app, client=("127.0.0.1", 1234)) as client:
        gateway.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(official))
        response = client.post(
            "/v1/responses",
            headers={"Authorization": "Bearer " + credential},
            json={"model": "gpt-fixture", "input": "hi"},
        )
    assert len(seen) == 1
    assert response.status_code == 429
    assert response.json()["error"]["message"] == "fixture quota exhausted"


def test_local_auth_antigravity_route_succeeds_without_openai_file(
    gateway: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    gateway.AUTH = tmp_path / "missing-openai-auth.json"
    credential = "fixture-local-credential-" + "x" * 32
    (gateway.STATE / "gateway-token").write_text(credential, encoding="utf-8")

    async def completed(*args):
        yield b'event: response.completed\ndata: {"type":"response.completed"}\n\n'

    monkeypatch.setattr(gateway, "antigravity_stream", completed)
    with TestClient(gateway.app, client=("127.0.0.1", 1234)) as client:
        response = client.post(
            "/v1/responses",
            headers={"Authorization": "Bearer " + credential},
            json={"model": "antigravity/gemini-3.8-flash", "stream": True, "input": "hi"},
        )
        rejected = client.post(
            "/v1/responses",
            headers={"Authorization": "Bearer incorrect"},
            json={"model": "antigravity/gemini-3.8-flash", "stream": True, "input": "hi"},
        )
    assert response.status_code == 200
    assert rejected.status_code == 401
    assert not gateway.AUTH.exists()


def request() -> dict:
    return {
        "model": "antigravity/gemini-3.8-flash",
        "stream": True,
        "tools": [tool("existing")],
        "input": [
            {"role": "user", "content": "before loading"},
            {
                "type": "additional_tools",
                "role": "developer",
                "tools": [
                    {
                        "type": "namespace",
                        "name": "fixture",
                        "tools": [
                            tool(),
                            {
                                "type": "custom",
                                "name": "patch",
                                "format": {
                                    "type": "grammar",
                                    "syntax": "lark",
                                    "definition": "start: /.+/",
                                },
                            },
                        ],
                    },
                ],
            },
            {
                "type": "function_call",
                "namespace": "fixture",
                "name": "read",
                "call_id": "fixture-call",
                "arguments": '{"path":"fixture.txt"}',
            },
            {"type": "function_call_output", "call_id": "fixture-call", "output": "real-output"},
            {"role": "user", "content": "continue"},
        ],
    }


def test_desktop_unpaired_page_context_is_preserved_without_fake_calls(gateway: ModuleType) -> None:
    context = [
        {
            "type": "function_call_output",
            "id": "context-open",
            "name": "codex_apps_open_page",
            "namespace": None,
            "output": '{"page_id":null}',
        },
        {
            "type": "function_call_output",
            "id": "context-selected",
            "name": "codex_apps_selected_page_part_1_of_1",
            "output": "selected 文本",
        },
        {"role": "user", "content": "hi"},
    ]
    original = copy.deepcopy(context)
    payload, _ = gateway.translate({"model": "antigravity/gemini-3.8-flash", "input": context})
    assert context == original
    assert [m["role"] for m in payload["messages"]] == ["user", "user", "user"]
    assert not any(m.get("tool_calls") or m.get("tool_call_id") for m in payload["messages"])
    assert "untrusted data" in payload["messages"][0]["content"]
    for expected, message in zip(context[:2], payload["messages"][:2], strict=True):
        preserved = json.loads(message["content"].split("\n", 1)[1])
        assert preserved["name"] == expected["name"]
        assert preserved["output"] == expected["output"]


@pytest.mark.parametrize(
    "item",
    [
        {"type": "function_call", "name": "read", "arguments": "{}"},
        {"type": "function_call_output", "output": "unidentified"},
        {"type": "function_call_output", "name": "context"},
        {"type": "function_call_output", "call_id": 42, "output": "invalid"},
    ],
)
def test_missing_call_identity_is_not_fabricated(gateway: ModuleType, item: dict) -> None:
    with pytest.raises(ValueError):
        gateway.translate({"model": "antigravity/gemini-3.8-flash", "input": [item]})


def test_additional_tools_keep_schemas_namespaces_and_history(gateway: ModuleType) -> None:
    body = request()
    original = copy.deepcopy(body)
    payload, mapping = gateway.translate(body)
    assert body == original
    assert set(mapping) == {"existing", "fixture__read", "fixture__patch"}
    definitions = {t["function"]["name"]: t["function"] for t in payload["tools"]}
    assert definitions["fixture__read"]["parameters"] == tool()["parameters"]
    assert '"syntax": "lark"' in definitions["fixture__patch"]["description"]
    messages = payload["messages"]
    assert [m["role"] for m in messages] == ["user", "system", "assistant", "tool", "user"]
    assert "fixture__read" in messages[1]["content"]
    assert messages[2]["tool_calls"][0]["function"]["name"] == "fixture__read"
    assert messages[3]["content"] == "real-output"
    body["tool_choice"] = {"type": "custom", "namespace": "fixture", "name": "patch"}
    assert gateway.translate(body)[0]["tool_choice"]["function"]["name"] == "fixture__patch"


def test_replayed_identical_tools_deduplicate_but_conflicts_fail(gateway: ModuleType) -> None:
    body = request()
    body["input"].insert(1, {"type": "additional_tools", "tools": [tool("existing")]})
    assert len(gateway.translate(body)[0]["tools"]) == 3
    body["input"][1]["tools"][0]["parameters"] = {"type": "object", "properties": {}}
    with pytest.raises(ValueError, match="Ambiguous tool alias"):
        gateway.translate(body)


@pytest.mark.parametrize(
    "item",
    [
        {"type": "additional_tools", "role": "user", "tools": []},
        {"type": "additional_tools", "tools": {}},
        {"type": "additional_tools", "tools": [{"type": "unsupported_fixture"}]},
    ],
)
def test_invalid_additions_are_not_silently_dropped(gateway: ModuleType, item: dict) -> None:
    with pytest.raises(ValueError):
        gateway.translate({"model": "antigravity/gemini-3.8-flash", "input": [item]})


def test_response_route_accepts_added_tools_without_remote_execution(
    gateway: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = {}

    async def fixture_stream(_request, _body, payload, mapping):
        observed.update(payload=payload, mapping=mapping)
        yield b'event: response.completed\ndata: {"type":"response.completed"}\n\n'

    monkeypatch.setattr(gateway, "authenticate", lambda _request: None)
    monkeypatch.setattr(gateway, "antigravity_stream", fixture_stream)
    with TestClient(gateway.app) as client:
        response = client.post("/v1/responses", json=request())
    assert response.status_code == 200
    assert "response.completed" in response.text
    assert "fixture__read" in observed["mapping"]
