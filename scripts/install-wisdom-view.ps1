param(
    [string]$PythonExe = (Join-Path (Split-Path -Parent $PSScriptRoot) ".venv\Scripts\python.exe"),
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$DataDir = "$env:LOCALAPPDATA\UuMA",
    [string]$TaskName = "UuMA Wisdom Document View",
    [int]$Port = 8767,
    [switch]$DoNotStart,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

function Get-WisdomViewProcesses {
    param([int]$ExpectedPort)
    return @(
        Get-CimInstance Win32_Process | Where-Object {
            $_.Name -in @("python.exe", "pythonw.exe") -and
            $_.CommandLine -match '(?i)-m\s+uuma\.wisdom_view(?:\s|$)'
        }
    )
}

if ($Uninstall) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
    foreach ($process in Get-WisdomViewProcesses -ExpectedPort $Port) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Wisdom document view removed; documents and the read token were preserved."
    exit 0
}

$resolvedPython = (Resolve-Path -LiteralPath $PythonExe).Path
$resolvedProject = (Resolve-Path -LiteralPath $ProjectRoot).Path
$launcher = (Resolve-Path -LiteralPath (
    Join-Path $resolvedProject "scripts\start-wisdom-view.ps1"
)).Path
New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
$resolvedDataDir = (Resolve-Path -LiteralPath $DataDir).Path
# Resolve packaged-app LocalAppData redirection before leaving this process context.
# Task Scheduler otherwise opens a different wisdom.db under the same logical path.
$databaseFile = Get-Item -LiteralPath (Join-Path $resolvedDataDir "wisdom.db")
$databaseTargets = @(@($databaseFile.Target) | Where-Object { $_ })
if ($databaseTargets.Count -gt 0) {
    $resolvedDataDir = Split-Path -Parent ([IO.Path]::GetFullPath($databaseTargets[0]))
}

$occupied = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($occupied) {
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($occupied.OwningProcess)"
    if ($owner.CommandLine -notmatch '(?i)-m\s+uuma\.wisdom_view(?:\s|$)') {
        throw "Port $Port is already used by a different local service."
    }
}

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
foreach ($process in Get-WisdomViewProcesses -ExpectedPort $Port) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}

function Quote-Argument([string]$Value) {
    return '"' + $Value.Replace('"', '""') + '"'
}

$arguments = @(
    "-NoProfile",
    "-NonInteractive",
    "-WindowStyle", "Hidden",
    "-ExecutionPolicy", "Bypass",
    "-File", (Quote-Argument $launcher),
    "-PythonExe", (Quote-Argument $resolvedPython),
    "-ProjectRoot", (Quote-Argument $resolvedProject),
    "-DataDir", (Quote-Argument $resolvedDataDir),
    "-Port", "$Port"
) -join " "
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -Hidden `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 3650)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$task = New-ScheduledTask `
    -Action $action `
    -Principal $principal `
    -Settings $settings `
    -Trigger $trigger `
    -Description "Serves read-only Wisdom-Oldman topic documents on loopback."
Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
if (-not $DoNotStart) {
    Start-ScheduledTask -TaskName $TaskName
}
Write-Host "Wisdom document view installed at http://127.0.0.1:$Port/wisdom/topics."
