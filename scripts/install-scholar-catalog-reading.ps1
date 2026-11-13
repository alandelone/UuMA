# Prepare or install only the dedicated, fixed-release Catalog reading task.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ManifestPath,
    [Parameter(Mandatory = $true)][string]$DataRoot,
    [string]$ProjectRoot = '',
    [string]$ReceiptRoot = '',
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
if (-not $ProjectRoot) { $ProjectRoot = Split-Path -Parent $PSScriptRoot }
$ProjectRoot = (Get-Item -LiteralPath $ProjectRoot).FullName
$runner = Join-Path $PSScriptRoot 'run-scholar-catalog-reading.ps1'
$checkedText = & $runner -ManifestPath $ManifestPath -DataRoot $DataRoot -ProjectRoot $ProjectRoot -CheckOnly
$checked = ($checkedText -join [Environment]::NewLine) | ConvertFrom-Json
if ($checked.worker_started -ne $false -or $checked.runtime.kind -ne 'FIXED_RELEASE') {
    throw 'Task installation requires read-only fixed-release admission.'
}
$runtime = $checked.runtime
$name = 'UuMA Scholar Catalog Reading'
$user = "$env:USERDOMAIN\$env:USERNAME"
$arguments = '--headless powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' +
    $runner + '" -ManifestPath "' + $runtime.manifest + '" -DataRoot "' + $runtime.data_root + '" -ProjectRoot "' + $ProjectRoot + '"'
$plan = [ordered]@{
    task_name = $name; user = $user; execute = 'conhost.exe'; arguments = $arguments;
    working_directory = $ProjectRoot; manifest_sha256 = $runtime.manifest_sha256;
    package_sha256 = $runtime.package_sha256; owner_root = $runtime.data_root;
    automatic_window = $checked.automatic_window; manual_priority = $true;
    restart_count = 3; restart_interval = 'PT1M'; execution_time_limit = 'PT0S';
    multiple_instances = 'IgnoreNew'; logon_delay = 'PT45S'; daily_start = '00:00';
    installed = $false; started = $false
}
if (-not $Apply) { $plan | ConvertTo-Json -Depth 8 -Compress; return }
$previous = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if ($previous) {
    $actions = @($previous.Actions)
    if ($actions.Count -ne 1 -or (Split-Path -Leaf $actions[0].Execute) -ne 'conhost.exe' -or
        $actions[0].Arguments -ne $arguments -or $actions[0].WorkingDirectory -ne $ProjectRoot) {
        throw 'The existing Catalog reading task has an unexpected action; preserve it for review.'
    }
}
if (-not $ReceiptRoot) { $ReceiptRoot = Join-Path $ProjectRoot '.uuma-local/scholar-catalog-runtime/task-installations' }
$receipt = Join-Path $ReceiptRoot ([Guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $receipt -Force
if ($previous) {
    Export-ScheduledTask -TaskName $name | Out-File -LiteralPath (Join-Path $receipt 'before.xml') -Encoding UTF8
}
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$trigger.Delay = 'PT45S'
$nightTrigger = New-ScheduledTaskTrigger -Daily -At '00:00'
$action = New-ScheduledTaskAction -Execute 'conhost.exe' -WorkingDirectory $ProjectRoot -Argument $arguments
# Daily startup recovers an explicitly stopped supervisor even without another login.
# The worker still owns the night admission gate and manual-request priority.
Register-ScheduledTask -TaskName $name -Action $action -Trigger @($trigger, $nightTrigger) -Principal $principal -Settings $settings -Force | Out-Null
if ($previous -and $previous.State -eq 'Disabled') { Disable-ScheduledTask -TaskName $name | Out-Null }
Export-ScheduledTask -TaskName $name | Out-File -LiteralPath (Join-Path $receipt 'installed.xml') -Encoding UTF8
$plan.installed = $true
$plan['receipt_root'] = $receipt
$plan | ConvertTo-Json -Depth 8 | Out-File -LiteralPath (Join-Path $receipt 'receipt.json') -Encoding UTF8
$plan | ConvertTo-Json -Depth 8 -Compress
