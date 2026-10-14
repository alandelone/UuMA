"""Finish the exact previous fixture read-only; never replay its mutations."""
import hashlib
import json
import sqlite3
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
path = repo / ".tmp/scholar-overview-native-finish-v1.json"
if path.exists():
    raise RuntimeError("Preserve this exclusive read-only continuation")
parent_path = repo / ".tmp/scholar-overview-native-v1.json"
parent = json.loads(parent_path.read_text(encoding="utf-8"))
sha = lambda raw: hashlib.sha256(raw).hexdigest()
canonical = lambda value: sha(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
actions = [item["body"] for item in parent["responses"] if item["server"] == "catalog" and item["method"] == "POST" and item["status"] == 200]
originals = {item["request_id"]: item for item in actions}
expected_ids = ["overview-native-field-1", "overview-native-field-2", "overview-native-topic-1", "overview-native-topic-link", "overview-native-track-1", "overview-native-track-2", "overview-native-field-edit", "overview-native-topic-edit", "overview-native-track-edit"]
assert set(originals) == set(expected_ids)
root = Path(parent["catalog_root"])
with sqlite3.connect(root / "data/catalog.db") as conn:
    receipts = [json.loads(row[0]) for row in conn.execute("SELECT result_json FROM research_workspace_actions WHERE request_id LIKE 'overview-native-%' ORDER BY action_seq")]
    assert len(receipts) == len(expected_ids) == 9
    assert {item["request_id"]: item for item in receipts} == originals
    track_ids = [originals[f"overview-native-track-{index}"]["object_id"] for index in [1, 2]]
    assert not conn.execute("SELECT 1 FROM research_nodes WHERE track_id IN (?,?)", track_ids).fetchone()
    assert not conn.execute("SELECT 1 FROM track_snapshot_adoptions WHERE track_id IN (?,?)", track_ids).fetchone()
before = {item["path"].split('/')[2]: canonical(item["body"]) for item in parent["responses"][:5]}
assert len(before) == 5
created = [item["body"]["manuscript"]["manuscript_id"] for item in parent["responses"] if item["server"] == "studio" and item["method"] == "POST" and item["path"] == "/manuscripts"]
assert len(created) == 3 and len(set(created)) == 3
old_ms = "manuscript_bd7568923be94a2c8510d176010e4cca"
old_proof = json.loads((repo / ".tmp/scholar-response-native-v1.json").read_text(encoding="utf-8"))
proof = {"status": "STARTED", "browser_verified": False, "scientific_approval": False, "production_data_changed": False,
         "parent_sha256": sha(parent_path.read_bytes()), "parent_helper_sha256": sha((repo / ".tmp/scholar-overview-native-v1.py").read_bytes()),
         "initial_failure": "Receipt-count expectation was 8; the explicit action list contains 9. Native HTTP mutations and the preceding 7 ZIP comparisons had already succeeded. No mutation was rerun.",
         "request_receipts": receipts, "track_ids": track_ids, "manuscript_ids": created, "old_workspace_sha256": before}
with httpx.Client(base_url="http://127.0.0.1:8874/api", timeout=45) as studio, httpx.Client(base_url="http://127.0.0.1:8885", timeout=45) as catalog:
    for ms, digest in before.items():
        response = studio.get(f"/manuscripts/{ms}/workspace"); assert response.status_code == 200
        assert canonical(response.json()) == digest
    zip_hashes = {}
    packages = studio.get(f"/manuscripts/{old_ms}/packages").json()
    assert len(packages) == 7
    for package in packages:
        response = studio.get(f"/manuscripts/{old_ms}/packages/{package['package_id']}/download")
        assert response.status_code == 200
        zip_hashes[package["package_id"]] = sha(response.content)
    for package_id, digest in old_proof["old_package_zip_sha256"].items():
        assert zip_hashes[package_id] == digest
    calls_before = next(item["body"] for item in parent["responses"] if item["path"] == f"/manuscripts/{old_ms}/model-calls")
    assert studio.get(f"/manuscripts/{old_ms}/model-calls").json() == calls_before
    data = catalog.get("/api/catalog/research-overview").json()
    assert {row["manuscript_id"] for row in data["manuscripts"] if row["track_id"] == track_ids[0]} == set(created[:2])
    assert {row["manuscript_id"] for row in data["manuscripts"] if row["track_id"] == track_ids[1]} == {created[2]}
    for index, ms in enumerate(created):
        record = studio.get(f"/manuscripts/{ms}/workspace").json()
        assert record["manuscript"]["manuscript_id"] == ms
        assert record["manuscript"]["track_id"] == track_ids[0 if index < 2 else 1]
        assert not record["active_generated_version_id"]
    return_url = httpx.URL("http://127.0.0.1:8885/").copy_add_param("overview_state", json.dumps({"workspace": data["workspace_id"], "collapsed": [], "focus": "", "anchor": "", "offset": 0, "scroll": 0}))
    page = catalog.get("http://127.0.0.1:3000/", params={"manuscript": created[0], "from": "catalog", "track": track_ids[0], "return": str(return_url)})
    assert page.status_code == 200
    catalog_page = catalog.get("/"); script = catalog.get("/catalog-research-overview.js")
    assert catalog_page.status_code == script.status_code == 200
    assert catalog_page.content == (repo.parent / "RSTV4/src/rstv4/catalog_web.html").read_bytes()
    assert script.content == (repo.parent / "RSTV4/src/rstv4/catalog_research_overview.js").read_bytes()
    proof.update(status="NATIVE_GLOBAL_OVERVIEW_METADATA_AND_OWNED_MANUSCRIPTS_PASSED", workspace_id=data["workspace_id"],
                 new_model_calls=0, new_mutations_in_continuation=0, old_package_zip_sha256=zip_hashes,
                 page_sha256=sha(catalog_page.content), script_sha256=sha(script.content), frontend_url=str(page.url), frontend_status=page.status_code)
path.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({key: value for key, value in proof.items() if key != "request_receipts"}, ensure_ascii=False, indent=2))
