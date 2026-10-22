# Persistent, component-scoped host for Writing Studio. Does not restart Catalog/workers.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet("Api", "Web")][string]$Component,
    [string]$ProjectRoot = ""
)
$ErrorActionPreference = "Stop"
if (-not $ProjectRoot) { $ProjectRoot = Split-Path -Parent $PSScriptRoot }
$workspace = Split-Path -Parent $ProjectRoot
$studioRoot = Join-Path $workspace "writing-studio"
$rstRoot = Join-Path $workspace "RSTV4"
$logRoot = Join-Path $ProjectRoot ".uuma-local\windows-service-logs"
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$log = Join-Path $logRoot "WritingStudio-$Component.service.log"
$mutex = [Threading.Mutex]::new($false, "Local\UuMA.WritingStudio.$Component")
$locked = $false
function Write-StudioLog([string]$Message) {
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$(Get-Date -Format o) $Message"
}
try {
    try { $locked = $mutex.WaitOne(0) }
    catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { Write-StudioLog "Existing component supervisor owns the lock."; exit 0 }
    $env:PYTHONUTF8 = "1"
    $env:PYTHONPATH = "$(Join-Path $rstRoot 'src');$(Join-Path $ProjectRoot 'src')"
    $env:RSTV4_ROOT = $rstRoot
    $env:RSTV4_STUDIO_PORT = "8874"
    $env:RSTV4_API = "http://127.0.0.1:8874/api"
    if ($Component -eq "Api") {
        $port = 8874
        $executable = Join-Path $rstRoot ".venv\Scripts\python.exe"
        $childArguments = @("-u", "-m", "uvicorn", "rstv4.studio_api:create_app", "--factory",
            "--host", "127.0.0.1", "--port", "8874")
        $cwd = $rstRoot
    } else {
        $port = 3000
        $executable = (Get-Command node.exe -ErrorAction Stop).Source
        $cli = Join-Path $studioRoot "node_modules\vinext\dist\cli.js"
        if (-not (Test-Path -LiteralPath (Join-Path $studioRoot "dist\server\index.js"))) {
            throw "Writing Studio production build is missing. Run npm run build in $studioRoot."
        }
        $childArguments = @("`"$cli`"", "start", "--hostname", "127.0.0.1", "--port", "3000")
        $cwd = $studioRoot
    }
    while ($true) {
        $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($listener) {
            $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
            $expected = if ($Component -eq "Api") { "rstv4.studio_api:create_app" } else { $cli }
            if (-not $owner -or $owner.CommandLine -notmatch [regex]::Escape($expected)) {
                throw "Port $port has an unexpected owner; no process was stopped."
            }
            # An already-running verified service is observed until it exits; no duplicate child.
            Write-StudioLog "Observed existing verified listener PID $($owner.ProcessId)."
            $existing = Get-Process -Id $owner.ProcessId -ErrorAction SilentlyContinue
            if ($existing) { $existing.WaitForExit() }
        } else {
            $stamp = Get-Date -Format "yyyyMMddTHHmmssfff"
            Write-StudioLog "Launching $Component on 127.0.0.1:$port."
            $child = Start-Process -FilePath $executable -ArgumentList $childArguments -WorkingDirectory $cwd `
                -WindowStyle Hidden -PassThru `
                -RedirectStandardOutput (Join-Path $logRoot "WritingStudio-$Component.$stamp.stdout.log") `
                -RedirectStandardError (Join-Path $logRoot "WritingStudio-$Component.$stamp.stderr.log")
            $null = $child.Handle
            $child.WaitForExit()
            $child.Refresh()
            Write-StudioLog "Child PID $($child.Id) exited with code $($child.ExitCode); retry in 5 seconds."
        }
        Start-Sleep -Seconds 5
    }
} catch {
    Write-StudioLog "ERROR: $($_.Exception.Message)"
    Write-Error $_ -ErrorAction Continue
    exit 1
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
