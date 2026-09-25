param(
    [Parameter(Mandatory = $false)][string]$RunnerTaskName = "UuMA Question Orbit Runner",
    [Parameter(Mandatory = $false)][string]$ProfileHome = "$env:LOCALAPPDATA\hermes\profiles\wisdom-oldman",
    [Parameter(Mandatory = $false)][string]$DataDir = "$env:LOCALAPPDATA\UuMA"
)

$ErrorActionPreference = "Stop"

# The 1-minute watchdog task has been retired in favor of on-demand lifecycle control (manage-orbit-runner.ps1).
# If this script is executed, safely unregister any lingering legacy watchdog task.
$watchdogTask = Get-ScheduledTask -TaskName "UuMA Question Orbit Watchdog" -ErrorAction SilentlyContinue
if ($watchdogTask) {
    Stop-ScheduledTask -TaskName "UuMA Question Orbit Watchdog" -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName "UuMA Question Orbit Watchdog" -Confirm:$false
}
