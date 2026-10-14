import hashlib,json,os,re,subprocess,time
from pathlib import Path
import httpx
repo=Path(__file__).resolve().parents[1]
prior=json.loads((repo/'.tmp/scholar-hierarchy-runtime-final-v1.json').read_text(encoding='utf-8'))
old_assets=json.loads((repo/'.tmp/scholar-hierarchy-refresh-v4.json').read_text(encoding='utf-8'))['served_assets_sha256']
build=json.loads((repo/'.tmp/scholar-template-mapping-build-v1.json').read_text(encoding='utf-8'))
assert build['status']=='PASS' and build['original_source_and_dist_unchanged']
root=Path(build['root']).resolve()
assert root.name=='writing-studio' and root.parent.name.startswith('scui-template-mapping-build-')
query=f'''
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$all = Get-CimInstance Win32_Process
$ids = [System.Collections.Generic.HashSet[int]]::new()
[void]$ids.Add({prior['backend_launch_pid']})
[void]$ids.Add({prior['frontend_launch_pid']})
do {{ $added=$false; foreach ($p in $all) {{ if ($ids.Contains([int]$p.ParentProcessId) -and $ids.Add([int]$p.ProcessId)) {{ $added=$true }} }} }} while ($added)
[pscustomobject]@{{Processes=@($all | Where-Object {{ $ids.Contains([int]$_.ProcessId) }} | Select-Object ProcessId,ParentProcessId,CommandLine,ExecutablePath,CreationDate);Listeners=@(Get-NetTCPConnection -State Listen -LocalPort 3004,8877 | Select-Object LocalAddress,LocalPort,OwningProcess)}} | ConvertTo-Json -Depth 5
'''
def observe(command):
    return json.loads(subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True,text=True,encoding='utf-8',check=True).stdout)
observed=observe(query);processes={p['ProcessId']:p for p in observed['Processes']}
for listener in observed['Listeners']:
    assert listener['LocalAddress']=='127.0.0.1'
    owner=prior['backend_launch_pid'] if listener['LocalPort']==8877 else prior['frontend_launch_pid']
    pid=listener['OwningProcess'];chain=[pid]
    while pid!=owner:
        assert pid in processes and len(chain)<8
        pid=processes[pid]['ParentProcessId'];chain.append(pid)
    listener['verified_ancestry']=chain
assert {l['LocalPort'] for l in observed['Listeners']}=={3004,8877}
listener=next(l for l in observed['Listeners'] if l['LocalPort']==3004)
pid=listener['OwningProcess'];old=processes[pid]
sealed=next(p for p in prior['observed']['Processes'] if p['ProcessId']==pid)
assert old==sealed and str(Path(prior['production_root'])) in old['CommandLine'] and old['ExecutablePath'].lower().endswith('node.exe')
fixture=json.loads((repo/'.tmp/scholar-template-native-fixture-v1.json').read_text(encoding='utf-8'))
db=Path(fixture['root'])/'data/catalog.db';before=db.read_bytes()
with httpx.Client(timeout=12) as client:
    for asset,digest in old_assets.items():
        response=client.get('http://127.0.0.1:3004'+asset)
        assert response.status_code==200 and hashlib.sha256(response.content).hexdigest()==digest
    response=client.get(f"http://127.0.0.1:8877/api/manuscripts/{fixture['native_manuscript_id']}/workspace");response.raise_for_status()
    assert response.json()['document_revision']==49
path=repo/'.tmp/scholar-template-mapping-refresh-v1.json'
receipt={'status':'OWNED_FRONTEND_VERIFIED','production_root':str(root),'before_listener':listener,'before_process':old,'backend_launch_pid':prior['backend_launch_pid'],'before_observed':observed}
with path.open('x',encoding='utf-8') as h:json.dump(receipt,h,indent=2)
fresh=observe(f'Get-CimInstance Win32_Process -Filter "ProcessId={pid}" | Select-Object ProcessId,ParentProcessId,CommandLine,ExecutablePath,CreationDate | ConvertTo-Json')
assert fresh==old
subprocess.run(['powershell','-NoProfile','-Command',f'Stop-Process -Id {pid} -ErrorAction Stop'],check=True)
env=os.environ.copy();env.update(NEXT_PUBLIC_RSTV4_API=build['api'],NODE_OPTIONS='--max-old-space-size=1536',RAYON_NUM_THREADS='2',UV_THREADPOOL_SIZE='2')
command=['cmd.exe','/c','npm.cmd','run','start','--','--port','3004','--hostname','127.0.0.1']
with (repo/'.tmp/scholar-template-mapping-frontend-v1.log').open('x',encoding='utf-8') as log:
    process=subprocess.Popen(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
receipt.update(frontend_launch_pid=process.pid,command=command)
path.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
with httpx.Client(timeout=4) as client:
    deadline=time.monotonic()+35
    while True:
        try:
            response=client.get('http://127.0.0.1:3004/')
            if response.status_code==200:break
        except httpx.HTTPError:pass
        assert process.poll() is None and time.monotonic()<deadline
        time.sleep(.3)
    assets={}
    for asset in set(re.findall(r'(?:src|href)="([^"?]+\.(?:js|css))"',response.text)):
        response=client.get('http://127.0.0.1:3004'+asset)
        assert response.status_code==200 and response.content==(root/'dist/client'/asset.lstrip('/')).read_bytes()
        assets[asset]=hashlib.sha256(response.content).hexdigest()
    assert assets
assert db.read_bytes()==before
receipt.update(status='READY',served_assets_sha256=assets,backend_and_database_unchanged=True)
path.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k not in {'before_process','before_listener','served_assets_sha256','before_observed'}},ensure_ascii=False))
