from pathlib import Path
import hashlib
import json
import sqlite3
import sys

repo = Path.cwd()
root = repo / ".tmp/scholar-g09-current-generation-native-v1"
out = root / "generated-v5-audited"
out.mkdir()
read = lambda p:json.loads(Path(p).read_text(encoding="utf-8"))
before = read(root / "input-audited-v2/all-tables.json")
info = read(root / "baseline.json")
db = Path(info["database"])
digest = hashlib.sha256(db.read_bytes()).hexdigest()
with sqlite3.connect(f"file:{db.as_posix()}?mode=ro",uri=True) as conn:
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    tables={r[0]:[dict(v) for v in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
assert hashlib.sha256(db.read_bytes()).hexdigest()==digest
ms=info["manuscript_id"]
changed={"studio_jobs","studio_model_calls","studio_artifacts","manuscript_versions","studio_documents",
         "manuscripts","review_comments","studio_comment_response_state","studio_response_checks","studio_sample_candidates","sqlite_sequence"}
for name,rows in before.items():
    if name not in changed:
        assert tables[name]==rows,name
    elif name in {"studio_jobs","studio_model_calls","studio_artifacts","manuscript_versions","studio_sample_candidates"}:
        assert all(row in tables[name] for row in rows),name
job_id="studio_job_de2856bae51842b38ed6342f3fca6b10"
version_id="manuscript_version_de30b95a2d6843059d3c8b420627bf58"
new_jobs=[r for r in tables["studio_jobs"] if r not in before["studio_jobs"]]
assert len(new_jobs)==1 and new_jobs[0]["job_id"]==job_id
assert new_jobs[0]["status"]=="SUCCEEDED" and new_jobs[0]["input_revision"]==62
new_calls=[r for r in tables["studio_model_calls"] if r not in before["studio_model_calls"]]
assert len(new_calls)==11 and len(tables["studio_model_calls"])==27
contracts={r["input_sha256"]:r for r in read(root / "input-audited-v2/contracts.json")}
seen=set()
for call in new_calls:
    assert call["manuscript_id"]==ms and call["job_id"]==job_id and call["input_revision"]==62
    assert call["status"]=="VALIDATED" and call["task"]=="paragraph_realization"
    payload=json.loads(call["input_json"])
    key=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    assert key in contracts and key not in seen and payload==contracts[key]["payload"]
    assert json.loads(call["output_json"])==contracts[key]["response"]
    seen.add(key)
assert seen==set(contracts)
new_versions=[r for r in tables["manuscript_versions"] if r not in before["manuscript_versions"]]
assert len(new_versions)==1 and new_versions[0]["manuscript_version_id"]==version_id
new_artifacts=[r for r in tables["studio_artifacts"] if r not in before["studio_artifacts"]]
assert len(new_artifacts)==5 and len(tables["studio_artifacts"])==25
for artifact in tables["studio_artifacts"]:
    raw=Path(artifact["storage_path"]).read_bytes()
    assert len(raw)==artifact["size_bytes"] and hashlib.sha256(raw).hexdigest()==artifact["sha256"]
for old,current in zip(before["studio_documents"],tables["studio_documents"]):
    if old["manuscript_id"]!=ms:
        assert current==old
    else:
        expected=dict(old)
        expected.update(active_generated_version_id=version_id,last_generated_revision=62,updated_at=current["updated_at"])
        assert current==expected
for old,current in zip(before["manuscripts"],tables["manuscripts"]):
    expected=dict(old)
    if old["manuscript_id"]==ms:
        expected["updated_at"]=current["updated_at"]
    assert current==expected
a206="comment_8ecd722c5ea041858723009b72fc4cce"
for old,current in zip(before["review_comments"],tables["review_comments"]):
    if old["comment_id"]!=a206:
        assert current==old
    else:
        assert {k:v for k,v in old.items() if k not in {"author_decision","response_text","status","updated_at"}}=={k:v for k,v in current.items() if k not in {"author_decision","response_text","status","updated_at"}}
        assert current["status"]=="RESOLVED"
assert len(before["review_comments"])==len(tables["review_comments"])==206
context=read(root / "response-context-current-v5-before-confirm.json")
evidence=[e for e in context["evidence"] if e["status"]=="GENERATED_TEXT_CHANGED"]
assert len(evidence)==1 and evidence[0]["thought_id"]=="thought_5f3edebed89d482cb0b2d9d42c4930d8"
assert evidence[0]["final_page"]==evidence[0]["final_page_end"]==1
assert evidence[0]["final_line"]==8 and evidence[0]["final_line_end"]==9 and evidence[0]["boxes"]
assert evidence[0]["final_pdf_sha256"]=="f3d27b83a2256d7cffa25e3162b67e060fc55c30311abcc6329c8d3394f0e0e4"
assert "[@" not in context["baseline_to_target_display_diff"] and "[@" in context["baseline_to_target_diff"]
assert context["baseline_version_number"]==3 and context["target_version_number"]==5
first=read(root / "first-check-history-api.json")["history"]
assert len(first)==len(tables["studio_response_checks"])==1
check=tables["studio_response_checks"][0]
assert check["check_id"]==first[0]["check_id"] and check["generated_version_id"]==version_id
assert json.loads(check["context_json"])==first[0]["context"]
assert json.loads(check["request_json"])==first[0]["request"]
(out / "all-tables.json").write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding="utf-8")
receipt={"status":"PASS_NATIVE_CURRENT_V5_SOURCE_CALLS_AND_PDF_LOCATION", "version_id":version_id,
         "job_id":job_id,"input_revision":62,"new_exact_fixture_calls":11,"new_artifacts":5,
         "original_four_versions_twenty_artifacts_exact":True,"all_original205_comments_exact":True,
         "two_rounds_fixed_baselines_exact":True,"all_old_history_and_other_manuscript_exact":True,
         "actual_note_final_page":1,"actual_note_final_lines":[8,9],"overall11_complete":False}
(out / "receipt.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
print(json.dumps(receipt),flush=True)
