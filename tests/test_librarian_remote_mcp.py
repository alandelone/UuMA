import json
import os
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from uuma.auth import TokenRegistry
from uuma.remote_mcp import create_app


def test_authenticated_remote_reader_keeps_record_scopes_and_rejects_spoofing(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1] / "test-fixtures/librarian/archive"
    monkeypatch.setenv("UUMA_LIBRARIAN_ARCHIVE_ROOT", str(root))
    registry = TokenRegistry(tmp_path / "tokens.json")
    tokens = registry.initialize()
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "librarian_search_records", "arguments": {}}}

    def headers(identity, token):
        return {"Authorization": "Bearer " + token, "X-Uuma-Identity": identity,
                "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-03-26"}

    with TestClient(create_app(registry, services=["librarian"])) as client:
        permitted = client.post("/librarian/", json=payload, headers=headers("yonc", tokens["yonc"]))
        assert permitted.status_code == 200
        assert permitted.json()["result"]["structuredContent"]["total"] == 3
        librarian = client.post("/librarian/", json=payload,
                                headers=headers("librarian", tokens["librarian"]))
        assert librarian.status_code == 200
        assert librarian.json()["result"]["structuredContent"]["total"] == 3
        denied = client.post("/librarian/", json=payload, headers=headers("honc", tokens["honc"]))
        assert denied.status_code == 200
        assert denied.json()["result"]["structuredContent"]["total"] == 0
        spoof = client.post("/librarian/", json=payload, headers=headers("yonc", tokens["honc"]))
        assert spoof.status_code == 403
        payload["params"] = {"name": "librarian_read_record",
                             "arguments": {"record_id": "example-question", "version_id": "v1"}}
        denied_read = client.post("/librarian/", json=payload, headers=headers("honc", tokens["honc"]))
        assert denied_read.status_code == 200 and denied_read.json()["result"]["isError"]


def test_remote_proxy_uses_librarian_service_only_when_configured(monkeypatch):
    from uuma import mcp_librarian, remote_mcp

    calls = []
    monkeypatch.setenv("UUMA_REMOTE_MCP_URL", "http://127.0.0.1:8769")
    monkeypatch.setattr(remote_mcp, "run_stdio_proxy", lambda service: calls.append(service))
    mcp_librarian.main()
    assert calls == ["librarian"]


@pytest.mark.skipif(os.name != "posix", reason="Catalog publication requires POSIX")
def test_remote_mcp_reads_only_explicitly_published_versions(tmp_path, monkeypatch):
    from uuma.librarian_catalog_publish import publish_catalog

    fixture = Path(__file__).resolve().parents[1] / "test-fixtures/librarian/archive"
    catalog = json.loads((fixture / "catalog.json").read_text(encoding="utf-8"))
    versions = frozenset((r["record_id"], r["version_id"]) for r in catalog["records"])
    sources = {r["content_sha256"]: fixture / "objects" / r["content_sha256"][:2] / r["content_sha256"]
               for r in catalog["records"]}
    root = tmp_path / "published"
    root.mkdir(mode=0o700)
    with pytest.raises(PermissionError):
        publish_catalog(root, catalog, approved_versions=frozenset(), object_sources=sources,
                        expected_current_sha256=None)
    assert not (root / "catalog.json").exists()
    publish_catalog(root, catalog, approved_versions=versions, object_sources=sources,
                    expected_current_sha256=None)
    monkeypatch.setenv("UUMA_LIBRARIAN_ARCHIVE_ROOT", str(root))
    registry = TokenRegistry(tmp_path / "tokens.json")
    token = registry.initialize()["yonc"]
    headers = {"Authorization": "Bearer " + token, "X-Uuma-Identity": "yonc",
               "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-03-26"}
    payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
               "params": {"name": "librarian_read_record",
                          "arguments": {"record_id": "example-question", "version_id": "v1"}}}
    with TestClient(create_app(registry, services=["librarian"])) as client:
        response = client.post("/librarian/", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["result"]["structuredContent"]["content_verified"] is True
