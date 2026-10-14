"""Read back native edits, source provenance, guards, and actual file parsers."""
import hashlib
import json
import sqlite3
from pathlib import Path

import httpx

repo=Path(__file__).resolve().parents[1]
info=json.loads((repo/'.tmp/scholar-revision-isolated-services-v1.json').read_text())
root=Path(info['root']).resolve();golden=Path(info['golden_root']).resolve()
assert root.name=='scui-revision-native-p48co4i6' and root!=golden
db=root/'data/catalog.db';ms=info['manuscripts']['revision']
output=repo/'.tmp/scholar-revision-native-audit-v3.json'
assert not output.exists()
sha=lambda raw:hashlib.sha256(raw).hexdigest()

def tables(path):
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as conn:
        conn.row_factory=sqlite3.Row
        names=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {n:[dict(r) for r in conn.execute('SELECT * FROM "'+n+'" ORDER BY rowid')] for n in names}

before=sha(db.read_bytes()); original=tables(golden/'data/catalog.db'); current=tables(db)
assert sha((golden/'data/catalog.db').read_bytes())==info['golden_database_sha256']
changed=[n for n in original if original[n]!=current[n]]
allowed={'studio_artifacts','review_comments','comment_changes','studio_documents','manuscripts','studio_operations','studio_changes','studio_change_link_state','studio_comment_response_state'}
assert set(changed)<=allowed,changed
# Archive and restore each advance the reply-verification revision. Existing rows stay exact.
assert current['studio_comment_response_state']==original['studio_comment_response_state']+[
    {'comment_id':'comment_af961fc8ce894b4cb185308fb1ca52d4','revision':2}
]

for table in ('studio_operations','studio_changes','comment_changes','studio_change_link_state'):
    assert current[table][:len(original[table])]==original[table],table
assert [r for r in current['manuscripts'] if r['manuscript_id']!=ms]==[r for r in original['manuscripts'] if r['manuscript_id']!=ms]
rebases=json.loads((repo/'.tmp/scholar-revision-clone-paths-v1.json').read_text())['changes']
paths={r['artifact_id']:r['clone_storage_path'] for r in rebases}
assert current['studio_artifacts']==[{**r,'storage_path':paths[r['artifact_id']]} for r in original['studio_artifacts']]
trace=[];previews={}
with httpx.Client(base_url='http://127.0.0.1:8877/api',timeout=30) as client:
    def call(method,path,expected=200,**kwargs):
        response=client.request(method,path,**kwargs)
        trace.append({'method':method,'path':path,'status':response.status_code})
        assert response.status_code==expected,response.text[:2500]
        return response.json()
    workspace=call('GET',f'/manuscripts/{ms}/workspace')
    assert workspace['document_revision']==9
    assert workspace['document']['sections'][0]['paragraphs'][0]['intents'][0]['thoughts'][0]['text']=='Native second-tab author text saved while the first tab is offline.'
    comments=call('GET',f'/manuscripts/{ms}/comments',params={'include_archived':'true'})
    assert len(comments)==205
    restored=next(c for c in comments if c['display_label']=='A01')
    assert restored['comment_id']=='comment_af961fc8ce894b4cb185308fb1ca52d4' and restored['archived_at'] is None
    assert next(c for c in comments if c['display_label']=='A02')['comment_id']=='comment_682fc9c10fe54c68814a152608cdfb0f'
    single=next(c for c in comments if c['display_label']=='A105')
    assert single['original_text']=='Native browser single opinion.\n\nKeep this second paragraph in the same opinion.'
    expected_raw='\n\n'.join(f'Native pasted opinion {i:03d}. Preserve exact original text.' for i in range(1,102))
    batch=[c for c in comments if c['import_metadata'].get('raw_import_text')==expected_raw]
    assert len(batch)==100
    assert {c['original_text'] for c in batch}=={f'Native pasted opinion {i:03d}. Preserve exact original text.' for i in range(1,101)}
    assert all('Native pasted opinion 101.' in c['import_metadata']['raw_import_text'] for c in batch)
    changes=call('GET',f'/manuscripts/{ms}/changes')
    for change in changes:
        if change.get('from_revision',-1)>=6:
            assert not change.get('comment_ids'),change
    fixture=repo/'.tmp/scholar-revision-upload-fixtures-v1'
    for name,mime in [('opinions-101.txt','text/plain'),('opinion.md','text/markdown'),('opinion.docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document'),('opinion.pdf','application/pdf')]:
        preview=call('POST','/review-comments/preview-file',files={'file':(name,(fixture/name).read_bytes(),mime)})
        assert preview['metadata']['filename']==name
        assert preview['metadata']['size_bytes']==(fixture/name).stat().st_size
        assert len(preview['comments'])==(101 if name.endswith('.txt') else 1)
        assert all(c['text']==c['original_text'] and c['include'] for c in preview['comments'])
        previews[name]=preview
    assert previews['opinions-101.txt']['metadata']['original_text']==(fixture/'opinions-101.txt').read_bytes().decode('utf-8')
    assert 'Native pasted' not in previews['opinions-101.txt']['metadata']['original_text']
    blocked=call('POST',f"/review-rounds/{single['review_round_id']}/comments",422,
                 json={'source':'SOFTWARE_API_GUARD','comments':previews['opinions-101.txt']['comments'],
                       'import_metadata':previews['opinions-101.txt']['metadata']})
    assert '100' in blocked['detail']
assert sha(db.read_bytes())==before,'Readback, file previews and rejected import must not change the DB.'
assert tables(db)==current
export=Path('C:/Users/Alandelone/Downloads')/f'{ms}-local-draft.json'
downloaded=json.loads(export.read_text(encoding='utf-8'))
assert downloaded['baseRevision']==8 and downloaded['manuscriptId']==ms
assert downloaded['document']['sections'][0]['paragraphs'][0]['intents'][0]['thoughts'][0]['text'].startswith('Native offline first-tab draft.')
assert not any(r['operation_id']==downloaded['operationId'] for r in current['studio_operations'])
retained=repo/'.tmp/scholar-revision-exported-offline-copy-v1.json'
with retained.open('xb') as h:h.write(export.read_bytes())
result={'status':'PASS_NATIVE_WRITES_PROVENANCE_CONFLICT_AND_4_ACTUAL_FILE_PARSERS',
        'root':str(root),'scientific_approval':False,'browser_upload_verified':False,
        'browser_upload_blocker':'ChatGPT Chrome extension file URL access disabled',
        'golden_database_sha256':info['golden_database_sha256'],'golden_all_108_tables_preserved':True,
        'clone_declared_changed_tables':changed,'clone_existing_history_preserved':True,
        'new_comments':101,'active_comments':205,'single_raw_blank_lines_preserved':True,
        'unselected_101st_original_preserved_in_saved_import_provenance':True,
        'original_a01_restored_same_id_and_number':True,'new_document_revision':9,
        'offline_operation_not_applied':True,'offline_export_sha256':sha(export.read_bytes()),
        'exported_local_copy':downloaded,'new_model_calls':0,'new_generation_jobs':0,
        'four_actual_file_previews':previews,'requests':trace,'db_unchanged_during_audit':True,
        'changes':changes}
assert current['studio_model_calls']==original['studio_model_calls']
assert current['studio_jobs']==original['studio_jobs']
assert sha((golden/'data/catalog.db').read_bytes())==info['golden_database_sha256']
with output.open('x',encoding='utf-8') as h:json.dump(result,h,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in result.items() if k not in {'exported_local_copy','four_actual_file_previews','requests','changes'}},ensure_ascii=False))
