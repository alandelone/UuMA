import json
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
subprocess.run(['powershell','-NoProfile','-Command',(repo / '.tmp/scholar-collection-fixture-guard-v3.ps1').read_text(encoding='utf-8')],cwd=repo,check=True)
fixture = json.loads((repo / '.tmp/scholar-collection-native-v2.json').read_text(encoding='utf-8'))
request = {'field_id':fixture['field_id'],'topic_id':fixture['topic_id'],'track_id':fixture['track_id'],
           'name':'Actual concurrent software Collection','queries':['software concurrent fixture query'],
           'idempotency_key':'collection-concurrent-actual-native-v1'}
def create(_):
    with httpx.Client(base_url='http://127.0.0.1:8886',timeout=30) as client:
        response=client.post('/api/catalog/collections',json=request)
        assert response.status_code==201,response.text
        return response.json()
with ThreadPoolExecutor(max_workers=8) as pool:
    receipts=list(pool.map(create,range(8)))
assert all(row==receipts[0] for row in receipts)
collection=receipts[0]
with httpx.Client(base_url='http://127.0.0.1:8886',timeout=30) as client:
    detail=client.get('/api/catalog/collections/'+collection['collection_id']);assert detail.status_code==200
    assert detail.json()['counts']['jobs']==1
    paused=client.post('/api/catalog/collections/'+collection['collection_id']+'/pause',json={'expected_revision':collection['revision']})
    assert paused.status_code==200
with sqlite3.connect((Path(fixture['root'])/'data/catalog.db').as_uri()+'?mode=ro',uri=True) as conn:
    assert conn.execute("SELECT COUNT(*) FROM collections WHERE status!='PAUSED'").fetchone()[0]==0
    assert conn.execute('SELECT COUNT(*) FROM papers').fetchone()[0]==1
    assert conn.execute('SELECT COUNT(*) FROM paper_assessments').fetchone()[0]==0
    assert conn.execute('SELECT COUNT(*) FROM studio_model_calls').fetchone()[0]==0
proof={'status':'PASS_EIGHT_CONCURRENT_ACTUAL_HTTP_REQUESTS_ONE_COLLECTION_ONE_JOB',
       'browser_verified':False,'root':fixture['root'],'receipts':receipts,'collection_id':collection['collection_id'],
       'jobs':1,'all_fixture_collections_paused':True,'paper_candidates':1,'new_model_calls':0,'scientific_approval':False}
with (repo / '.tmp/scholar-collection-concurrent-native-v1.json').open('x',encoding='utf-8') as handle:
    json.dump(proof,handle,ensure_ascii=False,indent=2)
print('Eight concurrent actual HTTP creations returned the exact same Collection; one real queued job, no new models.')
