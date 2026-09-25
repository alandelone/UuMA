param(
    [string]$PythonExe = (Join-Path (Split-Path -Parent $PSScriptRoot) ".venv\Scripts\python.exe"),
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$DataDir = (Join-Path $env:LOCALAPPDATA "UuMA"),
    [string]$ProfileHome = (Join-Path $env:LOCALAPPDATA "hermes\profiles\forge-lab-bot"),
    [string]$DefaultHermesHome = (Join-Path $env:LOCALAPPDATA "hermes"),
    [string]$LogsDataSource = "06d7c1c5-a614-4577-ab62-a238ce376675",
    [string]$CandidatesDataSource = "b68cd096-9176-4571-83f7-ddfa7c082bc7",
    [int]$ReconcileSeconds = 900,
    [string]$TaskName = "UuMA Forge Journal Runner",
    [string]$WatchdogTaskName = "UuMA Forge Journal Watchdog",
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"
$PythonExe = (Resolve-Path -LiteralPath $PythonExe).Path
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$ProfileHome = (Resolve-Path -LiteralPath $ProfileHome).Path
$DefaultHermesHome = (Resolve-Path -LiteralPath $DefaultHermesHome).Path
if ($ReconcileSeconds -lt 300) {
    throw "Forge Journal reconciliation must be at least 300 seconds."
}

$database = Join-Path $DataDir "forge-lab-bot\lab.db"
if (Test-Path -LiteralPath $database) {
    $backupDir = Join-Path $DataDir "backups"
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd-HHmmssfff"
    Copy-Item -LiteralPath $database `
        -Destination (Join-Path $backupDir "lab-before-forge-journal-runner-$stamp.db")
}

foreach ($name in @($WatchdogTaskName, $TaskName)) {
    $existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($existing) {
        $backupDir = Join-Path $DataDir "backups"
        New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
        $stamp = Get-Date -Format "yyyyMMdd-HHmmssfff"
        Export-ScheduledTask -TaskName $name |
            Set-Content -LiteralPath (Join-Path $backupDir "$name-$stamp.xml") -Encoding Unicode
        Disable-ScheduledTask -TaskName $name | Out-Null
        Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
    }
}
Get-CimInstance Win32_Process `
    -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -match '(?i)-m\s+uuma\.forge_journal_runner(?:\s|$)' -and
        $_.CommandLine -like "*$ProfileHome*"
    } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$quoted = @(
    "-m", "uuma.forge_journal_runner",
    "--data-dir", ('"{0}"' -f $DataDir),
    "--profile-home", ('"{0}"' -f $ProfileHome),
    "--default-hermes-home", ('"{0}"' -f $DefaultHermesHome),
    "--logs-data-source", $LogsDataSource,
    "--candidates-data-source", $CandidatesDataSource,
    "--reconcile-seconds", $ReconcileSeconds,
    "--once"
) -join " "
$action = New-ScheduledTaskAction `
    -Execute $PythonExe -Argument $quoted -WorkingDirectory $ProjectRoot
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero)
$task = New-ScheduledTask -Action $action -Principal $principal -Settings $settings
Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null

if ($StartNow) { Start-ScheduledTask -TaskName $TaskName }
Write-Host (
    "Installed $TaskName as an armed event-driven one-shot; " +
    "no automatic triggers, retries, or watchdog. Use Stop to pause delivery."
)
