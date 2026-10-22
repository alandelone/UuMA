param(
    [string]$PythonExe = (Get-Command python).Source,
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$DataDir = "$env:LOCALAPPDATA\UuMA",
    [int]$Port = 8765
)

if ($env:UUMA_CONTROL_URL -or $env:UUMA_REQUIRE_REMOTE_CONTROL -eq '1') {
    throw 'Control state is remote. Use the configured SSH tunnel instead of starting another local control API.'
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:UUMA_DATA_DIR = $DataDir
$env:UUMA_PORT = "$Port"
& $PythonExe -m uuma.api
