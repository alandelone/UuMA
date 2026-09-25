param(
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [Parameter(Mandatory = $true)][string]$DataDir,
    [string]$ServiceTaskName = 'UuMA ChatGPT Bridge',
    [int]$Port = 8787
)

$ErrorActionPreference = 'Stop'

function Test-BridgeHealth {
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 2
        return ($health.service -eq 'uuma-chatgpt-bridge' -and $health.worker_healthy)
    }
    catch { return $false }
}

if (-not (Test-BridgeHealth)) {
    Start-ScheduledTask -TaskName $ServiceTaskName
    $deadline = (Get-Date).AddSeconds(30)
    while (-not (Test-BridgeHealth)) {
        if ((Get-Date) -ge $deadline) {
            throw 'ChatGPT Bridge did not become ready within 30 seconds.'
        }
        Start-Sleep -Milliseconds 500
    }
}

Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot 'src'
& $PythonExe -m uuma.chatgpt_cli --data-dir $DataDir --port $Port dashboard
if ($LASTEXITCODE -ne 0) { throw 'Unable to open the authorized dashboard.' }
