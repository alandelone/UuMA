[CmdletBinding()]
param([string]$ProjectRoot = "")
$ErrorActionPreference = "Stop"
if (-not $ProjectRoot) { $ProjectRoot = Split-Path -Parent $PSScriptRoot }
$stateDir = Join-Path $ProjectRoot ".uuma-local\codex-antigravity-ui-20261102"
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$mutex = [Threading.Mutex]::new($false, "Local\UuMA.AntigravityGateway")
$locked = $false
try {
    try { $locked = $mutex.WaitOne(0) }
    catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { exit 0 }
    $env:CODEX_AGY_STATE = $stateDir
    $env:PYTHONUTF8 = "1"
    $python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $gatewayPy = Join-Path $ProjectRoot "integrations\codex_antigravity\gateway.py"
    while ($true) {
        $listener = Get-NetTCPConnection -LocalPort 18782 -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($listener) {
            $existing = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
            if ($existing) { $existing.WaitForExit() }
        } else {
            $child = Start-Process -FilePath $python -ArgumentList @($gatewayPy) `
                -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru `
                -RedirectStandardOutput (Join-Path $stateDir "gateway.stdout.log") `
                -RedirectStandardError (Join-Path $stateDir "gateway.stderr.log")
            $null = $child.Handle
            $child.WaitForExit()
        }
        Start-Sleep -Seconds 3
    }
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
