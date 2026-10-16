from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / '.tmp/scholar-g11-identity-native-v1'
sys.path.insert(0, str(REPO / '.tmp/scholar-g11-parallel-v1'))
from runtime_copy_and_serve_v8 import product_guard, snapshot, digest, read_json, exclusive_json

CONTRACT = read_json(REPO / '.tmp/scholar-g11-completion-audit-v1/identity-native-preparation-contract.json')
FILE = CONTRACT['file_version_id']
TARGET = f'/api/catalog/review/cases/{FILE}/actions'
JOBS = {item['job_id']: item for item in CONTRACT['expected_source_impact']['jobs']}

def snap(path):
    return json.loads(json.dumps(snapshot(path), ensure_ascii=False))

def rows(state, table, key):
    value = state['tables'][table]
    return {item[key]: item for values in value['rows']
            if (item := dict(zip(value['columns'], values))) is not None}

def protected(root):
    return {str(p): digest(p) for p in (root / 'data').rglob('*') if p.is_file()}

def original_guard(receipt):
    assert product_guard() == receipt['product_vector']
    assert snap(Path(receipt['source_root']) / 'data/catalog.db') == read_json(OUT / 'before.json')
    assert all(digest(Path(p)) == sha for p, sha in receipt['protected_original_files'].items())
    assert digest(Path(CONTRACT['source_storage_path'])) == CONTRACT['pdf_sha256']

def prepare():
    OUT.mkdir()
    source = Path(CONTRACT['source_root'])
    sealed = REPO / CONTRACT['sealed_logical_baseline']
    assert digest(sealed) == CONTRACT['sealed_logical_baseline_sha256']
    before = snap(source / 'data/catalog.db')
    assert before == read_json(sealed)
    assert len(before['tables']) == 105
    assert not before['tables']['research_nodes']['rows']
    assert not before['tables']['manuscripts']['rows']
    for ident, expected in JOBS.items():
        current = rows(before, 'acquisition_jobs', 'job_id')[ident]
        assert all(current[k] == v for k, v in expected.items())
    pdf = Path(CONTRACT['source_storage_path'])
    assert pdf.stat().st_size == CONTRACT['pdf_bytes'] and digest(pdf) == CONTRACT['pdf_sha256']
    originals = protected(source)
    root = Path(tempfile.mkdtemp(prefix='scui-g11-identity-')).resolve()
    assert root.is_relative_to(Path(tempfile.gettempdir()).resolve())
    exclusive_json(OUT / 'copy-attempt.json', {'root': str(root), 'source': str(source)})
    shutil.copytree(source / 'data', root / 'data',
                    ignore=lambda _, names: [n for n in names if n in {'catalog.db', 'catalog.db-shm', 'catalog.db-wal'}])
    with closing(sqlite3.connect((source / 'data/catalog.db').as_uri() + '?mode=ro', uri=True)) as src:
        with closing(sqlite3.connect(root / 'data/catalog.db')) as dst:
            src.backup(dst)
    assert snap(root / 'data/catalog.db') == before
    assert protected(source) == originals
    for name, sha in originals.items():
        p = Path(name)
        if p.name not in {'catalog.db', 'catalog.db-shm', 'catalog.db-wal'}:
            assert digest(root / p.relative_to(source)) == sha
    exclusive_json(OUT / 'before.json', before)
    receipt = {'root': str(root), 'source_root': str(source),
               'protected_original_files': originals, 'product_vector': product_guard(),
               'worker_started': False, 'models_denied': True, 'native_complete': False}
    exclusive_json(OUT / 'prepared.json', receipt)
    original_guard(receipt)
    log = (OUT / 'server.log').open('x', encoding='utf-8')
    child = subprocess.Popen([str(REPO / '.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'),
                              str(Path(__file__).resolve()), 'serve'],
                             cwd=REPO, stdout=log, stderr=subprocess.STDOUT,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    log.close()
    exclusive_json(OUT / 'launched.json', {'pid': child.pid, 'root': str(root)})
    print(json.dumps({'status': 'PREPARED_EXACT_COPY_SERVER_LAUNCHED_NOT_NATIVE_ACCEPTANCE',
                      'root': str(root), 'pid': child.pid}), flush=True)

def serve():
    import uvicorn
    from fastapi.responses import JSONResponse, Response
    sys.path.insert(0, str(REPO.parent / 'RSTV4/src'))
    from rstv4.catalog_web import create_app
    receipt = read_json(OUT / 'prepared.json')
    original_guard(receipt)
    root = Path(receipt['root'])
    before = read_json(OUT / 'before.json')
    app = create_app(root)
    class Deny:
        def analyze(self, *_args, **_kwargs):
            raise RuntimeError('Independent identity-only native fixture denies model calls')
    app.state.discussions.gateway = Deny()
    app.state.fieldkg_semantics.gateway = Deny()
    assert snap(root / 'data/catalog.db') == before
    actions = ['REOPEN_IDENTITY', 'APPROVE_IDENTITY']
    used = 0
    @app.middleware('http')
    async def bound(request, call_next):
        nonlocal used
        path = request.url.path
        if request.method in {'GET', 'HEAD', 'OPTIONS'}:
            return await call_next(request)
        if request.method == 'POST' and path in {'/api/catalog/papers/query',
                '/api/catalog/discussion/context', '/api/catalog/discussion/history'}:
            return await call_next(request)
        if request.method == 'POST' and path == TARGET and used < 2:
            body = await request.json()
            if body.get('action') != actions[used] or '软件验收' not in body.get('reason', ''):
                return JSONResponse({'detail': 'Only the declared software identity review action is allowed'}, status_code=403)
            step = used + 1
            used += 1
            exclusive_json(OUT / f'action-{step}-request.json', body)
            response = await call_next(request)
            raw = b''.join([part async for part in response.body_iterator])
            exclusive_json(OUT / f'action-{step}-response.json',
                           {'status_code': response.status_code, 'body': json.loads(raw)})
            exclusive_json(OUT / f'action-{step}-all-tables.json', snap(root / 'data/catalog.db'))
            return Response(raw, status_code=response.status_code, headers=dict(response.headers))
        return JSONResponse({'detail': 'Owned identity fixture permits only its two declared review actions and reads'}, status_code=403)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    exclusive_json(OUT / 'server-ready.json', {'pid': os.getpid(), 'port': port, 'root': str(root),
                    'url': f'http://127.0.0.1:{port}/?view=all',
                    'workers_started': 0, 'model_calls_allowed': 0})
    uvicorn.Server(uvicorn.Config(app, log_level='warning')).run(sockets=[sock])

def audit():
    receipt = read_json(OUT / 'prepared.json')
    original_guard(receipt)
    before = read_json(OUT / 'before.json')
    middle = read_json(OUT / 'action-1-all-tables.json')
    after = read_json(OUT / 'action-2-all-tables.json')
    final = snap(Path(receipt['root']) / 'data/catalog.db')
    assert final == after
    root = Path(receipt['root'])
    source = Path(receipt['source_root'])
    copied_names = set()
    for name, sha in receipt['protected_original_files'].items():
        p = Path(name)
        if p.name not in {'catalog.db', 'catalog.db-shm', 'catalog.db-wal'}:
            copied = root / p.relative_to(source)
            assert digest(copied) == sha, str(copied)
            copied_names.add(str(copied))
    derived = [str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()
               and str(p) not in copied_names
               and p.name not in {'catalog.db', 'catalog.db-shm', 'catalog.db-wal'}]
    allowed = {'source_file_versions', 'catalog_review_actions', 'acquisition_jobs'}
    for state in [middle, after]:
        assert state['schema'] == before['schema']
        assert state['tables'].keys() == before['tables'].keys()
        for name, table in before['tables'].items():
            assert state['tables'][name]['columns'] == table['columns']
            if name not in allowed:
                assert state['tables'][name] == table, name
    files = rows(before, 'source_file_versions', 'file_version_id')
    for state, status in [(middle, 'NEEDS_REVIEW'), (after, 'VERIFIED')]:
        actual = rows(state, 'source_file_versions', 'file_version_id')
        assert actual.keys() == files.keys()
        for ident, old in files.items():
            if ident != FILE:
                assert actual[ident] == old
            else:
                assert actual[ident]['identity_status'] == status
                assert {k: v for k, v in actual[ident].items() if k not in {'identity_status','validation_json'}} == {k: v for k, v in old.items() if k not in {'identity_status','validation_json'}}
    old_jobs = rows(before, 'acquisition_jobs', 'job_id')
    permitted_fields = set(CONTRACT['allowed_write_tables']['acquisition_jobs']['allowed_fields'])
    for state, status in [(middle, 'NEEDS_HUMAN'), (after, 'READY')]:
        actual = rows(state, 'acquisition_jobs', 'job_id')
        assert actual.keys() == old_jobs.keys()
        for ident, old in old_jobs.items():
            item = actual[ident]
            if ident not in JOBS:
                assert item == old, ident
            else:
                assert item['status'] == status
                assert item['fencing_token'] == old['fencing_token'] + 1
                assert {k:v for k,v in item.items() if k not in permitted_fields} == {k:v for k,v in old.items() if k not in permitted_fields}
                assert item['lease_owner'] is None and item['lease_expires_at'] is None
                if status == 'NEEDS_HUMAN':
                    assert item['last_error_code'] == 'SOURCE_REVIEW_REOPENED'
                else:
                    assert item['last_error_code'] is None and item['last_error_detail'] is None
                    assert json.loads(item['result_json']) == json.loads(old['result_json'])
    prior_actions = rows(before, 'catalog_review_actions', 'action_id')
    all_actions = rows(after, 'catalog_review_actions', 'action_id')
    assert len(all_actions) == len(prior_actions) + 2
    assert all(all_actions[k] == value for k, value in prior_actions.items())
    new = []
    for step, action, status in [(1, 'REOPEN_IDENTITY', 'IDENTITY_REOPENED'), (2, 'APPROVE_IDENTITY', 'APPROVED_IDENTITY')]:
        response = read_json(OUT / f'action-{step}-response.json')
        assert response['status_code'] == 200
        value = response['body']
        assert value['action'] == action and value['case_id'] == FILE and value['file_version_id'] == FILE
        assert value['result']['status'] == status
        if step == 1:
            assert value['result']['scientific_approval_restored'] is False
        else:
            assert set(value['result']['resumed_jobs']) == set(JOBS)
            assert set(value['result']['parse_jobs']) <= set(old_jobs)
            assert value['supersedes_action_id'] == new[0]['action_id']
        new.append(value)
    exclusive_json(OUT / 'final-all-tables.json', final)
    exclusive_json(OUT / 'audit.json', {'status': 'PASS_CURRENT_NATIVE_IDENTITY_REOPEN_APPROVE_RECOVERY_AND_ALL_TABLE_AUDIT',
                    'tables': 105, 'unchanged_tables': 102, 'exact_original_rows': True,
                    'actions_appended': 2, 'nonterminal_jobs_restored': sorted(JOBS),
                    'terminal_jobs_exact': True, 'workers_started': 0, 'new_attempts': 0,
                    'models_executed': 0, 'new_parses': 0, 'original_files_exact': True,
                    'copied_original_files_exact': True, 'new_owned_derived_files': derived,
                    'scientific_approval': False, 'all11_complete': False})
    print('PASS_CURRENT_NATIVE_IDENTITY_REOPEN_APPROVE_RECOVERY_AND_105_TABLE_AUDIT')

if __name__ == '__main__':
    {'prepare': prepare, 'serve': serve, 'audit': audit}[sys.argv[1]]()
