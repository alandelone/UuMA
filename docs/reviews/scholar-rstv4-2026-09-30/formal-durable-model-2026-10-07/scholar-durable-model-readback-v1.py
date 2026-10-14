import hashlib
import json
import socket
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from rstv4.catalog_web import create_app

repo = Path(__file__).resolve().parents[1]
native = json.loads((repo / '.tmp/scholar-durable-model-native-v1.json').read_text(encoding='utf-8'))
root = Path(native['root']).resolve()
db = root / 'data/catalog.db'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
before = sha(db.read_bytes())
app = create_app(root)
assert sha(db.read_bytes()) == before
sock = socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
server = uvicorn.Server(uvicorn.Config(app, log_level='warning'))
thread = threading.Thread(target=server.run, kwargs={'sockets':[sock]}, daemon=True);thread.start()
trace = []
def call(client, path):
    response = client.get(path);assert response.status_code == 200, response.text[:1000]
    trace.append({'path':path,'status':response.status_code})
    return response.json()
try:
    deadline = time.monotonic()+15
    while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.05)
    assert server.started
    with httpx.Client(base_url=f'http://127.0.0.1:{sock.getsockname()[1]}',timeout=10) as client:
        paper_id = native['request']['paper_id']
        paper = call(client, f'/api/catalog/papers/{paper_id}')
        current = [c for c in paper['model_calls'] if (c.get('contract') or {}).get('router_run_id') == 'run_2147b77dd2f14b939ec55f589d8f653f']
        assert len(current) == 1 and current[0]['status'] == 'WAITING'
        original = call(client, f"/api/catalog/papers/{paper_id}/model-calls/{current[0]['call_id']}")
        assert original['source']['parse_run_id'] == native['parse_run_id']
        assert original['input']['raw_text'] and original['output'] is None
        assert original['contract']['transport_operation_id'] == original['source']['transport_operation_id']
        progress = call(client, f"/api/catalog/collections/{native['jobs'][0]['collection_id']}/progress")
    with httpx.Client(base_url='http://127.0.0.1:8080',timeout=10,headers={'Authorization':'Bearer local-router'}) as client:
        vendor = call(client, '/v1/runs/run_2147b77dd2f14b939ec55f589d8f653f')
    assert sha(db.read_bytes()) == before
    proof = {'status':'PASS_ACTUAL_WAITING_MODEL_RECEIPT_READBACK', 'root':str(root),
        'database_sha256':before,'database_unchanged':True,'requests':trace,
        'actual_http_requests':len(trace),'call':original,
        'vendor':{k:vendor.get(k) for k in ['id','status','attempts','current_provider','current_model','waiting_reason','last_attempt_status']},
        'new_model_submissions':0,'new_scientific_approval':False,'new_intent_pipeline_verified':False,
        'observed_at':time.time(),'browser_verified':False}
    with (repo/'.tmp/scholar-durable-model-readback-v1.json').open('x',encoding='utf-8') as handle:
        json.dump(proof,handle,ensure_ascii=False,indent=2)
    print(json.dumps({'status':proof['status'],'requests':len(trace),'vendor_status':vendor['status'],'new_model_submissions':0,'database_unchanged':True}),flush=True)
finally:
    server.should_exit=True;thread.join(10);sock.close()
