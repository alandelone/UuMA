param(
    [string]$TaskName = "UuMA Phoenix",
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

if ($Remove) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed Windows auto-start task '$TaskName'."
    }
    else {
        Write-Host "Windows auto-start task '$TaskName' is not installed."
    }
    exit 0
}

$serviceScript = Join-Path $ProjectRoot "scripts\run-phoenix-service.ps1"
if (-not (Test-Path -LiteralPath $serviceScript)) {
    throw "Phoenix service script not found at '$serviceScript'."
}

$windowsPowerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$arguments = (
    "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass " +
    "-File `"$serviceScript`""
)
$action = New-ScheduledTaskAction -Execute $windowsPowerShell -Argument $arguments `
    -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description "Starts the local UuMA Phoenix observability service after Windows sign-in." `
    -Force | Out-Null

Write-Host "Installed Windows auto-start task '$TaskName' for $userId."
Write-Host "Phoenix will start automatically after this user signs in."
