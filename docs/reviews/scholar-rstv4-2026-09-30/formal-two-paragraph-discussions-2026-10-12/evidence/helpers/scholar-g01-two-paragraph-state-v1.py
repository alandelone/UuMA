from pathlib import Path
import json,sqlite3,hashlib,sys
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();sys.path.insert(0,str(repo.parent/'RSTV4/src'))
from rstv4.studio_read_views import generated_version
phase=sys.argv[1];assert phase in {'before-reorder-v3','after-reorder-before-generation','after-reorder-v4','after-old-locations'}
fixture=json.loads((repo/'.tmp/scholar-citation-source-native-v1.json').read_text(encoding='utf-8'));root=Path(fixture['root']);db=root/'data/catalog.db';ms=fixture['manuscript_id'];before=hashlib.sha256(db.read_bytes()).hexdigest()
out=repo/'.tmp'/('scholar-g01-two-paragraph-'+phase);out.mkdir()
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as conn:
 conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON')
 tables={r[0]:[dict(x) for x in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
 versions=[generated_version(conn,root/'data/writing-studio',ms,r['manuscript_version_id']) for r in conn.execute('SELECT * FROM manuscript_versions WHERE manuscript_id=? ORDER BY version',(ms,))]
assert len(tables)==109 and all(r['status'] not in {'QUEUED','RUNNING'} for table in ['studio_jobs','research_discussion_jobs'] for r in tables[table])
base=json.loads((repo/'.tmp/scholar-g01-two-paragraph-baseline-tables-v1.json').read_text(encoding='utf-8'))
for table in ['manuscript_versions','studio_jobs','studio_model_calls','studio_chat_messages','research_discussion_messages','research_discussion_jobs','studio_artifacts']:
 keys={'manuscript_versions':'manuscript_version_id','studio_jobs':'job_id','studio_model_calls':'call_id','studio_chat_messages':'message_id','research_discussion_messages':'message_id','research_discussion_jobs':'request_id','studio_artifacts':'artifact_id'}
 current={r[keys[table]]:r for r in tables[table]}
 assert all(current[r[keys[table]]]==r for r in base[table]),table
v3=versions[2];assert v3['version']==3 and v3['input_revision']==10
paragraphs=[b for b in v3['blocks'] if b['kind']=='paragraph'];assert len(paragraphs)==2
assert [b['object_id'] for b in paragraphs]==['paragraph_e197b886c810436a823c7171839afac2','paragraph_895901de3a694d6f9a4b996e5459feeb']
authors=[r for r in tables['studio_chat_messages'] if r['role']=='AUTHOR' and r['content'].startswith('G01 ')]
assert len(authors)==2
for author,paragraph,label in zip(authors,paragraphs,['ALPHA','BETA'],strict=True):
 quote=json.loads(author['quoted_json']);assert author['content'].startswith('G01 '+label+' original discussion:')
 assert quote['source']['generated_version_id']==v3['generated_version_id'] and author['anchor_id']==paragraph['anchor_id']
 assert quote['text']==paragraph['display_text'] and quote['start']==0 and quote['end']==len(quote['text'])
 assert quote['offset_unit']=='utf16' and quote['annotation'].startswith('G01 '+label+': real selected numeric citation text')
 assert author['status']=='COMPLETE' and author['anchor_revision']==10
 agents=[r for r in tables['studio_chat_messages'] if r['parent_message_id']==author['message_id'] and r['role']=='AGENT'];assert len(agents)==1
 assert json.loads(agents[0]['quoted_json'])['source']==quote['source'] and json.loads(agents[0]['quoted_json'])['text']==quote['text']
 agent_call=next(r for r in tables['studio_model_calls'] if r['message_id']==author['message_id']);assert agent_call['status']=='RETURNED'
 assert hashlib.sha256(agent_call['input_json'].encode()).hexdigest()==agent_call['input_sha256']
 assert json.loads(agent_call['input_json'])['generated_version']['generated_version_id']==v3['generated_version_id']
 assert json.loads(agent_call['contract_json'])['actual_model']=='TEST_FIXTURE_G01_NATIVE'
doc=next(r for r in tables['studio_documents'] if r['manuscript_id']==ms);document=json.loads(doc['document_json'])
if phase=='before-reorder-v3':
 assert doc['revision']==10 and [p['id'] for p in document['sections'][0]['paragraphs']]==[b['object_id'] for b in paragraphs]
 assert len(versions)==3 and len(tables['studio_chat_messages'])==9 and len(tables['studio_model_calls'])==9
else:
 assert [p['id'] for p in document['sections'][0]['paragraphs']]==[b['object_id'] for b in reversed(paragraphs)]
 if phase!='after-reorder-before-generation':
  v4=versions[3];new=[b for b in v4['blocks'] if b['kind']=='paragraph'];assert len(versions)==4 and [b['object_id'] for b in new]==[b['object_id'] for b in reversed(paragraphs)]
  assert [r['evidence_id'] for r in v4['references']]==[r['evidence_id'] for r in reversed(v3['references'])]
  assert new[0]['display_text']=='Beta software paragraph cites original page 1 [1] and additional source [2].'
  assert new[1]['display_text']=='First source [2]. Next [1]. Repeat [2].'
(out/'all-tables.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'generated-versions.json').write_text(json.dumps(versions,ensure_ascii=False,indent=2),encoding='utf-8')
assert hashlib.sha256(db.read_bytes()).hexdigest()==before
receipt={'status':'PASS_READ_ONLY_EXACT_G01_STATE','phase':phase,'database_bytes_preserved':True,'table_count':109,'document_revision':doc['revision'],'generated_versions':[v['generated_version_id'] for v in versions],'v3_paragraphs':[{'object_id':b['object_id'],'anchor_id':b['anchor_id'],'display_text':b['display_text']} for b in paragraphs],'original_author_messages':[r['message_id'] for r in authors],'original_agent_messages':[r['message_id'] for r in tables['studio_chat_messages'] if r['role']=='AGENT' and r['parent_message_id'] in {a['message_id'] for a in authors}],'all_old_failure_and_versions_exact':True}
(out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(receipt,ensure_ascii=False),flush=True)
