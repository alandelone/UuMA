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
parent_path = repo / '.tmp/scholar-scope-literature-native-v2.json'
parent = json.loads(parent_path.read_text(encoding='utf-8'))
assert parent['status'] == 'PASS_ACTUAL_SCOPE_LIST_READ_ONLY'
source = Path(parent['root']).resolve() / 'data/catalog.db'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
source_sha = sha(source.read_bytes())
assert source_sha == parent['database_sha256']
previous_fixture=json.loads((repo/'.tmp/scholar-track-decisions-fixture-v1.json').read_text(encoding='utf-8'))
root=Path(previous_fixture['root']).resolve()
assert root.is_relative_to(Path(tempfile.gettempdir()).resolve()) and root.name.startswith('scui-track-')
db=root/'data/catalog.db'

def snapshot():
    with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as conn:
        return {row[0]: conn.execute('SELECT * FROM "' + row[0] + '" ORDER BY rowid').fetchall()
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}

before = snapshot()
app = create_app(root)
assert snapshot() == before, 'Startup must not change source data or schema'
trace = []

@app.middleware('http')
async def observed(request, call_next):
    response = await call_next(request)
    trace.append({'method': request.method, 'path': request.url.path, 'status': response.status_code})
    return response

with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as conn:
    field, topic = conn.execute('SELECT field_id,topic_id FROM collections WHERE field_id IS NOT NULL AND topic_id IS NOT NULL LIMIT 1').fetchone()
    track_id = conn.execute("SELECT track_id FROM research_tracks WHERE title='Isolated native scientific proposal software verification'").fetchone()[0]
    snapshot_id=conn.execute('SELECT snapshot_id FROM track_snapshot_adoptions WHERE track_id=?',(track_id,)).fetchone()[0]
    skeleton = conn.execute('SELECT skeleton_id FROM paper_skeletons LIMIT 1').fetchone()[0]
sock = socket.socket()
sock.bind(('127.0.0.1', 0))
sock.listen(128)
server = uvicorn.Server(uvicorn.Config(app, log_level='warning'))
thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
thread.start()
fixture = repo / '.tmp/scholar-track-decisions-fixture-v2.json'
with fixture.open('x', encoding='utf-8') as handle:
    json.dump({'base': f'http://127.0.0.1:{sock.getsockname()[1]}', 'root': str(root), 'process_id': os.getpid(),
               'field_id': field, 'topic_id': topic, 'skeleton_id': skeleton, 'track_id':track_id,'snapshot_id':snapshot_id,
               'source_dir': str(repo.parent / 'RSTV4/src/rstv4')}, handle, indent=2)
try:
    deadline = time.monotonic() + 15
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(.05)
    assert server.started
    subprocess.run(['node', str(repo / '.tmp/scholar-track-decisions-native-v2.mjs'), str(fixture),
                    str(repo / '.tmp/scholar-track-decisions-http-v2.json')], check=True)
    after = snapshot()
    allowed = {'research_tracks', 'track_topics', 'fieldkg_builds', 'fieldkg_build_papers',
               'fieldkg_evidence_candidates', 'fieldkg_candidate_gaps', 'evidence',
               'projection_outbox', 'research_workspace_actions', 'sqlite_sequence',
               'fieldkg_snapshots', 'fieldkg_snapshot_members', 'track_snapshot_adoptions',
               'research_nodes', 'decisions', 'node_evidence'}
    assert before.keys() == after.keys()
    for name in before:
        if name not in allowed:
            assert after[name] == before[name], name
        elif name != 'sqlite_sequence':
            assert after[name][:len(before[name])] == before[name], 'Old rows changed: ' + name
    assert sha(source.read_bytes()) == source_sha
    with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM research_nodes WHERE status='APPROVED'").fetchone()[0] == sum(r[3] == 'APPROVED' for r in before['research_nodes'])
        assert conn.execute('SELECT COUNT(*) FROM approval_grants').fetchone()[0] == len(before['approval_grants'])
    proof = {'status': 'PASS_ACTUAL_TRACK_PROPOSAL_AND_EXACT_RETRY_WITHOUT_APPROVAL',
             'root': str(root), 'source_database': str(source), 'source_database_sha256': source_sha,
             'source_receipt_sha256': sha(parent_path.read_bytes()), 'database_sha256': sha(db.read_bytes()),
             'requests': trace, 'actual_http_requests': len(trace), 'table_count': len(before),
             'all_original_rows_preserved': True, 'new_approval_grants': 0,
             'new_approved_scientific_nodes': 0, 'new_model_calls': 0,
             'browser_verified': False, 'scientific_approval': False, 'gap_path_verified':False, 'missing_structured_intent_preserved':True}
    with (repo / '.tmp/scholar-track-decisions-native-v2.json').open('x', encoding='utf-8') as handle:
        json.dump(proof, handle, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in proof.items() if k != 'requests'}), flush=True)
finally:
    server.should_exit = True
    thread.join(10)
    sock.close()
