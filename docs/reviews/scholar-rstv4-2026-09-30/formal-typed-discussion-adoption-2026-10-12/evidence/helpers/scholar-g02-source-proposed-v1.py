from pathlib import Path
import json,sqlite3,sys,hashlib
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();root=Path(json.loads((repo/'.tmp/scholar-citation-source-native-v1.json').read_text(encoding='utf-8'))['root']);db=root/'data/catalog.db';digest=hashlib.sha256(db.read_bytes()).hexdigest()
out=repo/'.tmp/scholar-g02-typed-native-v1/source-proposed';out.mkdir()
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as conn:
    conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON')
    tables={r[0]:[dict(x) for x in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
baseline=json.loads((repo/'.tmp/scholar-g02-typed-native-v1/baseline-all-tables.json').read_text(encoding='utf-8'))
assert tables['studio_documents']==baseline['studio_documents'] and tables['studio_suggestion_decisions']==baseline['studio_suggestion_decisions'] and tables['studio_operations']==baseline['studio_operations'] and tables['studio_changes']==baseline['studio_changes']
author=next(r for r in tables['studio_chat_messages'] if r['role']=='AUTHOR' and r['content'].startswith('G02 SOFTWARE SOURCE:'));agent=next(r for r in tables['studio_chat_messages'] if r['role']=='AGENT' and r['parent_message_id']==author['message_id']);call=next(r for r in tables['studio_model_calls'] if r['message_id']==author['message_id'])
assert author['status']=='COMPLETE' and agent['status']=='SUGGESTION' and call['status']=='RETURNED'
proposal=json.loads(agent['quoted_json'])['suggestions'][0];assert proposal['kind']=='SOURCE' and len(proposal['changes'])==1
payload=json.loads(call['input_json']);candidate=next(r for r in payload['retrieved_evidence'] if r['evidence_id']=='evidence_3a2639ee8b5e432aafd7e3743c825f33')
assert candidate['reference_snapshot_source']=='generation_input' and candidate['source_context']['available'] is True
assert candidate['title']=='Catalog selected source' and candidate['statement']=='Original software source body 2.'
assert payload['generated_version']['version']==3 and len(payload['additional_sources'])==1
assert json.loads(call['contract_json'])['actual_model']=='TEST_FIXTURE_G02_TYPED_NATIVE'
assert len(tables['studio_model_calls'])==13 and len(tables['studio_chat_messages'])==13 and len(tables['research_discussion_jobs'])==7
assert hashlib.sha256(db.read_bytes()).hexdigest()==digest
(out/'all-tables.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf-8')
receipt={'status':'PASS_SOURCE_PROPOSED_WITHOUT_AUTHOR_CHANGE','author':author['message_id'],'agent':agent['message_id'],'call':call['call_id'],'source_proposal':proposal,'primary_target':payload['discussion_source']['context']['target'],'additional_sources':payload['additional_sources'],'fixed_candidate':candidate,'document_revision':12,'author_decisions_and_document_unchanged':True,'database_bytes_unchanged_by_read':True}
(out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in receipt.items() if k not in {'additional_sources','fixed_candidate','source_proposal'}},ensure_ascii=False));print('PROPOSAL '+json.dumps(proposal,ensure_ascii=False)[:3200]);print('EXTRA '+json.dumps(payload['additional_sources'],ensure_ascii=False)[:1800])
