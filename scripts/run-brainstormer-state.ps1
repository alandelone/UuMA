param([string]$DataDir = "$env:LOCALAPPDATA\UuMA")
$ErrorActionPreference = 'Stop'
$workspace = Split-Path $PSScriptRoot -Parent
$env:PYTHONPATH = Join-Path $workspace 'src'
$env:UUMA_DATA_DIR = $DataDir
$logDir = Join-Path $DataDir 'logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
# A single loopback writer is shared with Live. Do not start a competing writer.
if (Get-NetTCPConnection -LocalPort 8772 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8772 is already in use; verify the existing state daemon.'
}
$navigationEnvironment = Join-Path $workspace '.uuma-local\workstation-node-production-20261022\startup.json'
$navigationModule = 'uuma.state_daemon'
if (Test-Path -LiteralPath $navigationEnvironment) {
    $startup = Get-Content -LiteralPath $navigationEnvironment -Raw | ConvertFrom-Json
    $startup.services.navigation.environment.psobject.Properties | ForEach-Object {
        [Environment]::SetEnvironmentVariable($_.Name, [string]$_.Value, 'Process')
    }
    $navigationModule = 'uuma.navigation_proxy'
}
$child = Start-Process (Join-Path $workspace '.venv\Scripts\python.exe') `
    -ArgumentList '-m', $navigationModule -WorkingDirectory $workspace -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logDir 'brainstormer-state.stdout.log') `
    -RedirectStandardError (Join-Path $logDir 'brainstormer-state.stderr.log') -Wait -PassThru
exit $child.ExitCode
