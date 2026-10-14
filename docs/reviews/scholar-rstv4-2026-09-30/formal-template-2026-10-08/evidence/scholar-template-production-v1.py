import hashlib
import json
import os
import re
import socket
import subprocess
import time
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
build = json.loads((repo / '.tmp/scholar-template-build-v3.json').read_text(encoding='utf-8'))
root = Path(build['root']).resolve()
assert build['status'] == 'PASS' and build['original_source_and_dist_unchanged']
assert root.parent.name.startswith('scui-template-build-') and root.name == 'writing-studio'
with socket.socket() as check:
    assert check.connect_ex(('127.0.0.1',3004)) != 0, 'An existing listener must not be replaced'
env = os.environ.copy()
env.update(NEXT_PUBLIC_RSTV4_API=build['api'], NODE_OPTIONS='--max-old-space-size=1536', RAYON_NUM_THREADS='2')
command = ['cmd.exe','/c','npm.cmd','run','start','--','--port','3004','--hostname','127.0.0.1']
with (repo / '.tmp/scholar-template-production-v1.log').open('x', encoding='utf-8') as log:
    process = subprocess.Popen(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW)
path = repo / '.tmp/scholar-template-production-v1.json'
receipt = {'root':str(root),'command':command,'launch_pid':process.pid,'port':3004,
           'api':build['api'],'status':'STARTING','development_replaced':True,'golden_frontend_untouched':True}
with path.open('x', encoding='utf-8') as handle:
    json.dump(receipt, handle, indent=2)
with httpx.Client(timeout=3) as client:
    deadline = time.monotonic()+35
    while time.monotonic() < deadline:
        try:
            response = client.get('http://127.0.0.1:3004/')
            if response.status_code == 200:
                break
        except httpx.HTTPError:
            pass
        assert process.poll() is None, 'Owned production launcher exited'
        time.sleep(.3)
    else:
        raise AssertionError('Production endpoint did not become ready')
    assets = {}
    for asset in set(re.findall(r'(?:src|href)="([^"?]+\.(?:js|css))"',response.text)):
        raw = client.get('http://127.0.0.1:3004'+asset)
        assert raw.status_code == 200 and raw.content == (root / 'dist/client' / asset.lstrip('/')).read_bytes()
        assets[asset] = hashlib.sha256(raw.content).hexdigest()
    assert assets
    scripts = ''.join((root / 'dist/client' / asset.lstrip('/')).read_text(encoding='utf-8') for asset in assets if asset.endswith('.js'))
    assert '模板采用范围' in scripts and '完整模板与部分采用' in scripts and build['api'] in scripts
receipt.update(status='READY',served_assets_sha256=assets)
path.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k != 'served_assets_sha256'}, ensure_ascii=False))
