"""Serve the explicitly preserved existing G10 data copy; no model execution."""
from pathlib import Path
from types import SimpleNamespace
import json
import sys

repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo.parent / "RSTV4/src"))
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from rstv4.catalog_web import create_app as catalog_app
from rstv4.studio_api import create_app as studio_app

mode=sys.argv[1]
assert mode in {"catalog","studio"}
info=json.loads((repo / ".tmp/scholar-g10-native-v1/prepared-existing-copy/receipt.json").read_text(encoding="utf-8"))
root=Path(info["root"])
assert root.name.startswith("scui-g10-existing-copy-") and (root / "data/catalog.db").is_file()
def deny(task,payload):
    raise RuntimeError("G10 existing source browsing only: no model execution declared; no remote fallback")
app=catalog_app(root) if mode=="catalog" else studio_app(root)
app.state.discussions.gateway=SimpleNamespace(analyze=deny)
if mode=="catalog":
    app.state.fieldkg_semantics.gateway=SimpleNamespace(analyze=deny)
else:
    app.state.studio.gateway=SimpleNamespace(analyze=deny)
    app.add_middleware(CORSMiddleware,allow_origins=["http://127.0.0.1:3000"],allow_methods=["*"],allow_headers=["*"])
uvicorn.run(app,host="127.0.0.1",port=8885 if mode=="catalog" else 8886,log_level="warning")
