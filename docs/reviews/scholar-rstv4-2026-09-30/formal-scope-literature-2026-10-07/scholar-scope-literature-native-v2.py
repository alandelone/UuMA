import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
from contextlib import closing
from pathlib import Path

import uvicorn
from rstv4.catalog_web import create_app

repo = Path(__file__).resolve().parents[1]
parent_path = repo / '.tmp/scholar-deep-read-native-v2.json'
parent = json.loads(parent_path.read_text(encoding='utf-8'))
assert parent['status'] == 'PASS_ACTUAL_QUICKREAD_SKELETON_ASSESSMENT_AND_FORMAL_READBACK'
source = Path(parent['root']).resolve() / 'data/catalog.db'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
source_sha = sha(source.read_bytes())
previous=json.loads((repo/'.tmp/scholar-scope-literature-native-v1.json').read_text(encoding='utf-8'))
root=Path(previous['root']).resolve()
assert root.is_relative_to(Path(tempfile.gettempdir()).resolve()) and root.name.startswith('scui-literature-')
db=root/'data/catalog.db'
assert sha(db.read_bytes())==previous['database_sha256']
app = create_app(root)
trace = []

@app.middleware('http')
async def observed(request, call_next):
    response = await call_next(request)
    trace.append({'method': request.method, 'path': request.url.path, 'status': response.status_code})
    return response

def snapshot():
    with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as conn:
        return {row[0]: conn.execute('SELECT * FROM "' + row[0] + '" ORDER BY rowid').fetchall()
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}

with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as conn:
    field, topic = conn.execute('SELECT field_id,topic_id FROM collections WHERE collection_id=?', (parent['request']['job']['collection_id'],)).fetchone()
before = snapshot()
sock = socket.socket()
sock.bind(('127.0.0.1', 0))
sock.listen(128)
port = sock.getsockname()[1]
server = uvicorn.Server(uvicorn.Config(app, log_level='warning'))
thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
thread.start()
fixture = repo / '.tmp/scholar-scope-literature-fixture-v2.json'
with fixture.open('x', encoding='utf-8') as handle:
    json.dump({'base': f'http://127.0.0.1:{port}', 'root': str(root), 'process_id': os.getpid(),
               'field_id': field, 'topic_id': topic, 'paper_id': parent['request']['job']['paper_id'],
               'source_dir': str(repo.parent / 'RSTV4/src/rstv4')}, handle, indent=2)
try:
    deadline = time.monotonic() + 15
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(.05)
    assert server.started
    bytes_before = sha(db.read_bytes())
    subprocess.run(['node', str(repo / '.tmp/scholar-scope-literature-native-v2.mjs'), str(fixture),
                    str(repo / '.tmp/scholar-scope-literature-http-v2.json')], check=True)
    assert snapshot() == before
    assert sha(db.read_bytes()) == bytes_before
    assert sha(source.read_bytes()) == source_sha
    proof = {'status': 'PASS_ACTUAL_SCOPE_LIST_READ_ONLY', 'root': str(root), 'requests': trace,
             'actual_http_requests': len(trace), 'source_database_sha256': source_sha,
             'source_database': str(source), 'source_receipt_sha256': sha(parent_path.read_bytes()),
             'all_tables_unchanged': len(before), 'database_sha256': bytes_before,
             'new_model_calls': 0, 'browser_verified': False, 'scientific_approval': False}
    with (repo / '.tmp/scholar-scope-literature-native-v2.json').open('x', encoding='utf-8') as handle:
        json.dump(proof, handle, ensure_ascii=False, indent=2)
    print(json.dumps(proof), flush=True)
finally:
    server.should_exit = True
    thread.join(10)
    sock.close()
