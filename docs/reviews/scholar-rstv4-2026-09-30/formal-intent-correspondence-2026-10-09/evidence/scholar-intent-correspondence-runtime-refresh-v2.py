from pathlib import Path
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import httpx

repo=Path.cwd()
fixture=json.loads((repo/'.tmp/scholar-intent-correspondence-native-v1.json').read_text(encoding='utf-8'))
inspection=json.loads((repo/'.tmp/scholar-intent-correspondence-runtime-inspect-v1.log').read_text(encoding='utf-8'))
assert inspection['Listeners']==[] and inspection['OriginalRoot']==[]
root=Path(fixture['root'])
ms=fixture['manuscript_id']
def snapshot():
    with sqlite3.connect(root/'data/catalog.db') as conn:
        conn.row_factory=sqlite3.Row
        return {r[0]:[dict(v) for v in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
before=snapshot()
assert before==json.loads((repo/'.tmp/scholar-intent-correspondence-native-v1/after-tables.json').read_text(encoding='utf-8'))
document=next(d for d in before['studio_documents'] if d['manuscript_id']==ms)
assert document['revision']==19
with socket.socket() as handle: assert handle.connect_ex(('127.0.0.1',8879))!=0
env={**os.environ,'PYTHONPATH':str(repo.parent/'RSTV4/src'),'PYTHONUTF8':'1'}
helper=repo/'.tmp/scholar-intent-correspondence-native-prepare-v1.py'
with (repo/'.tmp/scholar-intent-correspondence-backend-runtime-v2.log').open('x',encoding='utf-8') as log:
    process=subprocess.Popen([sys.executable,str(helper),'serve'],cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
ready=False
with httpx.Client(timeout=5) as client:
    deadline=time.monotonic()+40
    while not ready and time.monotonic()<deadline:
        try:
            response=client.get(f'http://127.0.0.1:8879/api/manuscripts/{ms}/workspace')
            if response.status_code==200:
                workspace=response.json()
                assert workspace['document_revision']==19
                assert workspace['document']==json.loads(document['document_json'])
                version=client.get(f"http://127.0.0.1:8879/api/manuscripts/{ms}/generated-versions/{document['active_generated_version_id']}")
                assert version.status_code==200,version.text
                ready=True
        except httpx.HTTPError: pass
        if not ready: time.sleep(0.3)
assert ready
command="""
$runtimeRootId = ROOT_ID
$runtimeProcesses = @(Get-CimInstance Win32_Process)
$runtimeListeners = @(Get-NetTCPConnection -State Listen -LocalPort 8879,3006,8878,3005,8877,3004 | Select-Object LocalAddress,LocalPort,OwningProcess)
$runtimeChain = @()
$runtimeCurrent = @($runtimeListeners | Where-Object { $_.LocalPort -eq 8879 })[0].OwningProcess
while ($true) {
  $runtimeItem = @($runtimeProcesses | Where-Object { $_.ProcessId -eq $runtimeCurrent })
  if ($runtimeItem.Count -ne 1 -or $runtimeChain.ProcessId -contains $runtimeCurrent) { throw 'Cannot prove new owner ancestry' }
  $runtimeChain += $runtimeItem[0]
  if ($runtimeCurrent -eq $runtimeRootId) { break }
  $runtimeCurrent = $runtimeItem[0].ParentProcessId
}
[pscustomobject]@{Processes=@($runtimeChain | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine,CreationDate);Listeners=$runtimeListeners} | ConvertTo-Json -Depth 6
""".replace('ROOT_ID',str(process.pid))
observed=subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True,text=True,encoding='utf-8',check=True)
owner=json.loads(observed.stdout)
assert {x['LocalPort'] for x in owner['Listeners']}=={8879,3006,8878,3005,8877,3004}
assert all(x['LocalAddress']=='127.0.0.1' for x in owner['Listeners'])
assert all(str(helper) in x['CommandLine'] and x['CommandLine'].endswith(' serve') for x in owner['Processes'])
assert snapshot()==before
receipt={'status':'PASS_FINAL_BACKEND_REFRESH','prior_root_terminal_proved':inspection,
         'new_backend_root_pid':process.pid,'observed':owner,'only_owned_8879_replaced':True,
         'other_runtimes_preserved':True,'all109tables_unchanged':True,'fixed_revision':19,
         'final_immutable_version_read':True,'scientific_acceptance':False}
(repo/'.tmp/scholar-intent-correspondence-runtime-refresh-v1.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k not in {'observed','prior_root_terminal_proved'}}))
