# Foreground entry point for the dedicated Catalog reading supervisor.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ManifestPath,
    [Parameter(Mandatory = $true)][string]$DataRoot,
    [string]$ProjectRoot = '',
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
if (-not $ProjectRoot) { $ProjectRoot = Split-Path -Parent $PSScriptRoot }
$resolver = Join-Path $PSScriptRoot 'resolve-scholar-catalog-runtime.ps1'
$resolvedText = & $resolver -ManifestPath $ManifestPath -ExpectedDataRoot $DataRoot -ProjectRoot $ProjectRoot
$runtime = ($resolvedText -join [Environment]::NewLine) | ConvertFrom-Json
if ($runtime.kind -ne 'FIXED_RELEASE' -or $runtime.admission.read_only -ne $true -or
    $runtime.admission.migration_performed -ne $false) {
    throw 'Catalog reading requires an admitted fixed release and existing upgraded owner.'
}
$digestAlgorithm = [Security.Cryptography.SHA256]::Create()
try {
    $manifestDigest = [BitConverter]::ToString(
        $digestAlgorithm.ComputeHash([IO.File]::ReadAllBytes($runtime.manifest))).Replace('-', '').ToLowerInvariant()
} finally { $digestAlgorithm.Dispose() }
if ($manifestDigest -ne $runtime.manifest_sha256) {
    throw 'The Catalog release changed after admission; no worker was started.'
}
# Content indexing is explicitly enabled by this fixed release; rollback disables it.
$settings = Get-Content -LiteralPath $runtime.manifest -Raw -Encoding UTF8 | ConvertFrom-Json
$contentIndexEnabled = $false
if ($settings.PSObject.Properties.Name -contains 'catalog_content_index_enabled') {
    if ($settings.catalog_content_index_enabled -isnot [bool]) {
        throw 'Catalog content indexing requires an explicit boolean release setting.'
    }
    $contentIndexEnabled = $settings.catalog_content_index_enabled
}
if ($CheckOnly) {
    [ordered]@{
        runtime = $runtime; module = 'rstv4.catalog_reading_worker'; slot = '1';
        automatic_window = '00:00-08:00 Asia/Kuala_Lumpur'; manual_priority = $true;
        content_index_enabled = $contentIndexEnabled;
        worker_started = $false
    } | ConvertTo-Json -Depth 10 -Compress
    return
}
$env:RSTV4_CATALOG_CONTENT_INDEX = if ($contentIndexEnabled) { '1' } else { '0' }
# The foreground child keeps Task Scheduler supervision attached to its real exit.
# The worker enforces the night window, manual priority, durable replay and owner lock.
Push-Location -LiteralPath $runtime.data_root
try {
    & $runtime.python -u -m rstv4.catalog_reading_worker --root $runtime.data_root --slot '1'
    $workerExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $workerExitCode
