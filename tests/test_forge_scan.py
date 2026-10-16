from pathlib import Path

from uuma.observatory.adapters.forge import ForgeAdapter


def test_forge_projects_scan():
    adapter = ForgeAdapter(Path("."))
    items = adapter.list_items(limit=50)
    print("Found items count:", len(items))
    for it in items:
        print(f"[{it.kind}] {it.item_id} | Status: {it.status} | Title: {it.title}")

    kinds = [it.kind for it in items]
    assert "forge_workspace" in kinds
    assert "forge_project" in kinds
    assert "forge_journal" in kinds
    assert "forge_commerce" in kinds

    # Check 5 projects
    project_items = [it for it in items if it.kind == "forge_project"]
    assert len(project_items) >= 5

    pids = [it.payload.get("project_id") for it in project_items]
    assert "ugv-rbcar-fertigation-sprayer" in pids
    assert "diy-nas-home-server" in pids
    assert "portable-iot-solar-tnc-report-system" in pids
    assert "trade-enabled-nanocentralised-ogpv-sares" in pids
    assert "portable-solar-cloud-capture-weather-tower" in pids

    # Check NO generic ACTIVE status
    for p in project_items:
        assert p.status != "ACTIVE"
        assert "progress_pct" in p.payload
        assert p.payload["progress_pct"] is not None
        assert "bom_count" in p.payload
        assert "procurement_trace" in p.payload

    # Check commerce engine health
    comm = next(it for it in items if it.kind == "forge_commerce")
    assert "engine_health" in comm.payload
    eh = comm.payload["engine_health"]
    assert "status_dot" in eh
    assert "channels" in eh
    assert "pdd" in eh["channels"]
    assert "shopee" in eh["channels"]
    assert "taobao" in eh["channels"]

    # Check workspace overview project breakdown
    ws = next(it for it in items if it.kind == "forge_workspace")
    assert "deployed_count" in ws.payload
    assert "progressing_count" in ws.payload
    assert ws.payload["project_count"] >= 5

    # Check forge journal sync time and runner status
    journ = next(it for it in items if it.kind == "forge_journal")
    assert "runner_status" in journ.payload
    assert "last_synced_at" in journ.payload
    assert journ.payload["last_synced_at"] is not None


