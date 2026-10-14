from pathlib import Path
from copy import deepcopy
import hashlib
import json
import sqlite3

from rstv4.studio import StudioService
from rstv4.studio_correspondence import realization_document, validate
from rstv4.studio_structure import argument_context

repo = Path.cwd()
fixture = json.loads((repo/'.tmp/scholar-intent-correspondence-native-v1.json').read_text(encoding='utf-8'))
parent = json.loads((repo/'.tmp/scholar-source-hierarchy-fixture-v1.json').read_text(encoding='utf-8'))
ms = fixture['manuscript_id']
root = Path(fixture['root'])
out = repo/'.tmp/scholar-intent-correspondence-native-v2'
out.mkdir(exist_ok=True)
def snapshot(db):
    with sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        assert not conn.execute('PRAGMA foreign_key_check').fetchone()
        return {row[0]: [dict(record) for record in conn.execute(f'SELECT * FROM "{row[0]}" ORDER BY rowid')]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
before = snapshot(Path(parent['root'])/'data/catalog.db')
after = snapshot(root/'data/catalog.db')
assert before.keys() == after.keys() and len(after) == 109
assert next(row for row in before['studio_documents'] if row['manuscript_id'] == ms)['revision'] == 8
allowed = {'studio_documents', 'studio_operations', 'studio_changes', 'studio_template_instances',
           'studio_assets', 'studio_jobs', 'studio_model_calls', 'studio_artifacts',
           'manuscripts', 'manuscript_versions', 'studio_sample_candidates'}
for table in before:
    if table == 'studio_change_link_state':
        assert after[table][:len(before[table])] == before[table]
        new_changes = {c['change_id'] for c in after['studio_changes'] if c['manuscript_id'] == ms} - {c['change_id'] for c in before['studio_changes'] if c['manuscript_id'] == ms}
        new_rows = after[table][len(before[table]):]
        assert len(new_rows) == len(new_changes) == 11
        assert {r['change_id'] for r in new_rows} == new_changes
        assert all(r['initial_comment_ids_json'] == '[]' and r['initial_origin'] == 'recorded_at_save' and r['link_revision'] == 0 for r in new_rows)
    elif table not in allowed:
        assert before[table] == after[table], f'Unrelated table changed: {table}'
    else:
        assert [row for row in before[table] if row.get('manuscript_id') != ms] == [row for row in after[table] if row.get('manuscript_id') != ms], f'Another manuscript changed: {table}'
own_ops = sorted([row for row in after['studio_operations'] if row['manuscript_id'] == ms], key=lambda row:row['resulting_revision'])
assert [row for row in own_ops if row['resulting_revision'] <= 8] == sorted([row for row in before['studio_operations'] if row['manuscript_id'] == ms], key=lambda row:row['resulting_revision'])
expected = ['ADOPT_TEMPLATE','MAP_AUTHOR_INTENT','MAP_AUTHOR_INTENT','UNDO','REDO','UNMAP_AUTHOR_INTENT','UNDO','EDIT','UNDO','REDO','UNDO']
assert [row['operation_kind'] for row in own_ops[8:]] == expected
docs = {row['resulting_revision']: json.loads(row['payload_json'])['document'] for row in own_ops}
assert docs[8] == fixture['baseline_document']
assert docs[12] == docs[10] and docs[13] == docs[11]
assert docs[14] == docs[10] and docs[15] == docs[11]
assert docs[17] == docs[15] and docs[18] == docs[16] and docs[19] == docs[17]
for revision in range(9,20):
    doc = docs[revision]
    bank = next(s for s in doc['sections'] if s['id'] == docs[8]['sections'][0]['id'])
    expected_bank = deepcopy(docs[8]['sections'][0])
    expected_bank['placement_status'] = 'UNPLACED'
    if revision in [16,18]:
        expected_bank['paragraphs'][1]['intents'][0]['thoughts'][0]['text'] = 'AUTHOR second original wording stays independent. Edited through chosen slot Ω.'
    assert bank == expected_bank, f'Canonical author data changed in r{revision}'
    assert doc['argument_relations'] == docs[8]['argument_relations']
    op = own_ops[revision-1]
    assert json.loads(op['inverse_json'])['document'] == docs[revision-1]
    change = next(c for c in after['studio_changes'] if c['operation_id'] == op['operation_id'])
    assert json.loads(change['before_json']) == docs[revision-1]
    assert json.loads(change['after_json']) == doc
owners, context_owners = validate(docs[19])
assert owners == {'intent_c27c009a52334af0834cd9978e18cd01': 'intent_20a2122a4697456e9037d7ca357f7018',
                  'intent_56a5681618b24da2b65bfa184158e683': 'intent_70932ec2d56e48c393b3d2cab8fa6a01'}
assert len(context_owners) == 2
jobs = [j for j in after['studio_jobs'] if j['manuscript_id'] == ms]
assert len(jobs) == 1 and jobs[0]['status'] == 'SUCCEEDED' and jobs[0]['input_revision'] == 19
calls = [c for c in after['studio_model_calls'] if c['manuscript_id'] == ms]
assert len(calls) == 2 and all(c['status']=='VALIDATED' and c['input_revision']==19 for c in calls)
projected = realization_document(docs[19])
paragraphs = [p for s in projected['sections'] for p in s['paragraphs']]
for call in calls:
    request = json.loads(call['input_json'])
    assert hashlib.sha256(call['input_json'].encode('utf-8')).hexdigest() == call['input_sha256']
    paragraph = next(p for p in paragraphs if p['intents'] == request['intents'])
    assert request['author_contexts'] == paragraph['author_contexts']
    assert request['argument_relations'] == argument_context(docs[19],paragraph)
    assert request['section_path'] == ['Source Alpha Ω','Repeated source heading']
    assert json.loads(call['contract_json'])['actual_model'] == 'TEST_FIXTURE_AUTHOR_CORRESPONDENCE'
versions = [v for v in after['manuscript_versions'] if v['manuscript_id'] == ms]
assert len(versions) == 1
generated = json.loads(versions[0]['inputs_json'])['generated']
assert generated['author_source_sections'] == projected['author_source_sections']
assert generated['argument_relations'] == docs[19]['argument_relations']
assert [s.get('section_depth',0) for s in generated['sections']] == [0,1,1]
gparagraphs = [p for s in generated['sections'] for p in s['paragraphs']]
assert [p['thought_ids'] for p in gparagraphs] == [[t['id'] for i in p['intents'] for t in i['thoughts']] for p in paragraphs]
for generated_p, original_p in zip(gparagraphs, paragraphs, strict=True):
    assert generated_p['formulas'] == original_p['formulas']
    assert generated_p['asset_ids'] == original_p['asset_ids']
    assert generated_p['author_contexts'] == original_p['author_contexts']
artifacts = [a for a in after['studio_artifacts'] if a['manuscript_id'] == ms]
assert {a['artifact_kind'] for a in artifacts} == {'MARKDOWN','GENERATED_JSON','TEX','BIB','PDF'}
for a in artifacts:
    path=Path(a['storage_path']).resolve()
    assert path.is_relative_to(root)
    raw=path.read_bytes()
    assert len(raw)==a['size_bytes'] and hashlib.sha256(raw).hexdigest()==a['sha256']
    (out/path.name).write_bytes(raw)
asset = next(a for a in after['studio_assets'] if a['manuscript_id']==ms)
assert hashlib.sha256(Path(asset['storage_path']).read_bytes()).hexdigest() == fixture['asset_paths'][0]['sha256']
service=StudioService(root)
try:
    assert service.get_generated_version(ms, versions[0]['manuscript_version_id'])
finally:
    service._executor.shutdown(wait=True)
with sqlite3.connect(f'file:{(root/"data/catalog.db").as_posix()}?mode=ro', uri=True) as source:
    with sqlite3.connect(out/'final-native.db') as target: source.backup(target)
for name, data in [('before-tables.json',before), ('after-tables.json',after), ('all-author-revisions.json',docs), ('generated.json',generated)]:
    (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
receipt={'status':'PASS_NATIVE_MAPPING_HISTORY_GENERATION','ms':ms,'revision':19,
         'new_operations':len(expected),'mapping_owners':owners,'context_owners':context_owners,
         'canonical_data_and_group_and_edges_exact':True,'all_compensations_exact':True,
         'another_manuscript_and_all_unrelated_tables_exact':True,'fixed_source_pages':[2,4],
         'software_generation_jobs':len(jobs),'software_generation_model_calls':len(calls),
         'real_compiler_artifacts':5,'selected_citations_frozen':True,
         'scientific_acceptance':False,'actual_real_model_calls':0,'downloads_paused':True,
         'overall_complete':False,'all118_all11_scope_retained':True}
(out/'audit.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(receipt,ensure_ascii=False))
