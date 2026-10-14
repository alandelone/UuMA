import json
import os
import subprocess
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
os.environ.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
for name in ["studio", "frontend", "catalog"]:
    for suffix in ["", "-error"]:
        if (repo / f".tmp/scholar-fieldkg-{name}-v2{suffix}.log").exists():
            raise RuntimeError("Preserve existing service logs")
for name in ["scholar-ui-fixes-services", "scholar-overview-services"]:
    backup = repo / f".tmp/scholar-fieldkg-prior-{name}-v2.json"
    if backup.exists():
        raise RuntimeError("Preserve the exclusive prior receipt")
    backup.write_bytes((repo / f".tmp/{name}.json").read_bytes())
start = r'''
$ErrorActionPreference='Stop'
$studioReceipt=Get-Content -LiteralPath '.tmp/scholar-ui-fixes-services.json' -Raw | ConvertFrom-Json
$catalogReceipt=Get-Content -LiteralPath '.tmp/scholar-overview-services.json' -Raw | ConvertFrom-Json
$all=@(Get-CimInstance Win32_Process)
foreach($oldId in @($studioReceipt.owned_processes.studio,$studioReceipt.owned_processes.frontend,$catalogReceipt.catalog_process)) {
  if($all | Where-Object ProcessId -eq ([int]$oldId)) { throw 'A prior process ID still exists; leave it untouched.' }
}
if(@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -in 3000,8874,8885).Count) { throw 'A preview port is occupied; leave its owner untouched.' }
$rootPath=(Resolve-Path -LiteralPath $studioReceipt.root).Path
if($rootPath -ne (Resolve-Path -LiteralPath $catalogReceipt.root).Path -or (Split-Path $rootPath -Leaf) -notlike 'scholar-ui-fixes-2026-10-03-*') { throw 'Original isolated root differs.' }
if(!(Test-Path -LiteralPath (Join-Path $rootPath 'data/catalog.db'))) { throw 'Original isolated database is unavailable.' }
$logs=(Resolve-Path -LiteralPath '.tmp').Path
$python=(Resolve-Path -LiteralPath '../RSTV4/.venv/Scripts/python.exe').Path
$backend=(Resolve-Path -LiteralPath '../RSTV4').Path
$front=(Resolve-Path -LiteralPath '../writing-studio').Path
$studioHelper=(Resolve-Path -LiteralPath '.tmp/scholar-ui-fixes-services.py').Path
$catalogHelper=(Resolve-Path -LiteralPath '.tmp/scholar-overview-server.py').Path
$cli=Join-Path $front 'node_modules/vinext/dist/cli.js'
$env:PYTHONUTF8='1'
$env:NEXT_PUBLIC_RSTV4_API='http://127.0.0.1:8874/api'
$env:NEXT_PUBLIC_RSTV4_API_URL='http://127.0.0.1:8874/api'
$env:NEXT_PUBLIC_PAPER_CATALOG_URL='http://127.0.0.1:8885/'
$env:RAYON_NUM_THREADS='1'
$env:NODE_OPTIONS='--max-old-space-size=1024'
$newStudio=Start-Process -FilePath $python -ArgumentList @('-u',$studioHelper,'studio') -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'scholar-fieldkg-studio-v2.log') -RedirectStandardError (Join-Path $logs 'scholar-fieldkg-studio-v2-error.log')
$studioReceipt.owned_processes.studio=$newStudio.Id
[System.IO.File]::WriteAllText((Join-Path $logs 'scholar-ui-fixes-services.json'),($studioReceipt | ConvertTo-Json -Depth 20),[System.Text.UTF8Encoding]::new($false))
$newCatalog=Start-Process -FilePath $python -ArgumentList @('-u',$catalogHelper,'--root',$rootPath,'--port','8885') -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'scholar-fieldkg-catalog-v2.log') -RedirectStandardError (Join-Path $logs 'scholar-fieldkg-catalog-v2-error.log')
$newCatalogReceipt=@{root=$rootPath;catalog_process=$newCatalog.Id;catalog_port=8885;production_data_changed=$false;catalog_mode='fieldkg_workspace_preview'}
[System.IO.File]::WriteAllText((Join-Path $logs 'scholar-overview-services.json'),($newCatalogReceipt | ConvertTo-Json -Depth 20),[System.Text.UTF8Encoding]::new($false))
$newFront=Start-Process -FilePath 'node' -ArgumentList @($cli,'start','--hostname','127.0.0.1','--port','3000') -WorkingDirectory $front -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'scholar-fieldkg-frontend-v2.log') -RedirectStandardError (Join-Path $logs 'scholar-fieldkg-frontend-v2-error.log')
$studioReceipt.owned_processes.frontend=$newFront.Id
[System.IO.File]::WriteAllText((Join-Path $logs 'scholar-ui-fixes-services.json'),($studioReceipt | ConvertTo-Json -Depth 20),[System.Text.UTF8Encoding]::new($false))
Write-Output "Resumed original isolated root: Studio $($newStudio.Id), Catalog $($newCatalog.Id), frontend $($newFront.Id)."
'''
subprocess.run(["powershell", "-NoProfile", "-Command", start], cwd=repo, check=True)
print(json.dumps(json.loads((repo / ".tmp/scholar-ui-fixes-services.json").read_text(encoding="utf-8"))["owned_processes"]))
