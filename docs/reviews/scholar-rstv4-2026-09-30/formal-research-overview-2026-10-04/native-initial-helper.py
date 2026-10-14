"""Native HTTP acceptance against the owned isolated Catalog and Studio only."""
import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
path = repo / ".tmp/scholar-overview-native-v1.json"
if path.exists():
    raise RuntimeError("Preserve this exclusive mutation receipt")
subprocess.run(["powershell", "-NoProfile", "-Command", (repo / ".tmp/scholar-current-preview-proof.ps1").read_text(encoding="utf-8")], cwd=repo, check=True)
catalog_receipt = json.loads((repo / ".tmp/scholar-overview-services.json").read_text(encoding="utf-8"))
process_guard = r'''
$ErrorActionPreference = 'Stop'
$receipt = Get-Content -LiteralPath '.tmp/scholar-overview-services.json' -Raw | ConvertFrom-Json
$all = @(Get-CimInstance Win32_Process)
$root = $all | Where-Object ProcessId -eq ([int]$receipt.catalog_process)
if (!$root -or $root.CommandLine -notlike '*scholar-overview-server.py*--root*scholar-ui-fixes-2026-10-03-*--port 8885*') { throw 'Catalog root identity is unverified.' }
$owned = [System.Collections.Generic.List[int]]::new(); $owned.Add([int]$root.ProcessId)
do { $changed=$false; foreach($item in $all) { if($owned.Contains([int]$item.ParentProcessId) -and !$owned.Contains([int]$item.ProcessId)) { $owned.Add([int]$item.ProcessId); $changed=$true } } } while($changed)
$listeners = @(Get-NetTCPConnection -LocalPort 8885 -State Listen -ErrorAction SilentlyContinue)
if(!$listeners.Count) { throw 'Owned Catalog is not listening.' }
foreach($item in $listeners) { if(!$owned.Contains([int]$item.OwningProcess)) { throw 'Catalog port has another owner.' } }
Write-Output 'Isolated Catalog identity and listener verified.'
'''
subprocess.run(["powershell", "-NoProfile", "-Command", process_guard], cwd=repo, check=True)
sha = lambda raw: hashlib.sha256(raw).hexdigest()
canonical = lambda value: sha(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
proof = {"status": "STARTED", "browser_verified": False, "scientific_approval": False,
         "production_data_changed": False, "responses": [], "catalog_root": catalog_receipt["root"]}
def persist():
    path.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
persist()
with httpx.Client(base_url="http://127.0.0.1:8874/api", timeout=45) as studio, httpx.Client(base_url="http://127.0.0.1:8885", timeout=45) as catalog:
    def call(client, method, endpoint, expected=200, **kwargs):
        response = client.request(method, endpoint, **kwargs)
        body = response.json()
        proof["responses"].append({"server": "catalog" if client is catalog else "studio", "method": method,
                                   "path": endpoint, "status": response.status_code, "body": body})
        persist()
        assert response.status_code == expected, response.text[:1000]
        return body
    def metadata(operation, request_id, expected=200, **values):
        return call(catalog, "POST", "/api/catalog/research-actions", expected, json={"operation": operation, "request_id": request_id, **values})
    old_ms = ["manuscript_3a132decd09349b99b186a5c44dc191d", "manuscript_6d6a4ed3c59a40f08be2d7e68da63b11", "manuscript_d6725ffb3d7c43f9b4035f8c21f8f70b", "manuscript_cb7d936db4204d64a955b345d8eb8ce3", "manuscript_bd7568923be94a2c8510d176010e4cca"]
    before_workspaces = {ms: canonical(call(studio, "GET", f"/manuscripts/{ms}/workspace")) for ms in old_ms}
    response_ms = old_ms[-1]
    packages = call(studio, "GET", f"/manuscripts/{response_ms}/packages")
    assert len(packages) == 7
    old_zips = {}
    for item in packages:
        response = studio.get(f"/manuscripts/{response_ms}/packages/{item['package_id']}/download")
        assert response.status_code == 200
        old_zips[item["package_id"]] = sha(response.content)
    model_calls = call(studio, "GET", f"/manuscripts/{response_ms}/model-calls")
    original_overview = call(catalog, "GET", "/api/catalog/research-overview")
    page = catalog.get("/"); assert page.status_code == 200
    assert 'data-research-operation="' in page.text and 'id="overview-add-field"' in page.text
    assert 'disabled title="等待采集后端接入"' in page.text
    script = catalog.get("/catalog-research-overview.js"); assert script.status_code == 200
    assert script.content == (repo.parent / "RSTV4/src/rstv4/catalog_research_overview.js").read_bytes()
    assert sha(page.content) == sha((repo.parent / "RSTV4/src/rstv4/catalog_web.html").read_bytes())
    field = metadata("CREATE_FIELD", "overview-native-field-1", name="验收软件 Field A", description="Software fixture only")
    second = metadata("CREATE_FIELD", "overview-native-field-2", name="验收软件 Field B")
    topic = metadata("CREATE_TOPIC", "overview-native-topic-1", field_id=field["object_id"], name="验收软件共享 Topic")
    metadata("CREATE_TOPIC", "overview-native-topic-duplicate", 409, field_id=second["object_id"], name="验收软件共享 Topic")
    linked = metadata("LINK_TOPIC", "overview-native-topic-link", field_id=second["object_id"], topic_id=topic["object_id"])
    track_values = {"field_id": field["object_id"], "primary_topic_id": topic["object_id"], "title": "验收软件 Track A", "scope": "Software acceptance, no scientific claim", "research_type": "conceptual_framework"}
    track = metadata("CREATE_TRACK", "overview-native-track-1", **track_values)
    assert metadata("CREATE_TRACK", "overview-native-track-1", **track_values) == track
    track_b = metadata("CREATE_TRACK", "overview-native-track-2", **{**track_values, "field_id": second["object_id"], "title": "验收软件 Track B"})
    metadata("EDIT_TRACK", "overview-native-wrong-owner", 404, field_id=second["object_id"], track_id=track["object_id"], expected_digest=track["metadata_digest"], title="Wrong owner")
    saved = metadata("EDIT_FIELD", "overview-native-field-edit", field_id=field["object_id"], name="验收软件 Field A 已修改", description="Explicit metadata edit", expected_digest=field["metadata_digest"])
    metadata("EDIT_FIELD", "overview-native-field-stale", 409, field_id=field["object_id"], name="Stale overwrite", expected_digest=field["metadata_digest"])
    topic_edit = metadata("EDIT_TOPIC", "overview-native-topic-edit", field_id=second["object_id"], topic_id=topic["object_id"], name="验收软件共享 Topic 已修改", description="Shared metadata, independent Tracks", expected_digest=linked["metadata_digest"])
    track_edit = metadata("EDIT_TRACK", "overview-native-track-edit", field_id=field["object_id"], track_id=track["object_id"], title="验收软件 Track A 已修改", expected_digest=track["metadata_digest"])
    for name in track["object"].keys() - {"title", "updated_at"}:
        assert track_edit["object"][name] == track["object"][name]
    manuscript_ids = []
    for owner, title in [(track["object_id"], "软件稿件 A1"), (track["object_id"], "软件稿件 A2"), (track_b["object_id"], "软件稿件 B1")]:
        workspace = call(studio, "POST", "/manuscripts", 201, json={"track_id": owner, "title": title})
        ms = workspace["manuscript"]["manuscript_id"]; manuscript_ids.append(ms)
        assert workspace["manuscript"]["track_id"] == owner
        opened = call(studio, "GET", f"/manuscripts/{ms}/workspace")
        assert opened["manuscript"]["manuscript_id"] == ms and opened["manuscript"]["track_id"] == owner
    latest = call(catalog, "GET", "/api/catalog/research-overview")
    assert len([t for t in latest["topics"] if t["topic_id"] == topic["object_id"]]) == 1
    assert len([l for l in latest["field_topics"] if l["topic_id"] == topic["object_id"]]) == 2
    assert next(f for f in latest["fields"] if f["field_id"] == field["object_id"])["metadata_digest"] == saved["metadata_digest"]
    assert next(t for t in latest["topics"] if t["topic_id"] == topic["object_id"])["metadata_digest"] == topic_edit["metadata_digest"]
    assert {ms["manuscript_id"] for ms in latest["manuscripts"] if ms["track_id"] == track["object_id"]} == set(manuscript_ids[:2])
    for collection, id_name in [("fields", "field_id"), ("topics", "topic_id"), ("tracks", "track_id"), ("manuscripts", "manuscript_id")]:
        for old in original_overview[collection]:
            assert next(item for item in latest[collection] if item[id_name] == old[id_name]) == old
    for ms, digest in before_workspaces.items():
        assert canonical(call(studio, "GET", f"/manuscripts/{ms}/workspace")) == digest
    for package_id, digest in old_zips.items():
        response = studio.get(f"/manuscripts/{response_ms}/packages/{package_id}/download")
        assert response.status_code == 200 and sha(response.content) == digest
    assert call(studio, "GET", f"/manuscripts/{response_ms}/model-calls") == model_calls
    assert len(call(studio, "GET", f"/manuscripts/{response_ms}/packages")) == 7
    with sqlite3.connect(Path(catalog_receipt["root"]) / "data/catalog.db") as conn:
        receipts = [json.loads(row[0]) for row in conn.execute("SELECT result_json FROM research_workspace_actions WHERE request_id LIKE 'overview-native-%' ORDER BY action_seq")]
        assert len(receipts) == 8
        assert not conn.execute("SELECT 1 FROM research_nodes WHERE track_id IN (?,?)", (track["object_id"], track_b["object_id"])).fetchone()
        assert not conn.execute("SELECT 1 FROM track_snapshot_adoptions WHERE track_id IN (?,?)", (track["object_id"], track_b["object_id"])).fetchone()
    assert catalog.get(f"http://127.0.0.1:3000/?manuscript={manuscript_ids[0]}&from=catalog&track={track['object_id']}").status_code == 200
    proof.update(status="NATIVE_GLOBAL_OVERVIEW_METADATA_AND_OWNED_MANUSCRIPTS_PASSED", field_ids=[field["object_id"], second["object_id"]], topic_id=topic["object_id"], track_ids=[track["object_id"], track_b["object_id"]], manuscript_ids=manuscript_ids, request_receipts=receipts,
                 old_workspace_sha256=before_workspaces, old_package_zip_sha256=old_zips, new_model_calls=0,
                 page_sha256=sha(page.content), script_sha256=sha(script.content), workspace_id=latest["workspace_id"])
    persist()
print(json.dumps({key: value for key, value in proof.items() if key not in {"responses", "request_receipts"}}, ensure_ascii=False, indent=2))
