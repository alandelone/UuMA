param(
    [string]$PythonExe = (Get-Command python).Source,
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$DataDir = "$env:LOCALAPPDATA\UuMA",
    [int]$Port = 8766
)

$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:UUMA_DATA_DIR = $DataDir
$env:UUMA_PORT = "$Port"
& $PythonExe -m uuma.api
