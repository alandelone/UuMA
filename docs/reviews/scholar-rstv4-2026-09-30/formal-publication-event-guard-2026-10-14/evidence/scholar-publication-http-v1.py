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

here = repo / '.tmp/scholar-publication-http-v1'
here.mkdir(exist_ok=False)
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
snap = lambda p: json.loads(json.dumps(snapshot(p), ensure_ascii=False))
prepared = repo / '.tmp/scholar-re10-native-v1'
receipt = read(prepared / 'copy-receipt.json')
original = Path(receipt['source'])
baseline = read(prepared / 'before-all-tables.json')
full_vector = read(repo / '.tmp/scholar-publication-full-v1/source-before.json')
frozen_files = read(prepared / 'protected-source-files.json')


def source_guard():
    for name, digest in full_vector.items():
        assert sha(repo.parent / 'RSTV4' / name) == digest, name
    old_studio = read(repo / '.tmp/scholar-publication-before-v1/source-before.json')['src/rstv4/studio.py']
    for name, digest in receipt['source_vector'].items():
        path = Path(name)
        if path.resolve() == (repo.parent / 'RSTV4/src/rstv4/studio.py').resolve():
            assert digest == old_studio
            assert sha(path) == full_vector['src/rstv4/studio.py']
        else:
            assert sha(path) == digest, name
    current = {p.relative_to(original).as_posix(): sha(p) for p in original.rglob('*')
               if p.is_file() and not p.name.endswith(('-wal', '-shm'))}
    assert current == frozen_files
    assert snap(original / 'data/catalog.db') == baseline


source_guard()
root = Path(tempfile.mkdtemp(prefix='scui-publication-http-')).resolve()
exclusive_json(here / 'allocated.json', {'root': str(root), 'source': str(original)})
shutil.copytree(original / 'data', root / 'data', ignore=lambda _p, names: [
    n for n in names if n in {'catalog.db', 'catalog.db-wal', 'catalog.db-shm'}])
with closing(sqlite3.connect((original / 'data/catalog.db').as_uri() + '?mode=ro', uri=True)) as src:
    with closing(sqlite3.connect(root / 'data/catalog.db')) as dst:
        src.backup(dst)
assert snap(root / 'data/catalog.db') == baseline
exclusive_json(here / 'before.json', baseline)
app = create_app(root)
assert snap(root / 'data/catalog.db') == baseline


class DenyModels:
    def analyze(self, *_args, **_kwargs):
        raise RuntimeError('Publication software acceptance denies every model call')

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


def call(label, method, path, payload, expected):
    raw = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', data=raw, method=method,
                                 headers={'Content-Type': 'application/json'})
    try:
        response = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        value = {'method': method, 'path': path, 'request': payload,
                 'status': response.status, 'body': json.loads(response.read())}
    exclusive_json(here / f'http-{label}.json', value)
    exclusive_json(here / f'after-{label}.json', snap(root / 'data/catalog.db'))
    assert value['status'] == expected, value
    return value['body']


def records(state, name, key):
    t = state['tables'][name]
    return {row[key]: row for values in t['rows'] if (row := dict(zip(t['columns'], values)))}


ms = receipt['manuscript_id']
zero = 'manuscript_bea23f3050174ed1a0df075a32c25e13'
payload = {'venue': 'Isolated software workflow acceptance', 'round_number': 2,
           'status': 'PUBLISHED',
           'detail': 'Software acceptance event only. No external submission, acceptance, publication or scientific approval.'}
completed = False
try:
    call('zero-rejected', 'POST', f'/api/manuscripts/{zero}/submission-events', payload, 422)
    assert snap(root / 'data/catalog.db') == baseline
    call('stage-rejected', 'POST', f'/api/manuscripts/{ms}/submission-events', payload, 422)
    assert snap(root / 'data/catalog.db') == baseline
    old = records(baseline, 'manuscripts', 'manuscript_id')[ms]
    stage = call('finalization', 'POST', f'/api/manuscripts/{ms}/stage', {
        'stage': 'FINALIZATION_SUBMISSION', 'expected_revision': old['revision'],
        'reason': 'Software fixture: explicitly finalize the existing current r62/v5 without generation',
    }, 200)
    assert stage['active_generated_version_id'] == 'manuscript_version_de30b95a2d6843059d3c8b420627bf58'
    assert stage['document_revision'] == stage['last_generated_revision'] == 62
    event = call('publication', 'POST', f'/api/manuscripts/{ms}/submission-events', payload, 201)
    fresh = call('readback', 'GET', f'/api/manuscripts/{ms}/workspace', None, 200)
    assert fresh['workflow_stage'] == 'PUBLICATION'
    assert fresh['manuscript']['submissions'][-1] == event
    assert fresh['manuscript']['history'][-1]['reason'] == payload['detail']
    assert fresh['document'] == stage['document']
    assert fresh['document_revision'] == fresh['last_generated_revision'] == 62
    assert fresh['active_generated_version_id'] == stage['active_generated_version_id']
    final = snap(root / 'data/catalog.db')
    assert final['schema'] == baseline['schema']
    changed = {'manuscripts', 'manuscript_status_history', 'submission_events'}
    for name, table in baseline['tables'].items():
        if name not in changed:
            assert final['tables'][name] == table, name
    old_ms = records(baseline, 'manuscripts', 'manuscript_id')
    new_ms = records(final, 'manuscripts', 'manuscript_id')
    assert new_ms.keys() == old_ms.keys()
    for ident, row in old_ms.items():
        if ident != ms:
            assert new_ms[ident] == row
        else:
            excluded = {'workflow_stage', 'writing_status', 'revision', 'updated_at'}
            assert {k: v for k, v in row.items() if k not in excluded} == {
                k: v for k, v in new_ms[ident].items() if k not in excluded}
            assert new_ms[ident]['revision'] == row['revision'] + 2
    for table, key, count in [('submission_events', 'event_id', 1),
                              ('manuscript_status_history', 'history_id', 2)]:
        before = records(baseline, table, key)
        after = records(final, table, key)
        assert all(after[k] == v for k, v in before.items())
        additions = [v for k, v in after.items() if k not in before]
        assert len(additions) == count and all(v['manuscript_id'] == ms for v in additions)
    for name, digest in frozen_files.items():
        if name.startswith('data/') and name != 'data/catalog.db':
            assert sha(root / name) == digest
    source_guard()
    exclusive_json(here / 'audit.json', {
        'status': 'PASS_REAL_HTTP_GUARDS_ATOMIC_PUBLICATION_AND_109_TABLE_AUDIT',
        'schemas': 109, 'unchanged_tables': 106, 'original_rows_preserved': True,
        'new_history': 2, 'new_local_software_submission_events': 1,
        'author_revision': 62, 'generated_version': 5, 'new_jobs_models_generations': 0,
        'source_files_exact': True, 'native_browser_executed': False,
        'accepted_and_fixed_final_version_archive_full_chain_complete': False,
        'all11_complete': False,
    })
    completed = True
finally:
    server.should_exit = True
    worker.join(timeout=30)
    assert not worker.is_alive(), 'Observe same server handle; never restart uncertain actions'
    app.state.discussions.shutdown()
    app.state.studio._executor.shutdown(wait=True)
    exclusive_json(here / 'terminal.json', {'completed': completed, 'server_stopped': True,
                                           'port': port, 'pid': os.getpid()})
print('PASS_REAL_HTTP_GUARDS_ATOMIC_PUBLICATION_AND_109_TABLE_AUDIT')
