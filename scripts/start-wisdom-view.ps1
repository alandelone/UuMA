param(
    [string]$PythonExe = (Join-Path (Split-Path -Parent $PSScriptRoot) ".venv\Scripts\python.exe"),
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$DataDir = "$env:LOCALAPPDATA\UuMA",
    [int]$Port = 8767
)

$ErrorActionPreference = "Stop"

# Resolve packaged-app LocalAppData redirection before configuring environment
$resolvedDataDir = (Resolve-Path -LiteralPath $DataDir).Path
$databaseFile = Get-Item -LiteralPath (Join-Path $resolvedDataDir "wisdom.db") -ErrorAction SilentlyContinue
if ($databaseFile) {
    $databaseTargets = @(@($databaseFile.Target) | Where-Object { $_ })
    if ($databaseTargets.Count -gt 0) {
        $resolvedDataDir = Split-Path -Parent ([IO.Path]::GetFullPath($databaseTargets[0]))
    }
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:UUMA_DATA_DIR = $resolvedDataDir
$env:UUMA_WISDOM_VIEW_PORT = "$Port"
$env:UUMA_WISDOM_VIEW_BASE_URL = "http://127.0.0.1:$Port"
$stdoutLog = Join-Path $resolvedDataDir "wisdom-view.log"
$stderrLog = Join-Path $resolvedDataDir "wisdom-view-err.log"

$proc = Start-Process -FilePath $PythonExe `
    -ArgumentList "-m", "uuma.wisdom_view" `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

$proc.WaitForExit()
