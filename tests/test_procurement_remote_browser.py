from __future__ import annotations

import pytest

from uuma import mcp_procurement, mcp_worker
from uuma.procurement_client import RemoteSourcingCrawlerEngine
from uuma.remote_mcp import ALLOWED, MODULES


def test_procurement_transport_only_authorizes_forge():
    assert MODULES["procurement"] == "uuma.mcp_procurement"
    assert ALLOWED["procurement"] == {"forge-lab-bot"}
    with pytest.raises(PermissionError):
        RemoteSourcingCrawlerEngine("http://127.0.0.1:8770/mcp/procurement", "honc", "token")


def test_server_crawler_factory_selects_remote_without_opening_browser(monkeypatch):
    sentinel = object()
    monkeypatch.setenv("UUMA_PROCUREMENT_MCP_URL", "http://127.0.0.1:8770/mcp/procurement")
    monkeypatch.setattr(RemoteSourcingCrawlerEngine, "from_env", lambda: sentinel)
    mcp_worker._crawler_engine.cache_clear()
    try:
        assert mcp_worker._crawler_engine() is sentinel
    finally:
        mcp_worker._crawler_engine.cache_clear()


def test_browser_search_does_not_move_procurement_store_to_workstation(monkeypatch):
    client = RemoteSourcingCrawlerEngine(
        "http://127.0.0.1:8770/mcp/procurement", "forge-lab-bot", "token",
    )
    calls = []

    def call(name, arguments):
        calls.append((name, arguments))
        return {"result": [{"unit_price": 2, "requirement_id": "req-1"}]}

    monkeypatch.setattr(client, "_call", call)

    class OwnerStore:
        def lookup_or_expand_terms(self, query):
            assert query == "resistor"
            return {"aliases": []}

        def get_requirement(self, requirement_id):
            assert requirement_id == "req-1"
            return {"requirement_id": requirement_id}

        def record_offers(self, offers):
            assert offers == [{"unit_price": 2, "requirement_id": "req-1"}]
            return [{"offer_id": "offer-1", **offers[0]}]

        def evaluate_sourcing(self, requirements):
            assert requirements == ["req-1"]
            return {"owner_evaluation": True}

    result = client.search_harvest_and_evaluate(
        "resistor", requirement_id="req-1", proc_store=OwnerStore(),
    )
    assert result["evaluation"] == {"owner_evaluation": True}
    assert result["harvested_offers_count"] == 1
    assert calls == [("procurement_search_and_harvest", {
        "query": "resistor", "platforms": None,
        "max_per_platform": 5, "requirement_id": "req-1",
    })]


def test_failed_remote_browser_does_not_fall_back_or_retry(monkeypatch):
    client = RemoteSourcingCrawlerEngine(
        "http://127.0.0.1:8770/mcp/procurement", "forge-lab-bot", "token",
    )
    calls = []

    def call(name, arguments):
        calls.append(name)
        raise RuntimeError("desktop_unavailable")

    monkeypatch.setattr(client, "_call", call)
    with pytest.raises(RuntimeError, match="desktop_unavailable"):
        client.search_and_harvest("resistor")
    assert calls == ["procurement_search_and_harvest"]


@pytest.mark.parametrize("identity", ["orchestrator", "wisdom-oldman", "", "honc"])
def test_workstation_browser_rejects_other_identities_before_browser(monkeypatch, identity):
    monkeypatch.setenv("UUMA_AGENT_ID", identity)
    monkeypatch.setattr(mcp_procurement, "_engine", lambda: pytest.fail("Browser must not open"))
    with pytest.raises(PermissionError):
        mcp_procurement.procurement_check_crawler_status()


@pytest.mark.parametrize("arguments", [
    {"query": ""}, {"query": "r", "max_per_platform": 51},
    {"query": "r", "platforms": ["https://example.com"]},
    {"query": "r", "platforms": []},
])
def test_workstation_browser_rejects_unbounded_or_arbitrary_operations(monkeypatch, arguments):
    monkeypatch.setenv("UUMA_AGENT_ID", "forge-lab-bot")
    monkeypatch.setattr(mcp_procurement, "_engine", lambda: pytest.fail("Browser must not open"))
    with pytest.raises(ValueError):
        mcp_procurement.procurement_search_and_harvest(**arguments)


def test_workstation_harvest_only_uses_browser_and_returns_offers(monkeypatch):
    monkeypatch.setenv("UUMA_AGENT_ID", "forge-lab-bot")

    class Browser:
        def search_and_harvest(self, query, **arguments):
            assert query == "resistor"
            assert arguments == {
                "platforms": ["1688"], "max_per_platform": 3,
                "requirement_id": "req-1",
            }
            return [{"unit_price": 2}]

    monkeypatch.setattr(mcp_procurement, "_engine", lambda: Browser())
    assert mcp_procurement.procurement_search_and_harvest(
        "resistor", ["1688"], 3, "req-1",
    ) == [{"unit_price": 2}]
