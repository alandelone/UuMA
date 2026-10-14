import hashlib
import json
import socket
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

import httpx
import uvicorn
from rstv4.catalog_web import create_app

repo=Path(__file__).resolve().parents[1]
original=json.loads((repo/'.tmp/scholar-fieldkg-semantics-native-v1.json').read_text(encoding='utf-8'))
fixture=json.loads((repo/'.tmp/scholar-fieldkg-semantics-fixture-v1.json').read_text(encoding='utf-8'))
root=Path(original['root']).resolve();db=root/'data/catalog.db'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
def snapshot():
    with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as conn:
        return {row[0]:conn.execute('SELECT * FROM "'+row[0]+'" ORDER BY rowid').fetchall()
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
before=snapshot();before_sha=sha(db.read_bytes())
app=create_app(root)
assert snapshot()==before and sha(db.read_bytes())==before_sha
sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
server=uvicorn.Server(uvicorn.Config(app,log_level='warning'))
thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
trace=[]
try:
    deadline=time.monotonic()+15
    while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.05)
    assert server.started
    with httpx.Client(base_url=f'http://127.0.0.1:{sock.getsockname()[1]}',timeout=10) as client:
        def call(path,body=None,expected=200):
            response=client.post(path,json=body) if body is not None else client.get(path)
            assert response.status_code==expected,response.text[:1000]
            trace.append({'path':path,'status':response.status_code});return response.json()
        field=fixture['field_id'];data=call(f'/api/catalog/fields/{field}/workspace')
        assert len(data['semantic_objects'])==7 and all(o['status']=='ACCEPTED' for o in data['semantic_objects'])
        fixed=call(f"/api/catalog/fields/{field}/workspace?snapshot={data['snapshots'][0]['snapshot_id']}")['selected_snapshot']
        assert fixed['members_match'] and len(fixed['frozen_semantic_objects'])==7
        for obj in fixed['frozen_semantic_objects']:
            target={'module':'FIELDKG','field_id':field,'object_kind':'semantic','object_id':obj['object_id'],'snapshot_id':fixed['snapshot_id']}
            context=call('/api/research/discussion/context',target)
            assert obj['references'][0]['quote'] in context['object_text']
        for table in ['research_nodes','decisions','approval_grants','manuscripts','studio_model_calls']:
            assert not before[table],table
        assert snapshot()==before and sha(db.read_bytes())==before_sha
finally:
    server.should_exit=True;thread.join(10);sock.close()
assert snapshot()==before and sha(db.read_bytes())==before_sha
proof={'status':'PASS_SAME_SEMANTIC_FIXTURE_POST_CLOSE_READBACK','root':str(root),'database_sha256':before_sha,
       'all_table_rows_unchanged':len(before),'requests':trace,'actual_http_requests':len(trace),
       'model_is_explicit_software_fixture':True,'new_model_calls':0,'scientific_approval':False,'browser_verified':False,
       'prior_pre_close_sha256':original['database_sha256'],'prior_pre_close_wal_hash_failure_retained':True}
with (repo/'.tmp/scholar-fieldkg-semantics-native-readback-v2.json').open('x',encoding='utf-8') as handle:json.dump(proof,handle,indent=2)
print(json.dumps({k:v for k,v in proof.items() if k!='requests'}),flush=True)
