"""Current runtime, fixed source and all four original request retries; zero new calls."""
import ast
import hashlib
import json
import re
import sqlite3
import subprocess
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
path = repo / '.tmp/scholar-scientific-binding-original-final-v3.json'
if path.exists():
    raise RuntimeError('Preserve the exclusive final receipt.')
tree = ast.parse((repo / '.tmp/scholar-overview-native-v1.py').read_text(encoding='utf-8'))
guard = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'process_guard' for target in node.targets))
subprocess.run(['powershell', '-NoProfile', '-Command', guard + '\n' + (repo / '.tmp/scholar-current-preview-proof.ps1').read_text(encoding='utf-8')], cwd=repo, check=True)
native = json.loads((repo / '.tmp/scholar-studio-shared-native-v2.json').read_text(encoding='utf-8'))
assert native['status'] == 'PASS_NATIVE_SHARED_STUDIO_FIXED_CONVERSATION'
root = Path(native['root']).resolve()
db = root / 'data/catalog.db'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
canonical = lambda value: sha(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode())
before = sha(db.read_bytes())
prior_final = json.loads((repo / '.tmp/scholar-withdrawal-original-final-v3.json').read_text(encoding='utf-8'))
# The retained v1 check failed across the unfixed startup. No original hash is restored.
fixed_baseline = json.loads((repo / '.tmp/scholar-scientific-binding-post-migration-baseline-v3.json').read_text(encoding='utf-8'))
migration = json.loads((repo / '.tmp/scholar-scientific-binding-migration-v3.json').read_text(encoding='utf-8'))
assert migration['original_database_sha256'] == prior_final['database_sha256']
assert before == migration['current_database_sha256']
assert migration['old_tables_unchanged_except_catalog_schema_version'] and migration['new_review_tables_empty']
assert before == fixed_baseline['database_sha256'], 'Fixed startup must preserve database bytes.'

def assert_all_original_records():
    with sqlite3.connect(f'{db.as_uri()}?mode=ro', uri=True) as conn:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        actual = {table: canonical(conn.execute('SELECT * FROM "' + table.replace('"', '""') + '" ORDER BY rowid').fetchall()) for table in tables}
        assert actual == fixed_baseline['all_table_sha256'], 'Every original table must remain unchanged.'
        assert canonical(conn.execute('SELECT * FROM sqlite_master ORDER BY name').fetchall()) == fixed_baseline['schema_sha256']

assert_all_original_records()
request_ids = ['research-chat-native-message-v3', 'research-conversation-native-followup-v1', 'studio-shared-native-first-v1', 'studio-shared-native-followup-v1']
with sqlite3.connect(f'{db.as_uri()}?mode=ro', uri=True) as conn:
    requests = {rid: json.loads(conn.execute('SELECT request_json FROM research_discussion_requests WHERE request_id=?', (rid,)).fetchone()[0]) for rid in request_ids}
    counts = {table: conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ['research_discussion_jobs', 'research_discussion_messages', 'research_discussion_annotations', 'studio_model_calls']}
assert counts['research_discussion_jobs'] == 4 and counts['research_discussion_messages'] == 8 and counts['research_discussion_annotations'] == 2
responses = []
def call(client, method, endpoint, expected=200, **kwargs):
    raw = client.request(method, endpoint, **kwargs)
    assert raw.status_code == expected, raw.text[:1500]
    body = raw.json()
    responses.append({'method': method, 'path': endpoint, 'status': raw.status_code, 'body': body})
    return body

with httpx.Client(base_url='http://127.0.0.1:8885', timeout=45) as catalog, httpx.Client(base_url='http://127.0.0.1:8874/api', timeout=45) as studio, httpx.Client(base_url='http://127.0.0.1:3000', timeout=45) as frontend:
    receipts = {}
    for rid, payload in requests.items():
        with sqlite3.connect(f'{db.as_uri()}?mode=ro', uri=True) as conn:
            owner = conn.execute('SELECT scope_key FROM research_discussion_requests WHERE request_id=?', (rid,)).fetchone()[0]
        receipt = call(catalog, 'GET', f'/api/research/discussion/requests/{rid}', params={'scope': owner})
        assert receipt['job']['status'] == 'COMPLETE'
        previous = next(item['body'] for item in prior_final['responses'] if item['method'] == 'GET' and item['path'] == f'/api/research/discussion/requests/{rid}')
        assert receipt == previous, 'The exact original discussion receipt must remain unchanged.'
        repeated = call(studio, 'POST', '/research/discussion/messages', 202, json=payload)
        assert repeated['job'] == receipt['job'] and repeated['messages'] == receipt['messages'] and repeated['studio_messages'] == receipt['studio_messages']
        receipts[rid] = receipt
    ms = native['manuscript_id']
    first, second = [receipts[rid] for rid in request_ids[-2:]]
    bound = second['job']['input']['source']['context']
    assert call(studio, 'POST', '/research/discussion/context', json=bound['target']) == bound
    for receipt in [first, second]:
        for message in receipt['studio_messages']:
            original = call(studio, 'GET', f"/manuscripts/{ms}/chat/{message['message_id']}/context")
            assert original['quote']['object_text'] == bound['object_text']
            assert original['quote']['text'] == '固定来源' and original['quote']['source']['anchor_revision'] == 0
    scope = bound['scope_key']
    historical = call(studio, 'GET', f"/research/discussion/messages/{second['messages'][-1]['message_id']}/context", params={'scope': scope})
    assert len(historical['conversation']) == 4 and historical['sources'][0]['context'] == bound
    calls = call(studio, 'GET', f'/manuscripts/{ms}/model-calls')
    assert len(calls) == 2 and {row['call_id'] for row in calls} == set(native['new_studio_model_call_ids'])
    for row, receipt in zip(sorted(calls, key=lambda row: row['started_at']), [first, second]):
        assert row['contract'] == receipt['job']['model_contract'] and row['input'] == receipt['job']['input']['writing_payload']
        assert row['status'] == 'RETURNED' and row['task'] == 'writing_chat'
    assert canonical(call(studio, 'GET', f'/manuscripts/{ms}/workspace')) == native['owned_software_workspace_sha256']
    assert {ms: canonical(call(studio, 'GET', f'/manuscripts/{ms}/workspace')) for ms in native['old_workspace_sha256']} == native['old_workspace_sha256']
    response_ms = 'manuscript_bd7568923be94a2c8510d176010e4cca'
    packages = call(studio, 'GET', f'/manuscripts/{response_ms}/packages')
    zips = {}
    for package in packages:
        response = studio.get(f"/manuscripts/{response_ms}/packages/{package['package_id']}/download")
        assert response.status_code == 200
        zips[package['package_id']] = sha(response.content)
    assert zips == native['old_package_zip_sha256']
    published = {}
    for endpoint, name in [('/', 'catalog_web.html'), ('/catalog-research-chat.js', 'catalog_research_chat.js'), ('/catalog-research-workspaces.js', 'catalog_research_workspaces.js'), ('/catalog-research-overview.js', 'catalog_research_overview.js'), ('/catalog-collections.js', 'catalog_collections.js'), ('/catalog-review-workflow.js', 'catalog_review_workflow.js'), ('/catalog-scientific-review.js', 'catalog_scientific_review.js')]:
        response = catalog.get(endpoint)
        assert response.status_code == 200 and response.content == (repo.parent / f'RSTV4/src/rstv4/{name}').read_bytes()
        published[name] = sha(response.content)
    for manuscript_id in native['old_workspace_sha256']:
        review = call(catalog, 'GET', f'/api/catalog/manuscripts/{manuscript_id}/scientific-review')
        assert review['manuscript']['manuscript_id'] == manuscript_id and review['reviews'] == []
    html = frontend.get('/')
    assert html.status_code == 200
    assets = {}
    for asset in set(re.findall(r'(?:src|href)="([^"?]+\.(?:js|css))"', html.text)):
        raw = frontend.get(asset)
        assert raw.status_code == 200 and raw.content == (repo.parent / 'writing-studio/dist/client' / asset.lstrip('/')).read_bytes()
        assets[asset] = sha(raw.content)
    scripts = ''.join((repo.parent / 'writing-studio/dist/client' / asset.lstrip('/')).read_text(encoding='utf-8') for asset in assets if asset.endswith('.js'))
    assert 'RSTV4ResearchChat' in scripts and '原来源尚未核实' in scripts and '继续这段讨论' in scripts
    assert '当前对象 · 此版本' in scripts and 'studio_discussion' in scripts and '选用这条原来源' in scripts
    assert '定位原对象' in scripts and 'discussion_source' in scripts and 'http://127.0.0.1:8885/' in scripts
assert sha(db.read_bytes()) == before
with sqlite3.connect(f'{db.as_uri()}?mode=ro', uri=True) as conn:
    assert counts == {table: conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in counts}
    for table, expected in native['unchanged_scientific_table_sha256'].items():
        assert canonical(conn.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall()) == expected
    old_calls = [row for row in conn.execute('SELECT * FROM studio_model_calls ORDER BY rowid') if row[0] not in native['new_studio_model_call_ids']]
    assert canonical(old_calls) == native['original_studio_model_calls_sha256']
result = {'status': 'PASS_CURRENT_SCIENTIFIC_BINDING_AND_ORIGINAL_RETRIES', 'new_jobs': 0, 'new_model_calls': 0, 'browser_verified': False, 'counts': counts, 'database_sha256': before, 'legacy_retry_verified': True, 'studio_origin_verified': True, 'source_context_sha256': bound['context_sha256'], 'actual_contracts': native['actual_contracts'], 'historical_chain_messages': 4, 'published_sha256': published, 'compiled_assets_sha256': assets, 'responses': responses}
assert_all_original_records()
result['bytes_changed_only_by_declared_7_to_8_migration'] = before == migration['current_database_sha256'] and before != prior_final['database_sha256']
result['original_97_tables_preserved_except_catalog_schema_version'] = True
result['new_scientific_review_tables_empty'] = True
result['earlier_pre_fix_startup_byte_equality_failure_retained'] = True
result['fixed_startup_all_tables_and_bytes_unchanged'] = True
result['all_tables_verified'] = len(fixed_baseline['all_table_sha256'])
result['exact_previous_discussion_receipts_unchanged'] = True
with path.open('x', encoding='utf-8') as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
print(json.dumps({key: value for key, value in result.items() if key not in ['responses', 'actual_contracts']}, ensure_ascii=False))
