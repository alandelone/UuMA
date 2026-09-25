param(
    [ValidateSet('status', 'start', 'stop', 'dashboard', 'migrate')]
    [string]$Action = 'status',
    [switch]$Start,
    [switch]$Stop,
    [switch]$Status,
    [string]$TaskName = 'UuMA ChatGPT Bridge',
    [string]$DashboardTaskName = 'UuMA ChatGPT Bridge Dashboard',
    [string]$WatchdogTaskName = 'UuMA ChatGPT Bridge Watchdog'
)

$ErrorActionPreference = 'Stop'
if (@(@($Start, $Stop, $Status) | Where-Object { $_ }).Count -gt 1) {
    throw 'Choose only one lifecycle action.'
}
if ($Start) { $Action = 'start' }
if ($Stop) { $Action = 'stop' }
if ($Status) { $Action = 'status' }
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$arguments = $task.Actions.Arguments
function Get-TaskArgument([string]$Name) {
    if ($arguments -match ('(?i)(?:^|\s)-' + $Name + '\s+"([^"]+)"')) {
        return $Matches[1]
    }
    throw "Task is missing a quoted $Name argument; refusing to control an unknown service."
}
$dataDir = Get-TaskArgument 'DataDir'
$pythonExe = Get-TaskArgument 'PythonExe'
$projectRoot = Get-TaskArgument 'ProjectRoot'
if ($arguments -notmatch '(?i)(?:^|\s)-Port\s+(\d+)(?:\s|$)') { throw 'Missing task port.' }
$port = [int]$Matches[1]
$dataPattern = '(?i)(?:^|\s)--data-dir\s+(?:"' + [regex]::Escape($dataDir) +
    '"|' + [regex]::Escape($dataDir) + ')(?=\s|$)'
function Get-BridgeProcesses {
    @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
        Where-Object {
            $_.CommandLine -match '(?i)(?:^|\s)-m\s+uuma\.chatgpt_cli\s' -and
            $_.CommandLine -match $dataPattern -and
            $_.CommandLine -match ('(?:^|\s)--port\s+' + $port + '(?=\s|$)') -and
            $_.CommandLine -match '\sserve\s*$'
        })
}
function Test-BridgeHealth {
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$port/health" -TimeoutSec 2
        return ($health.service -eq 'uuma-chatgpt-bridge' -and $health.worker_healthy)
    } catch { return $false }
}
if ($Action -eq 'migrate') {
    $backup = Join-Path $dataDir ('chatgpt-bridge\task-backups\' + (Get-Date -Format 'yyyyMMdd-HHmmssfff'))
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    Export-ScheduledTask -TaskName $TaskName | Set-Content (Join-Path $backup 'service.xml')
    $watchdog = Get-ScheduledTask -TaskName $WatchdogTaskName -ErrorAction SilentlyContinue
    if ($watchdog) {
        Export-ScheduledTask -TaskName $WatchdogTaskName | Set-Content (Join-Path $backup 'watchdog.xml')
        Disable-ScheduledTask -TaskName $WatchdogTaskName | Out-Null
        Stop-ScheduledTask -TaskName $WatchdogTaskName
        Unregister-ScheduledTask -TaskName $WatchdogTaskName -Confirm:$false
    }
    Stop-ScheduledTask -TaskName $TaskName
    foreach ($process in (Get-BridgeProcesses)) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    [xml]$xml = Export-ScheduledTask -TaskName $TaskName
    $triggers = $xml.SelectSingleNode('/*[local-name()="Task"]/*[local-name()="Triggers"]')
    if ($triggers) { $triggers.RemoveAll() }
    $restart = $xml.Task.Settings.RestartOnFailure
    if ($restart) { $xml.Task.Settings.RemoveChild($restart) | Out-Null }
    $startWhenAvailable = $xml.SelectSingleNode(
        '/*[local-name()="Task"]/*[local-name()="Settings"]/*[local-name()="StartWhenAvailable"]'
    )
    if ($startWhenAvailable) { $startWhenAvailable.InnerText = 'false' }
    $enabled = $xml.SelectSingleNode(
        '/*[local-name()="Task"]/*[local-name()="Settings"]/*[local-name()="Enabled"]'
    )
    if ($enabled) { $enabled.InnerText = 'true' }
    Register-ScheduledTask -TaskName $TaskName -Xml $xml.OuterXml -Force | Out-Null
    Enable-ScheduledTask -TaskName $TaskName | Out-Null
    $shortcutPath = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\UuMA\ChatGPT Bridge.lnk'
    New-Item -ItemType Directory -Path (Split-Path $shortcutPath) -Force | Out-Null
    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
    $shortcut.TargetPath = (Get-Command powershell.exe).Source
    $shortcut.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' +
        $PSCommandPath + '" -Action dashboard -TaskName "' + $TaskName +
        '" -WatchdogTaskName "' + $WatchdogTaskName + '"'
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.Description = 'Start ChatGPT Bridge on demand and open its dashboard'
    $shortcut.Save()
    Write-Host "Migrated to on-demand mode. Previous tasks saved in $backup"
    $Action = 'stop'
}
if ($Action -eq 'stop') {
    Stop-ScheduledTask -TaskName $DashboardTaskName -ErrorAction SilentlyContinue
    if (Get-ScheduledTask -TaskName $WatchdogTaskName -ErrorAction SilentlyContinue) {
        Disable-ScheduledTask -TaskName $WatchdogTaskName | Out-Null
        Stop-ScheduledTask -TaskName $WatchdogTaskName
    }
    Stop-ScheduledTask -TaskName $TaskName
    foreach ($process in (Get-BridgeProcesses)) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 500
    if ((Get-BridgeProcesses).Count) { throw 'Bridge processes remain after stop.' }
    Write-Host 'Bridge stopped. The trigger-free task remains ready for agent lazy start.'
}
if ($Action -eq 'dashboard' -and
    (Get-ScheduledTask -TaskName $DashboardTaskName -ErrorAction SilentlyContinue)) {
    Start-ScheduledTask -TaskName $DashboardTaskName
    Write-Host 'Opening the authorized ChatGPT Bridge dashboard.'
    return
}
if ($Action -in @('start', 'dashboard')) {
    $task = Get-ScheduledTask -TaskName $TaskName
    if (@($task.Triggers | Where-Object { $null -ne $_ }).Count -or $task.Settings.RestartCount -or
        (Get-ScheduledTask -TaskName $WatchdogTaskName -ErrorAction SilentlyContinue)) {
        throw 'Run this script with -Action migrate before starting in on-demand mode.'
    }
    Start-ScheduledTask -TaskName $TaskName
    $deadline = (Get-Date).AddSeconds(30)
    while (-not (Test-BridgeHealth)) {
        if ((Get-Date) -ge $deadline) { throw 'Bridge did not become healthy within 30 seconds.' }
        Start-Sleep -Milliseconds 500
    }
    if (-not (Get-BridgeProcesses).Count) { throw 'Health endpoint has no matching bridge process.' }
    Write-Host 'Bridge is healthy.'
    if ($Action -eq 'dashboard') {
        $env:PYTHONPATH = Join-Path $projectRoot 'src'
        & $pythonExe -m uuma.chatgpt_cli --data-dir $dataDir --port $port dashboard
        if ($LASTEXITCODE -ne 0) { throw 'Unable to open dashboard.' }
    }
}
if ($Action -eq 'status') {
    [pscustomobject]@{
        Task = $TaskName
        State = [string]$task.State
        Triggers = @($task.Triggers | Where-Object { $null -ne $_ }).Count
        AutomaticRetries = $task.Settings.RestartCount
        WatchdogPresent = [bool](Get-ScheduledTask -TaskName $WatchdogTaskName -ErrorAction SilentlyContinue)
        DashboardLauncherPresent = [bool](Get-ScheduledTask -TaskName $DashboardTaskName -ErrorAction SilentlyContinue)
        Processes = (Get-BridgeProcesses).Count
        Healthy = Test-BridgeHealth
    }
}
