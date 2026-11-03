# Native fixed-release admission tests. Only the explicitly supplied fixture root is written.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Python,
    [Parameter(Mandatory = $true)][string]$FixtureRoot
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$resolver = Join-Path $repo 'scripts/resolve-scholar-catalog-runtime.ps1'
if (Test-Path -LiteralPath $FixtureRoot) { throw 'Use a new fixture root; preserve previous results.' }
$null = New-Item -ItemType Directory -Path $FixtureRoot
$FixtureRoot = (Get-Item -LiteralPath $FixtureRoot).FullName
$utf8 = [Text.UTF8Encoding]::new($false)
$legacyName = ([string][char]0x6587) + ([string][char]0x732e) + 'POOL'
$runtimeSource = @'
import argparse, json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root');p.add_argument('--engine-root');a=p.parse_args()
root=Path(a.root); mode_path=root/'admission-mode.txt';mode=mode_path.read_text() if mode_path.exists() else 'ok'
with (root/'admission-calls.txt').open('a') as stream:stream.write('admission\n')
if mode=='exit-failure':raise SystemExit(7)
print(json.dumps({'owner_root':str(root) if mode!='wrong-owner' else str(root/'wrong'),
 'engine_root':a.engine_root if mode!='wrong-engine' else str(root/'wrong'),
 'package_sha256':'a'*64 if mode!='wrong-package' else 'b'*64,
 'schema_version':20 if mode!='wrong-schema' else 14,
 'read_only':mode!='writable','migration_performed':mode=='migrated'}))
'@
function Fixture-Digest([string]$Path) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($algorithm.ComputeHash([IO.File]::ReadAllBytes($Path))).Replace('-', '').ToLowerInvariant() }
    finally { $algorithm.Dispose() }
}
function Assert-True([bool]$Value, [string]$Message) { if (-not $Value) { throw $Message } }
$runtimeProbe = "import hashlib, importlib.metadata as m, json, sys; from pathlib import Path; print(json.dumps({'python':sys.version.split()[0],'pip':m.version('pip'),'base_sha':hashlib.sha256(Path(sys._base_executable).read_bytes()).hexdigest()}))"
$fixtureRuntime = (& $Python -c $runtimeProbe) | ConvertFrom-Json
$fixturePythonDigest = Fixture-Digest $Python
$fixtureConfigurationDigest = Fixture-Digest (Join-Path (Split-Path -Parent (Split-Path -Parent $Python)) 'pyvenv.cfg')
function New-Case([string]$Name, [switch]$NoDatabase) {
    $caseRoot = Join-Path $FixtureRoot $Name
    $engine = Join-Path $caseRoot 'fixed engine'
    $owner = Join-Path $caseRoot 'catalog owner'
    $null = New-Item -ItemType Directory -Path (Join-Path $engine 'src/rstv4') -Force
    $null = New-Item -ItemType Directory -Path (Join-Path $engine 'scripts') -Force
    $null = New-Item -ItemType Directory -Path (Join-Path $engine "$legacyName/paperpool/workers") -Force
    $null = New-Item -ItemType Directory -Path (Join-Path $owner 'data') -Force
    if (-not $NoDatabase) { [IO.File]::WriteAllText((Join-Path $owner 'data/catalog.db'), 'UNCHANGED SOFTWARE FIXTURE', $utf8) }
    $source = @{}
    foreach ($relative in @('src/rstv4/__init__.py','src/rstv4/catalog_web.py','src/rstv4/catalog_mcp.py',
        'src/rstv4/catalog_reading_worker.py','src/rstv4/catalog_runtime.py','scripts/mineru_bridge.py')) {
        $text = if ($relative -eq 'src/rstv4/catalog_runtime.py') { $runtimeSource } else { '# Software fixture; never serves or invokes a model.' }
        $path = Join-Path $engine $relative
        [IO.File]::WriteAllText($path, $text, $utf8)
        $source[$relative] = (Fixture-Digest $path)
    }
    $legacy = @{}
    foreach ($name in @('pdf_parser_worker.py','content_refiner_worker.py')) {
        $relative = "$legacyName/paperpool/workers/$name"
        $path = Join-Path $engine $relative
        [IO.File]::WriteAllText($path, '# Software fixture; no parser execution.', $utf8)
        $legacy[$relative] = (Fixture-Digest $path)
    }
    $manifest = [ordered]@{ schema_version = 1; component = 'scholar-catalog'; data_root = $owner;
        engine_root = $engine; parser_engine_root = $engine; resource_root = $owner;
        python = $Python; mineru_python = $Python; catalog_schema_version = 20;
        package_sha256 = ('a' * 64); python_version = $fixtureRuntime.python; python_sha256 = $fixturePythonDigest;
        runtime_configuration_sha256 = $fixtureConfigurationDigest; base_python_sha256 = $fixtureRuntime.base_sha;
        dependency_versions = @{ pip = $fixtureRuntime.pip }; source_sha256 = $source; legacy_sha256 = $legacy }
    return @{ Root = $caseRoot; Owner = $owner; Engine = $engine;
        Manifest = $manifest; Path = (Join-Path $caseRoot 'active.json') }
}
function Write-Manifest($Case) {
    [IO.File]::WriteAllText($Case.Path, ($Case.Manifest | ConvertTo-Json -Depth 8), $utf8)
}
$script:Results = @()
function Check-Rejected($Case, [string]$Expected, [bool]$BeforeAdmission = $true) {
    Write-Manifest $Case
    $rejected = $false
    try { $null = & $resolver -ManifestPath $Case.Path -ExpectedDataRoot $Case.Owner -ProjectRoot $repo }
    catch {
        if ($_.Exception.Message -notlike "*$Expected*") { throw }
        $rejected = $true
    }
    Assert-True $rejected 'Expected exact fixed-release refusal.'
    if ($BeforeAdmission) {
        Assert-True (-not (Test-Path -LiteralPath (Join-Path $Case.Owner 'admission-calls.txt'))) 'Invalid manifest reached its child runtime.'
    }
    $database = Join-Path $Case.Owner 'data/catalog.db'
    if (Test-Path -LiteralPath $database) {
        Assert-True ((Get-Content -LiteralPath $database -Raw) -eq 'UNCHANGED SOFTWARE FIXTURE') 'Admission modified its existing owner database.'
    }
    $script:Results += [pscustomobject]@{ name = (Split-Path -Leaf $Case.Root); rejected = $true; before_admission = $BeforeAdmission }
}
$good = New-Case 'valid release with spaces'
Write-Manifest $good
$resolved = (& $resolver -ManifestPath $good.Path -ExpectedDataRoot $good.Owner -ProjectRoot $repo) | ConvertFrom-Json
Assert-True ($resolved.kind -eq 'FIXED_RELEASE' -and $resolved.service_started -eq $false) 'Valid release must resolve without launching a service.'
Assert-True ($resolved.data_root -eq $good.Owner -and $resolved.engine_root -eq $good.Engine) 'The exact declared owner and engine must be retained.'
Assert-True ((Get-Content -LiteralPath (Join-Path $good.Owner 'data/catalog.db') -Raw) -eq 'UNCHANGED SOFTWARE FIXTURE') 'Valid admission changed its database.'
$script:Results += [pscustomobject]@{ name = 'valid release with spaces'; resolved = $true; service_started = $false }
$case = New-Case 'source digest changed'
[IO.File]::AppendAllText((Join-Path $case.Engine 'src/rstv4/catalog_web.py'), '# changed', $utf8)
Check-Rejected $case 'differs from its verified digest'
$case = New-Case 'extra unpinned source'
[IO.File]::WriteAllText((Join-Path $case.Engine 'src/rstv4/unexpected.py'), '# unexpected', $utf8)
Check-Rejected $case 'unpinned source file'
$case = New-Case 'path traversal'
$case.Manifest.source_sha256['../outside.py'] = 'a' * 64
Check-Rejected $case 'leaves its fixed engine directory'
$case = New-Case 'missing required parser'
$case.Manifest.legacy_sha256.Remove("$legacyName/paperpool/workers/pdf_parser_worker.py")
Check-Rejected $case 'required Catalog or parser source is not pinned'
$case = New-Case 'wrong resource owner'
$case.Manifest.resource_root = $case.Engine
Check-Rejected $case 'explicit Catalog data and resource owner'
$case = New-Case 'missing database' -NoDatabase
Check-Rejected $case 'existing Catalog database is missing'
foreach ($mode in @('wrong-owner','wrong-engine','wrong-package','wrong-schema','writable','migrated')) {
    $case = New-Case $mode
    [IO.File]::WriteAllText((Join-Path $case.Owner 'admission-mode.txt'), $mode, $utf8)
    Check-Rejected $case 'actual Catalog admission differs' $false
}
$case = New-Case 'child admission failure'
[IO.File]::WriteAllText((Join-Path $case.Owner 'admission-mode.txt'), 'exit-failure', $utf8)
Check-Rejected $case 'owner admission failed' $false
foreach ($name in @('python_sha256','runtime_configuration_sha256')) {
    $case = New-Case ('changed '+$name)
    $case.Manifest[$name] = '0' * 64
    Check-Rejected $case 'Python executable or runtime configuration changed'
}
$case = New-Case 'changed actual Python version'
$case.Manifest.python_version = '9.9.9'
Check-Rejected $case 'actual Python interpreter differs' $false
$case = New-Case 'changed base interpreter'
$case.Manifest.base_python_sha256 = '0' * 64
Check-Rejected $case 'actual Python interpreter differs' $false
$case = New-Case 'changed dependency version'
$case.Manifest.dependency_versions['pip'] = '0.0.0'
Check-Rejected $case 'runtime dependency differs' $false
Assert-True ($script:Results.Count -eq 19) 'All nineteen native admission cases must run.'
[ordered]@{ passed = $script:Results.Count; fixture_root = $FixtureRoot; cases = $script:Results;
    real_services_started = 0; tasks_changed = 0; real_catalog_modified = $false } | ConvertTo-Json -Depth 8
