import hashlib
import json
import os
import socket
import sqlite3
import tempfile
import threading
import time
from contextlib import closing
from pathlib import Path

import httpx
import uvicorn
from rstv4.acquisition import AcquisitionService
from rstv4.acquisition_worker import ROLE_QUEUES, AcquisitionWorker
from rstv4.catalog_web import create_app
from rstv4.model_gateway import UnlimitedLLMGateway
from rstv4.skeleton_intent import INTENT_VERSION, validate_intent

repo = Path(__file__).resolve().parents[1]
parent_path = repo / '.tmp/scholar-track-decisions-native-v2.json'
parent = json.loads(parent_path.read_text(encoding='utf-8'))
source = Path(parent['root']).resolve() / 'data/catalog.db'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
assert sha(source.read_bytes()) == parent['database_sha256']
owned=json.loads((repo/'.tmp/scholar-structured-intent-original-request-v1.json').read_text(encoding='utf-8'))
root=Path(owned['root']).resolve()
assert root.is_relative_to(Path(tempfile.gettempdir()).resolve()) and root.name.startswith('scui-intent-')
db=root/'data/catalog.db'

def table_rows():
    with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as conn:
        return {r[0]: conn.execute('SELECT * FROM "' + r[0] + '" ORDER BY rowid').fetchall()
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
before = table_rows()
previous_http = json.loads((repo / '.tmp/scholar-track-decisions-http-v2.json').read_text(encoding='utf-8'))
parse_run_id = previous_http['parse_run_id']
field_id = before['research_fields'][0][0]
with closing(sqlite3.connect(db)) as conn:
    paper_id = conn.execute('SELECT sf.paper_id FROM parse_runs p JOIN source_file_versions sf ON sf.file_version_id=p.file_version_id WHERE p.parse_run_id=?', (parse_run_id,)).fetchone()[0]
    collection_id = conn.execute('SELECT collection_id FROM collection_memberships WHERE paper_id=?', (paper_id,)).fetchone()[0]
service = AcquisitionService(root)
app = create_app(root)
trace = []
@app.middleware('http')
async def observe(request, call_next):
    response = await call_next(request)
    trace.append({'method': request.method, 'path': request.url.path, 'status': response.status_code})
    return response
sock = socket.socket();sock.bind(('127.0.0.1', 0));sock.listen(128)
server = uvicorn.Server(uvicorn.Config(app, log_level='warning'))
thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True);thread.start()
out = repo / '.tmp/scholar-structured-intent-native-v2.json'
proof = {'status': 'STARTED_NEW_STRUCTURED_INTENT_CONTRACT', 'root': str(root),
         'source_database': str(source), 'source_database_sha256': parent['database_sha256'],
         'parent_receipt_sha256': sha(parent_path.read_bytes()), 'parse_run_id': parse_run_id,
         'scientific_approval': False, 'browser_verified': False, 'jobs': []}
def save():
    out.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding='utf-8')
def call(client, method, path, body=None, expected=200):
    response = client.request(method, path, json=body) if body else client.request(method, path)
    assert response.status_code == expected, response.text[:1500]
    return response.json()
try:
    deadline = time.monotonic() + 15
    while not server.started and thread.is_alive() and time.monotonic() < deadline:time.sleep(.05)
    assert server.started
    with httpx.Client(base_url=f'http://127.0.0.1:{sock.getsockname()[1]}', timeout=45) as client:
        progress = call(client, 'GET', f'/api/catalog/collections/{collection_id}/progress')
        if progress['status'] == 'PAUSED':
            call(client, 'POST', f'/api/catalog/collections/{collection_id}/resume', {'expected_revision': progress['revision']})
        request = {'paper_id': paper_id, 'parse_run_id': parse_run_id,
                   'reason': 'Explicit new located-intent contract verification; preserve prior generation and do not invent findings or gaps for this software document',
                   'idempotency_key': 'actual-structured-intent-contract-v1'}
        job = call(client, 'POST', f'/api/catalog/collections/{collection_id}/deep-read', request, expected=202)
        assert job['status'] == 'READY'
        proof.update(request=request, job_id=job['job_id']);save()
        os.environ['RSTV4_LLM_MODE'] = 'http'
        ROLE_QUEUES['model'] = ['MODEL_SKELETON']
        worker = AcquisitionWorker(root, 'model', model_gateway=UnlimitedLLMGateway(root), worker_id='actual-located-intent-v2')
        execution = worker.run_once()
        proof['jobs'].append(execution);save()
        assert execution['job_id'] == job['job_id'] and execution['status'] == 'SUCCEEDED', 'Keep actual failed task and returned model receipts; do not replay completed calls'
        published = json.loads(execution['result_json'])
        paper = call(client, 'GET', f'/api/catalog/papers/{paper_id}')
        new_calls = [c for c in paper['model_calls'] if c['job_id'] == job['job_id']]
        assert len(new_calls) == 12
        originals = [call(client, 'GET', f"/api/catalog/papers/{paper_id}/model-calls/{c['call_id']}") for c in new_calls]
        layer3 = [c for c in originals if c['task'] == 'skeleton_layer_3']
        assert len(layer3) == 3
        for c in layer3:
            assert c['status'] == 'RETURNED' and c['contract']['actual_model']
            assert c['contract']['prompt_version'] == INTENT_VERSION
            validate_intent(c['output'], c['input']['raw_text'])
            assert c['source']['parse_run_id'] == parse_run_id
        sources = call(client, 'GET', '/api/catalog/research/skeletons')['sources']
        current = next(s for s in sources if s['skeleton_id'] == published['skeleton_id'])
        assert current['prompt_version'] == 'paper-skeleton-v2-located-intent'
        assert current['parse_run_id'] == parse_run_id
        build = call(client, 'POST', '/api/catalog/fieldkg-actions', {'operation': 'CREATE_BUILD',
            'request_id': 'native-located-intent-build-v1', 'confirmed': True, 'field_id': field_id,
            'sources': {current['skeleton_id']: current['context_sha256']}})
        assert build['build']['semantic_coverage']['complete']
        # Actual software source may correctly produce no findings: report the model's
        # classification, never assert an intended scientific label or fabricate a Gap.
        proof.update(published=published, build_id=build['object_id'], source=current,
            actual_intents=[u['layer3']['intent'] for u in current['units']],
            actual_evidence_candidate_count=len(build['build']['evidence_candidates']),
            actual_gap_candidate_count=len(build['build']['candidate_gaps']), model_calls=originals)
        save()
        completed_again = call(client, 'POST', f'/api/catalog/collections/{collection_id}/deep-read', request, expected=202)
        assert completed_again['job_id'] == job['job_id'] and completed_again['status'] == 'SUCCEEDED'
    after = table_rows()
    fixed = ['papers', 'source_file_versions', 'parse_runs', 'paper_versions', 'document_blocks',
             'reference_entries', 'approval_grants', 'research_nodes', 'decisions', 'node_evidence',
             'manuscripts', 'manuscript_nodes', 'manuscript_evidence', 'fieldkg_snapshots',
             'fieldkg_snapshot_members', 'track_snapshot_adoptions', 'studio_model_calls']
    for name in fixed:assert after[name] == before[name], name
    for name in ['skeleton_runs', 'skeleton_checkpoints', 'paper_skeletons', 'skeleton_units', 'acquisition_model_call_events']:
        assert after[name][:len(before[name])] == before[name], name
    assert sha(source.read_bytes()) == parent['database_sha256']
    collection = service.get_collection(collection_id)
    service.pause_collection(collection_id, collection['revision'])
    proof.update(status='PASS_ACTUAL_STRUCTURED_INTENT_AND_NEW_BUILD', database_sha256=sha(db.read_bytes()),
                 actual_http_requests=len(trace), requests=trace, new_model_calls=len(originals),
                 old_generations_and_model_receipts_preserved=True, scientific_tables_unchanged=True,
                 source_database_unchanged=True, collection_paused=True, qualified_scientific_content=False)
    save()
    print(json.dumps({k: proof[k] for k in ['status', 'root', 'actual_intents', 'actual_evidence_candidate_count', 'actual_gap_candidate_count', 'new_model_calls', 'actual_http_requests', 'scientific_approval']}), flush=True)
finally:
    server.should_exit = True;thread.join(10);sock.close()
