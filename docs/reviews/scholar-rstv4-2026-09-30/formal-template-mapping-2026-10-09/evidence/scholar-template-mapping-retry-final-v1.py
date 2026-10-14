import hashlib,json,sqlite3
from pathlib import Path
import httpx
repo=Path(__file__).resolve().parents[1]
fixture=json.loads((repo/'.tmp/scholar-template-native-fixture-v1.json').read_text(encoding='utf-8'))
db=Path(fixture['root'])/'data/catalog.db';ms=fixture['native_manuscript_id'];before=db.read_bytes()
with sqlite3.connect(f'{db.as_uri()}?mode=ro',uri=True) as conn:
    conn.row_factory=sqlite3.Row
    template=dict(conn.execute('SELECT * FROM studio_template_instances WHERE manuscript_id=? ORDER BY rowid DESC LIMIT 1',(ms,)).fetchone())
    document=json.loads(conn.execute('SELECT document_json FROM studio_documents WHERE manuscript_id=?',(ms,)).fetchone()[0])
request=json.loads(template['adopted_json'])['request'];assert request['base_revision']==55 and request['mode']=='REPLACE'
with httpx.Client(base_url='http://127.0.0.1:8877/api',timeout=15) as client:
    response=client.post(f'/manuscripts/{ms}/template-adoption',json=request);response.raise_for_status();body=response.json()
    assert body['document_revision']==61 and body['document']==document
    assert body['adoption']['template_instance_id']==template['template_instance_id']
assert db.read_bytes()==before
result={'status':'PASS_HTTP_EXACT_RETRY_AFTER_UNDO','request':request,'response':body,'current_revision':61,'original_resulting_revision':56,'whole_database_unchanged':True,'native_browser_retry':False,'db_sha256':hashlib.sha256(before).hexdigest()}
with (repo/'.tmp/scholar-template-mapping-retry-final-v1.json').open('x',encoding='utf-8') as h:json.dump(result,h,indent=2,ensure_ascii=False)
print(json.dumps({k:v for k,v in result.items() if k not in ['request','response']}))
