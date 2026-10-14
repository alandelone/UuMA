import hashlib,json,sqlite3,sys,time
from pathlib import Path
import httpx
repo=Path(__file__).resolve().parents[1]
fixture=json.loads((repo/'.tmp/scholar-template-native-fixture-v1.json').read_text(encoding='utf-8'))
original=json.loads((repo/'.tmp/scholar-template-mapping-observe-chat-and-l2-unchanged-v1.json').read_text(encoding='utf-8'))['document']
label,expected=sys.argv[1],int(sys.argv[2]);ms=fixture['native_manuscript_id'];db=Path(fixture['root'])/'data/catalog.db'
with httpx.Client(timeout=12) as client:
    for _ in range(20):
        response=client.get(f'http://127.0.0.1:8877/api/manuscripts/{ms}/workspace');response.raise_for_status();body=response.json()
        if body['document_revision']==expected:break
        time.sleep(.25)
    assert body['document_revision']==expected
before=db.read_bytes()
with sqlite3.connect(f'{db.as_uri()}?mode=ro',uri=True) as c:
    c.row_factory=sqlite3.Row
    record=dict(c.execute('SELECT * FROM studio_documents WHERE manuscript_id=?',(ms,)).fetchone())
    ops=[dict(r) for r in c.execute('SELECT * FROM studio_operations WHERE manuscript_id=? AND base_revision>=61 ORDER BY base_revision',(ms,))]
    assert record['revision']==expected and json.loads(record['document_json'])==body['document']
    assert len(ops)==expected-61
    docs={61:original}
    for op in ops:
        change=dict(c.execute('SELECT * FROM studio_changes WHERE operation_id=?',(op['operation_id'],)).fetchone())
        assert json.loads(change['before_json'])==docs[op['base_revision']]
        docs[op['resulting_revision']]=json.loads(change['after_json'])
    assert not c.execute('SELECT 1 FROM studio_jobs WHERE manuscript_id=?',(ms,)).fetchone()
all_thoughts=lambda d:[t for s in d['sections'] for p in s['paragraphs'] for i in p['intents'] for t in i['thoughts']]
original_thoughts=all_thoughts(original)
for rev,doc in docs.items():
    assert [t for t in all_thoughts(doc) if t['id'] in {t['id'] for t in original_thoughts}]==original_thoughts
    assert doc.get('argument_relations')==original.get('argument_relations')
    cleaned=json.loads(json.dumps(doc))
    for s in cleaned['sections']:
        for p in s['paragraphs']:
            for i in p['intents']:i['thoughts']=[t for t in i['thoughts'] if t['id'] in {t['id'] for t in original_thoughts}]
    assert cleaned==original
if expected>=62:
    added=[t for t in all_thoughts(docs[62]) if t['id'] not in {t['id'] for t in original_thoughts}]
    assert len(added)==1 and added[0]['text']=='' and added[0]['citation_mode']=='PENDING' and added[0]['citations']==[]
if expected>=63:
    thought=next(t for t in all_thoughts(docs[63]) if t['id']==added[0]['id'])
    assert thought=={**added[0],'text':'\n'} and len(all_thoughts(docs[63]))==3
if expected>=64:assert docs[64]==docs[62]
if expected>=65:assert docs[65]==docs[61]
assert db.read_bytes()==before
result={'status':'PASS_NATIVE_THOUGHT_KEYS_INDEPENDENT_RECORDS','label':label,'revision':expected,'document':body['document'],'operations':ops,'documents_by_revision':docs,'original_words_ids_citations_and_attachments_exact':True,'new_thought_only_empty_then_newline':True,'no_models_or_generation':True,'read_only_database_unchanged':True,'db_sha256':hashlib.sha256(before).hexdigest()}
with (repo/f'.tmp/scholar-template-mapping-thought-{label}-v1.json').open('x',encoding='utf-8') as h:json.dump(result,h,indent=2,ensure_ascii=False)
print(json.dumps({k:v for k,v in result.items() if k not in ['document','operations','documents_by_revision']}))
