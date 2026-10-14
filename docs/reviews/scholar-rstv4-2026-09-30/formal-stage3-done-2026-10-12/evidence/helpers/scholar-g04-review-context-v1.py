from pathlib import Path
import hashlib,json,sqlite3,sys
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();out=repo/'.tmp/scholar-g04-native-v1/first-failed-check';out.mkdir()
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'));sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
info=read(out.parent/'baseline.json');base=read(out.parent/'baseline-all-tables.json');db=Path(info['root'])/'data/catalog.db';digest=sha(db)
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as conn:
    conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON');tables={r[0]:[dict(x) for x in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
assert all(all(r in tables[t] for r in rows) for t,rows in base.items() if t not in {'sqlite_sequence','studio_sample_candidates'})
call=tables['studio_model_calls'][-1];job=tables['studio_jobs'][-1];payload=json.loads(call['input_json']);result=json.loads(job['result_json'])
assert len(tables['studio_model_calls'])==15 and call['status']=='FAILED' and json.loads(call['error_json'])['type']=='AssertionError'
assert result['semantic_status']=='UNAVAILABLE: ' and len(result['findings'])==2 and all(r['source']=='RULE' for r in result['findings'])
assert payload['author_input_revision']==11 and payload['generated_version_id']=='manuscript_version_2feb293fad7e4e6591d4217cd322d9d9'
original=repo/'.tmp/scholar-g04-native-server-v1.py';raw=original.read_bytes();(out/'original-server.py').write_bytes(raw)
code=original.read_text(encoding='utf-8');old='Beta software paragraph cites original page 1 [1] and additional source [2].'
new='Beta software paragraph cites original page 1 [@evidence_b5348fa59b3948ae9540b75a33ca9bd9] and additional source [@evidence_6b169de2b78d452f919391b00916f2c8].'
assert code.count(old)==1 and new in payload['generated_manuscript'] and old not in payload['generated_manuscript']
replacement=repo/'.tmp/scholar-g04-native-server-v2.py';assert not replacement.exists();replacement.write_text(code.replace(old,new),encoding='utf-8')
(out/'all-tables.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf-8')
receipt={'status':'PRESERVED_EXACT_FAILED_REVIEW_AND_CORRECTED_INPUT_CONTRACT','call':call,'job':job,'old_server_sha256':hashlib.sha256(raw).hexdigest(),'new_server_sha256':sha(replacement),'reason':'The native reading view renders numeric citations, but the frozen saved/model input uses original [@evidence_ID] source markers. The fixture mistakenly tested presentation text against saved input. Preserve failure and assert the exact saved marker text; no product edit, no assertion removal, no seed or remote fallback.','original4_generations_unchanged':True,'a_author_revision':13,'database_bytes_unchanged':sha(db)==digest}
(out/'context.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print(receipt['status'],flush=True)
