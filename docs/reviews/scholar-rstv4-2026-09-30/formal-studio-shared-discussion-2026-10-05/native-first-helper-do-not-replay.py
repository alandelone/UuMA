"""Two real Studio discussion calls on the owned software manuscript. Never replay."""
import ast
import hashlib
import json
import re
import sqlite3
import subprocess
import time
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
path = repo / '.tmp/scholar-studio-shared-native-v1.json'
if path.exists():
    raise RuntimeError('Preserve this receipt and resume the saved request read-only.')
tree = ast.parse((repo / '.tmp/scholar-overview-native-v1.py').read_text(encoding='utf-8'))
guard = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'process_guard' for target in node.targets))
subprocess.run(['powershell', '-NoProfile', '-Command', guard + '\n' + (repo / '.tmp/scholar-current-preview-proof.ps1').read_text(encoding='utf-8')], cwd=repo, check=True)
original = json.loads((repo / '.tmp/scholar-research-chat-native-v3.json').read_text(encoding='utf-8'))
previous = json.loads((repo / '.tmp/scholar-conversation-native-v1.json').read_text(encoding='utf-8'))
root = Path(original['root']).resolve()
assert root == Path(json.loads((repo / '.tmp/scholar-overview-services.json').read_text(encoding='utf-8'))['root']).resolve()
db = root / 'data/catalog.db'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
canonical = lambda value: sha(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode())
manuscript = 'manuscript_0dd6fc921b534d44b01735629157f761'
proof = {'status': 'STARTED', 'root': str(root), 'manuscript_id': manuscript, 'responses': [], 'browser_verified': False, 'production_data_changed': False, 'scientific_approval': False, 'new_actual_model_calls': 0, 'requests_submitted': []}
def persist():
    path.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding='utf-8')
persist()

def connection():
    return sqlite3.connect(f'{db.as_uri()}?mode=ro', uri=True)

with httpx.Client(base_url='http://127.0.0.1:8885', timeout=45) as catalog, httpx.Client(base_url='http://127.0.0.1:8874/api', timeout=45) as studio, httpx.Client(base_url='http://127.0.0.1:3000', timeout=45) as frontend:
    def call(client, method, endpoint, expected=200, **kwargs):
        response = client.request(method, endpoint, **kwargs)
        body = response.json()
        proof['responses'].append({'server': 'catalog' if client is catalog else 'studio', 'method': method, 'path': endpoint, 'status': response.status_code, 'body': body})
        persist()
        assert response.status_code == expected, response.text[:2000]
        return body

    old_ms = {ms: canonical(call(studio, 'GET', f'/manuscripts/{ms}/workspace')) for ms in original['old_workspace_sha256']}
    assert old_ms == original['old_workspace_sha256']
    response_ms = 'manuscript_bd7568923be94a2c8510d176010e4cca'
    packages = call(studio, 'GET', f'/manuscripts/{response_ms}/packages')
    assert len(packages) == 7
    def package_hashes():
        result = {}
        for package in packages:
            response = studio.get(f"/manuscripts/{response_ms}/packages/{package['package_id']}/download")
            assert response.status_code == 200
            result[package['package_id']] = sha(response.content)
        return result
    zips = package_hashes()
    assert zips == original['old_package_zip_sha256']
    with connection() as conn:
        before_science = {table: canonical(conn.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall()) for table in original['scientific_records_sha256']}
        before_call_ids = [row[0] for row in conn.execute('SELECT model_call_id FROM studio_model_calls ORDER BY rowid')]
        assert before_science == original['scientific_records_sha256']
        assert conn.execute('SELECT COUNT(*) FROM research_discussion_jobs').fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM studio_jobs WHERE status IN ('QUEUED','RUNNING')").fetchone()[0] == 0
        old_requests = {rid: json.loads(conn.execute('SELECT request_json FROM research_discussion_requests WHERE request_id=?', (rid,)).fetchone()[0]) for rid in [original['message_request_id'], previous['message_request_id']]}
        before_projection = conn.execute('SELECT COUNT(*) FROM studio_chat_messages').fetchone()[0]

    # Both old generations keep their exact request identity and actual contract.
    old_source = next(row['body'] for row in original['responses'] if row['path'] == '/api/catalog/discussion/context')
    before_retry = sha(db.read_bytes())
    for rid, payload in old_requests.items():
        old = call(catalog, 'GET', f'/api/research/discussion/requests/{rid}', params={'scope': old_source['scope_key']})
        repeated = call(catalog, 'POST', '/api/catalog/discussion/messages', 202, json=payload)
        assert old['messages'] == repeated['messages'] and old['job'] == repeated['job']
    assert sha(db.read_bytes()) == before_retry
    proof['old_v1_v2_retry_added_calls'] = 0

    workspace = call(studio, 'GET', f'/manuscripts/{manuscript}/workspace')
    workspace_sha = canonical(workspace)
    assert workspace['document_revision'] == 0 and workspace['active_generated_version_id'] is None
    target = {'module': 'STUDIO', 'manuscript_id': manuscript, 'object_kind': 'paper', 'object_id': manuscript, 'document_revision': 0}
    before_context = sha(db.read_bytes())
    bound = call(studio, 'POST', '/research/discussion/context', json=target)
    assert bound == call(catalog, 'POST', '/api/research/discussion/context', json=target)
    assert sha(db.read_bytes()) == before_context
    quote = {'text': '固定来源', 'start': 0, 'end': 4, 'offset_unit': 'utf16', 'annotation': '软件验收：固定标题选区，不修改稿件。'}
    assert bound['object_text'][:4] == quote['text']
    source = {'target': bound['target'], 'expected_context_sha256': bound['context_sha256'], 'quote': quote}
    annotation = call(studio, 'POST', '/research/discussion/annotations', 201, json={'request_id': 'studio-shared-native-annotation-v1', 'source': source, 'comment': quote['annotation']})
    assert annotation['context'] == bound and annotation['quote']['text'] == quote['text']

    bodies = [
        {'request_id': 'studio-shared-native-first-v1', 'source': source, 'content': '这是工作台软件验收，不是科学结论。请用一句话解释当前选中的“固定来源”怎样绑定到这份稿件的原文和结构版本。不要修改稿件，不提出修改建议，suggestions 和 evidence_ids 都返回空数组。'},
        {'request_id': 'studio-shared-native-followup-v1', 'content': '请接着上一轮回答：先复述上一轮用户想核对什么，再用一句话解释为什么继续讨论仍要保留同一个标题选区、批注及结构 r0。不要修改稿件，不提出修改建议，suggestions 和 evidence_ids 都返回空数组。'},
    ]
    receipts = []
    for index, body in enumerate(bodies):
        if index:
            parent = receipts[0]['messages'][-1]['message_id']
            body.update(source={**source, 'history_message_id': parent}, parent_message_id=parent)
        proof['requests_submitted'].append(body)
        persist()
        receipt = call(studio, 'POST', '/research/discussion/messages', 202, json=body)
        started = time.monotonic()
        while receipt['job']['status'] in ['QUEUED', 'RUNNING'] and receipt['execution_observation'] == 'LIVE_WORKER' and time.monotonic() - started < 360:
            time.sleep(2)
            receipt = call(studio, 'GET', f"/research/discussion/requests/{body['request_id']}", params={'scope': bound['scope_key']})
        proof['last_request_status'] = receipt['job']['status']
        persist()
        assert receipt['job']['status'] == 'COMPLETE', 'Resume this saved request read-only; do not invent or replay a model call.'
        assert receipt['job']['input']['source']['context'] == bound
        assert receipt['job']['model_contract']['prompt_version'] == 'writing-chat-v3-fixed-conversation'
        assert receipt['job']['model_contract']['actual_model'] and receipt['job']['raw_response']
        assert [row['message_id'] for row in receipt['studio_messages']] == [row['message_id'] for row in receipt['messages']]
        for row in receipt['studio_messages']:
            assert row['quoted']['text'] == quote['text'] and row['quoted']['annotation'] == quote['annotation']
            assert row['anchor_revision'] == 0
        if index:
            assert len(receipt['job']['input']['conversation']) == 2
            assert receipt['messages'][0]['reply_to'] == parent
            writing = receipt['job']['input']['writing_payload']
            assert len(writing['conversation']) == 2
            assert [message['content'] for message in writing['conversation']] == [message['content'] for message in receipts[0]['messages']]
            assert all(message['source']['quote']['text'] == quote['text'] for message in writing['conversation'])
        receipt_catalog = call(catalog, 'GET', f"/api/research/discussion/requests/{body['request_id']}", params={'scope': bound['scope_key']})
        assert receipt_catalog['job'] == receipt['job'] and receipt_catalog['studio_messages'] == receipt['studio_messages']
        before = sha(db.read_bytes())
        repeated = call(studio, 'POST', '/research/discussion/messages', 202, json=body)
        assert repeated['job'] == receipt['job'] and repeated['studio_messages'] == receipt['studio_messages']
        assert sha(db.read_bytes()) == before
        receipts.append(receipt)
        proof['new_actual_model_calls'] = len(receipts)
        persist()
    history = call(studio, 'POST', '/research/discussion/history', json={'target': target})
    assert len(history['messages']) == 4 and len(history['annotations']) == 1
    chat = call(studio, 'GET', f'/manuscripts/{manuscript}/chat')
    assert {row['message_id'] for row in chat['items']} == {row['message_id'] for receipt in receipts for row in receipt['studio_messages']}
    historical = call(studio, 'GET', f"/research/discussion/messages/{receipts[-1]['messages'][-1]['message_id']}/context", params={'scope': bound['scope_key']})
    assert len(historical['conversation']) == 4 and historical['sources'][0]['context'] == bound
    assert canonical(call(studio, 'GET', f'/manuscripts/{manuscript}/workspace')) == workspace_sha
    assert {ms: canonical(call(studio, 'GET', f'/manuscripts/{ms}/workspace')) for ms in old_ms} == old_ms
    assert package_hashes() == zips
    with connection() as conn:
        for table, expected in before_science.items():
            rows = conn.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall()
            if table == 'studio_model_calls':
                old_rows = [row for row in rows if row[0] in before_call_ids]
                new_rows = [row for row in rows if row[0] not in before_call_ids]
                assert canonical(old_rows) == expected
                assert len(new_rows) == 2 and all(row[1] == manuscript and row[4] == 'writing_chat' and row[10] == 'RETURNED' for row in new_rows)
                proof['new_studio_model_call_ids'] = [row[0] for row in new_rows]
            else:
                assert canonical(rows) == expected
        assert conn.execute('SELECT COUNT(*) FROM research_discussion_jobs').fetchone()[0] == 4
        assert conn.execute('SELECT COUNT(*) FROM research_discussion_messages').fetchone()[0] == 8
        assert conn.execute('SELECT COUNT(*) FROM research_discussion_annotations').fetchone()[0] == 2
        assert conn.execute('SELECT COUNT(*) FROM studio_chat_messages').fetchone()[0] == before_projection + 4
    published = {}
    for endpoint, name in [('/', 'catalog_web.html'), ('/catalog-research-chat.js', 'catalog_research_chat.js')]:
        response = catalog.get(endpoint)
        assert response.status_code == 200 and response.content == (repo.parent / f'RSTV4/src/rstv4/{name}').read_bytes()
        published[name] = sha(response.content)
    response = frontend.get('/')
    assert response.status_code == 200
    assets = {}
    for asset in set(re.findall(r'(?:src|href)="([^"?]+\.(?:js|css))"', response.text)):
        raw = frontend.get(asset)
        assert raw.status_code == 200 and raw.content == (repo.parent / 'writing-studio/dist/client' / asset.lstrip('/')).read_bytes()
        assets[asset] = sha(raw.content)
    scripts = ''.join((repo.parent / 'writing-studio/dist/client' / asset.lstrip('/')).read_text(encoding='utf-8') for asset in assets if asset.endswith('.js'))
    assert 'RSTV4ResearchChat' in scripts and '继续这段讨论' in scripts and '保存讨论批注' in scripts
    proof.update(status='PASS_NATIVE_SHARED_STUDIO_FIXED_CONVERSATION', actual_contracts=[receipt['job']['model_contract'] for receipt in receipts], request_retry_added_calls=0, fixed_context_sha256=bound['context_sha256'], historical_chain_messages=4, old_workspace_sha256=old_ms, old_package_zip_sha256=zips, unchanged_scientific_table_sha256={key: value for key, value in before_science.items() if key != 'studio_model_calls'}, original_studio_model_calls_sha256=before_science['studio_model_calls'], owned_software_workspace_sha256=workspace_sha, published_sha256=published, compiled_assets_sha256=assets)
    persist()
print(json.dumps({key: proof[key] for key in ['status', 'new_actual_model_calls', 'actual_contracts', 'request_retry_added_calls', 'historical_chain_messages', 'browser_verified']}, ensure_ascii=False))
