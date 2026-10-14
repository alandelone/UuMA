import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
info = json.loads((repo / '.tmp/scholar-template-native-fixture-v1.json').read_text(encoding='utf-8'))
db = Path(info['root']) / 'data/catalog.db'
ms = info['native_manuscript_id']
initial = info['initial_document']
def paragraphs(document):
    return [p for s in document['sections'] for p in s['paragraphs']]
def thoughts(document):
    return {t['id']:t for p in paragraphs(document) for i in p['intents'] for t in i['thoughts']}
def formulas(document):
    return Counter(json.dumps(f,sort_keys=True) for p in paragraphs(document) for f in p.get('formulas',[]))
def assets(document):
    return Counter(a for p in paragraphs(document) for a in p.get('asset_ids',[]))
with sqlite3.connect(f'{db.as_uri()}?mode=ro', uri=True) as conn:
    conn.row_factory = sqlite3.Row
    document_row = dict(conn.execute('SELECT * FROM studio_documents WHERE manuscript_id=?',(ms,)).fetchone())
    operations = [dict(row) for row in conn.execute('SELECT * FROM studio_operations WHERE manuscript_id=? ORDER BY resulting_revision',(ms,))]
    assert document_row['revision'] == 27 and json.loads(document_row['document_json']) == initial
    assert len(operations) == 27
    expected = [(0,1,'EDIT'),(1,2,'ADOPT_TEMPLATE'),(2,3,'UNDO'),(3,4,'ADOPT_TEMPLATE'),(4,5,'EDIT'),(5,6,'UNDO'),(6,7,'UNDO'),(7,8,'ADOPT_TEMPLATE'),(8,9,'UNDO')]
    expected += [(base,base+1,'ADOPT_TEMPLATE' if base % 2 else 'UNDO') for base in range(9,27)]
    assert [(op['base_revision'],op['resulting_revision'],op['operation_kind']) for op in operations] == expected
    templates = [dict(row) for row in conn.execute('SELECT * FROM studio_template_instances WHERE manuscript_id=? ORDER BY rowid',(ms,))]
    assert len(templates) == 12
    requests = [json.loads(row['adopted_json'])['request'] for row in templates]
    assert [(r['base_revision'],r['mode'],len(r['selected_unit_ids'])) for r in requests[:3]] == [(1,'INSERT',1),(3,'REPLACE',3),(7,'INSERT',1)]
    assert [(r['scope_type'],r['mode']) for r in requests[3:11]] == [(scope,mode) for scope in ['paper','section','paragraph','intent'] for mode in ['INSERT','REPLACE']]
    assert [(r['base_revision'],len(r['selected_unit_ids'])) for r in requests[3:11]] == [(9+2*i,1 if i==0 else 3) for i in range(8)]
    assert requests[-1]['base_revision'] == 25 and requests[-1]['scope_type'] == 'paragraph' and requests[-1]['mode'] == 'REPLACE' and len(requests[-1]['selected_unit_ids']) == 1
    chain = []
    for op in operations[9:]:
        doc = json.loads(op['payload_json'])['document']
        change = dict(conn.execute('SELECT * FROM studio_changes WHERE operation_id=?',(op['operation_id'],)).fetchone())
        assert json.loads(change['after_json']) == doc
        assert thoughts(doc) == thoughts(initial)
        assert formulas(doc) == formulas(initial) and assets(doc) == assets(initial)
        assert all(not t['text'].startswith('SOFTWARE_SOURCE_') for t in thoughts(doc).values())
        if op['operation_kind'] == 'UNDO':
            assert doc == initial and change['is_compensating'] == 1
        else:
            request = next(r for r in requests if r['operation_id'] == op['operation_id'])
            assert json.loads(change['before_json']) == initial
            assert bool([s for s in doc['sections'] if s.get('placement_status') == 'UNPLACED']) == (request['mode'] == 'REPLACE')
            assert request['replace_confirmed'] == (request['mode'] == 'REPLACE')
        assert not json.loads(op['payload_json'])['comment_ids']
        chain.append({'base_revision':op['base_revision'],'resulting_revision':op['resulting_revision'],
                      'operation_id':op['operation_id'],'kind':op['operation_kind'],'change_id':change['change_id'],
                      'exact_author_thoughts_citations_assets_formulas':True,'compensating':bool(change['is_compensating'])})
    assert not conn.execute('SELECT 1 FROM studio_jobs WHERE manuscript_id=?',(ms,)).fetchone()
    current = {table:[dict(row) for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid')] for table in info['before_native_tables']}
    allowed = {'manuscripts','studio_documents','studio_operations','studio_changes','studio_template_instances','studio_sample_candidates','studio_change_link_state'}
    changed = [table for table,before in info['before_native_tables'].items() if current[table] != before]
    assert set(changed) <= allowed, changed
    for table,before in info['before_native_tables'].items():
        for old in before:
            if table in {'manuscripts','studio_documents'} and old.get('manuscript_id') == ms:
                continue
            assert old in current[table], (table,old)
before_bytes = db.read_bytes()
with httpx.Client(base_url='http://127.0.0.1:8877/api',timeout=15) as client:
    response = client.post(f'/manuscripts/{ms}/template-adoption',json=requests[-1])
    assert response.status_code == 200, response.text
    replay = response.json()
    assert replay['idempotent_replay'] and replay['document_revision'] == 27 and replay['document'] == initial
    assert replay['operation']['resulting_revision'] == 26 and replay['operation']['operation_id'] == requests[-1]['operation_id']
assert db.read_bytes() == before_bytes, 'Retry after Undo must not write or restore the adoption'
assert hashlib.sha256((Path(info['golden_root'])/'data/catalog.db').read_bytes()).hexdigest() == info['golden_database_sha256']
result = {'status':'PASS_EXACT_8_NATIVE_SCOPE_MODE_CASES_AND_PRODUCTION_REPLACEMENT',
          'revision':27,'exact_initial_document_restored':True,'actual_chain':chain,'requests':requests,
          'template_instances':12,'native_cases':8,'production_cases':1,'post_undo_http_replay':replay,
          'post_undo_retry_entire_database_byte_equal':True,'old_rows_preserved':True,'changed_tables':changed,
          'global_model_tables_unchanged':True,'native_generation_jobs_added':0,'golden_bytes_unchanged':True}
with (repo / '.tmp/scholar-template-native-checkpoint-v3.json').open('x',encoding='utf-8') as handle:
    json.dump(result,handle,indent=2,ensure_ascii=False)
print(json.dumps({k:v for k,v in result.items() if k not in {'actual_chain','requests','post_undo_http_replay'}},ensure_ascii=False))
