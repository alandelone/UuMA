# Resolve and validate an existing fixed Catalog release without starting services.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ManifestPath,
    [Parameter(Mandatory = $true)][string]$ExpectedDataRoot,
    [Parameter(Mandatory = $true)][string]$ProjectRoot
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
function ExistingDirectory([string]$Path) {
    $item = Get-Item -LiteralPath $Path
    if (-not $item.PSIsContainer) { throw 'A release directory is missing.' }
    return $item.FullName.TrimEnd([IO.Path]::DirectorySeparatorChar)
}
function ExistingFile([string]$Path) {
    $item = Get-Item -LiteralPath $Path
    if ($item.PSIsContainer) { throw 'A release executable or manifest is missing.' }
    return $item.FullName
}
function Get-ReleaseFileDigest([string]$Path) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}
$ManifestPath = ExistingFile $ManifestPath
$manifestDigest = (Get-ReleaseFileDigest $ManifestPath)
$release = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($release.schema_version -ne 1 -or $release.component -ne 'scholar-catalog') {
    throw 'Unsupported Scholar Catalog release manifest.'
}
$ExpectedDataRoot = ExistingDirectory $ExpectedDataRoot
$ProjectRoot = ExistingDirectory $ProjectRoot
$dataRoot = ExistingDirectory $release.data_root
$engineRoot = ExistingDirectory $release.engine_root
$parserRoot = ExistingDirectory $release.parser_engine_root
$resourceRoot = ExistingDirectory $release.resource_root
$python = ExistingFile $release.python
$mineruPython = ExistingFile $release.mineru_python
if ($dataRoot -ne $ExpectedDataRoot -or $resourceRoot -ne $ExpectedDataRoot) {
    throw 'The release must preserve the explicit Catalog data and resource owner.'
}
if ($engineRoot -eq $dataRoot -or $parserRoot -ne $engineRoot) {
    throw 'The Catalog and parser must use the same separate fixed engine release.'
}
if (-not (Test-Path -LiteralPath (Join-Path $dataRoot 'data/catalog.db') -PathType Leaf)) {
    throw 'The existing Catalog database is missing; no initialization is allowed.'
}
$hashes = @{}
foreach ($field in @('source_sha256', 'legacy_sha256')) {
    $mapping = $release.$field
    if ($null -eq $mapping -or @($mapping.PSObject.Properties).Count -eq 0) {
        throw 'Complete source and parser provenance manifests are required.'
    }
    foreach ($property in $mapping.PSObject.Properties) {
        $relative = $property.Name.Replace([char]92, [char]47)
        if ($hashes.ContainsKey($relative) -or $property.Value -notmatch '^[a-fA-F0-9]{64}$') {
            throw 'The release has a duplicate path or invalid source digest.'
        }
        $path = [IO.Path]::GetFullPath((Join-Path $engineRoot $relative))
        $prefix = $engineRoot + [IO.Path]::DirectorySeparatorChar
        if (-not $path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'A release manifest path leaves its fixed engine directory.'
        }
        $null = ExistingFile $path
        if ((Get-ReleaseFileDigest $path) -ne $property.Value) {
            throw 'The fixed release source differs from its verified digest.'
        }
        $hashes[$relative] = [string]$property.Value
    }
}
$legacyName = ([string][char]0x6587) + ([string][char]0x732e) + 'POOL'
$packageRoot = ExistingDirectory (Join-Path $engineRoot 'src/rstv4')
$legacyRoot = ExistingDirectory (Join-Path $engineRoot $legacyName)
$required = @('src/rstv4/catalog_web.py', 'src/rstv4/catalog_mcp.py',
    'src/rstv4/catalog_runtime.py', 'src/rstv4/catalog_reading_worker.py', 'scripts/mineru_bridge.py',
    "$legacyName/paperpool/workers/pdf_parser_worker.py", "$legacyName/paperpool/workers/content_refiner_worker.py")
foreach ($relative in $required) {
    if (-not $hashes.ContainsKey($relative)) { throw 'A required Catalog or parser source is not pinned.' }
}
foreach ($directory in @($packageRoot, $legacyRoot)) {
    foreach ($item in (Get-ChildItem -LiteralPath $directory -Recurse -File)) {
        if ($item.FullName -match '[\/]__pycache__[\/]' -or $item.Extension -in @('.pyc', '.pyo')) { continue }
        # The legacy manifest pins executable Python sources, not mutable caches or assets.
        if ($directory -eq $legacyRoot -and $item.Extension -ne '.py') { continue }
        $relative = $item.FullName.Substring($engineRoot.Length + 1).Replace([char]92, [char]47)
        if (-not $hashes.ContainsKey($relative)) { throw 'The fixed engine contains an unpinned source file.' }
    }
}
if ($release.package_sha256 -notmatch '^[a-fA-F0-9]{64}$' -or $release.catalog_schema_version -lt 1) {
    throw 'The release needs its actual package digest and Catalog schema version.'
}
foreach ($name in @('python_sha256','runtime_configuration_sha256','base_python_sha256')) {
    if ($release.$name -notmatch '^[a-fA-F0-9]{64}$') { throw 'Pinned Python runtime digests are required.' }
}
$runtimeRoot = Split-Path -Parent (Split-Path -Parent $python)
$runtimeConfiguration = ExistingFile (Join-Path $runtimeRoot 'pyvenv.cfg')
if ((Get-ReleaseFileDigest $python) -ne $release.python_sha256 -or
    (Get-ReleaseFileDigest $runtimeConfiguration) -ne $release.runtime_configuration_sha256) {
    throw 'The Python executable or runtime configuration changed.'
}
if ($release.python_version -notmatch '^\d+\.\d+\.\d+$' -or $null -eq $release.dependency_versions -or
    @($release.dependency_versions.PSObject.Properties).Count -eq 0) {
    throw 'Pinned Python and dependency versions are required.'
}
foreach ($property in $release.dependency_versions.PSObject.Properties) {
    if ($property.Name -notmatch '^[A-Za-z0-9_.-]+$' -or $property.Value -isnot [string] -or -not $property.Value) {
        throw 'Invalid pinned dependency identity.'
    }
}
$env:PYTHONPATH = (Join-Path $engineRoot 'src') + ';' + (Join-Path $ProjectRoot 'src')
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$env:RSTV4_ROOT = $dataRoot
$env:RSTV4_ENGINE_ROOT = $parserRoot
$env:RSTV4_RESOURCE_ROOT = $resourceRoot
$env:RSTV4_MINERU_PYTHON = $mineruPython
$admissionText = & $python -m rstv4.catalog_runtime --root $dataRoot --engine-root $engineRoot
if ($LASTEXITCODE -ne 0) { throw 'The fixed Catalog owner admission failed; no service was started.' }
$admission = ($admissionText -join [Environment]::NewLine) | ConvertFrom-Json
if ($admission.owner_root -ne $dataRoot -or $admission.engine_root -ne $engineRoot -or
    $admission.package_sha256 -ne $release.package_sha256 -or
    $admission.schema_version -ne $release.catalog_schema_version -or
    $admission.read_only -ne $true -or $admission.migration_performed -ne $false) {
    throw 'The actual Catalog admission differs from its declared owner, source or schema.'
}
$versionProbe = @'
import hashlib, importlib.metadata as m, json, sys
from pathlib import Path
release=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
print(json.dumps({'python':sys.version.split()[0], 'prefix':sys.prefix,
 'base_python_sha256':hashlib.sha256(Path(sys._base_executable).read_bytes()).hexdigest(),
 'dependencies':{name:m.version(name) for name in release['dependency_versions']}}))
'@
$versionText = & $python -c $versionProbe $ManifestPath
if ($LASTEXITCODE -ne 0) { throw 'The pinned runtime dependency probe failed; no service was started.' }
$versions = ($versionText -join [Environment]::NewLine) | ConvertFrom-Json
if ($versions.python -ne $release.python_version -or $versions.prefix -ne $runtimeRoot -or
    $versions.base_python_sha256 -ne $release.base_python_sha256) {
    throw 'The actual Python interpreter differs from its pinned runtime.'
}
foreach ($property in $release.dependency_versions.PSObject.Properties) {
    if ($versions.dependencies.PSObject.Properties[$property.Name].Value -ne $property.Value) {
        throw 'An actual runtime dependency differs from its pinned version.'
    }
}
if ((Get-ReleaseFileDigest $ManifestPath) -ne $manifestDigest) {
    throw 'The active release manifest changed during admission.'
}
[ordered]@{
    kind = 'FIXED_RELEASE'; manifest = $ManifestPath; manifest_sha256 = $manifestDigest;
    data_root = $dataRoot; engine_root = $engineRoot; parser_engine_root = $parserRoot;
    resource_root = $resourceRoot; python = $python; mineru_python = $mineruPython;
    package_sha256 = $admission.package_sha256; manifest_file_count = $hashes.Count;
    admission = $admission; runtime = $versions; service_started = $false
} | ConvertTo-Json -Depth 8 -Compress
