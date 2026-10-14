"""Eleven exact pre-audited software realization inputs; every other task denied."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import sqlite3
import sys

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo.parent / "RSTV4/src"))
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from rstv4.studio_api import create_app

root = repo / ".tmp/scholar-g09-current-generation-native-v1"
read = lambda p:json.loads(Path(p).read_text(encoding="utf-8"))
fixture = read(repo / ".tmp/scholar-citation-source-native-v1.json")
prepared = read(root / "input-audited-v2/receipt.json")
contracts = read(root / "input-audited-v2/contracts.json")
db = Path(fixture["root"]) / "data/catalog.db"
assert prepared["revision"] == 62 and len(contracts) == 11
expected = {v["input_sha256"]:v for v in contracts}
assert len(expected) == 11
original_doc = next(v for v in read(root / "input-audited-v2/all-tables.json")["studio_documents"] if v["manuscript_id"] == fixture["manuscript_id"])
used = set()
def software_realization(task,payload):
    if task != "paragraph_realization":
        raise RuntimeError("G09 allows only the eleven declared current-revision software inputs")
    key = hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    if key not in expected or key in used or payload != expected[key]["payload"]:
        raise RuntimeError("Undeclared or repeated G09 input; no remote fallback")
    with sqlite3.connect(f"file:{db.as_posix()}?mode=ro",uri=True) as conn:
        conn.row_factory = sqlite3.Row
        current = dict(conn.execute("SELECT * FROM studio_documents WHERE manuscript_id=?",(fixture["manuscript_id"],)).fetchone())
    if current["revision"] != 62 or current["document_json"] != original_doc["document_json"]:
        raise RuntimeError("Pre-audited G09 author input changed; no fallback")
    used.add(key)
    return expected[key]["response"]
def deny_discussion(task,payload):
    raise RuntimeError("G09 discussion not declared; no remote fallback")
app = create_app(fixture["root"])
app.add_middleware(CORSMiddleware,allow_origins=["http://127.0.0.1:3008"],allow_methods=["*"],allow_headers=["*"])
app.state.studio.gateway = SimpleNamespace(analyze=software_realization)
app.state.discussions.gateway = SimpleNamespace(analyze=deny_discussion)
uvicorn.run(app,host="127.0.0.1",port=8881,log_level="warning")
