from pathlib import Path
import json
import hashlib
import sqlite3

repo = Path.cwd()
out = repo / ".tmp/scholar-g09-current-generation-native-v1"
out.mkdir()
(out / "proof").mkdir()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
info = read(repo / ".tmp/scholar-citation-source-native-v1.json")
db = Path(info["root"]) / "data/catalog.db"
with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as conn:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    tables = {r[0]:[dict(v) for v in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
              for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
previous = read(repo / ".tmp/scholar-g09-native-v2/final-native-source-and-reply/all-tables.json")
assert tables == previous
(out / "baseline-all-tables.json").write_text(json.dumps(tables, ensure_ascii=False, indent=2), encoding="utf-8")
(out / "baseline.json").write_text(json.dumps({"status":"PASS_QUIESCENT_AUTHOR40_SOURCE_AND_HISTORY_BASELINE", "database":str(db),
    "database_sha256":hashlib.sha256(db.read_bytes()).hexdigest(), "manuscript_id":info["manuscript_id"],
    "overall11_complete":False}, indent=2), encoding="utf-8")
print("PASS_QUIESCENT_ALL109_TABLE_BASELINE_AUTHOR40")
