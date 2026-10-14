"""Read-only native Catalog acceptance against the existing owned software database."""
from pathlib import Path
import json, sys
from fastapi.responses import JSONResponse
import uvicorn
repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo.parent / 'RSTV4/src'))
from rstv4.catalog_web import create_app
fixture = json.loads((repo / '.tmp/scholar-citation-source-native-v1.json').read_text(encoding='utf-8'))
app = create_app(fixture['root'])
@app.middleware('http')
async def read_only(request, call_next):
    if request.method not in {'GET', 'HEAD'} and request.url.path not in {'/api/catalog/papers', '/api/catalog/discussion/history'}:
        return JSONResponse({'detail': 'G03 read-only Catalog acceptance; no mutation or model action authorized.'}, status_code=403)
    return await call_next(request)
uvicorn.run(app, host='127.0.0.1', port=8875, log_level='warning')
