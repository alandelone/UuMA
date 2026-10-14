from pathlib import Path
import hashlib
import json
import sqlite3
import urllib.request
import urllib.error

repo = Path.cwd()
root = repo / ".tmp/scholar-g09-native-v2"
out = root / "source-wire-audited"
out.mkdir()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
fixture = read(repo / ".tmp/scholar-citation-source-native-v1.json")
db = Path(fixture["root"]) / "data/catalog.db"
def snapshot():
    with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return {v[0]:[dict(r) for r in conn.execute(f'SELECT * FROM "{v[0]}" ORDER BY rowid')]
                for v in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
before = snapshot()
digest = sha(db)
ms = fixture["manuscript_id"]
sources = []
for evidence in before["evidence"]:
    eid = evidence["evidence_id"]
    url = f"http://127.0.0.1:8881/api/manuscripts/{ms}/sources/{eid}"
    with urllib.request.urlopen(url, timeout=10) as response:
        assert response.status == 200
        source = json.load(response)
    context = source["source_context"]
    location = json.loads(evidence["location_json"])
    assert context["available"] and context["full_text_available"]
    assert context["skeleton_id"] == location["skeleton_id"]
    assert context["unit"]["unit_id"] == location["unit_id"]
    assert context["unit"]["page_idx"] == location["page"]
    assert context["unit"]["section"] == location["section"]
    assert context["unit"]["raw_text"] == evidence["excerpt"]
    original = next(v for v in before["source_file_versions"] if v["file_version_id"] == context["file_version_id"])
    assert sha(original["storage_path"]) == original["sha256"] == context["file_version"]["sha256"]
    path = f"/api/studio-files/manuscripts/{ms}/sources/{eid}/contexts/{context['context_sha256']}/pdf"
    with urllib.request.urlopen("http://127.0.0.1:3008" + path, timeout=10) as response:
        raw = response.read()
        assert response.status == 200 and response.headers["Content-Type"].startswith("application/pdf")
        assert response.headers["Cache-Control"] == "no-store"
        assert raw == Path(original["storage_path"]).read_bytes()
    (out / (eid + ".json")).write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")
    sources.append({"evidence_id":eid, "context_sha256":context["context_sha256"],
                    "original_pdf_sha256":hashlib.sha256(raw).hexdigest(), "same_origin_route":path})
assert len(sources) == 3 and snapshot() == before and sha(db) == digest
assert all(sha(a["storage_path"]) == a["sha256"] for a in before["studio_artifacts"])
receipt = {"status":"PASS_G09_REAL_SOURCE_CONTEXT_AND_PDF_WIRE_AUDIT", "sources":sources,
           "all109_tables_exact_after_reads":True, "database_bytes_exact":True,
           "original20_artifact_bytes_exact":True, "new_models":0, "new_jobs":0,
           "g09_complete":False, "overall11_complete":False}
(out / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(receipt), flush=True)
