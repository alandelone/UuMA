import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
fixture = json.loads((repo / '.tmp/scholar-source-hierarchy-fixture-v1.json').read_text(encoding='utf-8'))
if len(sys.argv) > 1:
    import uvicorn
    from fastapi.middleware.cors import CORSMiddleware
    from rstv4.studio_api import create_app

    app = create_app(fixture['root'])
    app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:3005'],
                       allow_methods=['*'], allow_headers=['*'])
    uvicorn.run(app, host='127.0.0.1', port=8878, log_level='warning')
    raise SystemExit()
import httpx

build = json.loads((repo / '.tmp/scholar-source-hierarchy-build-v1.json').read_text(encoding='utf-8'))
assert build['status'] == 'PASS' and build['api'] == 'http://127.0.0.1:8878/api'
for port in (8878, 3005):
    with socket.socket() as check:
        assert check.connect_ex(('127.0.0.1', port)) != 0, f'Existing service owns {port}'
processes = {}
for name, command, cwd in [
    ('backend', [sys.executable, str(Path(__file__).resolve()), 'serve'], repo),
    ('frontend', ['cmd.exe', '/c', 'npm.cmd', 'run', 'start', '--', '--port', '3005',
                  '--hostname', '127.0.0.1'], Path(build['root'])),
]:
    env = os.environ.copy()
    env.update(NODE_OPTIONS='--max-old-space-size=512', RAYON_NUM_THREADS='1', UV_THREADPOOL_SIZE='1')
    with (repo / f'.tmp/scholar-source-hierarchy-{name}-runtime-v1.log').open('x', encoding='utf-8') as log:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    processes[name] = process.pid
ready = set()
with httpx.Client(timeout=3) as client:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline and len(ready) < 2:
        for name, url in [('backend', f"http://127.0.0.1:8878/api/manuscripts/{fixture['manuscript_id']}/workspace"),
                          ('frontend', 'http://127.0.0.1:3005/')]:
            if name in ready:
                continue
            try:
                response = client.get(url)
                if response.status_code == 200:
                    ready.add(name)
            except httpx.HTTPError:
                pass
        if len(ready) < 2:
            time.sleep(0.3)
owner = json.loads(subprocess.run(['powershell', '-NoProfile', '-Command',
    "[pscustomobject]@{Processes=@(Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,CommandLine,ExecutablePath,CreationDate);Listeners=@(Get-NetTCPConnection -State Listen -LocalPort 8878,3005 | Select-Object LocalAddress,LocalPort,OwningProcess)} | ConvertTo-Json -Depth 6"],
    capture_output=True, text=True, check=True).stdout)
by_id = {p['ProcessId']: p for p in owner['Processes']}
retained = set()
for listener in owner['Listeners']:
    expected = processes['backend' if listener['LocalPort'] == 8878 else 'frontend']
    chain = []
    current = listener['OwningProcess']
    while current in by_id and current not in chain:
        chain.append(current)
        retained.add(current)
        if current == expected:
            break
        current = by_id[current]['ParentProcessId']
    assert chain[-1] == expected and listener['LocalAddress'] == '127.0.0.1'
    listener['verified_ancestry'] = chain
owner['Processes'] = [p for p in owner['Processes'] if p['ProcessId'] in retained]
receipt = {'root': fixture['root'], 'production_root': build['root'], 'processes': processes,
           'observed': owner, 'ready': sorted(ready), 'old_runtime_preserved': True,
           'scientific_approval': False, 'url': f"http://127.0.0.1:3005/?manuscript={fixture['manuscript_id']}&view=structure&left=1&right=1&chat=0"}
(repo / '.tmp/scholar-source-hierarchy-runtime-v1.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
assert ready == {'backend', 'frontend'}
print(json.dumps(receipt, ensure_ascii=False))
