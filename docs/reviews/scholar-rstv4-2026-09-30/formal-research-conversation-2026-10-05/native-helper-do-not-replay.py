"""Continue the original actual model reply once; never replay this mutation helper."""
import ast
import hashlib
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
os.environ.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
path = repo / '.tmp/scholar-conversation-native-v1.json'
if path.exists():
    raise RuntimeError('Preserve this receipt; use read-only observation to resume')
tree = ast.parse((repo / '.tmp/scholar-overview-native-v1.py').read_text(encoding='utf-8'))
guard = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'process_guard' for target in node.targets))
for check in [(repo / '.tmp/scholar-current-preview-proof.ps1').read_text(encoding='utf-8'), guard]:
    subprocess.run(['powershell', '-NoProfile', '-Command', check], cwd=repo, check=True)
root = Path(json.loads((repo / '.tmp/scholar-overview-services.json').read_text(encoding='utf-8'))['root']).resolve()
original = json.loads((repo / '.tmp/scholar-research-chat-native-v3.json').read_text(encoding='utf-8'))
assert root == Path(original['root']).resolve()
sha = lambda raw: hashlib.sha256(raw).hexdigest()
canonical = lambda value: sha(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode())
proof = {'status': 'STARTED', 'root': str(root), 'responses': [], 'browser_verified': False, 'production_data_changed': False, 'scientific_approval': False, 'new_actual_model_calls': 0}
def persist():
    path.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding='utf-8')
persist()
with httpx.Client(base_url='http://127.0.0.1:8885', timeout=45) as catalog, httpx.Client(base_url='http://127.0.0.1:8874/api', timeout=45) as studio:
    def call(client, method, endpoint, expected=200, **kwargs):
        response = client.request(method, endpoint, **kwargs)
        body = response.json()
        proof['responses'].append({'server': 'catalog' if client is catalog else 'studio', 'method': method, 'path': endpoint, 'status': response.status_code, 'body': body})
        persist()
        assert response.status_code == expected, response.text[:1500]
        return body
    old_ms = {ms: canonical(call(studio, 'GET', f'/manuscripts/{ms}/workspace')) for ms in original['old_workspace_sha256']}
    assert old_ms == original['old_workspace_sha256']
    response_ms = 'manuscript_bd7568923be94a2c8510d176010e4cca'
    packages = call(studio, 'GET', f'/manuscripts/{response_ms}/packages')
    assert len(packages) == 7
    def package_hashes():
        hashes = {}
        for package in packages:
            response = studio.get(f"/manuscripts/{response_ms}/packages/{package['package_id']}/download")
            assert response.status_code == 200
            hashes[package['package_id']] = sha(response.content)
        return hashes
    zips = package_hashes()
    assert zips == original['old_package_zip_sha256']
    scientific_tables = list(original['scientific_records_sha256'])
    with sqlite3.connect(root / 'data/catalog.db') as conn:
        before_records = {name: canonical(conn.execute(f'SELECT * FROM {name} ORDER BY rowid').fetchall()) for name in scientific_tables}
        before_jobs = conn.execute('SELECT COUNT(*) FROM research_discussion_jobs').fetchone()[0]
    assert before_records == original['scientific_records_sha256'] and before_jobs == 1
    bound = next(row['body'] for row in original['responses'] if row['path'] == '/api/catalog/discussion/context')
    first = call(catalog, 'GET', f"/api/catalog/discussion/requests/{original['message_request_id']}", params={'scope': bound['scope_key']})
    assert first['job']['status'] == 'COMPLETE' and first['job']['model_contract'] == original['actual_contract']
    parent = first['messages'][-1]['message_id']
    frozen = first['messages'][-1]['quote']
    selected = {'target': bound['target'], 'expected_context_sha256': bound['context_sha256'], 'history_message_id': parent, 'quote': {key: frozen[key] for key in ['text', 'start', 'end', 'offset_unit', 'annotation'] if key in frozen}}
    body = {'request_id': 'research-conversation-native-followup-v1', 'content': '请接着上一轮回答，指出上一轮用户问题问了哪些内容，再用一句话解释为什么仍须保留原文件和解析版本的未知信息。只讨论这个固定来源，不批准或更改科研状态。', 'source': selected, 'parent_message_id': parent}
    proof.update(message_request_id=body['request_id'], parent_message_id=parent, source_context_sha256=bound['context_sha256'])
    persist()
    call(catalog, 'POST', '/api/catalog/discussion/messages', 404, json={**body, 'request_id': 'conversation-invalid-parent-v1', 'parent_message_id': 'absent-parent-message'})
    receipt = call(catalog, 'POST', '/api/catalog/discussion/messages', 202, json=body)
    started = time.monotonic()
    while receipt['job']['status'] in ['QUEUED', 'RUNNING'] and receipt['execution_observation'] == 'LIVE_WORKER' and time.monotonic() - started < 360:
        time.sleep(2)
        receipt = call(catalog, 'GET', f"/api/catalog/discussion/requests/{body['request_id']}", params={'scope': bound['scope_key']})
    proof.update(model_request_status=receipt['job']['status'], execution_observation=receipt['execution_observation'])
    persist()
    assert receipt['job']['status'] == 'COMPLETE', 'Resume this actual request read-only; do not create another job'
    conversation = receipt['job']['input']['conversation']
    assert len(conversation) == 2
    for old, saved in zip(first['messages'], conversation):
        assert {key: old[key] for key in saved} == saved
    assert receipt['messages'][0]['reply_to'] == parent
    assert receipt['job']['input']['source']['context'] == bound
    assert receipt['job']['model_contract']['prompt_version'] == 'research-chat-v2-fixed-conversation'
    assert receipt['job']['model_contract']['actual_model'] and receipt['job']['raw_response']
    repeat = call(catalog, 'POST', '/api/catalog/discussion/messages', 202, json=body)
    assert repeat['messages'] == receipt['messages'] and repeat['job'] == receipt['job']
    historical = call(catalog, 'GET', f"/api/catalog/discussion/messages/{receipt['messages'][-1]['message_id']}/context", params={'scope': bound['scope_key']})
    assert len(historical['conversation']) == 4
    assert historical['sources'][0]['context'] == bound
    history = call(catalog, 'POST', '/api/catalog/discussion/history', json={'target': bound['target']})
    assert len(history['messages']) == 4 and len(history['annotations']) == 1
    with sqlite3.connect(root / 'data/catalog.db') as conn:
        assert {name: canonical(conn.execute(f'SELECT * FROM {name} ORDER BY rowid').fetchall()) for name in scientific_tables} == before_records
        assert conn.execute('SELECT COUNT(*) FROM research_discussion_jobs').fetchone()[0] == 2
        assert conn.execute('SELECT COUNT(*) FROM research_discussion_messages').fetchone()[0] == 4
        assert conn.execute('SELECT COUNT(*) FROM research_discussion_annotations').fetchone()[0] == 1
    assert {ms: canonical(call(studio, 'GET', f'/manuscripts/{ms}/workspace')) for ms in old_ms} == old_ms
    assert package_hashes() == zips
    published = {}
    for endpoint, name in [('/', 'catalog_web.html'), ('/catalog-research-chat.js', 'catalog_research_chat.js'), ('/catalog-research-workspaces.js', 'catalog_research_workspaces.js')]:
        response = catalog.get(endpoint)
        assert response.status_code == 200 and response.content == (repo.parent / f'RSTV4/src/rstv4/{name}').read_bytes()
        published[name] = sha(response.content)
    proof.update(status='PASS_NATIVE_FIXED_CONVERSATION', new_actual_model_calls=1, actual_model=receipt['job']['model_contract']['actual_model'], actual_contract=receipt['job']['model_contract'], original_contract=original['actual_contract'], old_workspace_sha256=old_ms, old_package_zip_sha256=zips, scientific_records_sha256=before_records, published_sha256=published, frozen_parent_messages=2, historical_chain_messages=4, request_retry_added_calls=0)
    persist()
print(json.dumps({key: value for key, value in proof.items() if key not in ['responses', 'scientific_records_sha256', 'old_workspace_sha256', 'old_package_zip_sha256', 'root']}, ensure_ascii=False))
