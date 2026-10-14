"""Actual HTTP acceptance, existing isolated root, software-only source fixture."""
import ast
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo.parent / "RSTV4/src"))
from rstv4.models import FieldKGBuildInput
from rstv4.track_first import TrackFirstService

os.environ.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
path = repo / ".tmp/scholar-fieldkg-native-v1.json"
if path.exists():
    raise RuntimeError("Preserve this exclusive mutation receipt; resume read-only")
tree = ast.parse((repo / ".tmp/scholar-overview-native-v1.py").read_text(encoding="utf-8"))
guard = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "process_guard" for target in node.targets))
for check in [(repo / ".tmp/scholar-current-preview-proof.ps1").read_text(encoding="utf-8"), guard]:
    subprocess.run(["powershell", "-NoProfile", "-Command", check], cwd=repo, check=True)
info = json.loads((repo / ".tmp/scholar-overview-services.json").read_text(encoding="utf-8"))
root = Path(info["root"]).resolve()
assert root.name.startswith("scholar-ui-fixes-2026-10-03-")
parent = json.loads((repo / ".tmp/scholar-overview-native-finish-v1.json").read_text(encoding="utf-8"))
sha = lambda raw: hashlib.sha256(raw).hexdigest()
canonical = lambda value: sha(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
proof = {"status": "STARTED", "root": str(root), "responses": [], "browser_verified": False, "production_data_changed": False, "scientific_approval": False, "new_model_calls": 0}
def persist():
    path.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
persist()
with httpx.Client(base_url="http://127.0.0.1:8885", timeout=45) as catalog, httpx.Client(base_url="http://127.0.0.1:8874/api", timeout=45) as studio:
    def call(client, method, endpoint, expected=200, **kwargs):
        response = client.request(method, endpoint, **kwargs)
        body = response.json()
        proof["responses"].append({"server": "catalog" if client is catalog else "studio", "method": method, "path": endpoint, "status": response.status_code, "body": body})
        persist()
        assert response.status_code == expected, response.text[:1000]
        return body
    def metadata(operation, request_id, **values):
        return call(catalog, "POST", "/api/catalog/research-actions", json={"operation": operation, "request_id": f"fieldkg-native-{request_id}", **values})
    def action(operation, request_id, expected=200, **values):
        return call(catalog, "POST", "/api/catalog/fieldkg-actions", expected, json={"field_id": field, "operation": operation, "request_id": f"fieldkg-native-{request_id}", "confirmed": True, **values})
    def view(snapshot=None):
        return call(catalog, "GET", f"/api/catalog/fields/{field}/workspace", params={"snapshot": snapshot} if snapshot else {})
    old_workspaces = {ms: canonical(call(studio, "GET", f"/manuscripts/{ms}/workspace")) for ms in parent["old_workspace_sha256"]}
    assert old_workspaces == parent["old_workspace_sha256"]
    response_ms = "manuscript_bd7568923be94a2c8510d176010e4cca"
    before_calls = call(studio, "GET", f"/manuscripts/{response_ms}/model-calls")
    packages = call(studio, "GET", f"/manuscripts/{response_ms}/packages")
    assert len(packages) == 7
    before_zips = {}
    for package in packages:
        download = studio.get(f"/manuscripts/{response_ms}/packages/{package['package_id']}/download")
        assert download.status_code == 200
        before_zips[package["package_id"]] = sha(download.content)
    assert before_zips == parent["old_package_zip_sha256"]
    with sqlite3.connect(root / "data/catalog.db") as conn:
        before_model_count = conn.execute("SELECT COUNT(*) FROM studio_model_calls").fetchone()[0]
    field = metadata("CREATE_FIELD", "field", name="FieldKG 流程软件验收", description="Isolated software fixture; no scientific claim approval")["object_id"]
    topic = metadata("CREATE_TOPIC", "topic", field_id=field, name="固定来源版本软件验收")["object_id"]
    track = metadata("CREATE_TRACK", "track", field_id=field, primary_topic_id=topic, title="FieldKG 采用软件验收", scope="Software source/review/seal/adoption checks only", research_type="conceptual_framework")["object_id"]
    manuscript = call(studio, "POST", "/manuscripts", 201, json={"track_id": track, "title": "固定来源往返软件验收"})["manuscript"]["manuscript_id"]
    proof.update(field_id=field, topic_id=topic, track_id=track, manuscript_id=manuscript); persist()
    pool = root / "fieldkg-software-source-v1.db"
    assert not pool.exists()
    semantics = []
    for seq, intent, text in [(1, "Research_Gap", "This software fixture lacks a recorded validation run."), (2, "Claim", "The fixture stores an original source sentence."), (3, "Boundary_Condition", "This sentence is a software test condition only.")]:
        semantics.append({"seq_idx": seq, "page_idx": 3, "section": "Software fixture", "raw_text": text, "layer1": {"coref_resolved": text, "triplets": [{"subject": "software fixture", "predicate": "records", "object": f"original sentence {seq}"}]}, "layer2": {"discourse_relation": "Context"}, "layer3": {"intent": intent, "confidence": 0.9}, "layer4": "Software_Test"})
    with sqlite3.connect(pool) as conn:
        conn.execute("CREATE TABLE paper(id INTEGER PRIMARY KEY,title TEXT,year TEXT,authors TEXT,file TEXT,DOI TEXT,ext TEXT,Pp_txt_dict TEXT,Pp_abstract TEXT,Pp_minced_semantics TEXT)")
        conn.execute("INSERT INTO paper VALUES(1,?,?,?,?,?,?,?,?,?)", ("Software acceptance source, not a research paper", "2026", '["Software fixture"]', None, None, None, None, "Software-only fixture", json.dumps(semantics)))
    service = TrackFirstService(root)
    seed = service.create_fieldkg_build(FieldKGBuildInput(field_id=field, retrieval_scope={"fixture_seed_only": True}))
    imported = service.import_paperpool(seed["build_id"], str(pool), [])
    proof.update(seed_build_id=seed["build_id"], seed_import=imported, pool_sha256=sha(pool.read_bytes())); persist()
    source = next(source for source in call(catalog, "GET", "/api/catalog/research/skeletons")["sources"] if source["title"] == "Software acceptance source, not a research paper")
    assert source["file_version_id"] is None and source["parse_run_id"] is None
    built = action("CREATE_BUILD", "create-build", sources={source["skeleton_id"]: source["context_sha256"]})
    build_id = built["object_id"]
    assert action("CREATE_BUILD", "create-build", sources={source["skeleton_id"]: source["context_sha256"]}) == built
    current = view(); gap = next(g for g in current["candidate_gaps"] if g["record"]["build_id"] == build_id)
    action("REVIEW_GAP", "early-gap", 422, object_id=gap["record"]["candidate_gap_id"], expected_context_sha256=gap["context_sha256"], decision="ACCEPTED", rationale="Must first review actual candidates")
    for candidate in [c for c in current["candidates"] if c["record"]["build_id"] == build_id]:
        decision = "REJECTED" if candidate["record"]["excerpt"].startswith("This sentence") else "ACCEPTED"
        reviewed = action("REVIEW_CANDIDATE", candidate["record"]["candidate_id"], object_id=candidate["record"]["candidate_id"], expected_context_sha256=candidate["context_sha256"], decision=decision, rationale="Software provenance check only")
        assert reviewed["review"]["record"]["status"] == decision
    current = view(); gap = next(g for g in current["candidate_gaps"] if g["record"]["build_id"] == build_id)
    action("REVIEW_GAP", "gap-review", object_id=gap["record"]["candidate_gap_id"], expected_context_sha256=gap["context_sha256"], decision="ACCEPTED", rationale="Include as candidate, no scientific Gap approval")
    current = view(); build = next(b for b in current["builds"] if b["build_id"] == build_id)
    ready = action("READY_BUILD", "ready", build_id=build_id, expected_context_sha256=build["context_sha256"])["build"]
    sealed = action("SEAL_SNAPSHOT", "seal", build_id=build_id, expected_context_sha256=ready["context_sha256"])
    snapshot = sealed["snapshot"]
    assert action("SEAL_SNAPSHOT", "seal", build_id=build_id, expected_context_sha256=ready["context_sha256"]) == sealed
    fixed = view(snapshot["snapshot_id"])["selected_snapshot"]
    assert fixed["digest_matches"] and fixed["members_match"] and fixed["source_records_available"]
    assert len(fixed["frozen_evidence"]) == 2 and len(fixed["frozen_candidate_gaps"]) == 1
    track_view = call(catalog, "GET", f"/api/catalog/tracks/{track}/workspace")
    adoption = action("ADOPT_SNAPSHOT", "adopt", track_id=track, snapshot_id=snapshot["snapshot_id"], expected_context_sha256=track_view["context_sha256"], expected_snapshot_digest=snapshot["content_digest"])
    assert action("ADOPT_SNAPSHOT", "adopt", track_id=track, snapshot_id=snapshot["snapshot_id"], expected_context_sha256=track_view["context_sha256"], expected_snapshot_digest=snapshot["content_digest"]) == adoption
    new_build = action("CREATE_BUILD", "living-next-build", sources={source["skeleton_id"]: source["context_sha256"]})
    latest = call(catalog, "GET", f"/api/catalog/tracks/{track}/workspace")
    assert len(latest["adoptions"]) == 1 and latest["adopted_snapshots"][0]["manifest"] == fixed["manifest"]
    assert latest["manuscripts"][0]["manuscript_id"] == manuscript
    assert not latest["nodes"] and not latest["decisions"] and not latest["milestones"] and "current_phase" not in latest
    call(catalog, "GET", "/api/catalog/papers/" + source["paper_id"])
    assert catalog.get(f"/?view=all&paper={source['paper_id']}").status_code == 200
    assert catalog.get(f"http://127.0.0.1:3000/?manuscript={manuscript}&from=catalog&track={track}").status_code == 200
    page = catalog.get("/"); script = catalog.get("/catalog-research-workspaces.js")
    assert page.content == (repo.parent / "RSTV4/src/rstv4/catalog_web.html").read_bytes()
    assert script.content == (repo.parent / "RSTV4/src/rstv4/catalog_research_workspaces.js").read_bytes()
    for ms, digest in old_workspaces.items():
        assert canonical(call(studio, "GET", f"/manuscripts/{ms}/workspace")) == digest
    for package_id, digest in before_zips.items():
        response = studio.get(f"/manuscripts/{response_ms}/packages/{package_id}/download")
        assert response.status_code == 200 and sha(response.content) == digest
    assert call(studio, "GET", f"/manuscripts/{response_ms}/model-calls") == before_calls
    with sqlite3.connect(root / "data/catalog.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM studio_model_calls").fetchone()[0] == before_model_count
        receipts = [json.loads(row[0]) for row in conn.execute("SELECT result_json FROM research_workspace_actions WHERE request_id LIKE 'fieldkg-native-%' ORDER BY action_seq")]
        assert len(receipts) == 12
    proof.update(status="NATIVE_FIXED_SOURCE_REVIEW_SEAL_ADOPTION_PASSED", build_id=build_id, living_next_build_id=new_build["object_id"], snapshot_id=snapshot["snapshot_id"], snapshot_digest=snapshot["content_digest"], source=source, fixed_snapshot=fixed, adopted_track=latest, request_receipts=receipts, old_workspace_sha256=old_workspaces, old_package_zip_sha256=before_zips, page_sha256=sha(page.content), script_sha256=sha(script.content)); persist()
print(json.dumps({key: value for key, value in proof.items() if key not in {"responses", "source", "fixed_snapshot", "adopted_track", "request_receipts"}}, ensure_ascii=False, indent=2))
