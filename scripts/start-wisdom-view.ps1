param(
    [string]$PythonExe = (Join-Path (Split-Path -Parent $PSScriptRoot) ".venv\Scripts\python.exe"),
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$DataDir = "$env:LOCALAPPDATA\UuMA",
    [int]$Port = 8767
)

$ErrorActionPreference = "Stop"
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:UUMA_DATA_DIR = $DataDir
$env:UUMA_WISDOM_VIEW_PORT = "$Port"
$env:UUMA_WISDOM_VIEW_BASE_URL = "http://127.0.0.1:$Port"
$env:UUMA_WISDOM_VIEW_TOKEN = (Get-Content -LiteralPath (Join-Path $DataDir "wisdom-view-token") -Raw).Trim()
& $PythonExe -m uuma.wisdom_view
