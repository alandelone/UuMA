param(
    [string]$DataDir = "$env:LOCALAPPDATA\UuMA"
)

$ErrorActionPreference = "Stop"
$runtimeDir = Join-Path $DataDir "phoenix-runtime"
$phoenixExe = Join-Path $runtimeDir "venv\Scripts\phoenix.exe"
$workingDir = Join-Path $runtimeDir "data"
$logDir = Join-Path $runtimeDir "logs"

if (-not (Test-Path -LiteralPath $phoenixExe)) {
    throw "Phoenix runtime is not installed at '$phoenixExe'. Run start-phoenix.ps1 once."
}

try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:6006/healthz" -TimeoutSec 2
    if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
        exit 0
    }
}
catch {
    # Expected when the service needs to be started.
}

New-Item -ItemType Directory -Path $workingDir, $logDir -Force | Out-Null
$env:PHOENIX_WORKING_DIR = $workingDir
$env:PHOENIX_ALLOW_EXTERNAL_RESOURCES = "false"
$env:PHOENIX_HOST = "127.0.0.1"
$env:PYTHONUTF8 = "1"

# Phoenix's Windows launcher expects a console during initialization. Start it in a hidden child
# process, then keep this scheduled-task supervisor alive for exactly the child's lifetime.
$process = Start-Process -FilePath $phoenixExe -ArgumentList "serve" -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logDir "phoenix-service.out.log") `
    -RedirectStandardError (Join-Path $logDir "phoenix-service.err.log") `
    -PassThru
$process.WaitForExit()
exit $process.ExitCode
