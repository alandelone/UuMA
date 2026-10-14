from pathlib import Path
import hashlib
import json
import sqlite3
import urllib.request
import zipfile
import io

repo=Path.cwd()
root=repo / ".tmp/scholar-g09-current-generation-native-v1"
out=root / "response-package-audited-v1"
out.mkdir()
read=lambda p:json.loads(Path(p).read_text(encoding="utf-8"))
sha=lambda raw:hashlib.sha256(raw).hexdigest()
info=read(root / "baseline.json")
db=Path(info["database"])
digest=sha(db.read_bytes())
with sqlite3.connect(f"file:{db.as_posix()}?mode=ro",uri=True) as c:
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA query_only=ON")
    now={r[0]:[dict(v) for v in c.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
         for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
assert sha(db.read_bytes())==digest
before=read(root / "generated-v5-audited-v2/all-tables.json")
allowed={"review_comments","studio_comment_response_state","studio_response_checks","studio_jobs","studio_submission_packages"}
for name,rows in before.items():
    if name not in allowed:
        assert now[name]==rows,name
    elif name in {"studio_jobs","studio_submission_packages","studio_response_checks"}:
        assert all(row in now[name] for row in rows),name
a206="comment_8ecd722c5ea041858723009b72fc4cce"
for old,current in zip(before["review_comments"],now["review_comments"]):
    if old["comment_id"]!=a206:
        assert current==old
    else:
        assert current["status"]=="RESOLVED" and current["response_text"]==old["response_text"]+" This review is limited to software behavior."
        assert {k:v for k,v in current.items() if k not in {"response_text","updated_at"}}=={k:v for k,v in old.items() if k not in {"response_text","updated_at"}}
assert len(now["review_comments"])==206 and len(now["studio_model_calls"])==27
for old,current in zip(before["studio_comment_response_state"],now["studio_comment_response_state"]):
    expected=dict(old)
    if old["comment_id"]==a206:expected["revision"]=old["revision"]+1
    assert current==expected
context=read(root / "second-check-current-context-api.json")
assert context["verification"]["status"]=="CURRENT" and len(context["history"])==2
assert context["history"][0]==read(root / "first-check-history-api.json")["history"][0]
assert len(now["studio_response_checks"])==2
for row,check in zip(now["studio_response_checks"],context["history"]):
    assert row["check_id"]==check["check_id"]
    assert json.loads(row["context_json"])==check["context"] and json.loads(row["request_json"])==check["request"]
    assert check["outcome"]=="MODIFIED" and check["generated_version_id"]=="manuscript_version_de30b95a2d6843059d3c8b420627bf58"
    claim=check["request"]["claims"][0]
    assert claim["start"]==0 and claim["end"]==len(check["context"]["state"]["response_text"].encode("utf-16-le"))//2
    assert claim["text"]==check["context"]["state"]["response_text"]
    selected=[r for r in check["context"]["evidence"] if r["evidence_id"] in claim["evidence_ids"]]
    assert len(selected)==1 and selected[0]["status"]=="GENERATED_TEXT_CHANGED"
    assert selected[0]["thought_id"]=="thought_5f3edebed89d482cb0b2d9d42c4930d8"
    assert selected[0]["final_page"]==1 and selected[0]["final_line"]==8 and selected[0]["final_line_end"]==9
packages=[r for r in now["studio_submission_packages"] if r not in before["studio_submission_packages"]]
assert len(packages)==1
package=packages[0]
package_id="submission_package_9ed351f308a34c08909b5933c99c9c24"
assert package["package_id"]==package_id
jobs=[r for r in now["studio_jobs"] if r not in before["studio_jobs"]]
assert len(jobs)==1 and jobs[0]["job_kind"]=="SUBMISSION_PACKAGE" and jobs[0]["status"]=="SUCCEEDED"
result=json.loads(jobs[0]["result_json"])
directory=Path(result["directory"])
manifest=read(directory / "manifest.json")
assert manifest==json.loads(package["manifest_json"])
assert manifest["review_round_id"]=="review_round_b51564f0224e499081e58f341103b336"
assert manifest["baseline_manuscript_version_id"]=="manuscript_version_7c2addf4da0f48948f8444b623cbe42e"
assert manifest["generated_version_id"]=="manuscript_version_de30b95a2d6843059d3c8b420627bf58" and manifest["input_revision"]==62
assert len(manifest["files"])==16 and manifest["unresolved_comment_ids"]==[]
history=read(directory / "response-review-history.json")
assert len(history["comments"])==1 and history["comments"][0]["checks"]==context["history"]
assert history["comments"][0]["verification"]["status"]=="CURRENT"
mapping=read(directory / "change-realization-map.json")
assert len(mapping["rows"])==4 and sum(r["status"]=="GENERATED_TEXT_CHANGED" for r in mapping["rows"])==1
assert manifest["location_summary"]["unknown_or_unattributed_rows"]==3
for name,item in manifest["file_integrity"].items():
    raw=(directory / name).read_bytes()
    assert sha(raw)==item["sha256"] and len(raw)==item["size_bytes"]
with urllib.request.urlopen(f"http://127.0.0.1:3008/api/studio-files/manuscripts/{info['manuscript_id']}/packages/{package_id}/download",timeout=15) as response:
    archive=response.read()
    assert response.status==200 and response.headers["Content-Type"].startswith("application/zip")
with zipfile.ZipFile(io.BytesIO(archive)) as z:
    assert len(z.namelist())==16 and set(z.namelist())==set(manifest["files"])
    for name in z.namelist():assert z.read(name)==(directory / name).read_bytes()
(out / "actual-response-package.zip").write_bytes(archive)
assert sha(db.read_bytes())==digest
for artifact in now["studio_artifacts"]:
    raw=Path(artifact["storage_path"]).read_bytes()
    assert sha(raw)==artifact["sha256"] and len(raw)==artifact["size_bytes"]
(out / "all-tables.json").write_text(json.dumps(now,ensure_ascii=False,indent=2),encoding="utf-8")
receipt={"status":"PASS_G09_NATIVE_GENERATION_REPLY_RECHECK_AND_PACKAGE_SUBCASES", "package_id":package_id,
         "fixed_round":2,"fixed_baseline_version":3,"target_version":5,"author_revision":62,
         "checks":2,"first_check_exact_after_stale_and_recheck":True,"final_verification":"CURRENT",
         "original205_opinions_unchanged":True,"new_remote_calls":0,"all_old_sources_artifacts_history_exact":True,
         "files":16,"archive_sha256":sha(archive),"actual_same_origin_archive_bytes_verified":True,
         "browser_download_completed":False,"native_final_pdf_open_blocked_by_client":True,
         "actual_final_pdf_locally_rendered_two_pages":True,"overall11_complete":False}
(out / "receipt.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
print(json.dumps(receipt),flush=True)
