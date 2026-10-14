import hashlib
import json
from pathlib import Path

from rstv4.database import transaction

repo = Path(__file__).resolve().parents[1]
info = json.loads((repo / '.tmp/scholar-template-native-fixture-v1.json').read_text(encoding='utf-8'))
db = Path(info['root']) / 'data/catalog.db'
manuscript_id = info['native_manuscript_id']
with transaction(db) as conn:
    row = conn.execute('SELECT * FROM studio_documents WHERE manuscript_id=?', (manuscript_id,)).fetchone()
    operations = [dict(row) for row in conn.execute('SELECT * FROM studio_operations WHERE manuscript_id=? ORDER BY resulting_revision', (manuscript_id,))]
    assert row['revision'] == 9
    assert json.loads(row['document_json']) == info['initial_document']
    assert [(op['base_revision'], op['resulting_revision'], op['operation_kind']) for op in operations] == [
        (0,1,'EDIT'),(1,2,'ADOPT_TEMPLATE'),(2,3,'UNDO'),(3,4,'ADOPT_TEMPLATE'),
        (4,5,'EDIT'),(5,6,'UNDO'),(6,7,'UNDO'),(7,8,'ADOPT_TEMPLATE'),(8,9,'UNDO')]
    assert not conn.execute('SELECT 1 FROM studio_jobs WHERE manuscript_id=?', (manuscript_id,)).fetchone()
    current = {table: [dict(row) for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]
               for table in info['before_native_tables']}
    allowed = {'manuscripts','studio_documents','studio_operations','studio_changes',
               'studio_template_instances','studio_sample_candidates','studio_change_link_state'}
    changed = [table for table, before in info['before_native_tables'].items() if current[table] != before]
    assert set(changed) <= allowed, changed
    for table, before in info['before_native_tables'].items():
        for old in before:
            if table in {'manuscripts', 'studio_documents'} and old.get('manuscript_id') == manuscript_id:
                continue
            assert old in current[table], (table, old)
    templates = [dict(row) for row in conn.execute('SELECT * FROM studio_template_instances WHERE manuscript_id=? ORDER BY rowid', (manuscript_id,))]
    assert len(templates) == 3
    requests = [json.loads(row['adopted_json'])['request'] for row in templates]
    assert [(r['base_revision'],r['mode'],len(r['selected_unit_ids'])) for r in requests] == [(1,'INSERT',1),(3,'REPLACE',3),(7,'INSERT',1)]
    checkpoint = {'revision': row['revision'], 'operations': operations, 'changed_tables': changed,
                  'template_requests': requests, 'model_jobs_added': 0, 'old_rows_preserved': True}
for name, expected_base in [('v1',1),('v2',7)]:
    network = json.loads((repo / f'.tmp/scholar-template-offline-network-{name}.json').read_text(encoding='utf-8'))
    sent = [event for event in network['events'] if event['method'] == 'Network.requestWillBeSent'
            and event['params']['request']['url'].endswith('/template-adoption')
            and event['params']['request']['method'] == 'POST']
    assert len(sent) == 1
    request = json.loads(sent[0]['params']['request']['postData'])
    assert request['base_revision'] == expected_base
    failed = [event for event in network['events'] if event['method'] == 'Network.loadingFailed'
              and event['params']['requestId'] == sent[0]['params']['requestId']]
    assert failed and failed[0]['params']['errorText'] == 'net::ERR_INTERNET_DISCONNECTED'
    assert any(r == request for r in requests) == (name == 'v2')
    checkpoint[f'offline_{name}'] = {'request': request, 'error': failed[0]['params']['errorText'], 'preflight_count': sum(e['method'] == 'Network.requestWillBeSent' and e['params']['request']['method'] == 'OPTIONS' for e in network['events'])}
assert hashlib.sha256((Path(info['golden_root']) / 'data/catalog.db').read_bytes()).hexdigest() == info['golden_database_sha256']
with (repo / '.tmp/scholar-template-native-checkpoint-v2.json').open('x', encoding='utf-8') as handle:
    json.dump(checkpoint, handle, indent=2, ensure_ascii=False)
print(json.dumps({k:v for k,v in checkpoint.items() if k not in {'operations','template_requests','offline_v1','offline_v2'}},ensure_ascii=False))
