import hashlib
import json
import socket
import sqlite3
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from rstv4.catalog_web import create_app

repo = Path(__file__).resolve().parents[1]
source = json.loads((repo / '.tmp/scholar-experiment-controls-source-audit-v1.json').read_text())
root = Path(source['root']).resolve()
assert root.name == 'scui-intent-beqtn_vr'
sk = source['skeleton']['skeleton_id']
db = root / 'data/catalog.db'
output = repo / '.tmp/scholar-source-build-native-v1.json'
assert not output.exists()
app = create_app(root)
def table_hashes():
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {n: hashlib.sha256(json.dumps(conn.execute('SELECT * FROM "'+n+'" ORDER BY rowid').fetchall(),ensure_ascii=False).encode()).hexdigest() for n in names}
before = table_hashes()
with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
    field = conn.execute('SELECT field_id FROM research_fields').fetchone()[0]
sock = socket.socket(); sock.bind(('127.0.0.1', 0)); sock.listen(128)
server = uvicorn.Server(uvicorn.Config(app, log_level='warning'))
thread = threading.Thread(target=server.run, kwargs={'sockets':[sock]}, daemon=True)
thread.start()
trace = []
proof = {'root':str(root),'field_id':field,'skeleton_id':sk,'scientific_approval':False}
try:
    deadline = time.monotonic()+15
    while not server.started and time.monotonic()<deadline:
        time.sleep(.05)
    assert server.started
    with httpx.Client(base_url=f'http://127.0.0.1:{sock.getsockname()[1]}',timeout=30) as client:
        def call(method, path, expected=200, **kwargs):
            response=client.request(method,path,**kwargs)
            trace.append({'method':method,'path':path,'status':response.status_code})
            assert response.status_code==expected,response.text[:1500]
            return response.json()
        sources=call('GET','/api/catalog/research/skeletons')['sources']
        selected=next(s for s in sources if s['skeleton_id']==sk)
        assert len(selected['units'])==3
        body={'operation':'CREATE_BUILD','request_id':'native-current-source-build-v1',
              'field_id':field,'sources':{sk:selected['context_sha256']},'confirmed':True}
        created=call('POST','/api/catalog/fieldkg-actions',json=body)
        assert call('POST','/api/catalog/fieldkg-actions',json=body)==created
        build=created['build']
        assert [s['skeleton_id'] for s in build['sources']]==[sk]
        assert not build['evidence_candidates'] and not build['candidate_gaps']
        assert build['semantic_coverage']['typed_units']==3
        assert build['semantic_coverage']['unknown_units']==1
        sem_body={'request_id':'native-current-source-semantics-v1','field_id':field,
                  'build_id':build['build_id'],'expected_context_sha256':build['context_sha256'],'confirmed':True}
        run=call('POST','/api/catalog/fieldkg-semantic-runs',201,json=sem_body)
        assert call('POST','/api/catalog/fieldkg-semantic-runs',201,json=sem_body)==run
        advanced=call('POST',f"/api/catalog/fields/{field}/semantic-runs/{run['run_id']}/advance",json={})
        current=call('GET',f"/api/catalog/fields/{field}/semantic-runs/{run['run_id']}")
        assert advanced==current
        proof.update(build_id=build['build_id'],build=build,semantic_run=current)
finally:
    server.should_exit=True; thread.join(15); sock.close(); app.state.discussions.shutdown()
after=table_hashes()
changed=[n for n in before if before[n]!=after[n]]
assert set(changed)<= {'fieldkg_builds','fieldkg_build_papers','research_workspace_actions','fieldkg_semantic_runs','fieldkg_semantic_objects'}
proof.update(status='PASS_ACTUAL_3_UNIT_BUILD_AND_SEMANTIC_REQUEST',requests=trace,
             changed_tables=changed,source_tables_unchanged=True,before_table_sha256=before,after_table_sha256=after)
with output.open('x',encoding='utf-8') as h:
    json.dump(proof,h,ensure_ascii=False,indent=2)
print(json.dumps({'status':proof['status'],'build_id':proof['build_id'],
                  'semantic_status':proof['semantic_run']['status'],
                  'router_run_id':proof['semantic_run']['router_run_id'],
                  'candidate_count':0,'gap_count':0,'actual_http':len(trace)}),flush=True)
