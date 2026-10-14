from pathlib import Path
import hashlib,json,sqlite3,sys
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();out=repo/'.tmp/scholar-g06-native-v1'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'));sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
base=read(out/'baseline-all-tables.json');info=read(out/'baseline.json');db=Path(info['root'])/'data/catalog.db';digest=sha(db)
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as conn:
    conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON');tables={r[0]:[dict(x) for x in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
phase=sys.argv[1];dest=out/phase;dest.mkdir();a=info['manuscript_a']
for table in ['studio_model_calls','studio_chat_messages','research_discussion_messages','studio_suggestion_decisions','studio_jobs','manuscript_versions','studio_artifacts','studio_findings']:
    assert tables[table]==base[table],table
for table,rows in base.items():
    if table in {'sqlite_sequence','studio_sample_candidates'}:continue
    for row in rows:
        if table in {'manuscripts','studio_documents'} and row['manuscript_id']==a:continue
        assert row in tables[table],table
assert len(tables['review_rounds'])==1 and len(tables['review_comments'])==2
doc=next(r for r in tables['studio_documents'] if r['manuscript_id']==a)
assert doc['active_generated_version_id']=='manuscript_version_2feb293fad7e4e6591d4217cd322d9d9' and doc['last_generated_revision']==11
assert next(r for r in tables['manuscripts'] if r['manuscript_id']==a)['workflow_stage']=='WHOLE_PAPER_REVIEW'
if phase=='imported':assert doc==next(r for r in base['studio_documents'] if r['manuscript_id']==a) and tables['studio_operations']==base['studio_operations']
assert all(sha(r['storage_path'])==r['sha256'] for r in tables['studio_artifacts']) and sha(db)==digest
(dest/'all-tables.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf-8')
names=[k for k in tables if any(x in k for x in ['comment','change','review_round'])]
receipt={'status':'PASS_G06_PROTECTED_STATE_'+phase.upper(),'author_revision':doc['revision'],'new_model_calls':0,'new_generation_jobs':0,'old20_artifact_sha_exact':True,'read_only_database_bytes_preserved':True,'review_tables':{k:tables[k] for k in names}}
(dest/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(receipt,ensure_ascii=False)[:7000],flush=True)
