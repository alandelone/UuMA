import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

import httpx

repo=Path(__file__).resolve().parents[1]
fixture=json.loads((repo/'.tmp/scholar-template-native-fixture-v1.json').read_text(encoding='utf-8'))
baseline=json.loads((repo/'.tmp/scholar-hierarchy-preflight-v1.json').read_text(encoding='utf-8'))
db=Path(fixture['root'])/'data/catalog.db';ms=fixture['native_manuscript_id']
original=fixture['initial_document']
def paragraphs(doc):return [p for s in doc['sections'] for p in s['paragraphs']]
def thoughts(doc):return {t['id']:t for p in paragraphs(doc) for i in p['intents'] for t in i['thoughts']}
def formulas(doc):return Counter(json.dumps(f,sort_keys=True) for p in paragraphs(doc) for f in p.get('formulas',[]))
def assets(doc):return Counter(a for p in paragraphs(doc) for a in p.get('asset_ids',[]))
def schema(path):
    with sqlite3.connect(f'{path.as_uri()}?mode=ro',uri=True) as c:
        return c.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
assert schema(db)==schema(repo/'.tmp/scholar-hierarchy-before-v1/catalog.db')
with sqlite3.connect(f'{db.as_uri()}?mode=ro',uri=True) as conn:
    conn.row_factory=sqlite3.Row
    current={name:[dict(row) for row in conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid')] for name in baseline['before_tables']}
    allowed={'manuscripts','studio_documents','studio_operations','studio_changes','studio_template_instances','studio_sample_candidates','studio_change_link_state'}
    changed=[name for name,rows in baseline['before_tables'].items() if rows!=current[name]]
    assert set(changed)<=allowed,changed
    for name,rows in baseline['before_tables'].items():
        for row in rows:
            if name in {'manuscripts','studio_documents','studio_sample_candidates'} and row.get('manuscript_id')==ms:continue
            assert row in current[name],(name,row)
    ops=[dict(row) for row in conn.execute('SELECT * FROM studio_operations WHERE manuscript_id=? AND base_revision>=27 ORDER BY base_revision',(ms,))]
    expected=['ADD_SUBSECTION','EDIT','ADD_SUBSECTION','EDIT','DELETE_PARAGRAPH_GROUP','UNDO','MOVE_BLOCKS','ADD_ARGUMENT_RELATION','DELETE_ARGUMENT_RELATION','UNDO','REPARENT_SECTION','UNDO','EDIT_ARGUMENT_RELATION','DELETE_ARGUMENT_RELATION','UNDO','DELETE_SECTION_TREE','UNDO','REDO','UNDO','REPARENT_SECTION','ADOPT_TEMPLATE','UNDO']
    assert [(o['base_revision'],o['resulting_revision'],o['operation_kind']) for o in ops]==[(27+i,28+i,kind) for i,kind in enumerate(expected)]
    chain=[];previous=original
    for op in ops:
        change=dict(conn.execute('SELECT * FROM studio_changes WHERE operation_id=?',(op['operation_id'],)).fetchone())
        before=json.loads(change['before_json']);after=json.loads(change['after_json'])
        assert before==previous and after==json.loads(op['payload_json'])['document']
        previous=after
        deleted=op['base_revision'] in {31,42,44}
        if deleted:
            assert not paragraphs(after) and not after.get('argument_relations')
        else:
            assert thoughts(after)==thoughts(original)
            assert formulas(after)==formulas(original) and assets(after)==assets(original)
            assert {p['id']:p for p in paragraphs(after) if p['id'] in {p['id'] for p in paragraphs(original)}}=={p['id']:p for p in paragraphs(original)}
            assert [g for s in after['sections'] for g in s.get('paragraph_groups',[])]==original['sections'][0]['paragraph_groups']
        if op['operation_kind']=='UNDO':assert change['is_compensating']==1
        chain.append({'operation':op,'change':change,'before':before,'after':after})
    by_base={entry['operation']['base_revision']:entry for entry in chain}
    assert by_base[32]['after']==by_base[31]['before']
    assert by_base[33]['after']['sections'][2]['paragraphs']==original['sections'][0]['paragraphs']
    assert by_base[36]['after']==by_base[35]['before']
    assert by_base[39]['before']['argument_relations'][0]['id']==by_base[39]['after']['argument_relations'][0]['id']
    assert by_base[39]['after']['argument_relations'][0]['relation']=='Independent durable comparison Ω v2'
    assert by_base[41]['after']==by_base[40]['before']
    assert by_base[43]['after']==by_base[42]['before']==by_base[45]['after']
    assert by_base[44]['after']==by_base[42]['after']
    nested=by_base[47]['before'];adopted=by_base[47]['after']
    parent,child,grand=nested['sections']
    assert child['parent_section_id']==parent['id'] and grand['parent_section_id']==child['id']
    old=next(s for s in adopted['sections'] if s['id']==child['id'])
    assert old['placement_status']=='UNPLACED' and 'parent_section_id' not in old
    assert old['unplaced_parent_section_id']==parent['id']
    old_grand=next(s for s in adopted['sections'] if s['id']==grand['id'])
    assert old_grand['parent_section_id']==child['id'] and old_grand['placement_status']=='UNPLACED'
    assert all(s['parent_section_id']==parent['id'] for s in adopted['sections'][1:3])
    assert adopted['argument_relations']==nested['argument_relations']
    assert by_base[48]['after']==nested
    row=dict(conn.execute('SELECT * FROM studio_documents WHERE manuscript_id=?',(ms,)).fetchone())
    assert row['revision']==49 and json.loads(row['document_json'])==nested
    assert not conn.execute('SELECT 1 FROM studio_jobs WHERE manuscript_id=?',(ms,)).fetchone()
    template=dict(conn.execute('SELECT * FROM studio_template_instances WHERE manuscript_id=? ORDER BY rowid DESC LIMIT 1',(ms,)).fetchone())
    request=json.loads(template['adopted_json'])['request']
    assert request['base_revision']==47 and request['scope_type']=='section' and request['scope_id']==child['id'] and request['mode']=='REPLACE'
before=db.read_bytes()
with httpx.Client(base_url='http://127.0.0.1:8877/api',timeout=15) as client:
    response=client.post(f'/manuscripts/{ms}/template-adoption',json=request)
    response.raise_for_status();replay=response.json()
    assert replay['idempotent_replay'] and replay['document_revision']==49 and replay['document']==nested
    assert replay['operation']['resulting_revision']==48
    response=client.get(f'/manuscripts/{ms}/workspace');response.raise_for_status()
    assert response.json()['document_revision']==49 and response.json()['document']==nested
assert db.read_bytes()==before
assert hashlib.sha256((Path(fixture['golden_root'])/'data/catalog.db').read_bytes()).hexdigest()==fixture['golden_database_sha256']
result={'status':'PASS_22_ACTUAL_OPERATIONS_AND_EXACT_UNDO','revision':49,'schema_unchanged':True,
        'tables_verified':len(current),'changed_tables':changed,'old_rows_preserved':True,'actual_chain':chain,
        'native_models_added':0,'native_jobs_added':0,'current_document':nested,'post_undo_http_replay':replay,
        'post_undo_retry_entire_database_byte_equal':True,'golden_bytes_unchanged':True,
        'rapid_actions_coalesced_not_individual_passes':True,'unexpected_group_delete_compensated':True}
with (repo/'.tmp/scholar-hierarchy-native-final-v1.json').open('x',encoding='utf-8') as h:json.dump(result,h,indent=2,ensure_ascii=False)
print(json.dumps({k:v for k,v in result.items() if k not in {'actual_chain','current_document','post_undo_http_replay'}},ensure_ascii=False))
