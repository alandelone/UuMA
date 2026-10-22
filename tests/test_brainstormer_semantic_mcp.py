import asyncio
import hashlib
import json

import pytest
from starlette.testclient import TestClient

from uuma import mcp_brainstormer
from uuma.auth import TokenRegistry
from uuma.brainstormer_state import BrainstormerError
from uuma.remote_mcp import create_app


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("UUMA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UUMA_AGENT_ID", "orchestrator")
    root = tmp_path / "brainstormer"
    (root / "projects" / "project").mkdir(parents=True)
    (root / "proposals").mkdir()
    (root / "projects/project/state.json").write_text(json.dumps({
        "project_id": "project", "revision": 4, "links": [], "history": [],
        "objects": {"topic": {"id": "topic", "kind": "topic", "title": "Existing idea",
                              "updated_at": "2026-10-21T00:00:00Z"}},
    }), encoding="utf-8")
    return tmp_path


def test_semantic_reads_preserve_data_and_never_create_control_db(data):
    def inventory():
        return {str(p.relative_to(data)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in data.rglob("*") if p.is_file()}

    before = inventory()
    assert mcp_brainstormer.brainstormer_get_context("project")["revision"] == 4
    assert len(mcp_brainstormer.brainstormer_search_topics("idea")) == 1
    assert mcp_brainstormer.brainstormer_get_decision_map("project")["project_id"] == "project"
    assert inventory() == before
    assert not (data / "uuma.db").exists()
    with pytest.raises(ValueError):
        mcp_brainstormer.brainstormer_search_topics("idea", limit=101)
    with pytest.raises(BrainstormerError, match="Invalid identifier"):
        mcp_brainstormer.brainstormer_get_context("../elsewhere")


def test_domain_owner_never_silently_initializes_empty_data(tmp_path, monkeypatch):
    root = tmp_path / "missing"
    monkeypatch.setenv("UUMA_DATA_DIR", str(root))
    monkeypatch.setenv("UUMA_AGENT_ID", "brainstormer")
    with pytest.raises(RuntimeError, match="unavailable"):
        mcp_brainstormer.brainstormer_get_context("project")
    assert not root.exists()


def test_only_read_tools_and_no_identity_spoofing(data, monkeypatch):
    tools = asyncio.run(mcp_brainstormer.mcp.list_tools())
    assert {t.name for t in tools} == {
        "brainstormer_get_context", "brainstormer_get_decision_map", "brainstormer_search_topics",
    }
    monkeypatch.setenv("UUMA_AGENT_ID", "honc")
    with pytest.raises(PermissionError):
        mcp_brainstormer.brainstormer_get_context("project")
    registry = TokenRegistry(data / "test-tokens.json")
    tokens = registry.initialize()
    with TestClient(create_app(registry, services=["brainstormer"])) as client:
        for identity, token in (("honc", tokens["honc"]),
                                ("brainstormer", tokens["honc"]), ("orchestrator", "wrong")):
            response = client.post("/brainstormer/", json={}, headers={
                "Authorization": "Bearer " + token, "X-Uuma-Identity": identity,
            })
            assert response.status_code == 403
