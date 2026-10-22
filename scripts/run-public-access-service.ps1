[CmdletBinding()]
param([string]$ProjectRoot = "")
$ErrorActionPreference = "Stop"
if (-not $ProjectRoot) { $ProjectRoot = Split-Path -Parent $PSScriptRoot }
$logRoot = Join-Path $ProjectRoot ".uuma-local\windows-service-logs"
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$mutex = [Threading.Mutex]::new($false, "Local\UuMA.PublicAccess")
$locked = $false
try {
    try { $locked = $mutex.WaitOne(0) }
    catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { exit 0 }
    $env:PYTHONPATH = Join-Path $ProjectRoot "src"
    $env:PYTHONUTF8 = "1"
    $python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    while ($true) {
        $listener = Get-NetTCPConnection -LocalPort 8791 -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($listener) {
            $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
            if (-not $owner -or $owner.CommandLine -notmatch 'uuma\.public_access') {
                throw "Port 8791 has an unexpected owner; no process was stopped."
            }
            $existing = Get-Process -Id $owner.ProcessId -ErrorAction SilentlyContinue
            if ($existing) { $existing.WaitForExit() }
        } else {
            $stamp = Get-Date -Format yyyyMMddTHHmmssfff
            $child = Start-Process -FilePath $python -ArgumentList @("-u", "-m", "uuma.public_access") `
                -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru `
                -RedirectStandardOutput (Join-Path $logRoot "PublicAccess.$stamp.stdout.log") `
                -RedirectStandardError (Join-Path $logRoot "PublicAccess.$stamp.stderr.log")
            $null = $child.Handle
            $child.WaitForExit()
        }
        Start-Sleep -Seconds 5
    }
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
