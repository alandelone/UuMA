from pathlib import Path
import hashlib, json, sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')
repo = Path.cwd(); out = repo / '.tmp/scholar-g03-native-v1'
read = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
baseline = read(out / 'baseline-all-tables.json')
before_sync = read(out / 'online-before-all-tables.json')
fixture = read(repo / '.tmp/scholar-citation-source-native-v1.json')
db = Path(fixture['root']) / 'data/catalog.db'; digest = sha(db)
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True) as conn:
    conn.row_factory = sqlite3.Row; conn.execute('PRAGMA query_only=ON')
    current = {r[0]: [dict(x) for x in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
assert set(current) == set(baseline) and len(current) == 109
old_rows = {table: all(row in current[table] for row in rows) for table, rows in baseline.items() if table not in {'sqlite_sequence', 'studio_sample_candidates'}}
assert all(old_rows.values()), [t for t, ok in old_rows.items() if not ok]
for table in ['studio_model_calls','studio_chat_messages','research_discussion_messages','studio_suggestion_decisions','studio_jobs','manuscript_versions','studio_artifacts']:
    assert current[table] == baseline[table], table
assert len(current['studio_model_calls']) == 14 and len(current['studio_chat_messages']) == 15
assert len(current['studio_suggestion_decisions']) == 3 and len(current['studio_artifacts']) == 20
a = fixture['manuscript_id']; b = 'manuscript_bea23f3050174ed1a0df075a32c25e13'
assert len(current['manuscripts']) == 2
a_doc = next(r for r in current['studio_documents'] if r['manuscript_id'] == a)
b_doc = next(r for r in current['studio_documents'] if r['manuscript_id'] == b)
assert a_doc == baseline['studio_documents'][0] and a_doc['revision'] == 13
before_b = next(r for r in before_sync['studio_documents'] if r['manuscript_id'] == b)
assert before_b['revision'] == 0
b_before = json.loads(before_b['document_json']); b_after = json.loads(b_doc['document_json'])
expected_abstract = 'G03 B offline author abstract — keep locally during disconnection; software acceptance only, no scientific claim.'
assert b_doc['revision'] == 1 and b_after['abstract'] == expected_abstract
b_before['abstract'] = expected_abstract
assert b_after == b_before
assert next(r for r in current['manuscripts'] if r['manuscript_id'] == a)['workflow_stage'] == 'WHOLE_PAPER_REVIEW'
assert next(r for r in current['manuscripts'] if r['manuscript_id'] == b)['workflow_stage'] == 'DRAFTING'
new_ops = [r for r in current['studio_operations'] if r not in baseline['studio_operations']]
assert len(new_ops) == 1 and new_ops[0]['manuscript_id'] == b
artifact_checks = {r['artifact_id']: sha(r['storage_path']) == r['sha256'] for r in current['studio_artifacts']}
assert all(artifact_checks.values())
proof = out / 'proof'
for before, after in [('final-before-reload-v3.geometry.json','final-after-reload-v3.geometry.json'),('A-structure-before-refresh.geometry.json','A-structure-after-refresh.geometry.json')]:
    first, second = read(proof / before), read(proof / after)
    assert first == second and first['y'] == 807 and 0 < first['y'] < first['h'] - first['viewport']
catalog_before = read(proof / 'catalog-stable-before-refresh.geometry.json')
catalog_after = read(proof / 'catalog-stable-after-refresh.geometry.json')
assert catalog_before['rows'] == catalog_after['rows'] and catalog_before['y'] == catalog_after['y'] == 0
assert sum(r['expanded'] == 'false' for r in catalog_after['rows']) == 2
native_b = read(proof / 'B-final.geometry.json')
assert native_b['abstract'] == expected_abstract and native_b['direction'] == 'horizontal' and native_b['folded'] == ['展开 Introduction']
assert read(proof / 'A-structure-after-refresh.geometry.json')['direction'] == 'upright'
for file, tokens in {
    'failed-restored-object-current-v4.dom.txt':['artifact_7477255312e6405988e21c626026e5ae'],
    'failed-cross-manuscript-B.dom.txt':['还没有成文版本','上次选中的对象已不可用'],
    'final-after-reload-v3.dom.txt':['artifact_4012958fd937410ea0620eca7bd11c73','G03 A unsent α draft','G03 A annotation α','定位的历史原文与选区'],
    'offline-B-save-failed.dom.txt':['保存失败 · 请重试',expected_abstract],
    'offline-B-leave-guard.dom.txt':['留在此页','保留本地副本并返回',expected_abstract],
    'offline-B-stay-preserved.dom.txt':[expected_abstract,'G03 B unsent β draft'],
    'offline-returned-Track.dom.txt':['请确认本机 RSTV4 Writing Studio 服务已经启动'],
    'B-reconnected-local-draft-recovery.dom.txt':['已恢复未同步的本地副本',expected_abstract,'G03 B unsent β draft'],
    'B-final.dom.txt':[expected_abstract,'G03 B unsent β draft','G03 B annotation β'],
    'A-after-offline-B-return.dom.txt':['G03 A unsent α draft','G03 A annotation α','artifact_4012958fd937410ea0620eca7bd11c73'],
}.items():
    text = (proof / file).read_text(encoding='utf-8')
    assert all(token in text for token in tokens), file
checks = read(repo / '.tmp/scholar-g03-front-v3.json')
assert len(checks) == 5 and all(r['exit_code'] == 0 for r in checks)
build = read(repo / '.tmp/scholar-g03-build-v2.json')
assert build['status'] == 'PASS' and build['original_source_and_dist_unchanged']
front = repo.parent / 'writing-studio'
assert all(sha(front / p) == h for p, h in build['before'].items())
prior_manifest = read(repo / 'docs/reviews/scholar-rstv4-2026-09-30/formal-typed-discussion-adoption-2026-10-12/manifest.json')
unchanged_prior_sources = {p: sha(p) == h for p, h in prior_manifest['current_source_sha256'].items() if not p.endswith('components\\studio-workspace.tsx')}
assert all(unchanged_prior_sources.values())
sources = list(prior_manifest['current_source_sha256']) + [str(front / p) for p in ['app/page.tsx','lib/studio-view-state.ts','tests/unit/studio-view-state.cjs']]
source_sha = {p: sha(p) for p in sources}
mission = read(repo / 'mission_status.json')
assert mission['stage'] == 'verification'
assert sha(db) == digest
(out / 'final-all-tables.json').write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
receipt = {'status':'PASS_ORIGINAL_G03_SOFTWARE_NATIVE_ACCEPTANCE','manuscript_a':a,'manuscript_b':b,'a_author_revision':13,'b_author_revision':1,'b_first_author_edit_transition':'PLANNING -> DRAFTING','all_original_application_rows_exact':old_rows,'unchanged_prior_sources':unchanged_prior_sources,'artifact_sha256_checks':artifact_checks,'new_author_operations':new_ops,'new_model_calls':0,'new_discussion_messages':0,'source_sha256':source_sha,'read_only_audit_database_bytes_preserved':True,'overall_11_groups_complete':False}
(out / 'final-audit.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k not in {'all_original_application_rows_exact','unchanged_prior_sources','artifact_sha256_checks','new_author_operations','source_sha256'}}, ensure_ascii=False), flush=True)
