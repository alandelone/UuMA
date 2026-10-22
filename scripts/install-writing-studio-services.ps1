[CmdletBinding()]
param([string]$ProjectRoot = "")
$ErrorActionPreference = "Stop"
if (-not $ProjectRoot) { $ProjectRoot = Split-Path -Parent $PSScriptRoot }
$runner = Join-Path $ProjectRoot "scripts\run-writing-studio-service.ps1"
$backup = Join-Path $ProjectRoot (".uuma-local\writing-studio-task-backups\" + (Get-Date -Format yyyyMMddTHHmmssfff))
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$trigger.Delay = "PT45S"
foreach ($component in @("Api", "Web")) {
    $name = "UuMA Writing Studio $component"
    $previous = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($previous) {
        New-Item -ItemType Directory -Path $backup -Force | Out-Null
        Export-ScheduledTask -TaskName $name | Out-File -LiteralPath (Join-Path $backup "$component.xml") -Encoding UTF8
    }
    $disabled = $previous -and $previous.State -eq "Disabled"
    $action = New-ScheduledTaskAction -Execute "conhost.exe" -WorkingDirectory $ProjectRoot -Argument (
        "--headless powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runner`" -Component $component -ProjectRoot `"$ProjectRoot`""
    )
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Force | Out-Null
    if ($disabled) { Disable-ScheduledTask -TaskName $name | Out-Null }
    Write-Host "Installed: $name"
}
