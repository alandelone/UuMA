from pathlib import Path
import hashlib,json,sqlite3,sys
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();out=repo/'.tmp/scholar-g08-native-v1'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'));sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
base=read(out/'baseline-all-tables.json');info=read(out/'baseline.json');a=info['manuscript_a'];db=Path(info['root'])/'data/catalog.db';digest=sha(db)
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as conn:
    conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON');tables={r[0]:[dict(x) for x in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
phase=sys.argv[1];dest=out/phase;dest.mkdir()
for table in ['studio_model_calls','studio_chat_messages','research_discussion_messages','studio_suggestion_decisions','studio_jobs','manuscript_versions','studio_artifacts','studio_findings','review_comments','review_rounds','studio_review_round_baselines','comment_changes']:
    assert tables[table]==base[table],table
for table,rows in base.items():
    if table in {'sqlite_sequence','studio_sample_candidates'}:continue
    for row in rows:
        if table in {'manuscripts','studio_documents'} and row['manuscript_id']==a:continue
        assert row in tables[table],table
doc=next(r for r in tables['studio_documents'] if r['manuscript_id']==a);author=json.loads(doc['document_json']);original=json.loads(next(r for r in base['studio_documents'] if r['manuscript_id']==a)['document_json'])
assert doc['active_generated_version_id']=='manuscript_version_2feb293fad7e4e6591d4217cd322d9d9' and doc['last_generated_revision']==11
assert next(r for r in tables['manuscripts'] if r['manuscript_id']==a)['workflow_stage']=='WHOLE_PAPER_REVIEW'
def thoughts(document):
    return {t['id']:t for s in document['sections'] for p in s['paragraphs'] for i in p['intents'] for t in i['thoughts']}
assert all(thoughts(author).get(k)==v for k,v in thoughts(original).items())
if phase=='folded':assert author==original and doc['revision']==18 and tables['studio_operations']==base['studio_operations']
assert all(sha(r['storage_path'])==r['sha256'] for r in tables['studio_artifacts']) and sha(db)==digest
(dest/'all-tables.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf-8')
receipt={'status':'PASS_G08_PROTECTED_STATE_'+phase.upper(),'author_revision':doc['revision'],'original_thoughts_with_citations_exact':True,'new_model_calls':0,'new_generation_jobs':0,'original20_artifact_sha_exact':True,'read_only_database_bytes_preserved':True,'document':author}
(dest/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k!='document'},ensure_ascii=False),flush=True)
print(json.dumps({'sections':[{k:s.get(k) for k in ['id','title','paragraph_groups','block_order','placement_status']} for s in author['sections']],'thought_ids':list(thoughts(author)),'templates':tables.get('studio_template_instances',[])},ensure_ascii=False)[:1200],flush=True)
