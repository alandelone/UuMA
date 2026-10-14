import hashlib
import json
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

repo=Path(__file__).resolve().parents[1]
c=json.loads((repo/'.tmp/scholar-overview-services.json').read_text(encoding='utf-8'))
root=Path(c['root']).resolve();assert root.name.startswith('scholar-ui-fixes-2026-10-03-')
db=root/'data/catalog.db';prior=json.loads((repo/'.tmp/scholar-review-original-final-v1.json').read_text(encoding='utf-8'))
assert hashlib.sha256(db.read_bytes()).hexdigest()==prior['database_sha256']
with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as conn:
 for table in ['studio_jobs','research_discussion_jobs']:
  assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE status IN ('QUEUED','RUNNING')").fetchone()[0]==0
for name in ['scholar-overview-services.json','scholar-ui-fixes-services.json']:
 with (repo/'.tmp'/('scholar-withdrawal-resume-v2-prior-'+name)).open('xb') as h:h.write((repo/'.tmp'/name).read_bytes())
script=r'''
$ErrorActionPreference='Stop'
$c=Get-Content -LiteralPath '.tmp/scholar-overview-services.json' -Raw|ConvertFrom-Json
$s=Get-Content -LiteralPath '.tmp/scholar-ui-fixes-services.json' -Raw|ConvertFrom-Json
foreach($recorded in @($c.catalog_process,$s.owned_processes.studio,$s.owned_processes.frontend)){if(Get-Process -Id $recorded -ErrorAction SilentlyContinue){throw 'Recorded PID exists: verify its ownership before restart.'}}
if(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue|Where-Object LocalPort -in 8885,8874,3000){throw 'A preview port has another owner.'}
$python=(Resolve-Path -LiteralPath '../RSTV4/.venv/Scripts/python.exe').Path
$backend=(Resolve-Path -LiteralPath '../RSTV4').Path
$front=(Resolve-Path -LiteralPath '../writing-studio').Path
$rootPath=(Resolve-Path -LiteralPath $c.root).Path
$logs=(Resolve-Path -LiteralPath '.tmp').Path
foreach($name in @('catalog','studio','frontend')){if(Test-Path -LiteralPath (Join-Path $logs "scholar-withdrawal-resumed-$name-v2.log")){throw 'Preserve restart logs.'}}
$catalog=Start-Process -FilePath $python -ArgumentList @('-u',(Join-Path $logs 'scholar-overview-server.py'),'--root',$rootPath,'--port','8885') -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'scholar-withdrawal-resumed-catalog-v2.log') -RedirectStandardError (Join-Path $logs 'scholar-withdrawal-resumed-catalog-v2-error.log')
$studio=Start-Process -FilePath $python -ArgumentList @('-u',(Join-Path $logs 'scholar-ui-fixes-services.py'),'studio') -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'scholar-withdrawal-resumed-studio-v2.log') -RedirectStandardError (Join-Path $logs 'scholar-withdrawal-resumed-studio-v2-error.log')
$frontend=Start-Process -FilePath (Get-Command node).Source -ArgumentList @((Join-Path $front 'node_modules/vinext/dist/cli.js'),'start','--port','3000') -WorkingDirectory $front -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'scholar-withdrawal-resumed-frontend-v2.log') -RedirectStandardError (Join-Path $logs 'scholar-withdrawal-resumed-frontend-v2-error.log')
$c.catalog_process=$catalog.Id;$c.catalog_mode='source_withdrawal_preview'
$s.owned_processes.studio=$studio.Id;$s.owned_processes.frontend=$frontend.Id;$s.frontend_mode='production_build_source_withdrawal_preview'
[System.IO.File]::WriteAllText((Join-Path $logs 'scholar-overview-services.json'),($c|ConvertTo-Json -Depth 20),[System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText((Join-Path $logs 'scholar-ui-fixes-services.json'),($s|ConvertTo-Json -Depth 20),[System.Text.UTF8Encoding]::new($false))
Write-Output 'Only the missing owned previews were resumed; no existing process stopped.'
'''
subprocess.run(['powershell','-NoProfile','-Command',script],cwd=repo,check=True)
