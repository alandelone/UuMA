param(
    [string]$PythonExe = (Join-Path (Split-Path -Parent $PSScriptRoot) ".venv\Scripts\pythonw.exe"),
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$DataDir = "$env:LOCALAPPDATA\UuMA",
    [string]$ProfileHome = "$env:LOCALAPPDATA\hermes\profiles\wisdom-oldman",
    [string]$HermesExe = "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\hermes.exe",
    [string]$TaskName = "UuMA Question Orbit Runner",
    [string]$WatchdogTaskName = "UuMA Question Orbit Watchdog",
    [switch]$StartNow,
    [switch]$DoNotStart,
    [switch]$Uninstall,
    [switch]$AtLogon
)

$ErrorActionPreference = "Stop"

function Stop-OrbitRunnerProcesses {
    param([string]$ResolvedProfileHome)

    $profilePattern = [regex]::Escape($ResolvedProfileHome)
    $matches = @(
        Get-CimInstance Win32_Process | Where-Object {
            $_.Name -in @("python.exe", "pythonw.exe") -and
            $_.CommandLine -match '(?i)-m\s+uuma\.orbit_runner(?:\s|$)' -and
            $_.CommandLine -match $profilePattern
        }
    )
    foreach ($process in $matches | Sort-Object ParentProcessId -Descending) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    if ($matches.Count -gt 0) {
        Start-Sleep -Milliseconds 500
    }
    $remaining = @(
        Get-CimInstance Win32_Process | Where-Object {
            $_.Name -in @("python.exe", "pythonw.exe") -and
            $_.CommandLine -match '(?i)-m\s+uuma\.orbit_runner(?:\s|$)' -and
            $_.CommandLine -match $profilePattern
        }
    )
    if ($remaining.Count -gt 0) {
        throw "Unable to stop the existing Question Orbit runner process safely."
    }
}

function Resolve-EffectiveDataDir {
    param([string]$Candidate)

    $resolved = (Resolve-Path -LiteralPath $Candidate).Path
    foreach ($marker in @("wisdom.db", "uuma.db")) {
        $markerPath = Join-Path $resolved $marker
        if (-not (Test-Path -LiteralPath $markerPath)) { continue }
        $item = Get-Item -LiteralPath $markerPath
        $targets = @(@($item.Target) | Where-Object { $_ })
        if ($targets.Count -gt 0) {
            return (Split-Path -Parent ([IO.Path]::GetFullPath($targets[0])))
        }
    }
    return $resolved
}

if ($Uninstall) {
    $watchdogTask = Get-ScheduledTask -TaskName $WatchdogTaskName -ErrorAction SilentlyContinue
    if ($watchdogTask) {
        Stop-ScheduledTask -TaskName $WatchdogTaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $WatchdogTaskName -Confirm:$false
    }
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
    Stop-OrbitRunnerProcesses -ResolvedProfileHome ([IO.Path]::GetFullPath($ProfileHome))
    $configPath = Join-Path $ProfileHome "config.yaml"
    if (Test-Path -LiteralPath $configPath) {
        Copy-Item -LiteralPath $configPath -Destination "$configPath.orbit-runner-backup" -Force
        $matched = $false
        $updated = foreach ($line in Get-Content -LiteralPath $configPath) {
            if ($line -match '^\s*UUMA_QUESTION_ORBIT_ENABLED\s*:') {
                $matched = $true
                $indent = $line.Substring(0, $line.IndexOf('U'))
                "$indent" + "UUMA_QUESTION_ORBIT_ENABLED: 'false'"
            }
            else { $line }
        }
        if ($matched) {
            Set-Content -LiteralPath $configPath -Value $updated -Encoding utf8
        }
    }
    if (Test-Path -LiteralPath $HermesExe) {
        & $HermesExe gateway restart
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Orbit creation was disabled, but the Hermes gateway restart failed."
        }
    }
    Write-Host (
        "Question Orbit runner removed and automatic Orbit creation disabled; " +
        "wisdom.db and research history were preserved."
    )
    exit 0
}

$resolvedPython = (Resolve-Path -LiteralPath $PythonExe).Path
$resolvedProject = (Resolve-Path -LiteralPath $ProjectRoot).Path
$resolvedProfile = (Resolve-Path -LiteralPath $ProfileHome).Path
$launcher = (Resolve-Path -LiteralPath (
    Join-Path $resolvedProject "scripts\start-orbit-runner.ps1"
)).Path
$watchdog = (Resolve-Path -LiteralPath (
    Join-Path $resolvedProject "scripts\watch-orbit-runner.ps1"
)).Path
New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
$resolvedDataDir = Resolve-EffectiveDataDir -Candidate $DataDir
$existingWatchdogTask = Get-ScheduledTask -TaskName $WatchdogTaskName -ErrorAction SilentlyContinue
if ($existingWatchdogTask) {
    Stop-ScheduledTask -TaskName $WatchdogTaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $WatchdogTaskName -Confirm:$false
}
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
}
Stop-OrbitRunnerProcesses -ResolvedProfileHome $resolvedProfile

$databasePath = Join-Path $resolvedDataDir "wisdom.db"
if (Test-Path -LiteralPath $databasePath) {
    $backupRoot = Join-Path $resolvedDataDir "backups"
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    $backupPath = Join-Path $backupRoot (
        "wisdom-before-orbit-runner-" + (Get-Date -Format "yyyyMMdd-HHmmssfff") + ".db"
    )
    Copy-Item -LiteralPath $databasePath -Destination $backupPath
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
    "-ProfileHome", (Quote-Argument $resolvedProfile)
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
$taskArgs = @{
    Action = $action
    Principal = $principal
    Settings = $settings
    Description = "Runs governed Wisdom-Oldman Question Orbit research on demand."
}
if ($AtLogon) {
    $taskArgs["Trigger"] = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
}
$task = New-ScheduledTask @taskArgs
Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
if ($StartNow -and -not $DoNotStart) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Question Orbit runner task started."
}
Write-Host "Question Orbit runner task installed on-demand (legacy watchdog uninstalled)."
Write-Host "Question Orbit data directory: $resolvedDataDir"
