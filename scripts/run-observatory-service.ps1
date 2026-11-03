# Resilience wrapper for UuMA All-in-One Observatory Service
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [int]$Port = 8790,
    [string]$HostAddress = "127.0.0.1"
)

$ErrorActionPreference = "Continue"

Set-Location $ProjectRoot
$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
# Login tasks do not inherit an editable package installation or this shell's path.
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:PYTHONUTF8 = "1"
if (-not $env:UUMA_HARDWARE_WORKSPACE_DIR) {
    $workspaceManifestPath = Join-Path $ProjectRoot 'deploy\forge-workspace.json'
    if (Test-Path -LiteralPath $workspaceManifestPath) {
        $workspaceManifest = Get-Content -LiteralPath $workspaceManifestPath -Raw | ConvertFrom-Json
        $env:UUMA_HARDWARE_WORKSPACE_DIR = $workspaceManifest.windows_path
    }
}

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

    # Ensure port is not blocked by a rogue or zombie process
    $occupied = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($occupied) {
        $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($occupied.OwningProcess)" -ErrorAction SilentlyContinue
        if ($owner -and $owner.CommandLine -match '(?i)uuma\.observatory') {
            Log-Message "Observatory is actively listening on port $Port (PID $($occupied.OwningProcess)). Monitoring..."
            $process = Get-Process -Id $occupied.OwningProcess -ErrorAction SilentlyContinue
        } else {
            Log-Message "Terminating foreign process $($occupied.OwningProcess) occupying port $Port..."
            Stop-Process -Id $occupied.OwningProcess -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 1
            $process = $null
        }
    } else {
        # Port is not listening. Terminate any zombie python processes previously running observatory
        Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match '(?i)uuma\.observatory' -and $_.ProcessId -ne $PID } | ForEach-Object {
            Log-Message "Terminating zombie observatory process $($_.ProcessId)..."
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
        $process = $null
    }

    if (-not $process) {
        Log-Message "Launching python -m uuma.observatory..."
        $process = Start-Process -FilePath $python `
            -ArgumentList "-m", "uuma.observatory", "--host", $HostAddress, "--port", $Port `
            -WorkingDirectory $ProjectRoot `
            -PassThru `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $logDir "observatory.stdout.log") `
            -RedirectStandardError (Join-Path $logDir "observatory.stderr.log")

        if ($process) {
            Log-Message "Observatory process started with PID $($process.Id)."
            Start-Sleep -Seconds 3
        } else {
            Log-Message "Failed to start process."
            Start-Sleep -Seconds 3
            continue
        }
    }

    # Active health monitoring loop
    $failCount = 0
    while (-not $process.HasExited) {
        Start-Sleep -Seconds 10
        if (Test-Path $stopSignal) { break }

        try {
            $check = Invoke-WebRequest -Uri "http://${HostAddress}:${Port}/" -Method HEAD -TimeoutSec 4 -UseBasicParsing -ErrorAction Stop
            $failCount = 0
        } catch {
            # HTTP 200, 401, 405 indicate the HTTP server is alive and responding
            if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
                $failCount = 0
            } else {
                $failCount++
                Log-Message "Observatory health check failed ($failCount/3): $($_.Exception.Message)"
                if ($failCount -ge 3) {
                    Log-Message "Observatory unresponsive for 3 consecutive checks (port $Port). Terminating PID $($process.Id)..."
                    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                    Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $process.Id -or ($_.CommandLine -match '(?i)uuma\.observatory' -and $_.ProcessId -ne $PID) } | ForEach-Object {
                        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
                    }
                    break
                }
            }
        }
    }

    if (-not $process.HasExited) {
        $process.WaitForExit(3000)
    }
    Log-Message "Observatory process $($process.Id) stopped."

    if (Test-Path $stopSignal) {
        Log-Message "Stop signal received after exit. Stopping supervisor."
        break
    }

    Log-Message "Restarting Observatory in 3 seconds..."
    Start-Sleep -Seconds 3
}
