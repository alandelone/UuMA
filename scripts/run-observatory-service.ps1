# Resilience wrapper for UuMA All-in-One Observatory Service
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [int]$Port = 8790,
    [string]$HostAddress = "127.0.0.1"
)

$ErrorActionPreference = "Continue"

Set-Location $ProjectRoot
$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

$codexDir = "$env:LOCALAPPDATA\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\UuMA"
if (Test-Path $codexDir) {
    $env:UUMA_KNOWLEDGE_DATA_DIR = $codexDir
}

$logDir = "$env:LOCALAPPDATA\UuMA\logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$logFile = Join-Path $logDir "observatory-service.log"
$stopSignal = Join-Path $logDir ".stop_observatory"

if (Test-Path $stopSignal) {
    Remove-Item -Path $stopSignal -Force -ErrorAction SilentlyContinue
}

function Log-Message([string]$msg) {
    $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $line = "[$ts] $msg"
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Host $line
}

Log-Message "Observatory watchdog supervisor starting on port $Port..."

while ($true) {
    if (Test-Path $stopSignal) {
        Log-Message "Stop signal detected. Exiting watchdog supervisor."
        Remove-Item -Path $stopSignal -Force -ErrorAction SilentlyContinue
        break
    }

    # Ensure port is not blocked by a rogue process
    $occupied = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($occupied) {
        $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($occupied.OwningProcess)" -ErrorAction SilentlyContinue
        if ($owner -and $owner.CommandLine -match '(?i)uuma\.observatory') {
            Log-Message "Observatory is already actively listening on port $Port (PID $($occupied.OwningProcess)). Monitoring..."
            Start-Sleep -Seconds 10
            continue
        }
    }

    Log-Message "Launching python -m uuma.observatory..."
    $process = Start-Process -FilePath $python `
        -ArgumentList "-m", "uuma.observatory", "--host", $HostAddress, "--port", $Port `
        -WorkingDirectory $ProjectRoot `
        -PassThru `
        -NoNewWindow `
        -RedirectStandardOutput (Join-Path $logDir "observatory.stdout.log") `
        -RedirectStandardError (Join-Path $logDir "observatory.stderr.log")

    if ($process) {
        Log-Message "Observatory process started with PID $($process.Id)."
        $process.WaitForExit()
        Log-Message "Observatory process $($process.Id) exited with code $($process.ExitCode)."
    } else {
        Log-Message "Failed to start process."
    }

    if (Test-Path $stopSignal) {
        Log-Message "Stop signal received after exit. Stopping supervisor."
        break
    }

    Log-Message "Restarting Observatory in 3 seconds..."
    Start-Sleep -Seconds 3
}
