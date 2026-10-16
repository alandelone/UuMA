from pathlib import Path
import hashlib,json,sys
repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo/'.tmp/scholar-g11-parallel-v1'))
from runtime_copy_and_serve import snapshot
here=repo/'.tmp/scholar-block-menu-native-v1'
read=lambda p:json.loads(Path(p).read_text(encoding='utf8'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
r=read(here/'receipt.json');root=Path(r['root'])
def snap():
    result=snapshot(root/'data/catalog.db');result['schema']=[list(x) for x in result['schema']];return result
def put(name,value):
    with (here/name).open('x',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
def rows(s,name):
    t=s['tables'][name];return [dict(zip(t['columns'],x)) for x in t['rows']]
if sys.argv[1]=='before-delete':
    current=snap();assert current==read(here/'before110-all-tables.json')
    geometry=read(here/'native-hit-geometry.json')
    valid=[g for g in geometry if g['viewportName']=='wide1280' or g['viewportName']=='measured-narrow760']
    assert len(valid)==10
    for g in valid:
        assert g['viewport']['width']==(1280 if g['viewportName']=='wide1280' else 760)
        assert all(b['centerHitIsSelf'] and b['rect']['width']>0 and b['rect']['height']>0 for b in g['buttons'])
        for i,a in enumerate(g['buttons']):
            for b in g['buttons'][i+1:]:
                x,y=a['rect'],b['rect']
                assert min(x['right'],y['right'])<=max(x['left'],y['left']) or min(x['bottom'],y['bottom'])<=max(x['top'],y['top'])
    put('before-explicit-delete110.json',current)
    put('menu-readonly-audit.json',{'status':'PASS_FIVE_MENU_KINDS_TWO_MEASURED_WIDTHS','valid_cases':10,'prior_viewport_override_ineffective_five_cases_not_counted_as_narrow':True,'all110_exact_after_pointer_open_cancel':True,'author_revision':81,'models_jobs_business_mutations':0})
    print('PASS_TEN_MEASURED_GEOMETRY_CASES_FULL110_UNCHANGED')
elif sys.argv[1]=='after-undo':
    before=read(here/'before-explicit-delete110.json');after=snap();put('after-explicit-delete-undo110.json',after)
    assert before['schema']==after['schema']
    changed=[n for n in before['tables'] if before['tables'][n]!=after['tables'][n]]
    assert set(changed)<={'studio_documents','studio_operations','studio_changes','studio_change_link_state','manuscripts','studio_sample_candidates'}
    a,b=rows(before,'studio_documents')[0],rows(after,'studio_documents')[0]
    assert b['revision']==a['revision']+2==83
    assert json.loads(a['document_json'])==json.loads(b['document_json'])
    assert b['last_generated_revision']==a['last_generated_revision']==79
    assert b['active_generated_version_id']==a['active_generated_version_id']
    for name in set(before['tables'])-set(changed):assert before['tables'][name]==after['tables'][name]
    old_ids={x['operation_id'] for x in rows(before,'studio_operations')}
    operations=[x for x in rows(after,'studio_operations') if x['operation_id'] not in old_ids]
    assert len(operations)==2 and {x['operation_kind'] for x in operations}=={'DELETE_PARAGRAPH','UNDO'}
    deletion=next(x for x in operations if x['operation_kind']=='DELETE_PARAGRAPH')
    deleted_doc=json.loads(deletion['payload_json'])['document']
    paragraphs=lambda d:{p['id'] for s in d['sections'] for p in s['paragraphs']}
    assert paragraphs(json.loads(a['document_json']))-paragraphs(deleted_doc)=={'paragraph_2c105662a8c9486887b271348cc73b76'}
    put('delete-undo-audit.json',{'status':'PASS_EXPLICIT_POINTER_DELETE_AND_NATIVE_UNDO','before_revision':81,'after_revision':83,'deleted_only_declared_software_slot2':True,'entire_author_document_restored_exact':True,'all_generated_versions_calls_jobs_artifacts_checks_exact':True,'changed_tables':changed,'new_operations':[{'operation_id':x['operation_id'],'kind':x['operation_kind']} for x in operations],'all11_complete':False})
    print(json.dumps(read(here/'delete-undo-audit.json')))
else:raise ValueError('Unknown audit phase')
