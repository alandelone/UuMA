param(
    [int]$Port = 8767
)

$ErrorActionPreference = "SilentlyContinue"

$processes = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -in @("python.exe", "pythonw.exe") -and
    $_.CommandLine -match '(?i)-m\s+uuma\.wisdom_view(?:\s|$)'
}

$stopped = $false
foreach ($p in $processes) {
    Stop-Process -Id $p.ProcessId -Force
    Write-Host "Stopped wisdom_view process (PID: $($p.ProcessId))."
    $stopped = $true
}

$occupied = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($occupied) {
    Stop-Process -Id $occupied.OwningProcess -Force
    Write-Host "Stopped process on port $Port (PID: $($occupied.OwningProcess))."
    $stopped = $true
}

if (-not $stopped) {
    Write-Host "Wisdom Document View is not currently running."
}
