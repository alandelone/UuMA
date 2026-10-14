import hashlib
import json
import os
import re
import socket
import subprocess
import time
from pathlib import Path

import httpx

repo=Path(__file__).resolve().parents[1]
prior=json.loads((repo/'.tmp/scholar-template-runtime-final-v1.json').read_text(encoding='utf-8'))
fixture=json.loads((repo/'.tmp/scholar-template-native-fixture-v1.json').read_text(encoding='utf-8'))
build=json.loads((repo/'.tmp/scholar-hierarchy-build-v1.json').read_text(encoding='utf-8'))
assert build['status']=='PASS' and build['original_source_and_dist_unchanged']
root=Path(build['root']).resolve()
assert root.name=='writing-studio' and root.parent.name.startswith('scui-hierarchy-build-')
db=Path(fixture['root'])/'data/catalog.db'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before=sha(db)
gold=Path(fixture['golden_root'])/'data/catalog.db'
assert sha(gold)==fixture['golden_database_sha256']
query="Get-CimInstance Win32_Process -Filter 'ProcessId=82248 OR ProcessId=83352 OR ProcessId=35552 OR ProcessId=77500' | Select-Object ProcessId,ParentProcessId,CommandLine,CreationDate | ConvertTo-Json"
observed=json.loads(subprocess.run(['powershell','-NoProfile','-Command',query],capture_output=True,text=True,check=True).stdout)
assert {p['ProcessId'] for p in observed}=={82248,83352,35552,77500}
for p in observed:
    old=next(row for row in prior['observed']['Processes'] if row['ProcessId']==p['ProcessId'])
    assert p['CommandLine']==old['CommandLine'] and p['CreationDate']==old['CreationDate']
listeners=json.loads(subprocess.run(['powershell','-NoProfile','-Command',"Get-NetTCPConnection -State Listen -LocalPort 3004,8877 | Select-Object LocalAddress,LocalPort,OwningProcess | ConvertTo-Json"],capture_output=True,text=True,check=True).stdout)
assert {(p['LocalPort'],p['OwningProcess'],p['LocalAddress']) for p in listeners}=={(3004,77500,'127.0.0.1'),(8877,83352,'127.0.0.1')}
api='http://127.0.0.1:8877/api'
with httpx.Client(timeout=12) as client:
    response=client.get(f"{api}/manuscripts/{fixture['native_manuscript_id']}/workspace")
    response.raise_for_status()
    assert response.json()['document_revision']==27 and response.json()['document']==fixture['initial_document']
path=repo/'.tmp/scholar-hierarchy-refresh-v1.json'
receipt={'before_processes':observed,'before_listeners':listeners,'before_database_sha256':before,
         'backend_root':fixture['root'],'production_root':str(root),'status':'OWNERS_VERIFIED',
         'owned_services':{},'golden_root':fixture['golden_root'],'golden_database_sha256':sha(gold)}
with path.open('x',encoding='utf-8') as h:json.dump(receipt,h,indent=2)
for pid in [83352,77500]:
    # Reverify exact creation and command immediately before stopping only our listener.
    current=json.loads(subprocess.run(['powershell','-NoProfile','-Command',f'Get-CimInstance Win32_Process -Filter "ProcessId={pid}" | Select-Object ProcessId,ParentProcessId,CommandLine,CreationDate | ConvertTo-Json'],capture_output=True,text=True,check=True).stdout)
    assert current==next(p for p in observed if p['ProcessId']==pid)
    subprocess.run(['powershell','-NoProfile','-Command',f'Stop-Process -Id {pid} -ErrorAction Stop'],check=True)
for port in [8877,3004]:
    deadline=time.monotonic()+10
    while True:
        with socket.socket() as check: free=check.connect_ex(('127.0.0.1',port))!=0
        if free:break
        assert time.monotonic()<deadline
        time.sleep(.2)
python=repo/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
for name in ['backend','frontend']:
    env=os.environ.copy()
    env.update(PYTHONPATH=str(repo.parent/'RSTV4/src'),NEXT_PUBLIC_RSTV4_API=build['api'],NODE_OPTIONS='--max-old-space-size=1536',RAYON_NUM_THREADS='2',UV_THREADPOOL_SIZE='2')
    command=[str(python),str(repo/'.tmp/scholar-revision-isolated-services-v1.py'),'serve']
    cwd=repo
    if name=='frontend':
        command=['cmd.exe','/c','npm.cmd','run','start','--','--port','3004','--hostname','127.0.0.1']
        cwd=root
    with (repo/f'.tmp/scholar-hierarchy-{name}-v1.log').open('x',encoding='utf-8') as log:
        process=subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    receipt['owned_services'][name]={'launch_pid':process.pid,'command':command,'cwd':str(cwd)}
    path.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
with httpx.Client(timeout=4) as client:
    ready={}
    deadline=time.monotonic()+40
    urls={'backend':f"{api}/manuscripts/{fixture['native_manuscript_id']}/workspace",'frontend':'http://127.0.0.1:3004/'}
    while len(ready)<2:
        for name,url in urls.items():
            if name in ready:continue
            try:
                response=client.get(url)
                if response.status_code==200:ready[name]=response
            except httpx.HTTPError:pass
        if len(ready)==2:break
        assert time.monotonic()<deadline
        time.sleep(.3)
    assert ready['backend'].json()['document_revision']==27 and ready['backend'].json()['document']==fixture['initial_document']
    assets={}
    for asset in set(re.findall(r'(?:src|href)="([^"?]+\.(?:js|css))"',ready['frontend'].text)):
        response=client.get('http://127.0.0.1:3004'+asset)
        assert response.status_code==200 and response.content==(root/'dist/client'/asset.lstrip('/')).read_bytes()
        assets[asset]=hashlib.sha256(response.content).hexdigest()
    assert assets
    code=''.join(p.read_text(encoding='utf-8') for p in (root/'dist/client').rglob('*.js'))
    assert '高级 L2 关系' in code and '父章节' in code and build['api'] in code
assert before==sha(db) and sha(gold)==fixture['golden_database_sha256']
receipt.update(status='READY',served_assets_sha256=assets,database_unchanged_by_refresh=True)
path.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k not in {'before_processes','before_listeners','served_assets_sha256'}},ensure_ascii=False),flush=True)
