[CmdletBinding()]
param(
    [string]$ProjectRoot = ""
)
$ErrorActionPreference = "Stop"
if (-not $ProjectRoot) { $ProjectRoot = Split-Path -Parent $PSScriptRoot }
$runner = Join-Path $ProjectRoot "scripts\run-windows-agent-service.ps1"
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$trigger.Delay = "PT45S"
foreach ($entry in @(
    @{ Name = "UuMA Scholar Web"; Service = "Scholar" },
    @{ Name = "UuMA Live Agent"; Service = "LiveAgent" }
)) {
    $previous = Get-ScheduledTask -TaskName $entry.Name -ErrorAction SilentlyContinue
    $keepDisabled = $previous -and $previous.State -eq "Disabled"
    $action = New-ScheduledTaskAction -Execute "conhost.exe" -WorkingDirectory $ProjectRoot -Argument (
        "--headless powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runner`" -Service $($entry.Service) -ProjectRoot `"$ProjectRoot`""
    )
    Register-ScheduledTask -TaskName $entry.Name -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Force | Out-Null
    if ($keepDisabled) { Disable-ScheduledTask -TaskName $entry.Name | Out-Null }
    Write-Host "Installed login/recovery task: $($entry.Name)"
}
