"""Reload only the verified isolated acceptance services; preserve all old records."""
import ast
import json
import sqlite3
import subprocess
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
catalog_path = repo / '.tmp/scholar-overview-services.json'
studio_path = repo / '.tmp/scholar-ui-fixes-services.json'
catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
root = Path(catalog['root']).resolve()
assert root.name.startswith('scholar-ui-fixes-2026-10-03-')
with sqlite3.connect(f'{(root / "data/catalog.db").as_uri()}?mode=ro', uri=True) as conn:
    assert conn.execute("SELECT COUNT(*) FROM research_discussion_jobs WHERE status IN ('QUEUED','RUNNING')").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM studio_jobs WHERE status IN ('QUEUED','RUNNING')").fetchone()[0] == 0
tree = ast.parse((repo / '.tmp/scholar-overview-native-v1.py').read_text(encoding='utf-8'))
guard = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'process_guard' for target in node.targets))
for path in [catalog_path, studio_path]:
    with (repo / '.tmp' / f'scholar-studio-shared-prior-{path.name}').open('xb') as handle:
        handle.write(path.read_bytes())
script = guard + '\n' + (repo / '.tmp/scholar-current-preview-proof.ps1').read_text(encoding='utf-8') + r'''
$ErrorActionPreference = 'Stop'
$catalogReceipt = Get-Content -LiteralPath '.tmp/scholar-overview-services.json' -Raw | ConvertFrom-Json
$studioReceipt = Get-Content -LiteralPath '.tmp/scholar-ui-fixes-services.json' -Raw | ConvertFrom-Json
$processes = @(Get-CimInstance Win32_Process)
$owned = [System.Collections.Generic.List[int]]::new()
foreach($rootId in @($catalogReceipt.catalog_process, $studioReceipt.owned_processes.studio, $studioReceipt.owned_processes.frontend)) { $owned.Add([int]$rootId) }
do { $changed = $false; foreach($item in $processes) { if($owned.Contains([int]$item.ParentProcessId) -and !$owned.Contains([int]$item.ProcessId)) { $owned.Add([int]$item.ProcessId); $changed = $true } } } while($changed)
$logs = (Resolve-Path -LiteralPath '.tmp').Path
foreach($name in @('catalog', 'studio', 'frontend')) {
    foreach($suffix in @('.log', '-error.log')) {
        if(Test-Path -LiteralPath (Join-Path $logs "scholar-studio-shared-$name-v1$suffix")) { throw 'Preserve the exclusive service logs.' }
    }
}
foreach($processId in ($owned | Sort-Object -Descending)) { if(Get-Process -Id $processId -ErrorAction SilentlyContinue) { Stop-Process -Id $processId -ErrorAction Stop } }
$python = (Resolve-Path -LiteralPath '../RSTV4/.venv/Scripts/python.exe').Path
$backend = (Resolve-Path -LiteralPath '../RSTV4').Path
$frontend = (Resolve-Path -LiteralPath '../writing-studio').Path
$rootPath = (Resolve-Path -LiteralPath $catalogReceipt.root).Path
$catalogHelper = (Resolve-Path -LiteralPath '.tmp/scholar-overview-server.py').Path
$studioHelper = (Resolve-Path -LiteralPath '.tmp/scholar-ui-fixes-services.py').Path
$nodePath = (Get-Command node).Source
$catalogProcess = Start-Process -FilePath $python -ArgumentList @('-u', $catalogHelper, '--root', $rootPath, '--port', '8885') -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'scholar-studio-shared-catalog-v1.log') -RedirectStandardError (Join-Path $logs 'scholar-studio-shared-catalog-v1-error.log')
$studioProcess = Start-Process -FilePath $python -ArgumentList @('-u', $studioHelper, 'studio') -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'scholar-studio-shared-studio-v1.log') -RedirectStandardError (Join-Path $logs 'scholar-studio-shared-studio-v1-error.log')
$frontendProcess = Start-Process -FilePath $nodePath -ArgumentList @((Join-Path $frontend 'node_modules/vinext/dist/cli.js'), 'start', '--port', '3000') -WorkingDirectory $frontend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'scholar-studio-shared-frontend-v1.log') -RedirectStandardError (Join-Path $logs 'scholar-studio-shared-frontend-v1-error.log')
$catalogReceipt.catalog_process = $catalogProcess.Id
$catalogReceipt.catalog_mode = 'shared_studio_fixed_conversation_preview'
$studioReceipt.owned_processes.studio = $studioProcess.Id
$studioReceipt.owned_processes.frontend = $frontendProcess.Id
$studioReceipt.frontend_mode = 'production_build_shared_studio_preview'
[System.IO.File]::WriteAllText((Join-Path $logs 'scholar-overview-services.json'), ($catalogReceipt | ConvertTo-Json -Depth 20), [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText((Join-Path $logs 'scholar-ui-fixes-services.json'), ($studioReceipt | ConvertTo-Json -Depth 20), [System.Text.UTF8Encoding]::new($false))
Write-Output "Owned isolated services loaded: Catalog $($catalogProcess.Id), Studio $($studioProcess.Id), frontend $($frontendProcess.Id)."
'''
subprocess.run(['powershell', '-NoProfile', '-Command', script], cwd=repo, check=True)
