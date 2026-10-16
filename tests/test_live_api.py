from __future__ import annotations

import json
import urllib.request


def test_live_observatory_api():
    req = urllib.request.urlopen("http://127.0.0.1:8790/api/observatory/agents")
    assert req.status == 200
    data = json.loads(req.read().decode())

    forge = next(a for a in data["agents"] if a["agent_id"] == "forge-lab-bot")
    items = forge["items"]
    assert len(items) >= 8

    kinds = [it["kind"] for it in items]
    assert "forge_workspace" in kinds
    assert "forge_project" in kinds
    assert "forge_journal" in kinds
    assert "forge_commerce" in kinds

    # 5 hardware projects
    projects = [it for it in items if it["kind"] == "forge_project"]
    assert len(projects) == 5
    for p in projects:
        assert p["status"] != "ACTIVE"
        assert "progress_pct" in p["payload"]
        assert "bom_count" in p["payload"]
        print(
            f"Project: {p['title']} | Stage: {p['status']} "
            f"({p['payload']['progress_pct']}%) | BOM: {p['payload']['bom_count']}"
        )

    # Commerce
    commerce = next(it for it in items if it["kind"] == "forge_commerce")
    assert "status_breakdown" in commerce["payload"]
    assert commerce["payload"]["status_breakdown"]["in_transit"] == 11
    assert commerce["payload"]["status_breakdown"]["awaiting_dispatch"] == 148
    assert commerce["payload"]["status_breakdown"]["completed"] == 509

    # Journal
    journal = next(it for it in items if it["kind"] == "forge_journal")
    assert journal["payload"]["total_pages"] >= 29
    assert len(journal["payload"]["recent_journal_pages"]) > 0

    # Scholar
    scholar = next(a for a in data["agents"] if a["agent_id"] == "scholar")
    assert len(scholar["items"]) >= 3
    scholar_kinds = [it["kind"] for it in scholar["items"]]
    assert "research_hierarchy" in scholar_kinds
    assert "catalog_pipeline" in scholar_kinds
    assert "stage_progress" in scholar_kinds

    print("ALL LIVE OBSERVATORY API ASSERTIONS PASSED!")

