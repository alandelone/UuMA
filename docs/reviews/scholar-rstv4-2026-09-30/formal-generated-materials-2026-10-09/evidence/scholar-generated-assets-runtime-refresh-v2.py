from pathlib import Path
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import httpx

root=Path.cwd()
fixture=json.loads((root/'.tmp/scholar-generated-assets-native-v1.json').read_text(encoding='utf-8'))
db=Path(fixture['root'])/'data/catalog.db'
def snapshot():
    with sqlite3.connect(db) as conn:
        conn.row_factory=sqlite3.Row
        return {r[0]:[dict(v) for v in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
before=snapshot()
owned_jobs=[r for r in before['studio_jobs'] if r['manuscript_id']==fixture['manuscript_id']]
assert len(owned_jobs)==2 and all(j['status']=='SUCCEEDED' for j in owned_jobs)
helper=root/'.tmp/scholar-generated-assets-native-v1.py'
command="""
$materialRootId = ROOT_ID
$materialAll = @(Get-CimInstance Win32_Process)
$materialListener = @(Get-NetTCPConnection -State Listen -LocalPort 8880)
if ($materialListener.Count -ne 1 -or $materialListener[0].LocalAddress -ne '127.0.0.1') { throw 'Expected one owned listener' }
$materialChain = @()
$materialCurrentId = $materialListener[0].OwningProcess
while ($true) {
  $materialItem = @($materialAll | Where-Object { $_.ProcessId -eq $materialCurrentId })
  if ($materialItem.Count -ne 1 -or $materialChain.ProcessId -contains $materialCurrentId) { throw 'Cannot prove owner chain' }
  $materialChain += $materialItem[0]
  if ($materialCurrentId -eq $materialRootId) { break }
  $materialCurrentId = $materialItem[0].ParentProcessId
}
foreach ($item in $materialChain) {
  if (-not $item.CommandLine.Contains('HELPER_PATH') -or -not $item.CommandLine.EndsWith(' serve')) { throw 'Unexpected owned command' }
}
[pscustomobject]@{Processes=@($materialChain | Select-Object ProcessId,ParentProcessId,CommandLine,ExecutablePath,CreationDate);Listener=@($materialListener | Select-Object LocalAddress,LocalPort,OwningProcess)} | ConvertTo-Json -Depth 6
foreach ($item in $materialChain) {
  $fresh = Get-CimInstance Win32_Process -Filter "ProcessId=$($item.ProcessId)"
  if ($null -ne $fresh) {
    if ($fresh.CreationDate -ne $item.CreationDate -or $fresh.CommandLine -ne $item.CommandLine) { throw 'Owner identity changed' }
    Stop-Process -Id $item.ProcessId -ErrorAction Stop
  }
}
""".replace('ROOT_ID',str(json.loads((root/'.tmp/scholar-generated-assets-runtime-refresh-v1.json').read_text(encoding='utf-8'))['new_backend_root_pid'])).replace('HELPER_PATH',str(helper))
result=subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True,text=True,encoding='utf-8',check=True)
owned=json.loads(result.stdout)
with socket.socket() as handle: assert handle.connect_ex(('127.0.0.1',8880))!=0
env={**os.environ,'PYTHONPATH':str(root.parent/'RSTV4/src'),'PYTHONUTF8':'1'}
with (root/'.tmp/scholar-generated-assets-backend-runtime-v3.log').open('x',encoding='utf-8') as log:
    process=subprocess.Popen([sys.executable,str(helper),'serve'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
ready=False
with httpx.Client(timeout=4) as client:
    deadline=time.monotonic()+40
    while not ready and time.monotonic()<deadline:
        try:
            response=client.get(f"http://127.0.0.1:8880/api/manuscripts/{fixture['manuscript_id']}/workspace")
            if response.status_code==200:
                assert response.json()['document']==fixture['initial_document']
                ready=True
        except httpx.HTTPError:pass
        if not ready:time.sleep(.3)
assert ready and snapshot()==before
receipt={'status':'PASS_FINAL_MATERIAL_BACKEND_READY','prior_owned':owned,'new_backend_root_pid':process.pid,
         'all109tables_exact':True,'only_owned8880_replaced':True,'other_runtimes_preserved':True,
         'prior_two_jobs_terminal':True,'actual_models':0,'scientific_acceptance':False}
(root/'.tmp/scholar-generated-assets-runtime-refresh-v2.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k!='prior_owned'}))
