$ErrorActionPreference = 'Stop'
$name = 'UuMA Brainstormer State'
$runner = Join-Path $PSScriptRoot 'run-brainstormer-state.ps1'
if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
    throw 'State service already registered; inspect it before updating.'
}
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runner`""
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $name -Action $action -Principal $principal `
    -Trigger $trigger -Settings $settings -Description 'Shared local Brainstormer topic state for Telegram and Live.' | Out-Null
Start-ScheduledTask -TaskName $name
Write-Output 'Brainstormer state service registered and start requested.'
