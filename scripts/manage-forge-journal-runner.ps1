param(
    [ValidateSet("status", "start", "stop", "restart", "migrate", "run-once", "acceptance", "uninstall")]
    [string]$Action = "status",
    [string]$TaskName = "UuMA Forge Journal Runner",
    [string]$WatchdogTaskName = "UuMA Forge Journal Watchdog",
    [string]$PythonExe = (Join-Path (Split-Path -Parent $PSScriptRoot) ".venv\Scripts\python.exe"),
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$DataDir = (Join-Path $env:LOCALAPPDATA "UuMA"),
    [string]$ProfileHome = (Join-Path $env:LOCALAPPDATA "hermes\profiles\forge-lab-bot"),
    [string]$DefaultHermesHome = (Join-Path $env:LOCALAPPDATA "hermes"),
    [string]$LogsDataSource = "06d7c1c5-a614-4577-ab62-a238ce376675",
    [string]$CandidatesDataSource = "b68cd096-9176-4571-83f7-ddfa7c082bc7"
)

$ErrorActionPreference = "Stop"

function Get-RunnerProcesses {
    Get-CimInstance Win32_Process `
        -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -match '(?i)-m\s+uuma\.forge_journal_runner(?:\s|$)' -and
            $_.CommandLine -like "*$ProfileHome*"
        }
}

function Stop-RunnerProcesses {
    foreach ($process in @(Get-RunnerProcesses)) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-RunnerOnce {
    param([switch]$Acceptance)
    $env:PYTHONPATH = Join-Path $ProjectRoot "src"
    $arguments = @(
        "-m", "uuma.forge_journal_runner",
        "--profile-home", $ProfileHome,
        "--default-hermes-home", $DefaultHermesHome,
        "--data-dir", $DataDir,
        "--logs-data-source", $LogsDataSource,
        "--candidates-data-source", $CandidatesDataSource
    )
    $arguments += if ($Acceptance) { "--acceptance" } else { "--once" }
    & $PythonExe @arguments
    if ($LASTEXITCODE -ne 0) { throw "Forge Journal runner command failed." }
}

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$watchdog = Get-ScheduledTask -TaskName $WatchdogTaskName -ErrorAction SilentlyContinue

switch ($Action) {
    "migrate" {
        & (Join-Path $PSScriptRoot "install-forge-journal-runner.ps1") `
            -PythonExe $PythonExe -ProjectRoot $ProjectRoot -DataDir $DataDir `
            -ProfileHome $ProfileHome -DefaultHermesHome $DefaultHermesHome `
            -LogsDataSource $LogsDataSource -CandidatesDataSource $CandidatesDataSource `
            -TaskName $TaskName -WatchdogTaskName $WatchdogTaskName
    }
    "status" {
        [pscustomobject]@{
            TaskInstalled = [bool]$task
            TaskState = if ($task) { [string]$task.State } else { "Missing" }
            TaskEnabled = [bool]($task -and $task.State -ne "Disabled")
            DeliveryMode = if ($task -and $task.State -ne "Disabled") { "Armed" } else { "Paused" }
            TriggerCount = @($task.Triggers | Where-Object { $null -ne $_ }).Count
            RestartCount = if ($task) { $task.Settings.RestartCount } else { 0 }
            WatchdogInstalled = [bool]$watchdog
            WatchdogState = if ($watchdog) { [string]$watchdog.State } else { "Missing" }
            RunnerProcessCount = @(Get-RunnerProcesses).Count
        }
    }
    "start" {
        if (-not $task) { throw "Scheduled task '$TaskName' is not installed." }
        if ($task.Triggers -or $task.Settings.RestartCount -or $watchdog) {
            throw "Legacy automatic lifecycle detected. Run migrate before start."
        }
        Enable-ScheduledTask -TaskName $TaskName | Out-Null
        Start-ScheduledTask -TaskName $TaskName
    }
    "stop" {
        if ($watchdog) {
            Disable-ScheduledTask -TaskName $WatchdogTaskName | Out-Null
            Stop-ScheduledTask -TaskName $WatchdogTaskName -ErrorAction SilentlyContinue
        }
        if ($task) { Disable-ScheduledTask -TaskName $TaskName | Out-Null }
        if ($task) { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue }
        Stop-RunnerProcesses
        if ($task) { Disable-ScheduledTask -TaskName $TaskName | Out-Null }
    }
    "restart" {
        if (-not $task) { throw "Scheduled task '$TaskName' is not installed." }
        if ($task.Triggers -or $task.Settings.RestartCount -or $watchdog) {
            throw "Legacy automatic lifecycle detected. Run migrate before restart."
        }
        Enable-ScheduledTask -TaskName $TaskName | Out-Null
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Stop-RunnerProcesses
        Start-ScheduledTask -TaskName $TaskName
    }
    "run-once" {
        if ($task) { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue }
        Stop-RunnerProcesses
        Invoke-RunnerOnce
    }
    "acceptance" {
        if ($task) { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue }
        Stop-RunnerProcesses
        Invoke-RunnerOnce -Acceptance
    }
    "uninstall" {
        if ($watchdog) {
            Stop-ScheduledTask -TaskName $WatchdogTaskName -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $WatchdogTaskName -Confirm:$false
        }
        if ($task) {
            Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        }
        Stop-RunnerProcesses
    }
}
