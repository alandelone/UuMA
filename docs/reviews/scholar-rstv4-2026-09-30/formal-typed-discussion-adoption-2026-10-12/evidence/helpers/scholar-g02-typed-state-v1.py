from pathlib import Path
import copy,hashlib,json,sqlite3,sys
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();phase=sys.argv[1];assert phase in {'source-accepted','wording-proposed','wording-rejected','reopened-final'}
root=Path(json.loads((repo/'.tmp/scholar-citation-source-native-v1.json').read_text(encoding='utf-8'))['root']);db=root/'data/catalog.db';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();before=sha(db)
out=repo/'.tmp/scholar-g02-typed-native-v1'/phase;out.mkdir();read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
baseline=read(repo/'.tmp/scholar-g02-typed-native-v1/baseline-all-tables.json');proposed=read(repo/'.tmp/scholar-g02-typed-native-v1/source-proposed/all-tables.json')
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as conn:
    conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON')
    tables={r[0]:[dict(x) for x in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
for table,rows in proposed.items():
    if table not in {'studio_documents','manuscripts','studio_sample_candidates','sqlite_sequence'}:assert all(r in tables[table] for r in rows),table
source_author=next(r for r in tables['studio_chat_messages'] if r['role']=='AUTHOR' and r['content'].startswith('G02 SOFTWARE SOURCE:'));source_agent=next(r for r in tables['studio_chat_messages'] if r['parent_message_id']==source_author['message_id'] and r['role']=='AGENT')
source_suggestion=json.loads(source_agent['quoted_json'])['suggestions'][0];source_change=source_suggestion['changes'][0];evidence=source_change['evidence']
expected=json.loads(baseline['studio_documents'][0]['document_json']);beta=expected['sections'][0]['paragraphs'][0];thought=beta['intents'][0]['thoughts'][0];assert thought['id']==source_change['target_id']
assert all(c['selected'] for c in thought['citations']) and len(thought['citations'])==2
thought['citations'].append({'evidence_id':evidence['evidence_id'],'selected':False,'statement':evidence['statement'],'title':evidence['title']});thought['citation_mode']='PENDING'
doc=tables['studio_documents'][0];assert doc['revision']==13 and json.loads(doc['document_json'])==expected and doc['last_generated_revision']==11 and doc['active_generated_version_id']==baseline['studio_documents'][0]['active_generated_version_id']
decisions=[r for r in tables['studio_suggestion_decisions'] if r not in baseline['studio_suggestion_decisions']];source_decision=next(r for r in decisions if r['message_id']==source_agent['message_id']);assert source_decision['outcome']=='ACCEPT_ALL'
request=json.loads(source_decision['request_json']);provenance=json.loads(source_decision['provenance_json']);assert request['selected_change_ids']==[source_change['change_id']] and request['base_revision']==12
assert provenance['source']==json.loads(source_agent['quoted_json'])['source'] and provenance['source']['generated_version']==3 and provenance['source']['anchor_revision']==10
assert len(provenance['changes'])==1 and provenance['changes'][0]['evidence']==evidence
source_call=next(r for r in tables['studio_model_calls'] if r['message_id']==source_author['message_id']);payload=json.loads(source_call['input_json'])
assert payload['additional_sources'][0]['context']['target']['generated_version_id']=='manuscript_version_7ea00b67724045db8db687b46beb1530' and payload['generated_version']['version']==3
assert evidence['source_snapshot_available'] and evidence['source_context']['available'] and evidence['location']['page']==2 and evidence['title']=='Catalog selected source'
ops=[r for r in tables['studio_operations'] if r not in baseline['studio_operations']];changes=[r for r in tables['studio_changes'] if r not in baseline['studio_changes']]
assert len(ops)==1 and len(changes)==1 and ops[0]['operation_id']==source_decision['operation_id'] and ops[0]['base_revision']==12 and ops[0]['resulting_revision']==13
assert json.loads(changes[0]['before_json'])==json.loads(baseline['studio_documents'][0]['document_json']) and json.loads(changes[0]['after_json'])==expected
if phase=='source-accepted':
    assert len(tables['studio_chat_messages'])==13 and len(tables['studio_model_calls'])==13 and tables['sqlite_sequence']==[{'name':'research_discussion_messages','seq':13}] and len(decisions)==1
else:
    assert len(tables['studio_chat_messages'])==15 and len(tables['studio_model_calls'])==14 and tables['sqlite_sequence']==[{'name':'research_discussion_messages','seq':15}]
    word_author=next(r for r in tables['studio_chat_messages'] if r['role']=='AUTHOR' and r['content'].startswith('G02 SOFTWARE WORDING:'));word_agent=next(r for r in tables['studio_chat_messages'] if r['parent_message_id']==word_author['message_id'] and r['role']=='AGENT');word_call=next(r for r in tables['studio_model_calls'] if r['message_id']==word_author['message_id'])
    assert word_author['status']=='COMPLETE' and word_agent['status']=='SUGGESTION' and word_call['status']=='RETURNED' and json.loads(word_call['contract_json'])['actual_model']=='TEST_FIXTURE_G02_TYPED_NATIVE'
    word_suggestion=json.loads(word_agent['quoted_json'])['suggestions'][0];assert word_suggestion['kind']=='WORDING' and len(word_suggestion['changes'])==1
    word_change=word_suggestion['changes'][0];assert word_change['action']=='REPLACE_TEXT' and word_change['target_id']=='thought_author_1' and word_change['value']=='Review'
    assert word_change['quote']['text']=='Check' and word_change['quote']['start']==0 and word_change['quote']['end']==5 and word_change['quote']['offset_unit']=='utf16'
    if phase=='wording-proposed':assert len(decisions)==1
    else:
        word_decision=next(r for r in decisions if r['message_id']==word_agent['message_id']);assert word_decision['outcome']=='REJECT' and word_decision['operation_id'] is None and len(decisions)==2
        assert json.loads(word_decision['request_json'])['selected_change_ids']==[] and json.loads(word_decision['provenance_json'])['changes']==[]
        word_before=read(repo/'.tmp/scholar-g02-typed-native-v1/wording-proposed/all-tables.json');assert tables['studio_documents']==word_before['studio_documents'] and tables['studio_operations']==word_before['studio_operations'] and tables['studio_changes']==word_before['studio_changes']
assert len(tables['manuscript_versions'])==4 and len(tables['studio_jobs'])==4 and len(tables['studio_artifacts'])==20
assert all(r['status'] not in {'QUEUED','RUNNING'} for table in ['studio_jobs','research_discussion_jobs'] for r in tables[table])
for artifact in tables['studio_artifacts']:assert sha(Path(artifact['storage_path']))==artifact['sha256'] and Path(artifact['storage_path']).stat().st_size==artifact['size_bytes']
assert sha(db)==before
(out/'all-tables.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf-8')
receipt={'status':'PASS_G02_TYPED_NATIVE_STATE','phase':phase,'document_revision':13,'source_suggestion_id':source_suggestion['suggestion_id'],'source_agent_message_id':source_agent['message_id'],'source_decision_id':source_decision['decision_id'],'source_full_adoption_adds_only_unselected_candidate':True,'old_selected_citations_and_all_author_text_exact':True,'source_primary_v3_additional_v1_exact':True,'wording_explicitly_rejected_without_document_change':phase in {'wording-rejected','reopened-final'},'all_original_and_partial_records_exact':True,'all20artifact_bytes_exact':True,'database_read_only_bytes_preserved':True}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps(receipt),flush=True)
