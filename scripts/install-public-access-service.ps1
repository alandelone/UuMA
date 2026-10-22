[CmdletBinding()]
param([string]$ProjectRoot = "")
$ErrorActionPreference = "Stop"
if (-not $ProjectRoot) { $ProjectRoot = Split-Path -Parent $PSScriptRoot }
$name = "UuMA Public Access"
if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
    throw "Task already exists; inspect it before updating."
}
$runner = Join-Path $ProjectRoot "scripts\run-public-access-service.ps1"
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$trigger.Delay = "PT15S"
$action = New-ScheduledTaskAction -Execute "conhost.exe" -WorkingDirectory $ProjectRoot -Argument (
    "--headless powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runner`" -ProjectRoot `"$ProjectRoot`""
)
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName $name
Write-Host "Installed and started: $name"
