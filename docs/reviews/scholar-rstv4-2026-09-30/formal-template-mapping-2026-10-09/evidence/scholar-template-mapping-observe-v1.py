import hashlib,json,sqlite3,sys
from pathlib import Path
import httpx
repo=Path(__file__).resolve().parents[1]
fixture=json.loads((repo/'.tmp/scholar-template-native-fixture-v1.json').read_text(encoding='utf-8'))
baseline=json.loads((repo/'.tmp/scholar-template-mapping-preflight-v1.json').read_text(encoding='utf-8'))
label,revision=sys.argv[1],int(sys.argv[2]);assert label.replace('-','').isalnum()
db=Path(fixture['root'])/'data/catalog.db';ms=fixture['native_manuscript_id'];raw=db.read_bytes()
with sqlite3.connect(f'{db.as_uri()}?mode=ro',uri=True) as conn:
    conn.row_factory=sqlite3.Row
    current={name:[dict(row) for row in conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid')] for name in baseline['before_tables']}
    changed=[name for name,rows in baseline['before_tables'].items() if rows!=current[name]]
    allowed={'manuscripts','studio_documents','studio_operations','studio_changes','studio_template_instances','studio_sample_candidates','studio_change_link_state'}
    assert set(changed)<=allowed,changed
    for name,rows in baseline['before_tables'].items():
        for row in rows:
            if name in {'manuscripts','studio_documents','studio_sample_candidates'} and row.get('manuscript_id')==ms:continue
            assert row in current[name],(name,row)
    record=dict(conn.execute('SELECT * FROM studio_documents WHERE manuscript_id=?',(ms,)).fetchone())
    assert record['revision']==revision
    document=json.loads(record['document_json'])
    ops=[dict(row) for row in conn.execute('SELECT * FROM studio_operations WHERE manuscript_id=? AND base_revision>=49 ORDER BY base_revision',(ms,))]
    assert [(op['base_revision'],op['resulting_revision']) for op in ops]==[(49+i,50+i) for i in range(revision-49)]
    chain=[];previous=baseline['workspace']['document']
    for op in ops:
        change=dict(conn.execute('SELECT * FROM studio_changes WHERE operation_id=?',(op['operation_id'],)).fetchone())
        before=json.loads(change['before_json']);after=json.loads(change['after_json'])
        assert before==previous and after==json.loads(op['payload_json'])['document'];previous=after
        chain.append({'operation':op,'change':change,'before':before,'after':after})
    assert previous==document
    source=baseline['workspace']['document']
    paragraphs=lambda doc:{p['id']:p for s in doc['sections'] for p in s['paragraphs']}
    assert {pid:paragraphs(document)[pid] for pid in paragraphs(source)}==paragraphs(source)
    assert document.get('argument_relations')==source.get('argument_relations')
    groups=lambda doc:[g for s in doc['sections'] for g in s.get('paragraph_groups',[])]
    assert groups(document)==groups(source)
    assert not conn.execute('SELECT 1 FROM studio_jobs WHERE manuscript_id=?',(ms,)).fetchone()
    schema=conn.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
with sqlite3.connect(f"{(repo/'.tmp/scholar-template-mapping-before-v1/catalog.db').as_uri()}?mode=ro",uri=True) as c:
    assert [tuple(row) for row in schema]==c.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
with httpx.Client(timeout=12) as client:
    response=client.get(f'http://127.0.0.1:8877/api/manuscripts/{ms}/workspace');response.raise_for_status();workspace=response.json()
    assert workspace['document_revision']==revision and workspace['document']==document
assert db.read_bytes()==raw
assert hashlib.sha256((Path(fixture['golden_root'])/'data/catalog.db').read_bytes()).hexdigest()==fixture['golden_database_sha256']
receipt={'status':'PASS_INDEPENDENT_RECORDS','label':label,'revision':revision,'document':document,'workspace':workspace,'operations':chain,
         'tables_verified':len(current),'changed_tables':changed,'schema_unchanged':True,'old_rows_preserved':True,
         'author_objects_exact':True,'native_jobs_added':0,'native_models_added':0,'golden_database_unchanged':True,'read_only_db_bytes_unchanged':True,
         'database_sha256':hashlib.sha256(raw).hexdigest()}
with (repo/f'.tmp/scholar-template-mapping-observe-{label}-v1.json').open('x',encoding='utf-8') as h:json.dump(receipt,h,indent=2,ensure_ascii=False)
print(json.dumps({k:v for k,v in receipt.items() if k not in {'document','workspace','operations'}},ensure_ascii=False))
