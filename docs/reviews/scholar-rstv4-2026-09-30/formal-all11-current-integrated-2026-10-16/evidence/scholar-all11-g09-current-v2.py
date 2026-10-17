"""Dedicated A86 delivery copy: readonly G09 and exactly one round4 package."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid

REPO = Path(__file__).resolve().parents[1]
HERE = REPO / '.tmp/scholar-all11-g09-current-v2'
spec = importlib.util.spec_from_file_location('g11_runtime', REPO / '.tmp/scholar-all11-g11-runtime-v2.py')
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)
b, g11 = rt.load_base()
read, sha, put = rt.read, rt.sha, rt.put
MS = 'manuscript_56652adf9d054cb6ab3819efacf3475c'
ROUND = 'review_round_72931d507bda4bdb813dc14988444892'
CHECK = 'response_check_1b9b3eaa4905448092dd2c472f7c9324'
COMMENT = 'comment_f71edb5758ef41f3b0d96d8cdbed18d5'
VERSION = 'manuscript_version_8732ec9497074d82ae2b4359a7c235e5'
CONTEXT = REPO / '.tmp/scholar-all11-context-v2'
NATIVE = REPO / '.tmp/scholar-all11-native-v1'

def legacy_files_exact(root, path):
    expected = {k: v for k, v in read(path).items() if not k.endswith(('-wal', '-shm'))}
    actual = {k: v['sha256'] for k, v in b.filemap(root).items()}
    assert actual == expected, 'All payload paths and bytes, including main DB, must match'

def protected():
    rt.guard(b, g11)
    context = read(CONTEXT / 'receipt.json')
    original = Path(context['source_root'])
    assert b.snapshot(original / 'data/catalog.db') == read(NATIVE / 'protected-source110.json')
    legacy_files_exact(original, NATIVE / 'protected-source-all-files.json')
    mutable = Path(context['root'])
    assert b.snapshot(mutable / 'data/catalog.db') == read(CONTEXT / 'final110-all-tables.json')
    legacy_files_exact(mutable, CONTEXT / 'final-all-files.json')
    return original, context

def guard():
    original, context = protected()
    receipt = read(HERE / 'receipt.json')
    assert receipt['helper_sha256'] == sha(Path(__file__))
    assert receipt['original'] == str(original)
    return receipt, Path(receipt['root']), context

def prepare():
    original, context = protected()
    HERE.mkdir(exist_ok=False)
    before = b.snapshot(original / 'data/catalog.db')
    doc = b.one(before, 'studio_documents', 'manuscript_id', MS)
    assert doc['revision'] == doc['last_generated_revision'] == 86
    assert doc['active_generated_version_id'] == VERSION
    assert any(CHECK in str(row) for row in before['tables']['studio_response_checks']['rows'])
    root = Path(tempfile.mkdtemp(prefix='scui-all11-g09-current-')).resolve()
    shutil.copytree(original, root, dirs_exist_ok=True)
    assert b.snapshot(root / 'data/catalog.db') == before
    relocations = []
    with sqlite3.connect(root / 'data/catalog.db') as conn:
        conn.row_factory = sqlite3.Row
        for table, key in [('studio_artifacts', 'artifact_id'), ('studio_assets', 'asset_id')]:
            for row in conn.execute('SELECT * FROM ' + table):
                src = Path(row['storage_path']).resolve()
                assert src.is_relative_to(original.resolve())
                dst = root / src.relative_to(original.resolve())
                assert sha(src) == sha(dst) == row['sha256']
                assert src.stat().st_size == dst.stat().st_size == row['size_bytes']
                conn.execute('UPDATE '+table+' SET storage_path=? WHERE '+key+'=? AND storage_path=?',
                             (str(dst), row[key], row['storage_path']))
                relocations.append({'table': table, 'key': key, 'id': row[key],
                                    'from': row['storage_path'], 'to': str(dst), 'sha256': row['sha256']})
        conn.commit()
        assert tuple(conn.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()) == (0, 0, 0)
    after = b.snapshot(root / 'data/catalog.db')
    assert len(relocations) == 37 and before['schema'] == after['schema']
    assert {k for k in after['tables'] if after['tables'][k] != before['tables'][k]} == {'studio_artifacts', 'studio_assets'}
    for table, key in [('studio_artifacts', 'artifact_id'), ('studio_assets', 'asset_id')]:
        old = {r[key]: r for r in b.records(before, table)}
        new = {r[key]: r for r in b.records(after, table)}
        assert old.keys() == new.keys()
        for identifier in old:
            assert {k for k in old[identifier] if old[identifier][k] != new[identifier][k]} == {'storage_path'}
    put(HERE / 'before110.json', after)
    put(HERE / 'before-files.json', b.filemap(root))
    put(HERE / 'relocations37.json', relocations)
    put(HERE / 'receipt.json', {'root': str(root), 'original': str(original), 'helper_sha256': sha(Path(__file__)),
        'nonce': uuid.uuid4().hex, 'A_revision': 86, 'generated_version': VERSION, 'review_round_id': ROUND,
        'old_check': CHECK, 'frontend_root': context['frontend_root'], 'only_new_job': 'SUBMISSION_PACKAGE',
        'no_generation_models_confirmations_science': True})
    guard()
    print('PREPARED_A86_G09_DELIVERY_COPY_ONLY37_STORAGE_PATHS')

def launch():
    receipt, root, context = guard()
    assert not (HERE / 'launch-started.json').exists()
    for port in [8877, 3000]: rt.port_free(port)
    put(HERE / 'launch-started.json', {'nonce': receipt['nonce']})
    for component in ['backend', 'frontend']:
        if component == 'backend':
            argv = [sys.executable, '-X', 'utf8', str(Path(__file__).resolve()), 'serve']
            cwd = REPO
            env = os.environ.copy()
        else:
            argv = read(CONTEXT / 'frontend-launched.json')['argv'][:]
            argv[4] = '3000'
            cwd = Path(context['frontend_root'])
            env = os.environ.copy()
            env.update(NODE_OPTIONS='--max-old-space-size=512', RSTV4_API='http://127.0.0.1:8877/api',
                       NEXT_PUBLIC_RSTV4_API='http://127.0.0.1:8877/api')
        with (HERE / (component+'.log')).open('x', encoding='utf-8') as log:
            proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        saved = rt.identity(proc.pid)
        put(HERE / (component+'-launched.json'), {'identity': saved, 'argv': argv})
        deadline = time.monotonic()+35
        while time.monotonic() < deadline:
            assert proc.poll() is None, 'Keep failed startup logs; do not relaunch'
            if component == 'backend' and (HERE / 'backend-ready.json').exists():
                serving = read(HERE / 'backend-ready.json')['identity']
                assert serving == saved or any(p.pid == saved['pid'] and p.create_time() == saved['create_time'] for p in rt.psutil.Process(serving['pid']).parents())
                put(HERE / 'backend-ownership.json', {'launcher': saved, 'serving': serving})
                break
            if component == 'frontend':
                try:
                    with urllib.request.urlopen('http://127.0.0.1:3000/', timeout=1) as response:
                        assert response.status == 200
                    children = [rt.identity(p.pid) for p in rt.psutil.Process(proc.pid).children(recursive=True)]
                    assert all(Path(v['cmdline'][0]).name.lower() == 'conhost.exe' for v in children)
                    put(HERE / 'frontend-ready.json', {'identity': saved, 'console_children': children})
                    break
                except (OSError, TimeoutError): pass
            time.sleep(.1)
        assert (HERE / (component+'-ready.json')).exists()
    put(HERE / 'launch-complete.json', {'url': f'http://127.0.0.1:3000/?manuscript={MS}&view=reading&left=0&right=0&chat=0', 'nonce': receipt['nonce']})
    print(json.dumps(read(HERE / 'launch-complete.json')))

def serve():
    receipt, root, context = guard()
    sys.path.insert(0, str(b.RST / 'src'))
    import uvicorn
    from fastapi.responses import JSONResponse
    from rstv4.studio_api import create_app
    app = create_app(root)
    app.state.studio.gateway = rt.Deny()
    app.state.discussions.gateway = rt.Deny()
    assert b.snapshot(root / 'data/catalog.db') == read(HERE / 'before110.json')
    count = 0
    class Boundary:
        async def __call__(self, scope, receive, send):
            nonlocal count
            if scope['type'] != 'http': return await app(scope, receive, send)
            count += 1
            serial = count
            method, path = scope['method'], scope['path']
            allowed = method in {'GET', 'HEAD', 'OPTIONS'} or (method == 'POST' and path in {'/api/research/discussion/context', '/api/research/discussion/history'})
            raw = b''
            messages = []
            if method not in {'GET', 'HEAD', 'OPTIONS'}:
                while True:
                    msg = await receive()
                    messages.append(msg)
                    raw += msg.get('body', b'')
                    if not msg.get('more_body', False): break
                if method == 'POST' and path == f'/api/manuscripts/{MS}/jobs':
                    expected = {'kind': 'SUBMISSION_PACKAGE', 'input_revision': 86, 'request': {'review_round_id': ROUND}}
                    allowed = json.loads(raw) == expected and not (HERE / 'package-request-once.json').exists()
                    if allowed: put(HERE / 'package-request-once.json', expected)
            async def again(): return messages.pop(0) if messages else await receive()
            event = {'method': method, 'path': path, 'query': scope.get('query_string', b'').decode(), 'allowed': allowed, 'request_utf8': raw.decode() if raw else None}
            response_hash = hashlib.sha256()
            response = bytearray()
            async def observed(msg):
                if msg['type'] == 'http.response.start': event['status'] = msg['status']
                await send(msg)
                if msg['type'] == 'http.response.body':
                    data = msg.get('body', b'')
                    response_hash.update(data)
                    if raw: response.extend(data)
                    if not msg.get('more_body', False): event['complete'] = True
            try:
                if allowed: await app(scope, again, observed)
                else: await JSONResponse({'detail': 'Readonly G09 plus one explicit round4 package only'}, status_code=403)(scope, again, observed)
            except BaseException as exc:
                event['exception_type'] = type(exc).__name__
                raise
            finally:
                event['response_sha256'] = response_hash.hexdigest()
                if raw: event['response_utf8'] = response.decode(errors='replace')
                put(HERE / f'http-{serial:04d}.json', event)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 8877))
    sock.listen(128)
    put(HERE / 'backend-ready.json', {'identity': rt.identity(os.getpid()), 'nonce': receipt['nonce']})
    server = uvicorn.Server(uvicorn.Config(Boundary(), lifespan='off', log_level='warning'))
    done = threading.Event()
    def monitor():
        while not done.wait(.15):
            path = HERE / 'stop.request.json'
            if path.exists() and read(path).get('nonce') == receipt['nonce']:
                server.should_exit = True
                return
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    try: server.run(sockets=[sock])
    finally:
        done.set()
        thread.join(timeout=2)
        app.state.discussions.shutdown()
        app.state.studio._executor.shutdown(wait=True)
        sock.close()
        guard()
        put(HERE / 'backend-terminal.json', {'identity': rt.identity(os.getpid()), 'nonce': receipt['nonce'], 'protected_exact': True})

def stop():
    receipt, root, context = guard()
    assert not (HERE / 'owned-stop-terminal.json').exists()
    front = read(HERE / 'frontend-ready.json')
    p = rt.exact(front['identity'])
    if p:
        assert all(rt.identity(c.pid) in front['console_children'] for c in p.children(recursive=True))
        p.terminate()
        p.wait(timeout=20)
    for value in front['console_children']:
        if not rt.absent(value):
            p = rt.exact(value)
            try: p.wait(timeout=10)
            except rt.psutil.NoSuchProcess: pass
        assert rt.absent(value)
    put(HERE / 'stop.request.json', {'nonce': receipt['nonce']})
    ownership = read(HERE / 'backend-ownership.json')
    for value in [ownership['serving'], ownership['launcher']]:
        if not rt.absent(value):
            p = rt.exact(value)
            try: p.wait(timeout=35)
            except rt.psutil.NoSuchProcess: pass
        assert rt.absent(value)
    terminal = read(HERE / 'backend-terminal.json')
    assert terminal['nonce'] == receipt['nonce'] and terminal['protected_exact']
    for port in [8877, 3000]: rt.port_free(port)
    guard()
    put(HERE / 'final110.json', b.snapshot(root / 'data/catalog.db'))
    put(HERE / 'final-files.json', b.filemap(root))
    put(HERE / 'owned-stop-terminal.json', {'all_owned_services_retired': True, 'ports_free': [8877, 3000], 'protected_exact': True})
    print('G09_OWNED_SERVICES_RETIRED_PROTECTED_ROOTS_EXACT')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'launch', 'serve', 'stop'])
    globals()[parser.parse_args().mode]()
