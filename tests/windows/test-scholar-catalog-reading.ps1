# Native launcher contracts; all worker calls use an isolated software fixture.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Python,
    [Parameter(Mandatory = $true)][string]$FixtureRoot
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
# Reuse the complete release admission contract and its isolated fixture factory.
. (Join-Path $PSScriptRoot 'test-scholar-catalog-release.ps1') -Python $Python -FixtureRoot $FixtureRoot
$runner = Join-Path $repo 'scripts/run-scholar-catalog-reading.ps1'
$workerFixture = @'
import argparse,json,os,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root');p.add_argument('--slot');a=p.parse_args()
root=Path(a.root)
(root/'worker-call.json').write_text(json.dumps({'root':a.root,'slot':a.slot,'cwd':os.getcwd(),
 'engine':os.environ['RSTV4_ENGINE_ROOT'],'resource':os.environ['RSTV4_RESOURCE_ROOT']}))
code=root/'worker-exit.txt'
raise SystemExit(int(code.read_text()) if code.exists() else 0)
'@
function New-WorkerCase([string]$Name) {
    $case = New-Case $Name
    $relative = 'src/rstv4/catalog_reading_worker.py'
    [IO.File]::WriteAllText((Join-Path $case.Engine $relative), $workerFixture, $utf8)
    $case.Manifest.source_sha256[$relative] = Fixture-Digest (Join-Path $case.Engine $relative)
    Write-Manifest $case
    return $case
}
$case = New-WorkerCase 'reading check with spaces'
$checked = (& $runner -ManifestPath $case.Path -DataRoot $case.Owner -ProjectRoot $repo -CheckOnly) | ConvertFrom-Json
Assert-True (-not $checked.worker_started -and $checked.slot -eq '1') 'Check-only started a worker or changed its unique slot.'
Assert-True (-not (Test-Path -LiteralPath (Join-Path $case.Owner 'worker-call.json'))) 'Check-only invoked worker code.'
$results = @([pscustomobject]@{ name = 'read-only admission'; passed = $true })
foreach ($code in @(0, 7)) {
    $case = New-WorkerCase ('reading foreground exit ' + $code)
    [IO.File]::WriteAllText((Join-Path $case.Owner 'worker-exit.txt'), [string]$code, $utf8)
    & powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File $runner `
        -ManifestPath $case.Path -DataRoot $case.Owner -ProjectRoot $repo
    Assert-True ($LASTEXITCODE -eq $code) 'Foreground worker exit was not propagated to its supervisor.'
    $call = Get-Content -LiteralPath (Join-Path $case.Owner 'worker-call.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-True ($call.root -eq $case.Owner -and $call.cwd -eq $case.Owner -and $call.slot -eq '1') 'Worker lost owner, cwd or singleton slot.'
    Assert-True ($call.engine -eq $case.Engine -and $call.resource -eq $case.Owner) 'Worker lost fixed source or parser resources.'
    Assert-True ((Get-Content -LiteralPath (Join-Path $case.Owner 'data/catalog.db') -Raw) -eq 'UNCHANGED SOFTWARE FIXTURE') 'Launcher changed the owner database.'
    $results += [pscustomobject]@{ name = ('foreground exit ' + $code); passed = $true }
}
$case = New-WorkerCase 'reading changed source rejected'
[IO.File]::AppendAllText((Join-Path $case.Engine 'src/rstv4/catalog_reading_worker.py'), '# drift', $utf8)
$rejected = $false
try { $null = & $runner -ManifestPath $case.Path -DataRoot $case.Owner -ProjectRoot $repo -CheckOnly }
catch {
    if ($_.Exception.Message -notlike '*differs from its verified digest*') { throw }
    $rejected = $true
}
Assert-True ($rejected -and -not (Test-Path -LiteralPath (Join-Path $case.Owner 'worker-call.json'))) 'Invalid source reached the worker.'
$results += [pscustomobject]@{ name = 'changed source refusal'; passed = $true }
[ordered]@{ reading_launcher_cases = $results; real_model_calls = 0; real_services_started = 0;
    tasks_changed = 0; real_catalog_modified = $false } | ConvertTo-Json -Depth 8
