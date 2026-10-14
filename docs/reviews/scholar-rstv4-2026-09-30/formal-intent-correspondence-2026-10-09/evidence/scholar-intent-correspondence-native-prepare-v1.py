from pathlib import Path
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

repo = Path(__file__).resolve().parents[1]
receipt_path = repo / '.tmp/scholar-intent-correspondence-native-v1.json'
if len(sys.argv) > 1:
    import uvicorn
    from fastapi.middleware.cors import CORSMiddleware
    from rstv4.studio_api import create_app
    fixture = json.loads(receipt_path.read_text(encoding='utf-8'))
    app = create_app(fixture['root'])
    app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:3006'],
                       allow_methods=['*'], allow_headers=['*'])
    def software_realization(task, payload):
        assert task == 'paragraph_realization', 'Only declared isolated software generation is enabled'
        thoughts = [t for i in payload['intents'] for t in i['thoughts']]
        sources = list(dict.fromkeys(c['evidence_id'] for t in thoughts for c in t.get('citations', []) if c.get('selected')))
        return {'paragraph': ' '.join(t['text'] for t in thoughts) + ''.join(f' [@{source}]' for source in sources),
                'sentence_mappings': [{'sentence': 0, 'thought_ids': [t['id'] for t in thoughts]}],
                '_contract': {'actual_model': 'TEST_FIXTURE_AUTHOR_CORRESPONDENCE', 'task': task}}
    app.state.studio.gateway.analyze = software_realization
    uvicorn.run(app, host='127.0.0.1', port=8879, log_level='warning')
    raise SystemExit()

for port in [3006, 8879]:
    with socket.socket() as handle:
        assert handle.connect_ex(('127.0.0.1', port)) != 0, f'Existing service owns {port}'
parent = json.loads((repo/'.tmp/scholar-source-hierarchy-fixture-v1.json').read_text(encoding='utf-8'))
source_root = Path(parent['root']).resolve()
assert source_root.name.startswith('scui-source-hierarchy-native-')
root = Path(tempfile.mkdtemp(prefix='scui-intent-correspondence-native-')).resolve()
assert root.parent == Path(tempfile.gettempdir()).resolve()
shutil.copytree(source_root, root, dirs_exist_ok=True,
                ignore=lambda directory, names: [n for n in names if n.startswith('catalog.db')])
target_db = root/'data/catalog.db'
with sqlite3.connect(f'file:{(source_root/"data/catalog.db").as_posix()}?mode=ro', uri=True) as source:
    with sqlite3.connect(target_db) as target:
        source.backup(target)
with sqlite3.connect(target_db) as conn, conn:
    row = conn.execute('SELECT revision,document_json FROM studio_documents WHERE manuscript_id=?', (parent['manuscript_id'],)).fetchone()
    assert row[0] == 8
    baseline = json.loads(row[1])
    assert all(not s.get('placement_status') for s in baseline['sections'])
    asset_paths = []
    for asset_id, old in conn.execute('SELECT asset_id,storage_path FROM studio_assets WHERE manuscript_id=?', (parent['manuscript_id'],)):
        old_path = Path(old).resolve()
        assert old_path.is_relative_to(source_root)
        new_path = root/old_path.relative_to(source_root)
        assert new_path.read_bytes() == old_path.read_bytes()
        conn.execute('UPDATE studio_assets SET storage_path=? WHERE asset_id=?', (str(new_path), asset_id))
        asset_paths.append({'id': asset_id, 'path': str(new_path), 'sha256': hashlib.sha256(new_path.read_bytes()).hexdigest()})
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    assert len(tables) == 109
    assert conn.execute('SELECT count(*) FROM studio_jobs WHERE manuscript_id=?', (parent['manuscript_id'],)).fetchone()[0] == 0
    assert conn.execute('SELECT count(*) FROM studio_model_calls WHERE manuscript_id=?', (parent['manuscript_id'],)).fetchone()[0] == 0
receipt = {'root': str(root), 'manuscript_id': parent['manuscript_id'], 'skeleton_id': parent['skeleton_id'],
           'baseline_revision': 8, 'baseline_document': baseline, 'asset_paths': asset_paths,
           'software_fixture': True, 'actual_model_calls': 0, 'scientific_acceptance': False,
           'native_downloads_paused': True, 'old_runtimes_and_tabs_preserved': True}
with receipt_path.open('x', encoding='utf-8') as handle:
    json.dump(receipt, handle, ensure_ascii=False, indent=2)
source = (repo/'.tmp/scholar-template-build-v3.py').read_text(encoding='utf-8')
source = source.replace('scholar-template-build-v3.', 'scholar-intent-correspondence-build-v1.').replace(
    'scui-template-build-', 'scui-intent-correspondence-build-').replace('127.0.0.1:8877', '127.0.0.1:8879')
source = source.replace('--max-old-space-size=1536', '--max-old-space-size=512').replace(
    "RAYON_NUM_THREADS='2', UV_THREADPOOL_SIZE='2'", "RAYON_NUM_THREADS='1', UV_THREADPOOL_SIZE='1'")
exec(compile(source, str(repo/'.tmp/scholar-template-build-v3.py'), 'exec'), {'__file__': str(repo/'.tmp/scholar-template-build-v3.py')})
build = json.loads((repo/'.tmp/scholar-intent-correspondence-build-v1.json').read_text(encoding='utf-8'))
assert build['status'] == 'PASS'
env = {**os.environ, 'PYTHONPATH': str(repo.parent/'RSTV4/src'), 'PYTHONUTF8': '1',
       'NODE_OPTIONS': '--max-old-space-size=512', 'RAYON_NUM_THREADS': '1', 'UV_THREADPOOL_SIZE': '1'}
processes = {}
for name, command, cwd in [
    ('backend', [sys.executable, str(Path(__file__).resolve()), 'serve'], repo),
    ('frontend', ['cmd.exe', '/c', 'npm.cmd', 'run', 'start', '--', '--port', '3006', '--hostname', '127.0.0.1'], Path(build['root']))]:
    with (repo/f'.tmp/scholar-intent-correspondence-{name}-runtime-v1.log').open('x', encoding='utf-8') as log:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    processes[name] = process.pid
import httpx
ready = set()
with httpx.Client(timeout=3) as client:
    deadline = time.monotonic()+45
    while len(ready) < 2 and time.monotonic() < deadline:
        for name, url in [('backend', f"http://127.0.0.1:8879/api/manuscripts/{receipt['manuscript_id']}/workspace"), ('frontend', 'http://127.0.0.1:3006/')]:
            if name in ready:
                continue
            try:
                if client.get(url).status_code == 200:
                    ready.add(name)
            except httpx.HTTPError:
                pass
        if len(ready) < 2:
            time.sleep(0.3)
receipt.update(production_root=build['root'], processes=processes, ready=sorted(ready),
               url=f"http://127.0.0.1:3006/?manuscript={receipt['manuscript_id']}&view=structure&left=1&right=1&chat=0")
receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
assert ready == {'backend', 'frontend'}
print(json.dumps({k:v for k,v in receipt.items() if k!='baseline_document'}, ensure_ascii=False))
