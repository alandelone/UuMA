from uuma.orbit_discovery import DiscoveryOutcome
from uuma.orbit_mcp_discovery import XhsMCPDiscoveryProvider


def test_xhs_search_results_are_leads_without_signed_tokens():
    result = XhsMCPDiscoveryProvider.parse_result({
        "status": "success", "job_id": "xhs-1", "results": [{
            "url": "https://www.rednote.com/discovery/item/n1?xsec_token=private",
            "note_id": "n1", "title": "Battery ageing experience", "description": "snippet",
        }],
    }, limit=2)
    assert result.artifacts[0].locator == "https://www.rednote.com/discovery/item/n1"
    assert result.artifacts[0].metadata["discovery_only"]
    assert "private" not in repr(result.artifacts)


def test_xhs_offline_does_not_replay_an_old_completed_job():
    result = XhsMCPDiscoveryProvider.parse_result({
        "status": "offline", "current_job": {"status": "success", "results": [
            {"url": "https://www.rednote.com/discovery/item/old", "title": "Old query"},
        ]},
    }, limit=2)
    assert not result.artifacts and result.outcome == DiscoveryOutcome.AUTH_REQUIRED


def test_xhs_pairing_and_job_polling_are_explicit():
    blocked = XhsMCPDiscoveryProvider.parse_result(
        {"status": "error", "stage": "extension_unpaired"}, limit=2,
    )
    assert blocked.outcome == DiscoveryOutcome.AUTH_REQUIRED
    pending = XhsMCPDiscoveryProvider.parse_result(
        {"status": "running", "job_id": "xhs-1"}, limit=2,
    )
    assert pending.in_progress and pending.request_id == "xhs-1"


def test_xhs_rejects_a_different_queries_cached_results():
    result = XhsMCPDiscoveryProvider.parse_result({
        "status": "success", "query": "old query", "results": [
            {"url": "https://www.rednote.com/discovery/item/old", "title": "Old query"},
        ],
    }, limit=2, query="new query")
    assert not result.artifacts and result.outcome == DiscoveryOutcome.TRANSIENT_FAILURE
