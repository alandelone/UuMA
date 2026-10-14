from pathlib import Path
import json,sqlite3,hashlib,sys,copy
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();phase=sys.argv[1];assert phase in {'after-proposal','after-partial','after-reopen'}
out=repo/'.tmp/scholar-g02-partial-native-v1'/phase;out.mkdir();baseline=json.loads((repo/'.tmp/scholar-g02-partial-native-v1/baseline-all-tables.json').read_text(encoding='utf-8'))
fixture=json.loads((repo/'.tmp/scholar-citation-source-native-v1.json').read_text(encoding='utf-8'));db=Path(fixture['root'])/'data/catalog.db';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();before=sha(db)
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as conn:
    conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON')
    tables={r[0]:[dict(x) for x in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
assert len(tables)==109
for table,rows in baseline.items():
    if table not in {'studio_documents','manuscripts','studio_sample_candidates'}:assert all(r in tables[table] for r in rows),table
assert len(tables['manuscript_versions'])==4 and len(tables['studio_jobs'])==4 and len(tables['studio_artifacts'])==20
assert len(tables['studio_model_calls'])==12 and len(tables['studio_chat_messages'])==11 and len(tables['research_discussion_messages'])==11 and len(tables['research_discussion_jobs'])==6
author=next(r for r in tables['studio_chat_messages'] if r['role']=='AUTHOR' and r['content'].startswith('G02 SOFTWARE PARTIAL:'));assert author['status']=='COMPLETE'
agent=next(r for r in tables['studio_chat_messages'] if r['role']=='AGENT' and r['parent_message_id']==author['message_id']);assert agent['status']=='SUGGESTION'
quote=json.loads(author['quoted_json']);assert quote['source']['generated_version_id']=='manuscript_version_7c2addf4da0f48948f8444b623cbe42e' and author['anchor_revision']==10
assert quote['text']=='First source [1]. Next [2]. Repeat [1].' and quote['source']['anchor_id'].endswith(':paragraph_e197b886c810436a823c7171839afac2')
proposal=json.loads(agent['quoted_json'])['suggestions'];assert len(proposal)==1 and proposal[0]['kind']=='STRUCTURE' and len(proposal[0]['changes'])==2
chosen,omitted=proposal[0]['changes'];assert chosen['action']=='SET_FIELD' and chosen['field']=='purpose' and omitted['action']=='INSERT_INTENT'
call=next(r for r in tables['studio_model_calls'] if r['message_id']==author['message_id']);assert call['status']=='RETURNED' and json.loads(call['contract_json'])['actual_model']=='TEST_FIXTURE_G02_NATIVE'
doc=tables['studio_documents'][0];old=baseline['studio_documents'][0];expected=json.loads(old['document_json'])
if phase=='after-proposal':
    assert doc==old and tables['studio_suggestion_decisions']==baseline['studio_suggestion_decisions'] and tables['studio_operations']==baseline['studio_operations'] and tables['studio_changes']==baseline['studio_changes']
else:
    alpha=next(p for p in expected['sections'][0]['paragraphs'] if p['id']==chosen['target_id']);alpha['purpose']=chosen['value']
    assert doc['revision']==12 and json.loads(doc['document_json'])==expected
    assert doc['active_generated_version_id']==old['active_generated_version_id'] and doc['last_generated_revision']==11
    decisions=[r for r in tables['studio_suggestion_decisions'] if r not in baseline['studio_suggestion_decisions']];assert len(decisions)==1 and decisions[0]['outcome']=='ACCEPT_PARTIAL'
    ops=[r for r in tables['studio_operations'] if r not in baseline['studio_operations']];changes=[r for r in tables['studio_changes'] if r not in baseline['studio_changes']]
    assert len(ops)==1 and len(changes)==1 and ops[0]['base_revision']==11 and ops[0]['resulting_revision']==12
    assert json.loads(changes[0]['before_json'])==json.loads(old['document_json']) and json.loads(changes[0]['after_json'])==expected
for artifact in tables['studio_artifacts']:assert Path(artifact['storage_path']).stat().st_size==artifact['size_bytes'] and sha(Path(artifact['storage_path']))==artifact['sha256']
assert all(r['status'] not in {'QUEUED','RUNNING'} for table in ['studio_jobs','research_discussion_jobs'] for r in tables[table])
assert sha(db)==before
(out/'all-tables.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf-8')
receipt={'status':'PASS_G02_READ_ONLY_STATE','phase':phase,'document_revision':doc['revision'],'original_source_version':3,'original_source_revision':10,'author_message_id':author['message_id'],'agent_message_id':agent['message_id'],'model_call_id':call['call_id'],'suggestion':proposal[0],'old_records_and_all20_artifact_bytes_exact':True,'database_bytes_unchanged_by_audit':True,'document_unchanged_until_author_decision':phase=='after-proposal','only_chosen_purpose_applied':phase!='after-proposal','omitted_intent_absent':all(p['label']!='G02 omitted software Intent' for s in json.loads(doc['document_json'])['sections'] for para in s['paragraphs'] for p in para['intents'])}
(out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(receipt,ensure_ascii=False),flush=True)
