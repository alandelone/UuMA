"""Resume existing acceptance data; every model task requires a new explicit fixture."""
from pathlib import Path
from types import SimpleNamespace
import json
import sys

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo.parent / "RSTV4" / "src"))
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from rstv4.studio_api import create_app

fixture = json.loads((repo / ".tmp/scholar-citation-source-native-v1.json").read_text(encoding="utf-8"))
app = create_app(fixture["root"])
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:3008"],
                   allow_methods=["*"], allow_headers=["*"])

def deny_model(task, payload):
    raise RuntimeError("G09 serve-only recovery: no model fixture declared for this task; no remote fallback.")

app.state.studio.gateway = SimpleNamespace(analyze=deny_model)
app.state.discussions.gateway = SimpleNamespace(analyze=deny_model)
uvicorn.run(app, host="127.0.0.1", port=8881, log_level="warning")
