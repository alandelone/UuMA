"""Verify current code, both historical requests and saved provenance; no new jobs."""
import ast
import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
path = repo / '.tmp/scholar-conversation-final-v1.json'
if path.exists():
    raise RuntimeError('Preserve the exclusive final receipt')
tree = ast.parse((repo / '.tmp/scholar-overview-native-v1.py').read_text(encoding='utf-8'))
guard = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'process_guard' for target in node.targets))
subprocess.run(['powershell', '-NoProfile', '-Command', guard], cwd=repo, check=True)
native = json.loads((repo / '.tmp/scholar-conversation-native-v1.json').read_text(encoding='utf-8'))
original = json.loads((repo / '.tmp/scholar-research-chat-native-v3.json').read_text(encoding='utf-8'))
assert native['status'] == 'PASS_NATIVE_FIXED_CONVERSATION'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
db = Path(native['root']) / 'data/catalog.db'
before = sha(db.read_bytes())
with sqlite3.connect(f'{db.resolve().as_uri()}?mode=ro', uri=True) as conn:
    counts = {name: conn.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0] for name in ['research_discussion_jobs', 'research_discussion_messages', 'research_discussion_annotations']}
    requests = {request_id: json.loads(conn.execute('SELECT request_json FROM research_discussion_requests WHERE request_id=?', (request_id,)).fetchone()[0]) for request_id in [original['message_request_id'], native['message_request_id']]}
assert counts == {'research_discussion_jobs': 2, 'research_discussion_messages': 4, 'research_discussion_annotations': 1}
assert 'parent_message_id' not in requests[original['message_request_id']]
bound = next(row['body'] for row in original['responses'] if row['path'] == '/api/catalog/discussion/context')
with httpx.Client(base_url='http://127.0.0.1:8885', timeout=30) as client:
    receipts = {}
    for request_id, payload in requests.items():
        response = client.get(f'/api/catalog/discussion/requests/{request_id}', params={'scope': bound['scope_key']})
        assert response.status_code == 200, response.text
        first = response.json()
        assert first['job']['status'] == 'COMPLETE'
        repeated = client.post('/api/catalog/discussion/messages', json=payload)
        assert repeated.status_code == 202, repeated.text
        response = client.get(f'/api/catalog/discussion/requests/{request_id}', params={'scope': bound['scope_key']})
        assert response.status_code == 200
        assert response.json()['job'] == first['job'] and response.json()['messages'] == first['messages']
        receipts[request_id] = first
    assert receipts[original['message_request_id']]['job']['model_contract'] == original['actual_contract']
    current = receipts[native['message_request_id']]
    assert current['job']['model_contract'] == native['actual_contract']
    assert len(current['job']['input']['conversation']) == 2
    historical = client.get(f"/api/catalog/discussion/messages/{current['messages'][-1]['message_id']}/context", params={'scope': bound['scope_key']})
    assert historical.status_code == 200
    historical = historical.json()
    assert len(historical['conversation']) == 4
    assert historical['sources'][0]['context'] == bound
    history = client.post('/api/catalog/discussion/history', json={'target': bound['target']})
    assert history.status_code == 200 and len(history.json()['messages']) == 4
    published = {}
    for endpoint, name in [('/', 'catalog_web.html'), ('/catalog-research-chat.js', 'catalog_research_chat.js'), ('/catalog-research-workspaces.js', 'catalog_research_workspaces.js')]:
        response = client.get(endpoint)
        assert response.status_code == 200 and response.content == (repo.parent / f'RSTV4/src/rstv4/{name}').read_bytes()
        published[name] = sha(response.content)
assert sha(db.read_bytes()) == before
result = {'status': 'PASS_CURRENT_CONVERSATION_LEGACY_RETRY_AND_PUBLISHED_BYTES', 'new_jobs': 0, 'new_model_calls': 0, 'browser_verified': False, 'counts': counts, 'database_sha256': before, 'legacy_retry_verified': True, 'source_context_sha256': bound['context_sha256'], 'actual_contract': current['job']['model_contract'], 'original_contract': original['actual_contract'], 'published_sha256': published, 'historical_source_state': historical['sources'][0]['current_source_state'], 'historical_chain_messages': 4}
with path.open('x', encoding='utf-8') as out:
    json.dump(result, out, ensure_ascii=False, indent=2)
print(json.dumps(result, ensure_ascii=False))
