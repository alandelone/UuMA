from pathlib import Path
import hashlib
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
repo = Path.cwd()
root = repo / ".tmp/scholar-g09-native-v2"
phase = sys.argv[1]
out = root / phase
out.mkdir()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
info = read(repo / ".tmp/scholar-g08-native-v1/baseline.json")
db = Path(info["root"]) / "data/catalog.db"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
before = sha(db)
with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as conn:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    tables = {name: [dict(r) for r in conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid')]
              for name in names}
assert sha(db) == before and len(tables) == 109
base = read(root / "round2-created/all-tables.json")
delta = {name: {"old": len(rows), "now": len(tables[name]),
                 "removed_or_modified": [r for r in rows if r not in tables[name]],
                 "new_or_modified": [r for r in tables[name] if r not in rows]}
         for name, rows in base.items() if rows != tables[name]}
for name in ["studio_documents", "studio_operations", "studio_changes", "studio_model_calls",
             "studio_jobs", "studio_artifacts", "review_rounds", "studio_review_round_baselines"]:
    assert tables[name] == base[name], name
assert len(tables["review_comments"]) == 206
assert all(row in tables["review_comments"] for row in base["review_comments"])
new = [r for r in tables["review_comments"] if r not in base["review_comments"]]
assert len(new) == 1 and new[0]["comment_id"] == "comment_8ecd722c5ea041858723009b72fc4cce"
assert all(sha(v["storage_path"]) == v["sha256"] for v in tables["studio_artifacts"])
(out / "all-tables.json").write_text(json.dumps(tables, ensure_ascii=False, indent=2), encoding="utf-8")
(out / "delta.json").write_text(json.dumps(delta, ensure_ascii=False, indent=2), encoding="utf-8")
receipt = {"status": "PASS_G09_READONLY_SNAPSHOT", "phase": phase,
           "database_sha256": before, "all_original205_comments_exact": True,
           "author_operations_changes_models_jobs_artifacts_rounds_exact": True,
           "all20_artifact_bytes_exact": True, "new_comment": new[0],
           "changed_tables": list(delta), "overall11_complete": False}
(out / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(receipt, ensure_ascii=False), flush=True)
