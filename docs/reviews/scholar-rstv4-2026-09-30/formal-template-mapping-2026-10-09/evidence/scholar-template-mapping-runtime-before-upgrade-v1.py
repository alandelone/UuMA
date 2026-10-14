import hashlib,json,subprocess
from pathlib import Path
import httpx
repo=Path(__file__).resolve().parents[1]
refresh=json.loads((repo/'.tmp/scholar-template-mapping-refresh-v1.json').read_text(encoding='utf-8'))
query=f'''
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$all = Get-CimInstance Win32_Process
$ids = [System.Collections.Generic.HashSet[int]]::new()
[void]$ids.Add({refresh['backend_launch_pid']})
[void]$ids.Add({refresh['frontend_launch_pid']})
do {{ $added=$false; foreach ($p in $all) {{ if ($ids.Contains([int]$p.ParentProcessId) -and $ids.Add([int]$p.ProcessId)) {{ $added=$true }} }} }} while ($added)
[pscustomobject]@{{Processes=@($all | Where-Object {{ $ids.Contains([int]$_.ProcessId) }} | Select-Object ProcessId,ParentProcessId,CommandLine,ExecutablePath,CreationDate);Listeners=@(Get-NetTCPConnection -State Listen -LocalPort 3004,8877 | Select-Object LocalAddress,LocalPort,OwningProcess)}} | ConvertTo-Json -Depth 5
'''
observed=json.loads(subprocess.run(['powershell','-NoProfile','-Command',query],capture_output=True,text=True,encoding='utf-8',check=True).stdout)
processes={p['ProcessId']:p for p in observed['Processes']}
for listener in observed['Listeners']:
    assert listener['LocalAddress']=='127.0.0.1'
    owner=refresh['backend_launch_pid'] if listener['LocalPort']==8877 else refresh['frontend_launch_pid']
    pid=listener['OwningProcess'];chain=[pid]
    while pid!=owner:
        assert pid in processes and len(chain)<8
        pid=processes[pid]['ParentProcessId'];chain.append(pid)
    listener['verified_ancestry']=chain
    current=processes[listener['OwningProcess']]
    if listener['LocalPort']==3004:assert refresh['production_root'] in current['CommandLine'] and current['ExecutablePath'].lower().endswith('node.exe')
    else:
        old=next(p for p in refresh['before_observed']['Processes'] if p['ProcessId']==current['ProcessId'])
        assert current==old
assert {l['LocalPort'] for l in observed['Listeners']}=={3004,8877}
with httpx.Client(timeout=12) as client:
    for asset,digest in refresh['served_assets_sha256'].items():
        response=client.get('http://127.0.0.1:3004'+asset)
        assert response.status_code==200 and hashlib.sha256(response.content).hexdigest()==digest
result={**{k:refresh[k] for k in ['backend_launch_pid','frontend_launch_pid','production_root']},'observed':observed,'status':'PASS_OWNED_EXACT_BUILD'}
with (repo/'.tmp/scholar-template-mapping-runtime-before-upgrade-v1.json').open('x',encoding='utf-8') as h:json.dump(result,h,indent=2)
print(json.dumps({k:v for k,v in result.items() if k!='observed'}))
