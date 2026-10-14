import hashlib
import json
import os
import socket
import subprocess
import time
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
front = repo.parent / 'writing-studio'
runtime_info = json.loads((repo / '.tmp/scholar-source-hierarchy-runtime-v1.json').read_text(encoding='utf-8'))
env = os.environ.copy()
env.update(NODE_OPTIONS='--max-old-space-size=512', GOMAXPROCS='2', GOMEMLIMIT='512MiB')
commands = [['cmd.exe', '/c', 'node_modules\\.bin\\tsc.cmd', '--noEmit'],
            ['cmd.exe', '/c', 'node_modules\\.bin\\oxlint.cmd', '--threads=1', 'components/studio-template-adoption.tsx'],
            ['git', 'diff', '--check']]
results = []
with (repo / '.tmp/scholar-source-hierarchy-modal-static-v1.log').open('x', encoding='utf-8') as log:
    for command in commands:
        result = subprocess.run(command, cwd=front, env=env, stdout=log, stderr=subprocess.STDOUT)
        results.append({'command': command, 'exit_code': result.returncode})
        assert result.returncode == 0
(repo / '.tmp/scholar-source-hierarchy-modal-static-v1.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
source = (repo / '.tmp/scholar-template-build-v3.py').read_text(encoding='utf-8')
source = source.replace('scholar-template-build-v3.', 'scholar-source-hierarchy-build-v2.').replace(
    'scui-template-build-', 'scui-source-hierarchy-build-').replace('127.0.0.1:8877', '127.0.0.1:8878')
source = source.replace('--max-old-space-size=1536', '--max-old-space-size=512').replace(
    "RAYON_NUM_THREADS='2', UV_THREADPOOL_SIZE='2'", "RAYON_NUM_THREADS='1', UV_THREADPOOL_SIZE='1'")
exec(compile(source, __file__, 'exec'))
build_info = json.loads((repo / '.tmp/scholar-source-hierarchy-build-v2.json').read_text(encoding='utf-8'))
snapshot_command = "[pscustomobject]@{Processes=@(Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,CommandLine,ExecutablePath,CreationDate);Listeners=@(Get-NetTCPConnection -State Listen -LocalPort 8878,3005,8877,3004 | Select-Object LocalAddress,LocalPort,OwningProcess)} | ConvertTo-Json -Depth 6"
fresh = json.loads(subprocess.run(['powershell', '-NoProfile', '-Command', snapshot_command],
    capture_output=True, text=True, check=True).stdout)
by_pid = {p['ProcessId']: p for p in fresh['Processes']}
old_listener = next(p for p in runtime_info['observed']['Listeners'] if p['LocalPort'] == 3005)
for saved in runtime_info['observed']['Processes']:
    assert by_pid[saved['ProcessId']] == saved, 'Process ownership/fingerprint changed'
assert next(p['OwningProcess'] for p in fresh['Listeners'] if p['LocalPort'] == 3005) == old_listener['OwningProcess']
(repo / '.tmp/scholar-source-hierarchy-modal-runtime-before-v1.json').write_text(json.dumps(fresh, indent=2), encoding='utf-8')
subprocess.run(['powershell', '-NoProfile', '-Command', f"Stop-Process -Id {int(old_listener['OwningProcess'])} -Force"], check=True)
with socket.socket() as check:
    assert check.connect_ex(('127.0.0.1', 3005)) != 0
deploy_env = os.environ.copy()
deploy_env.update(NODE_OPTIONS='--max-old-space-size=512', RAYON_NUM_THREADS='1', UV_THREADPOOL_SIZE='1')
with (repo / '.tmp/scholar-source-hierarchy-modal-frontend-runtime-v1.log').open('x', encoding='utf-8') as log:
    process = subprocess.Popen(['cmd.exe', '/c', 'npm.cmd', 'run', 'start', '--', '--port', '3005', '--hostname', '127.0.0.1'],
        cwd=build_info['root'], env=deploy_env, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
import httpx
with httpx.Client(timeout=3) as client:
    deadline = time.monotonic() + 30
    ready = False
    while time.monotonic() < deadline:
        try:
            if client.get('http://127.0.0.1:3005/').status_code == 200:
                ready = True
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
assert ready
final = json.loads(subprocess.run(['powershell', '-NoProfile', '-Command', snapshot_command],
    capture_output=True, text=True, check=True).stdout)
current = {p['ProcessId']: p for p in final['Processes']}
chain = []
listener = next(p for p in final['Listeners'] if p['LocalPort'] == 3005)
pid = listener['OwningProcess']
while pid in current and pid not in chain:
    chain.append(pid)
    if pid == process.pid:
        break
    pid = current[pid]['ParentProcessId']
assert chain[-1] == process.pid and listener['LocalAddress'] == '127.0.0.1'
for port in (3004, 8877, 8878):
    assert next(p for p in final['Listeners'] if p['LocalPort'] == port) == next(p for p in fresh['Listeners'] if p['LocalPort'] == port)
final['Processes'] = [p for p in final['Processes'] if p['ProcessId'] in chain or p['ProcessId'] in {67988, 82492}]
receipt = {'status': 'PASS_OWNED_FRONTEND_REPLACED', 'frontend_root_pid': process.pid,
           'production_root': build_info['root'], 'verified_frontend_ancestry': chain,
           'observed': final, 'old_runtime_and_backend_preserved': True,
           'post_full_delta': 'Only dialog viewport bounds and list height classes',
           'component_sha256': hashlib.sha256((front / 'components/studio-template-adoption.tsx').read_bytes()).hexdigest()}
(repo / '.tmp/scholar-source-hierarchy-modal-runtime-v1.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt))
