"""Resume the existing native semantic operation; retain every source table."""
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
audit = json.loads((repo / '.tmp/scholar-experiment-controls-source-audit-v1.json').read_text())
root = Path(audit['root']).resolve()
assert root.name == 'scui-intent-beqtn_vr'
db = root / 'data/catalog.db'
output = repo / '.tmp/scholar-source-build-resume-v2.json'
assert not output.exists()

def rows():
    with sqlite3.connect(db.as_uri()+'?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {n: [dict(r) for r in conn.execute('SELECT * FROM "'+n+'" ORDER BY rowid')] for n in names}

def hashes(tables):
    return {n: hashlib.sha256(json.dumps(rs,sort_keys=True,ensure_ascii=False).encode()).hexdigest() for n,rs in tables.items()}

initial = rows()
run_row = next(r for r in initial['fieldkg_semantic_runs'] if r['request_id']=='native-current-source-semantics-v1')
field, run_id, build_id = run_row['field_id'], run_row['run_id'], run_row['build_id']
assert run_id == 'semantic_run_d268a4e7ed0ff7274e99ddc91aa42c13'
assert run_row['router_run_id'] == 'run_f69fcf0f8b224b99851df0fdb1ce4bc3'
action = next(r for r in initial['research_workspace_actions'] if r['request_id']=='native-current-source-build-v1')
created = json.loads(action['result_json'])
assert created['object_id']==build_id
build = created['build']
assert [s['skeleton_id'] for s in build['sources']]==[audit['skeleton']['skeleton_id']]
assert not build['evidence_candidates'] and not build['candidate_gaps']
assert build['semantic_coverage']['typed_units']==3 and build['semantic_coverage']['unknown_units']==1
assert next(r for r in initial['sqlite_sequence'] if r['name']=='research_workspace_actions')['seq'] == max(r['action_seq'] for r in initial['research_workspace_actions'])
assert next(r for r in initial['paper_skeletons'] if r['skeleton_id']==audit['skeleton']['skeleton_id'])==audit['skeleton']
assert [r for r in initial['skeleton_units'] if r['skeleton_id']==audit['skeleton']['skeleton_id']]==audit['units']

app = create_app(root)
assert rows()==initial, 'Application preparation must not change stored source or action records.'
sock=socket.socket(); sock.bind(('127.0.0.1',0)); sock.listen(128)
server=uvicorn.Server(uvicorn.Config(app,log_level='warning'))
thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True)
thread.start()
trace=[]
proof={'root':str(root),'field_id':field,'build_id':build_id,'run_id':run_id,
       'original_router_run_id':run_row['router_run_id'],'original_build_receipt':created,
       'before_table_sha256':hashes(initial),'scientific_approval':False,
       'v1_failure_retained':True,'v1_before_hashes_not_saved':True,
       'sequence_contract':'research_workspace_actions uses action_seq INTEGER PRIMARY KEY AUTOINCREMENT; SQLite also changes sqlite_sequence on a new action. The failed v1 omitted this table; its complete before hashes were not saved and are not reconstructed.'}
try:
    deadline=time.monotonic()+15
    while not server.started and time.monotonic()<deadline:
        time.sleep(.05)
    assert server.started
    with httpx.Client(base_url=f'http://127.0.0.1:{sock.getsockname()[1]}',timeout=30) as client:
        def call(method,path,expected=200,**kwargs):
            res=client.request(method,path,**kwargs)
            trace.append({'method':method,'path':path,'status':res.status_code})
            assert res.status_code==expected,res.text[:2000]
            return res.json()
        assert call('POST','/api/catalog/fieldkg-actions',json=json.loads(action['request_json']))==created
        before=call('GET',f'/api/catalog/fields/{field}/semantic-runs/{run_id}')
        assert call('POST','/api/catalog/fieldkg-semantic-runs',201,json=before['request'])==before
        advanced=call('POST',f'/api/catalog/fields/{field}/semantic-runs/{run_id}/advance',json={})
        assert call('GET',f'/api/catalog/fields/{field}/semantic-runs/{run_id}')==advanced
        assert advanced['router_run_id']==run_row['router_run_id'], 'Resume must consume the exact existing vendor handle.'
        proof.update(before_semantic_run=before,semantic_run=advanced)
finally:
    server.should_exit=True; thread.join(15); sock.close(); app.state.discussions.shutdown()
after=rows()
changed=[n for n in initial if initial[n]!=after[n]]
proof.update(requests=trace,changed_tables=changed,after_table_sha256=hashes(after))
# Persist actual observations before checks, including an unexpected failure.
with output.open('x',encoding='utf-8') as h: json.dump(proof,h,ensure_ascii=False,indent=2)
assert set(changed)<= {'fieldkg_semantic_runs','fieldkg_semantic_objects'}, changed
assert initial['sqlite_sequence']==after['sqlite_sequence']
assert initial['acquisition_model_call_events']==after['acquisition_model_call_events']
assert len(audit['calls'])==12 and all(c['status']=='RETURNED' for c in audit['calls'])
assert len(after['fieldkg_builds'])==len(initial['fieldkg_builds'])
assert len(after['fieldkg_semantic_runs'])==len(initial['fieldkg_semantic_runs'])
objects=[r for r in after['fieldkg_semantic_objects'] if r['run_id']==run_id]
assert all(r['status']=='PROPOSED' and r['reviewed_at'] is None for r in objects)
proof.update(status='PASS_EXACT_NATIVE_BUILD_RESUME_AND_SOURCE_INVARIANCE',
             source_tables_unchanged=True,original_12_model_calls_unchanged=True,
             native_semantic_objects=objects)
output.write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':proof['status'],'semantic_status':advanced['status'],
                  'router_run_id':advanced['router_run_id'],'object_count':len(objects),
                  'changed_tables':changed,'actual_http':len(trace)},ensure_ascii=False),flush=True)
