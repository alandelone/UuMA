import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
info = json.loads((repo / '.tmp/scholar-revision-isolated-services-v1.json').read_text())
root = Path(info['root']).resolve()
assert root.name == 'scui-revision-native-p48co4i6'
command = "[pscustomobject]@{Process=(Get-CimInstance Win32_Process -Filter 'ProcessId=63780' | Select-Object ProcessId,ExecutablePath,CommandLine); Listener=(Get-NetTCPConnection -State Listen -LocalPort 8877 | Select-Object LocalPort,OwningProcess)} | ConvertTo-Json -Depth 5"
owner = json.loads(subprocess.run(['powershell', '-NoProfile', '-Command', command], capture_output=True, text=True, check=True).stdout)
assert owner['Process']['ProcessId'] == owner['Listener']['OwningProcess'] == 63780
assert 'scholar-revision-isolated-services-v1.py' in owner['Process']['CommandLine']
db = root / 'data/catalog.db'
gold = Path(info['golden_root']) / 'data/catalog.db'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(gold) == info['golden_database_sha256']
with sqlite3.connect('file:' + str(db) + '?mode=ro', uri=True) as conn:
    conn.row_factory = sqlite3.Row
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    baseline = {table: [dict(row) for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid')] for table in tables}
    assert not conn.execute("SELECT 1 FROM studio_jobs WHERE status IN ('QUEUED','RUNNING')").fetchone()
with (repo / '.tmp/scholar-template-native-before-v1.json').open('x', encoding='utf-8') as handle:
    json.dump({'root': str(root), 'tables': baseline, 'database_sha256': sha(db)}, handle, ensure_ascii=False)
with (repo / '.tmp/scholar-template-native-before-v1.db').open('xb') as handle:
    handle.write(db.read_bytes())
subprocess.run(['powershell', '-NoProfile', '-Command', 'Stop-Process -Id 63780 -ErrorAction Stop'], check=True)
env = os.environ.copy()
env['PYTHONPATH'] = str(repo.parent / 'RSTV4/src')
with (repo / '.tmp/scholar-template-studio-v1.log').open('x', encoding='utf-8') as log:
    process = subprocess.Popen([sys.executable, str(repo / '.tmp/scholar-revision-isolated-services-v1.py'), 'serve'],
                               cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT,
                               creationflags=subprocess.CREATE_NO_WINDOW)
updated = {**info, 'owned_processes': {'studio': process.pid, 'frontend': 75360},
           'source_import_root': env['PYTHONPATH'], 'replaces_studio_pid': 63780, 'prior_owner': owner}
with httpx.Client(timeout=3) as client:
    ready = False
    for _ in range(100):
        try:
            ready = client.get(f"http://127.0.0.1:8877/api/manuscripts/{info['manuscripts']['reading']}/templates/skeleton_c4def72df1572dd62073ba2ac38a556c").status_code == 200
        except httpx.HTTPError:
            pass
        if ready:
            break
        time.sleep(.2)
    assert ready
assert sha(db) == json.loads((repo / '.tmp/scholar-template-native-before-v1.json').read_text(encoding='utf-8'))['database_sha256']
assert sha(gold) == info['golden_database_sha256']
with (repo / '.tmp/scholar-template-services-v1.json').open('x', encoding='utf-8') as handle:
    json.dump(updated, handle, indent=2)
print(json.dumps({'ready': True, 'studio_pid': process.pid, 'studio_port': 8877,
                  'frontend_pid': 75360, 'frontend_port': 3004, 'original_database_unchanged': True}))
