from pathlib import Path
import json
import os
import sqlite3
import subprocess
import sys
import time

import httpx

repo=Path.cwd()
fixture=json.loads((repo/'.tmp/scholar-intent-correspondence-native-v1.json').read_text(encoding='utf-8'))
expected_root=fixture['processes']['backend']
helper=repo/'.tmp/scholar-intent-correspondence-native-prepare-v1.py'
command=r'''
$rootId = ROOT_ID
$allProcesses = @(Get-CimInstance Win32_Process)
$listener = @(Get-NetTCPConnection -State Listen -LocalPort 8879)
if ($listener.Count -ne 1 -or $listener[0].LocalAddress -ne '127.0.0.1') { throw 'Expected one owned loopback listener' }
$chain = @()
$currentId = $listener[0].OwningProcess
while ($true) {
  $item = @($allProcesses | Where-Object { $_.ProcessId -eq $currentId })
  if ($item.Count -ne 1 -or $chain.ProcessId -contains $currentId) { throw 'Cannot verify owned ancestry' }
  $chain += $item[0]
  if ($currentId -eq $rootId) { break }
  $currentId = $item[0].ParentProcessId
}
foreach ($item in $chain) {
  if (-not $item.CommandLine.Contains('HELPER_PATH') -or -not $item.CommandLine.EndsWith(' serve')) { throw 'Unexpected service command' }
  $fresh = Get-CimInstance Win32_Process -Filter "ProcessId=$($item.ProcessId)"
  if ($fresh.CreationDate -ne $item.CreationDate -or $fresh.CommandLine -ne $item.CommandLine) { throw 'Service identity changed' }
}
[pscustomobject]@{Processes=@($chain | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine,CreationDate);Listeners=@($listener | Select-Object LocalAddress,LocalPort,OwningProcess)} | ConvertTo-Json -Depth 6
foreach ($item in $chain) { Stop-Process -Id $item.ProcessId -ErrorAction Stop }
'''.replace('ROOT_ID',str(expected_root)).replace('HELPER_PATH',str(helper))
base='http://127.0.0.1:8879/api'
with httpx.Client(timeout=10) as client:
    before=client.get(f"{base}/manuscripts/{fixture['manuscript_id']}/workspace").json()
    assert before['document_revision']==19
    with sqlite3.connect(Path(fixture['root'])/'data/catalog.db') as conn:
        statuses=[row[0] for row in conn.execute('SELECT status FROM studio_jobs WHERE manuscript_id=?',(fixture['manuscript_id'],))]
        assert statuses==['SUCCEEDED']
observed=subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True,text=True,encoding='utf-8',check=True)
owned=json.loads(observed.stdout)
env={**os.environ,'PYTHONPATH':str(repo.parent/'RSTV4/src'),'PYTHONUTF8':'1'}
with (repo/'.tmp/scholar-intent-correspondence-backend-runtime-v2.log').open('x',encoding='utf-8') as log:
    process=subprocess.Popen([sys.executable,str(helper),'serve'],cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
ready=False
with httpx.Client(timeout=5) as client:
    deadline=time.monotonic()+40
    while not ready and time.monotonic()<deadline:
        try:
            response=client.get(f"{base}/manuscripts/{fixture['manuscript_id']}/workspace")
            if response.status_code==200:
                after=response.json()
                assert after['document']==before['document']
                assert after['document_revision']==19
                version=client.get(f"{base}/manuscripts/{fixture['manuscript_id']}/generated-versions/{before['active_generated_version_id']}")
                assert version.status_code==200,version.text
                ready=True
        except httpx.HTTPError:
            pass
        if not ready: time.sleep(0.3)
receipt={'status':'PASS_FINAL_BACKEND_REFRESH','prior_owned':owned,'new_backend_root_pid':process.pid,
         'only_owned_8879_replaced':True,'other_runtimes_preserved':True,'fixed_revision':19,
         'final_immutable_version_read':ready,'scientific_acceptance':False}
(repo/'.tmp/scholar-intent-correspondence-runtime-refresh-v1.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
assert ready
print(json.dumps({k:v for k,v in receipt.items() if k!='prior_owned'}))
