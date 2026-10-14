import hashlib
import json
import os
import sqlite3
import subprocess
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
backend = repo.parent / "RSTV4"
os.environ.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
log = repo / ".tmp/scholar-fieldkg-multiple-versions-v1.log"
with log.open("x", encoding="utf-8") as handle:
    result = subprocess.run([str(backend / ".venv/Scripts/python.exe"), "-m", "pytest", "tests/test_fieldkg_workspace.py::test_track_can_explicitly_adopt_multiple_fixed_versions_without_replacing_first", "-q"], cwd=backend, stdout=handle, stderr=subprocess.STDOUT)
    handle.write(f"Exit: {result.returncode}\n")
assert result.returncode == 0
lint = subprocess.run([str(backend / ".venv/Scripts/python.exe"), "-m", "ruff", "check", "tests/test_fieldkg_workspace.py"], cwd=backend, capture_output=True, text=True)
assert lint.returncode == 0, lint.stdout
proof = json.loads((repo / ".tmp/scholar-fieldkg-native-v1.json").read_text(encoding="utf-8"))
assert proof["status"] == "NATIVE_FIXED_SOURCE_REVIEW_SEAL_ADOPTION_PASSED"
sha = lambda raw: hashlib.sha256(raw).hexdigest()
with httpx.Client(base_url="http://127.0.0.1:8885", timeout=30) as client:
    script = client.get("/catalog-research-workspaces.js"); page = client.get("/")
    assert script.status_code == page.status_code == 200
    assert script.content == (backend / "src/rstv4/catalog_research_workspaces.js").read_bytes()
    assert page.content == (backend / "src/rstv4/catalog_web.html").read_bytes()
    field = client.get(f"/api/catalog/fields/{proof['field_id']}/workspace", params={"snapshot": proof["snapshot_id"]}).json()
    fixed = field["selected_snapshot"]
    assert fixed["manifest"] == proof["fixed_snapshot"]["manifest"] and fixed["digest_matches"] and fixed["members_match"]
    track = client.get(f"/api/catalog/tracks/{proof['track_id']}/workspace").json()
    assert track["adoptions"] == proof["adopted_track"]["adoptions"]
    with sqlite3.connect(Path(proof["root"]) / "data/catalog.db") as conn:
        receipts = [json.loads(row[0]) for row in conn.execute("SELECT result_json FROM research_workspace_actions WHERE request_id LIKE 'fieldkg-native-%' ORDER BY action_seq")]
    assert receipts == proof["request_receipts"]
    output = {"status": "CURRENT_SCRIPT_AND_FROZEN_RECEIPTS_VERIFIED_READONLY", "native_parent_sha256": sha((repo / ".tmp/scholar-fieldkg-native-v1.json").read_bytes()), "page_sha256": sha(page.content), "script_sha256": sha(script.content), "snapshot_digest": fixed["content_digest"], "request_receipt_count": len(receipts), "new_mutations": 0, "new_model_calls": 0, "browser_verified": False, "additional_multiple_version_adoption_test": True}
    with (repo / ".tmp/scholar-fieldkg-final-readonly-v1.json").open("x", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
print(log.read_text(encoding="utf-8"))
print(json.dumps(output, ensure_ascii=False, indent=2))
