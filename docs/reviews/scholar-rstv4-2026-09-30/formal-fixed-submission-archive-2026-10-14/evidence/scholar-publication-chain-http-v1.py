from contextlib import closing
from pathlib import Path
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import threading
import urllib.error
import urllib.request

import uvicorn

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo / '.tmp/scholar-g11-parallel-v1'))
from runtime_copy_and_serve import exclusive_json, snapshot
sys.path.insert(0, str(repo.parent / 'RSTV4/src'))
from rstv4.studio_api import create_app

here = repo / '.tmp/scholar-publication-chain-http-v1'
here.mkdir(exist_ok=False)
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
snap = lambda p: json.loads(json.dumps(snapshot(p), ensure_ascii=False))
prepared = repo / '.tmp/scholar-re10-native-v1'
receipt = read(prepared / 'copy-receipt.json')
original = Path(receipt['source'])
old = read(prepared / 'before-all-tables.json')
frozen = read(repo / '.tmp/scholar-publication-chain-full-v2/source-before.json')
old_files = read(prepared / 'protected-source-files.json')


def guard():
    for name, digest in frozen.items():
        assert sha(repo.parent / 'RSTV4' / name) == digest, name
    assert snap(original / 'data/catalog.db') == old
    assert {p.relative_to(original).as_posix(): sha(p) for p in original.rglob('*')
            if p.is_file() and not p.name.endswith(('-wal', '-shm'))} == old_files


guard()
root = Path(tempfile.mkdtemp(prefix='scui-publication-chain-')).resolve()
exclusive_json(here / 'allocated.json', {'root': str(root), 'source': str(original)})
shutil.copytree(original / 'data', root / 'data', ignore=lambda _p, names: [
    n for n in names if n in {'catalog.db', 'catalog.db-wal', 'catalog.db-shm'}])
with closing(sqlite3.connect((original / 'data/catalog.db').as_uri() + '?mode=ro', uri=True)) as src:
    with closing(sqlite3.connect(root / 'data/catalog.db')) as dst:
        src.backup(dst)
assert snap(root / 'data/catalog.db') == old
app = create_app(root)
baseline = snap(root / 'data/catalog.db')
assert set(baseline['tables']) - set(old['tables']) == {'studio_submission_bindings'}
assert not baseline['tables']['studio_submission_bindings']['rows']
for name, table in old['tables'].items():
    if name != 'schema_version':
        assert baseline['tables'][name] == table, name
    else:
        expected = [r.copy() for r in table['rows']]
        cols = table['columns']
        actual = baseline['tables'][name]
        for values in expected:
            index = next(i for i, r in enumerate(actual['rows']) if r[0] == values[0])
            changed = dict(zip(cols, actual['rows'][index]))
            before = dict(zip(cols, values))
            if before['component'] == 'catalog':
                assert before['version'] == 13 and changed['version'] == 14
                assert {k: v for k, v in before.items() if k not in {'version', 'applied_at'}} == {
                    k: v for k, v in changed.items() if k not in {'version', 'applied_at'}}
            else:
                assert changed == before
new_schema = {(s[0], s[1]): s for s in baseline['schema']}
assert all(new_schema[(s[0], s[1])] == s for s in old['schema'])
exclusive_json(here / 'before.json', baseline)
exclusive_json(here / 'migration.json', {'old_tables': 109, 'new_tables': 110,
                                       'old_rows_and_schema_objects_exact': True,
                                       'catalog_version': [13, 14], 'new_table_empty': True})


class DenyModels:
    def analyze(self, *_args, **_kwargs):
        raise RuntimeError('Publication chain software acceptance denies model calls')

    operation_id = analyze
    analyze_for_operation = analyze


app.state.studio.gateway = DenyModels()
app.state.discussions.gateway = DenyModels()
sock = socket.socket()
sock.bind(('127.0.0.1', 0))
sock.listen(128)
port = sock.getsockname()[1]
server = uvicorn.Server(uvicorn.Config(app, lifespan='off', log_level='warning'))
worker = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
worker.start()
exclusive_json(here / 'server.json', {'pid': os.getpid(), 'port': port,
                                    'worker_lifespan_disabled': True, 'models_allowed': 0})
counter = 0


def call(label, method, path, payload, expected, body=None, headers=None):
    global counter
    raw = body if body is not None else json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', data=raw, method=method,
                                 headers=headers or {'Content-Type': 'application/json'})
    try:
        response = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        value = {'method': method, 'path': path, 'request': payload,
                 'status': response.status, 'body': json.loads(response.read())}
    counter += 1
    exclusive_json(here / f'http-{counter:02d}-{label}.json', value)
    state = snap(root / 'data/catalog.db')
    exclusive_json(here / f'after-{label}.json', state)
    assert value['status'] == expected, value
    return value['body']


def records(state, name, key):
    table = state['tables'][name]
    return {row[key]: row for values in table['rows'] if (row := dict(zip(table['columns'], values)))}


ms = receipt['manuscript_id']
version = 'manuscript_version_de30b95a2d6843059d3c8b420627bf58'
base = f'/api/manuscripts/{ms}'
event_path = base + '/submission-events'
notice = 'Local software workflow acceptance only; no external submission, acceptance or publication.'
request = {'venue': 'Software fixed-version acceptance', 'round_number': 4,
           'generated_version_id': version, 'detail': notice}
events = []


def event(status, label, expected=201, **fields):
    result = call(label, 'POST', event_path,
                  {**request, 'status': status, 'operation_id': 'software-chain-' + label, **fields}, expected)
    if expected == 201:
        events.append(result)
    return result


def unchanged_reject(label, fn):
    before = snap(root / 'data/catalog.db')
    fn()
    assert snap(root / 'data/catalog.db') == before, label


completed = False
try:
    workspace = call('initial', 'GET', base + '/workspace', None, 200)
    call('finalization', 'POST', base + '/stage', {
        'stage': 'FINALIZATION_SUBMISSION', 'expected_revision': workspace['manuscript']['revision'],
        'reason': notice}, 200)
    event('SUBMITTED', 'submitted')
    event('UNDER_REVIEW', 'under-review')
    unchanged_reject('no-acceptance', lambda: event('PUBLISHED', 'no-acceptance', 422))
    event('REVISION_REQUESTED', 'revision-requested')
    workspace = call('before-revision', 'GET', base + '/workspace', None, 200)
    call('revision', 'POST', base + '/stage', {
        'stage': 'REVISION', 'expected_revision': workspace['manuscript']['revision'], 'reason': notice}, 200)
    # Existing current v5 is explicitly reused; no new generation is claimed.
    event('SUBMITTED', 'resubmitted')
    accepted = event('ACCEPTED', 'accepted')
    unchanged_reject('wrong-venue', lambda: event('PUBLISHED', 'wrong-venue', 422, venue='Another venue'))
    workspace = call('before-stage6', 'GET', base + '/workspace', None, 200)
    assert workspace['publication']['accepted_generated_version_id'] == version
    call('stage6', 'POST', base + '/stage', {
        'stage': 'PUBLICATION', 'expected_revision': workspace['manuscript']['revision'], 'reason': notice}, 200)
    published = event('PUBLISHED', 'published')
    assert published['binding']['snapshot']['accepted_event_id'] == accepted['event_id']
    uploaded = []
    for role in ['final', 'proof']:
        boundary = 'SoftwareArchiveBoundary'
        content = f'{notice}\n{role}: v5 / author revision 62\n'.encode()
        raw = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="software-{role}.txt"\r\n'
               'Content-Type: text/plain\r\n\r\n').encode() + content + f'\r\n--{boundary}--\r\n'.encode()
        asset = call('upload-' + role, 'POST', base + '/assets',
                     {'filename': f'software-{role}.txt', 'sha256': hashlib.sha256(content).hexdigest()}, 201,
                     body=raw, headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
        assert asset['sha256'] == hashlib.sha256(content).hexdigest()
        uploaded.append(asset)
    archive_fields = {'final_asset_id': uploaded[0]['asset_id'], 'proof_asset_id': uploaded[1]['asset_id']}
    unchanged_reject('missing-ack', lambda: event('ARCHIVED', 'missing-ack', 422, **archive_fields))
    archive = event('ARCHIVED', 'archived', acknowledged=True, **archive_fields)
    before_replay = snap(root / 'data/catalog.db')
    replay = call('exact-replay', 'POST', event_path,
                  {**request, 'status': 'ARCHIVED', 'operation_id': 'software-chain-archived',
                   'acknowledged': True, **archive_fields}, 201)
    assert replay == archive
    assert snap(root / 'data/catalog.db') == before_replay
    unchanged_reject('collision', lambda: call('collision', 'POST', event_path,
        {**request, 'status': 'PUBLISHED', 'operation_id': 'software-chain-archived'}, 409))
    fresh = call('readback', 'GET', base + '/workspace', None, 200)
    assert fresh['publication']['completion']['status'] == 'CURRENT'
    assert fresh['publication']['completion']['event_id'] == archive['event_id']
    assert fresh['publication']['completion']['files'] == archive['binding']['snapshot']['files']
    assert fresh['workflow_stage'] == 'PUBLICATION'
    assert fresh['active_generated_version_id'] == version
    assert fresh['document_revision'] == fresh['last_generated_revision'] == 62
    assert fresh['document'] == workspace['document']
    assert archive['binding']['snapshot']['parent_event_id'] == published['event_id']
    assert archive['binding']['snapshot']['accepted_event_id'] == accepted['event_id']
    for entry in events:
        assert entry['binding']['snapshot']['generated_version']['manuscript_version_id'] == version
        assert entry['binding']['snapshot']['generated_version']['document_revision'] == 62
    final = snap(root / 'data/catalog.db')
    assert final['schema'] == baseline['schema']
    changes = {'manuscripts', 'manuscript_status_history', 'submission_events',
               'studio_submission_bindings', 'studio_assets'}
    for name, table in baseline['tables'].items():
        if name not in changes:
            assert final['tables'][name] == table, name
    before_ms = records(baseline, 'manuscripts', 'manuscript_id')
    after_ms = records(final, 'manuscripts', 'manuscript_id')
    assert before_ms.keys() == after_ms.keys()
    for ident, row in before_ms.items():
        if ident != ms:
            assert after_ms[ident] == row
        else:
            omit = {'workflow_stage', 'writing_status', 'revision', 'updated_at'}
            assert {k: v for k, v in row.items() if k not in omit} == {
                k: v for k, v in after_ms[ident].items() if k not in omit}
            assert after_ms[ident]['revision'] == row['revision'] + 3
    for name, key, count in [('manuscript_status_history', 'history_id', 3),
                              ('submission_events', 'event_id', 7),
                              ('studio_submission_bindings', 'event_id', 7),
                              ('studio_assets', 'asset_id', 2)]:
        before = records(baseline, name, key)
        after = records(final, name, key)
        assert all(after[k] == v for k, v in before.items())
        added = [v for k, v in after.items() if k not in before]
        assert len(added) == count and all(v['manuscript_id'] == ms for v in added), name
    for name, digest in old_files.items():
        if name.startswith('data/') and name != 'data/catalog.db':
            assert sha(root / name) == digest
    guard()
    exclusive_json(here / 'final.json', final)
    exclusive_json(here / 'audit.json', {'status': 'PASS_REAL_HTTP_FIXED_VERSION_ACCEPTED_FINAL_PROOF_ARCHIVED',
        'http_requests': counter, 'schemas': 110, 'unchanged_tables': 105,
        'only_declared_append_rows': True, 'original109_preserved_except_schema_version14': True,
        'local_submission_events': 7, 'new_history': 3, 'new_assets': 2,
        'author_revision': 62, 'generated_version': 5, 'new_models_jobs_generations': 0,
        'source_files_exact': True, 'native_browser_executed': False, 'all11_complete': False})
    completed = True
finally:
    server.should_exit = True
    worker.join(timeout=30)
    assert not worker.is_alive(), 'Observe same server handle; do not replay uncertain writes'
    app.state.discussions.shutdown()
    app.state.studio._executor.shutdown(wait=True)
    exclusive_json(here / 'terminal.json', {'completed': completed, 'server_stopped': True,
                                           'pid': os.getpid(), 'port': port})
print('PASS_REAL_HTTP_FIXED_VERSION_ACCEPTED_FINAL_PROOF_ARCHIVED')
