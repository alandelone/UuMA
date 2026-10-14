from pathlib import Path
import hashlib,json,sqlite3,sys
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();out=repo/'.tmp/scholar-g07-native-v1'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'));sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
base=read(out/'baseline-all-tables.json');info=read(out/'baseline.json');db=Path(info['root'])/'data/catalog.db';digest=sha(db)
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as conn:
    conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON');tables={r[0]:[dict(x) for x in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
phase=sys.argv[1];dest=out/phase;dest.mkdir()
assert len(tables)==109
for table,rows in base.items():
    if table in {'sqlite_sequence','studio_sample_candidates'}:continue
    assert all(r in tables[table] for r in rows),table
for table in ['manuscripts','studio_documents','studio_model_calls','studio_chat_messages','research_discussion_messages','studio_suggestion_decisions','studio_jobs','manuscript_versions','studio_artifacts','studio_findings','studio_operations','studio_changes','comment_changes','review_rounds','studio_review_round_baselines']:
    assert tables[table]==base[table],table
expected_count={'single':3,'duplicate-cancel':3,'duplicate-kept':4,'bulk-preview':4,'bulk100-preview':4,'bulk-cancel':4,'final':4}[phase]
assert len(tables['review_comments'])==expected_count
single='G07 single software comment: preserve this entire block as one original opinion.\n\nSecond paragraph belongs to the same single comment.\nKeep this line break; no scientific request.'
new=[r for r in tables['review_comments'] if r not in base['review_comments']]
assert len(new)==expected_count-2
for i,r in enumerate(new,3):
    assert r['original_text']==r['edited_text']==single and r['status']=='PENDING' and r['archived_at'] is None
    metadata=json.loads(r['import_metadata_json']);assert metadata['comment_number']==i and metadata['original_text']==single and metadata['raw_import_text']==single
assert sha(db)==digest and all(sha(r['storage_path'])==r['sha256'] for r in tables['studio_artifacts'])
(dest/'all-tables.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf-8')
receipt={'status':'PASS_G07_'+phase.upper(),'review_comments':tables['review_comments'],'new_model_calls':0,'new_generation_jobs':0,'new_author_operations':0,'original_all_application_rows_exact':True,'original20_artifact_sha_exact':True,'read_only_database_bytes_preserved':True}
(dest/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k!='review_comments'},ensure_ascii=False),flush=True)
print(json.dumps({'new_comment_ids':[r['comment_id'] for r in new],'numbers':[json.loads(r['import_metadata_json'])['comment_number'] for r in new],'whole_blank_line_text_exact':True},ensure_ascii=False),flush=True)
