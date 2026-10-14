from pathlib import Path
import hashlib,json,sqlite3,sys
sys.stdout.reconfigure(encoding='utf-8'); repo=Path.cwd(); out=repo/'.tmp/scholar-g04-native-v1'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8')); sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
base=read(out/'baseline-all-tables.json'); info=read(out/'baseline.json'); db=Path(info['root'])/'data/catalog.db'; digest=sha(db)
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as conn:
    conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON')
    tables={r[0]:[dict(x) for x in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
a=info['manuscript_a'];phase=sys.argv[1];dest=out/phase;dest.mkdir()
assert len(tables)==109 and len(tables['manuscripts'])==2
for table,rows in base.items():
    if table in {'sqlite_sequence','studio_sample_candidates'}:continue
    for row in rows:
        if phase!='checked' and table in {'manuscripts','studio_documents'} and row['manuscript_id']==a:continue
        assert row in tables[table],table
for table in ['research_discussion_messages','studio_chat_messages','studio_suggestion_decisions','manuscript_versions','studio_artifacts']:
    assert tables[table]==base[table],table
assert len(tables['studio_model_calls'])==15
calls=[r for r in tables['studio_model_calls'] if r not in base['studio_model_calls']];assert len(calls)==1
jobs=[r for r in tables['studio_jobs'] if r not in base['studio_jobs']]
assert len(jobs)==1 and jobs[0]['job_kind']=='WHOLE_PAPER_REVIEW' and jobs[0]['status']=='SUCCEEDED'
result=json.loads(jobs[0]['result_json']);assert result['generated_version_id']=='manuscript_version_2feb293fad7e4e6591d4217cd322d9d9' and result['author_input_revision']==11 and result['semantic_status']=='AVAILABLE'
assert result['model_contract']['actual_model']=='TEST_FIXTURE_G04_STAGE3_DONE_NATIVE'
findings=[r for r in tables['studio_findings'] if r not in base['studio_findings']]
assert findings and all(r['status']=='OPEN' and r['resolved_at'] is None for r in findings)
assert any(r['detail']=='G04 software review marker: keep this unresolved finding while returning from Stage 3 structure editing. No scientific judgment is asserted.' for r in findings)
doc=next(r for r in tables['studio_documents'] if r['manuscript_id']==a)
assert doc['active_generated_version_id']=='manuscript_version_2feb293fad7e4e6591d4217cd322d9d9' and doc['last_generated_revision']==11
assert next(r for r in tables['manuscripts'] if r['manuscript_id']==a)['workflow_stage']=='WHOLE_PAPER_REVIEW'
assert sum(r['job_kind']=='GENERATE' for r in tables['studio_jobs'])==4
if phase=='checked':
    assert doc['revision']==13 and tables['studio_operations']==base['studio_operations']
else:
    assert doc['revision']==14
    old=json.loads(next(r for r in base['studio_documents'] if r['manuscript_id']==a)['document_json']);actual=json.loads(doc['document_json'])
    old['sections'][0]['paragraphs'][0]['purpose']='G04 Stage 3 author structure edit: preserve generated v4 and unresolved review findings; no automatic Generate.'
    assert old==actual
    ops=[r for r in tables['studio_operations'] if r not in base['studio_operations']];assert len(ops)==1 and ops[0]['manuscript_id']==a
    assert jobs==read(out/'checked/all-tables.json')['studio_jobs'][-1:]
    assert findings==[r for r in read(out/'checked/all-tables.json')['studio_findings'] if r not in base['studio_findings']]
assert all(sha(r['storage_path'])==r['sha256'] for r in tables['studio_artifacts']) and sha(db)==digest
(dest/'all-tables.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf-8')
receipt={'status':'PASS_G04_'+phase.upper(),'author_revision':doc['revision'],'job':jobs[0],'new_model_call':calls[0],'findings':findings,'original20_artifact_sha_exact':True,'original4_generations_exact':True,'workflow_stage':'WHOLE_PAPER_REVIEW','new_generate_jobs':0,'new_discussion_messages':0,'read_only_database_bytes_preserved':True}
(dest/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k not in {'job','new_model_call','findings'}},ensure_ascii=False),flush=True)
print(json.dumps({'job_id':jobs[0]['job_id'],'new_model_call_keys':list(calls[0]),'findings':findings},ensure_ascii=False),flush=True)
