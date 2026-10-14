from pathlib import Path
import hashlib
import json
import sqlite3
import zipfile

repo=Path.cwd()
root=repo / ".tmp/scholar-g09-current-generation-native-v1"
out=root / "final-native-audited-v1"
out.mkdir()
read=lambda p:json.loads(Path(p).read_text(encoding="utf-8"))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
info=read(root / "baseline.json")
db=Path(info["database"])
with sqlite3.connect(f"file:{db.as_posix()}?mode=ro",uri=True) as c:
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA query_only=ON")
    now={r[0]:[dict(v) for v in c.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
         for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
assert now==read(root / "response-package-audited-v1/all-tables.json")
downloads=read(root / "native-download-receipt-v1.json")
assert downloads["status"]=="PASS_NATIVE_BROWSER_ACTUAL_ZIP_AND_PDF_DOWNLOAD"
assert sha(downloads["zip"]["path"])==downloads["zip"]["sha256"]=="42cca3508fdba2b6bd39527bbc4820514b2bd4c73415cd677a8a76f39634484c"
assert sha(downloads["pdf"]["path"])==downloads["pdf"]["sha256"]=="f3d27b83a2256d7cffa25e3162b67e060fc55c30311abcc6329c8d3394f0e0e4"
for old in read(root / "pdf-download-before.json"):
    path=Path("C:/Users/Alandelone/Downloads") / old["name"]
    stat=path.stat()
    assert stat.st_size==old["size"] and abs(stat.st_mtime*1000-old["mtime"])<0.01
with zipfile.ZipFile(downloads["zip"]["path"]) as z:
    assert len(z.namelist())==16
    assert hashlib.sha256(z.read("clean-manuscript.pdf")).hexdigest()==downloads["pdf"]["sha256"]
    history=json.loads(z.read("response-review-history.json"))
    expected=read(root / "second-check-current-context-api.json")
    assert history["comments"][0]["checks"]==expected["history"]
    assert history["comments"][0]["verification"]["status"]=="CURRENT"
    assert json.loads(z.read("unresolved-comments.json"))==[]
tests=read(repo / ".tmp/scholar-g09-readable-full-tests-v1/receipt.json")
assert tests["status"]=="PASS" and "1078 passed, 20 warnings" in tests["summary"]
assert all(sha(repo.parent / "RSTV4" / p)==h for p,h in read(repo / ".tmp/scholar-g09-readable-full-tests-v1/source-before.json").items())
receipt={"status":"PASS_G09_ORIGINAL_NATIVE_SOFTWARE_GROUP_DEFINITION",
         "original_definition":"Source page/block/version readable; independent second fixed baseline; original opinions, unassigned actual edits, true modifications and reply materials readable",
         "author_revision":62,"target_version":5,"second_round_baseline":3,
         "original205_comments_and_original_round_exact":True,"append_only_review_checks":2,
         "real_native_zip_and_pdf_download_verified":True,"final_pdf_two_pages_visually_checked":True,
         "narrow390_review_no_horizontal_overflow":True,"all109_tables_exact_after_download_and_refresh":True,
         "full_backend_tests":1078,"database_sha256":sha(db),"overall11_complete":False,
         "remaining_scope":["G10","G11","original118_final_audit","all11_integrated_native_flow"],
         "scientific_acceptance":False}
(out / "receipt.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
(out / "all-tables.json").write_text(json.dumps(now,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(receipt),flush=True)
