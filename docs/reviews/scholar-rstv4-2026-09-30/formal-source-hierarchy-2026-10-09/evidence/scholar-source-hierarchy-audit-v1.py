import hashlib
import json
import sqlite3
from copy import deepcopy
from pathlib import Path

from rstv4.research_views import skeleton_source

repo = Path(__file__).resolve().parents[1]
info = json.loads((repo / '.tmp/scholar-source-hierarchy-fixture-v1.json').read_text(encoding='utf-8'))
baseline = json.loads((repo / '.tmp/scholar-source-hierarchy-before-v1/baseline.json').read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
def snapshot(path):
    with sqlite3.connect(f'file:{Path(path).as_posix()}?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        tables = {r[0]: [dict(v) for v in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
                  for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
        assert not conn.execute('PRAGMA foreign_key_check').fetchone()
        sources = {s: skeleton_source(conn, s) for s in info['legacy_sources_exact']}
        current = skeleton_source(conn, info['skeleton_id']) if str(path) == info['database'] else None
    return tables, sources, current
tables, legacy, current_source = snapshot(info['database'])
old_tables, old_sources, _ = snapshot(baseline['database'])
assert old_tables == baseline['tables'] and old_sources == info['legacy_sources_exact']
assert legacy == info['legacy_sources_exact']
assert sha(baseline['golden_database']) == baseline['golden_sha256']
for table, old in info['before_tables'].items():
    if table != 'schema_version':
        assert tables[table][:len(old)] == old, table
for table in ['approval_grants', 'acquisition_model_call_events', 'studio_model_calls', 'studio_jobs']:
    assert tables[table] == info['before_tables'][table], table
assert tables['skeleton_source_outlines'] == info['after_fixture_tables']['skeleton_source_outlines']
assert current_source['context_sha256'] == info['preview']['source_sha256']
ops = [r for r in tables['studio_operations'] if r['manuscript_id'] == info['manuscript_id']]
ops.sort(key=lambda r: r['resulting_revision'])
assert [r['resulting_revision'] for r in ops] == list(range(1, 9))
documents = {r['resulting_revision']: json.loads(r['payload_json'])['document'] for r in ops}
for row in ops[1:]:
    assert row['base_revision'] == row['resulting_revision'] - 1
    assert json.loads(row['inverse_json'])['document'] == documents[row['base_revision']]
original = info['initial_document']
assert documents[1] == documents[3] == documents[6] == documents[8] == original
assert documents[2] == documents[4]
author = original['sections'][0]
for revision, document in documents.items():
    saved = deepcopy(next(s for s in document['sections'] if s['id'] == author['id']))
    saved.pop('placement_status', None)
    assert saved == author, revision
    assert document['argument_relations'] == original['argument_relations']
    assert 'SOFTWARE_SOURCE_BODY' not in json.dumps(document)
partial = documents[2]['sections'][1:]
assert len(partial) == 3 and [len(s['paragraphs']) for s in partial] == [0, 0, 1]
assert partial[1]['parent_section_id'] == partial[0]['id']
assert partial[2]['parent_section_id'] == partial[1]['id']
assert partial[2]['paragraphs'][0]['template_source']['source_path'] == [s['title'] for s in partial]
nested = documents[5]['sections'][4:]
assert len(nested) == 5 and sum(len(s['paragraphs']) for s in nested) == 10
assert nested[0]['parent_section_id'] == nested[4]['parent_section_id'] == partial[0]['id']
assert nested[1]['parent_section_id'] == nested[3]['parent_section_id'] == nested[0]['id']
assert nested[2]['parent_section_id'] == nested[1]['id']
replacement = documents[7]['sections']
assert len(replacement) == 6 and replacement[-1]['placement_status'] == 'UNPLACED'
assert replacement[1]['parent_section_id'] == replacement[3]['parent_section_id'] == replacement[0]['id']
assert replacement[2]['parent_section_id'] == replacement[1]['id']
assert not replacement[4].get('parent_section_id')
assert len({s['id'] for s in replacement}) == 6
for section in replacement[:-1]:
    for paragraph in section['paragraphs']:
        assert paragraph['purpose'] == paragraph['paradigm'] == ''
        assert paragraph['asset_ids'] == paragraph['formulas'] == []
        assert paragraph['intents'][0]['thoughts'] == []
        assert paragraph['intents'][0]['template_source'] == paragraph['template_source']
        assert paragraph['template_source']['source_sha256'] == info['preview']['source_sha256']
asset_id = author['paragraphs'][0]['asset_ids'][0]
asset = next(r for r in tables['studio_assets'] if r['asset_id'] == asset_id)
assert Path(asset['storage_path']).read_bytes() == b'x,y\n1,2\n' and sha(asset['storage_path']) == asset['sha256']
stored = next(r for r in tables['studio_documents'] if r['manuscript_id'] == info['manuscript_id'])
assert stored['revision'] == 8 and json.loads(stored['document_json']) == original
templates = [r for r in tables['studio_template_instances'] if r['manuscript_id'] == info['manuscript_id']]
adoptions = [json.loads(r['adopted_json']) for r in templates]
assert [a['resulting_revision'] for a in adoptions] == [2, 5, 7]
assert [a['request']['mode'] for a in adoptions] == ['INSERT', 'INSERT', 'REPLACE']
assert [a['request']['scope_type'] for a in adoptions] == ['paper', 'section', 'paper']
assert all(a['source'] == info['preview'] for a in adoptions)
full = json.loads((repo / '.tmp/scholar-source-hierarchy-full-v2.json').read_text(encoding='utf-8'))
assert full['status'] == 'PASS' and not full['changed_during_verification']
assert '1015 passed, 20 warnings' in (repo / '.tmp/scholar-source-hierarchy-full-v2.log').read_text(encoding='utf-8')
assert sha(repo / '.tmp/scholar-source-hierarchy-full-v2.log') == full['log_sha256']
paths = ['RSTV4/src/rstv4/database.py', 'RSTV4/src/rstv4/parser_quality.py',
         'RSTV4/src/rstv4/acquisition.py', 'RSTV4/src/rstv4/research_views.py',
         'RSTV4/src/rstv4/studio_templates.py', 'RSTV4/src/rstv4/skeleton_outline.py',
         'RSTV4/tests/test_skeleton_source_outline.py', 'RSTV4/tests/test_fieldkg_semantics.py',
         'writing-studio/lib/studio-types.ts', 'writing-studio/components/studio-template-adoption.tsx']
post_full = []
for relative in paths:
    path = repo.parent / relative
    if sha(path) != full['after_sha256'][str(path)]:
        post_full.append(relative)
assert post_full == ['writing-studio/components/studio-template-adoption.tsx']
before_modal = (repo / '.tmp/scholar-source-hierarchy-modal-before-v1.tsx').read_text(encoding='utf-8')
assert (repo.parent / post_full[0]).read_text(encoding='utf-8') == before_modal.replace(
    'className="sm:max-w-2xl"', 'className="sm:max-w-2xl max-h-[calc(100dvh-2rem)] overflow-y-auto"').replace(
    'className="max-h-72 overflow-y-auto', 'className="max-h-[min(18rem,35dvh)] overflow-y-auto')
result = {'status': 'PASS_SCOPED_SOURCE_HIERARCHY_AND_NATIVE_HISTORY', 'overall_complete': False,
          'manuscript_id': info['manuscript_id'], 'revision': 8, 'native_operations_added': 7,
          'fixture_author_operations': 1, 'adoptions': adoptions,
          'documents_by_revision': documents, 'operations': ops, 'old_table_count': len(old_tables),
          'new_table_count': len(tables), 'old_runtime_rows_exact': True, 'legacy_sources_exact': True,
          'golden_database_sha256': baseline['golden_sha256'], 'author_objects_exact_every_revision': True,
          'csv_sha256': asset['sha256'], 'new_actual_model_calls': 0, 'new_jobs': 0,
          'new_scientific_approvals': 0, 'full_tests_passed': 1015, 'warnings': 20,
          'full_log_sha256': full['log_sha256'], 'post_full_delta': post_full,
          'final_source_sha256': {relative: sha(repo.parent / relative) for relative in paths},
          'download_tests_paused': True, 'final_document_exact_initial_author_document': True}
(repo / '.tmp/scholar-source-hierarchy-audit-v1.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in result.items() if k not in {'adoptions', 'documents_by_revision', 'operations', 'final_source_sha256'}}, ensure_ascii=False))
