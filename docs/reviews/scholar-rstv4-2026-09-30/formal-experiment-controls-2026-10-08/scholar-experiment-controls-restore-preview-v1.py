import hashlib
import json
import sqlite3
import subprocess
import time
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
catalog_meta = repo / '.tmp/scholar-overview-services.json'
studio_meta = repo / '.tmp/scholar-ui-fixes-services.json'
catalog = json.loads(catalog_meta.read_text(encoding='utf-8'))
studio = json.loads(studio_meta.read_text(encoding='utf-8'))
root = Path(catalog['root']).resolve()
assert root == Path(studio['root']).resolve()
assert root.name == 'scholar-ui-fixes-2026-10-03-8pn_4t3h'
db = root / 'data/catalog.db'
baseline = json.loads((repo / '.tmp/scholar-fieldkg-semantics-post-migration-baseline-v1.json').read_text())
sha = lambda raw: hashlib.sha256(raw).hexdigest()
assert sha(db.read_bytes()) == baseline['database_sha256']
with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
    for table in ['studio_jobs', 'research_discussion_jobs']:
        assert conn.execute('SELECT COUNT(*) FROM ' + table + " WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM acquisition_jobs WHERE status='RUNNING'").fetchone()[0] == 0
backup = repo / '.tmp/scholar-experiment-controls-preview-original-v1'
backup.mkdir(exist_ok=False)
for path in [catalog_meta, studio_meta, db]:
    with (backup / path.name).open('xb') as h:
        h.write(path.read_bytes())
guard = r'''
$ErrorActionPreference='Stop'
$all=@(Get-CimInstance Win32_Process)
$cat=Get-Content -LiteralPath '.tmp/scholar-overview-services.json' -Raw|ConvertFrom-Json
$stu=Get-Content -LiteralPath '.tmp/scholar-ui-fixes-services.json' -Raw|ConvertFrom-Json
$catMatches=@($all|Where-Object {$_.CommandLine -like '*scholar-overview-server.py*--root*scholar-ui-fixes-2026-10-03-8pn_4t3h*--port 8885*'})
$stuMatches=@($all|Where-Object {$_.CommandLine -like '*scholar-ui-fixes-services.py studio*'})
$frontMatches=@($all|Where-Object {$_.CommandLine -match 'node.*writing-studio[/\]node_modules[/\]vinext[/\]dist[/\]cli.js start.*--port 3000'})
$listeners=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue|Where-Object LocalPort -in 8885,8874,3000)
$proof=@{listeners=@($listeners|Select-Object LocalPort,OwningProcess);catalog=@($catMatches|Select-Object ProcessId,ParentProcessId,CommandLine);studio=@($stuMatches|Select-Object ProcessId,ParentProcessId,CommandLine);frontend=@($frontMatches|Select-Object ProcessId,ParentProcessId,CommandLine)}
foreach($p in @(8885,8874,3000)){
 $matches=switch($p){8885 {$catMatches};8874 {$stuMatches};3000 {$frontMatches}}
 $port=@($listeners|Where-Object LocalPort -eq $p)
 if($port.Count -gt 1){throw 'Ambiguous listener'}
 if($port.Count -eq 1 -and $port[0].OwningProcess -notin $matches.ProcessId){throw 'Preview port belongs to another owner'}
 if($port.Count -eq 0 -and $matches.Count -gt 0){throw 'Preview startup already exists; do not duplicate'}
}
$logs=(Resolve-Path -LiteralPath '.tmp').Path
$python=(Resolve-Path -LiteralPath '../RSTV4/.venv/Scripts/python.exe').Path
$backend=(Resolve-Path -LiteralPath '../RSTV4').Path
$front=(Resolve-Path -LiteralPath '../writing-studio').Path
if(!($listeners|Where-Object LocalPort -eq 8885)){
 $process=Start-Process -FilePath $python -ArgumentList @('-u',(Join-Path $logs 'scholar-overview-server.py'),'--root',$cat.root,'--port','8885') -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'scholar-experiment-controls-catalog-v1.log') -RedirectStandardError (Join-Path $logs 'scholar-experiment-controls-catalog-v1-error.log')
 $cat.catalog_process=$process.Id
}
if(!($listeners|Where-Object LocalPort -eq 8874)){
 $process=Start-Process -FilePath $python -ArgumentList @('-u',(Join-Path $logs 'scholar-ui-fixes-services.py'),'studio') -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'scholar-experiment-controls-studio-v1.log') -RedirectStandardError (Join-Path $logs 'scholar-experiment-controls-studio-v1-error.log')
 $stu.owned_processes.studio=$process.Id
}
if(!($listeners|Where-Object LocalPort -eq 3000)){
 $node=(Get-Command node.exe).Source
 $process=Start-Process -FilePath $node -ArgumentList @((Join-Path $front 'node_modules/vinext/dist/cli.js'),'start','--host','127.0.0.1','--port','3000') -WorkingDirectory $front -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'scholar-experiment-controls-frontend-v1.log') -RedirectStandardError (Join-Path $logs 'scholar-experiment-controls-frontend-v1-error.log')
 $stu.owned_processes.frontend=$process.Id
}
[System.IO.File]::WriteAllText((Join-Path $logs 'scholar-overview-services.json'),($cat|ConvertTo-Json -Depth 20),[System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText((Join-Path $logs 'scholar-ui-fixes-services.json'),($stu|ConvertTo-Json -Depth 20),[System.Text.UTF8Encoding]::new($false))
$proof|ConvertTo-Json -Depth 10
'''
observed = subprocess.run(['powershell.exe', '-NoProfile', '-Command', guard], cwd=repo,
                          capture_output=True, text=True, check=True)
with (repo / '.tmp/scholar-experiment-controls-preview-authority-v1.json').open('x', encoding='utf-8') as h:
    h.write(observed.stdout)
deadline = time.monotonic() + 30
for url in ['http://127.0.0.1:8885/api/catalog/research-overview',
            'http://127.0.0.1:8874/api/manuscripts', 'http://127.0.0.1:3000/']:
    while True:
        try:
            response = httpx.get(url, timeout=2)
            assert response.status_code == 200, (url, response.status_code)
            break
        except (httpx.HTTPError, AssertionError):
            if time.monotonic() > deadline:
                raise
            time.sleep(.2)
assert sha(db.read_bytes()) == baseline['database_sha256']
print('PASS_OWNED_PREVIEW_RESTORE_DATABASE_BYTES_UNCHANGED')
