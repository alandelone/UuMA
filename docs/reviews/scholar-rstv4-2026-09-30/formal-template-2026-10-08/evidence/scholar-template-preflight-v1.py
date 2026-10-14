import hashlib
import json
import subprocess
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
info = json.loads((repo / '.tmp/scholar-revision-isolated-services-v1.json').read_text())
ps = subprocess.run(['powershell', '-NoProfile', '-Command',
    "Get-CimInstance Win32_Process -Filter 'ProcessId=63780 OR ProcessId=75360' | "
    "Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine,CreationDate | ConvertTo-Json"],
    capture_output=True, text=True, check=True)
owners = json.loads(ps.stdout)
assert {p['ProcessId'] for p in owners} == {63780, 75360}
assert 'scholar-revision-isolated-services-v1.py' in next(p for p in owners if p['ProcessId'] == 63780)['CommandLine']
assert '3004' in next(p for p in owners if p['ProcessId'] == 75360)['CommandLine']
root = Path(info['root']).resolve()
assert root.name == 'scui-revision-native-p48co4i6'
with httpx.Client(timeout=8) as client:
    assert client.get('http://127.0.0.1:3004/').status_code == 200
    assert client.get(f"http://127.0.0.1:8877/api/manuscripts/{info['manuscripts']['revision']}/workspace").status_code == 200
backup = repo / '.tmp/scholar-template-before-v1'
backup.mkdir()
paths = [repo.parent / 'RSTV4/src/rstv4/studio.py', repo.parent / 'RSTV4/src/rstv4/studio_api.py',
         repo.parent / 'writing-studio/components/studio-workspace.tsx',
         repo.parent / 'writing-studio/lib/studio-types.ts', repo.parent / 'writing-studio/lib/studio-api.ts']
hashes = {}
for path in paths:
    raw = path.read_bytes()
    with (backup / path.name).open('xb') as handle:
        handle.write(raw)
    hashes[str(path)] = hashlib.sha256(raw).hexdigest()
with (repo / '.tmp/scholar-template-preflight-v1.json').open('x', encoding='utf-8') as handle:
    json.dump({'services': info, 'live_owners': owners, 'before_sha256': hashes}, handle, indent=2)
print('PASS owned isolated services live; original source snapshots retained')
