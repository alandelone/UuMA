# Idempotent, logged entry point for Windows login tasks and the service watchdog.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Scholar", "LiveAgent")]
    [string]$Service,
    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"
if (-not $ProjectRoot) { $ProjectRoot = Split-Path -Parent $PSScriptRoot }
$workspace = Split-Path -Parent $ProjectRoot
# An explicit workspace path avoids packaged-app LocalAppData redirection.
$logDir = Join-Path $ProjectRoot ".uuma-local\windows-service-logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logFile = Join-Path $logDir "$Service-service.log"
$mutex = [Threading.Mutex]::new($false, "Local\UuMA.WindowsAgentService.$Service")
$locked = $false

function Write-ServiceLog([string]$Message) {
    Add-Content -LiteralPath $logFile -Encoding UTF8 -Value "$(Get-Date -Format o) $Message"
}

function Get-Listener([int]$Port) {
    Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

function Test-LiveReady {
    if (-not (Get-Listener 8765) -or -not (Get-Listener 5173)) { return $false }
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:5173/live/" -TimeoutSec 4
        return $response.StatusCode -eq 200
    } catch { return $false }
}

function Stop-OwnedListener([int]$Port, [string]$ExpectedScript) {
    $listener = Get-Listener $Port
    if (-not $listener) { return }
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    if (-not $owner -or $owner.CommandLine -notmatch [regex]::Escape($ExpectedScript)) {
        throw "Refusing recovery: port $Port belongs to an unexpected process."
    }
    Write-ServiceLog "Stopping verified owned listener on port $Port, PID $($owner.ProcessId)."
    Stop-Process -Id $owner.ProcessId -ErrorAction Stop
}

try {
    try { $locked = $mutex.WaitOne(0) }
    catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { Write-ServiceLog "Another launcher owns the service lock; skipping."; exit 0 }
    $env:PYTHONUTF8 = "1"

    if ($Service -eq "Scholar") {
        $root = Join-Path $workspace "RSTV4"
        $existing = Get-Listener 8875
        if ($existing) {
            $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($existing.OwningProcess)"
            if ($owner.CommandLine -notmatch 'rstv4\.catalog_web') {
                throw "Port 8875 belongs to an unexpected process."
            }
            Write-ServiceLog "Scholar is already listening; skipping."
            exit 0
        }
        $env:PYTHONPATH = "$(Join-Path $root 'src');$(Join-Path $ProjectRoot 'src')"
        $env:RSTV4_ROOT = $root
        $env:RSTV4_CATALOG_HOST = "0.0.0.0"
        $env:RSTV4_CATALOG_PORT = "8875"
        $env:RSTV4_ALLOWED_HOSTS = "*"
        $executable = Join-Path $root ".venv\Scripts\python.exe"
        $arguments = @("-u", "-m", "rstv4.catalog_web")
    } else {
        $root = Join-Path $workspace "livechat_agent"
        if (Test-LiveReady) { Write-ServiceLog "Live Agent UI and gateway are ready; skipping."; exit 0 }
        $statePath = Join-Path $root ".runtime-data\deployment\state.json"
        $distribution = "Debian"
        if (Test-Path -LiteralPath $statePath) {
            $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
            if ($state.profile -and $state.profile -ne "gemini") {
                throw "Automatic recovery preserves the Gemini profile; refusing to replace a Local deployment."
            }
            if ($state.distribution) { $distribution = [string]$state.distribution }
        }
        # A partial stack must be stopped by verified identity, never by a saved Windows PID.
        $linuxPidPath = Join-Path $root ".runtime-data\deployment\gateway-linux.pid"
        if (Test-Path -LiteralPath $linuxPidPath) {
            $linuxPid = (Get-Content -LiteralPath $linuxPidPath -Raw).Trim()
            if ($linuxPid -notmatch '^\d+$') { throw "Invalid gateway PID record." }
            $linuxRoot = "/mnt/" + $root.Substring(0, 1).ToLowerInvariant() + $root.Substring(2).Replace('\', '/')
            $verifyAndStop = @'
import os, pathlib, signal, sys
pid = int(sys.argv[1])
proc = pathlib.Path('/proc') / str(pid)
if proc.exists():
    args = (proc / 'cmdline').read_bytes().split(bytes([0]))
    cwd = (proc / 'cwd').resolve()
    expected = pathlib.Path(sys.argv[2]).resolve()
    if cwd != expected or len(args) < 2 or args[1] != b'server.py' or not args[0].endswith(b'/opt/livechat-agent/.venv/bin/python'):
        raise SystemExit('Refusing to stop a reused or unexpected Linux PID')
    os.kill(pid, signal.SIGTERM)
'@
            & wsl.exe -d $distribution -u liveagent -- /opt/livechat-agent/.venv/bin/python -c $verifyAndStop $linuxPid $linuxRoot
            if ($LASTEXITCODE -ne 0) { throw "Gateway process identity verification failed." }
        }
        Start-Sleep -Seconds 2
        if (Get-Listener 8765) { throw "Gateway port remains occupied; refusing an unverified shutdown." }
        Stop-OwnedListener 5173 (Join-Path $root "node_modules\vite\bin\vite.js")
        Stop-OwnedListener 8082 (Join-Path $workspace "unlimited_llmapi\live_broker.py")
        # The state daemon and Hermes dashboard can be shared: leave them running.
        if (Test-Path -LiteralPath $statePath) {
            Move-Item -LiteralPath $statePath -Destination "$statePath.before-recovery-$(Get-Date -Format yyyyMMddTHHmmssfff)"
        }
        $executable = "powershell.exe"
        $arguments = @("-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
            "`"$(Join-Path $root 'scripts\start-local.ps1')`"", "-Mode", "Gemini", "-Distribution", $distribution)
    }

    Write-ServiceLog "Launching $Service in $root."
    $child = Start-Process -FilePath $executable -ArgumentList $arguments -WorkingDirectory $root `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDir "$Service.stdout.log") `
        -RedirectStandardError (Join-Path $logDir "$Service.stderr.log")
    $null = $child.Handle
    $child.WaitForExit()
    $child.Refresh()
    $code = $child.ExitCode
    if ($null -eq $code) { throw "Child exit status unavailable; inspect service logs." }
    Write-ServiceLog "$Service child exited with code $code."
    if ($code -ne 0) { exit $code }
    if ($Service -eq "LiveAgent" -and -not (Test-LiveReady)) {
        throw "Live Agent launcher exited without a healthy UI and gateway."
    }
    exit 0
} catch {
    Write-ServiceLog "ERROR: $($_.Exception.Message)"
    Write-Error $_ -ErrorAction Continue
    exit 1
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
