param(
    [string]$PythonExe = (Join-Path (Split-Path -Parent $PSScriptRoot) ".venv\Scripts\python.exe"),
    [string]$DataDir = (Join-Path $env:LOCALAPPDATA "UuMA"),
    [string]$HermesExe = (Join-Path $env:LOCALAPPDATA "hermes\hermes-agent\venv\Scripts\hermes.exe"),
    [string]$TaskName = "UuMA ChatGPT Bridge",
    [string]$DashboardTaskName = "UuMA ChatGPT Bridge Dashboard",
    [string]$WatchdogTaskName = "UuMA ChatGPT Bridge Watchdog"
)

$ErrorActionPreference = "Stop"
$resolvedPython = (Resolve-Path -LiteralPath $PythonExe).Path
foreach ($name in @($WatchdogTaskName, $DashboardTaskName, $TaskName)) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
    }
}
$running = Get-CimInstance Win32_Process `
    -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match '(?i)-m\s+uuma\.chatgpt_cli.*\sserve(?:\s|$)' }
foreach ($process in $running) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}
$marker = Join-Path $DataDir "chatgpt-bridge\current-deployment.txt"
if (Test-Path -LiteralPath $marker) {
    $manifest = (Get-Content -LiteralPath $marker -Raw).Trim()
    if (Test-Path -LiteralPath $manifest) {
        & $resolvedPython -m uuma.chatgpt_deploy --rollback-manifest $manifest
        if ($LASTEXITCODE -ne 0) { throw "Profile rollback failed." }
    }
    Remove-Item -LiteralPath $marker -Force
}
$shortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\UuMA\ChatGPT Bridge.lnk"
if (Test-Path -LiteralPath $shortcut) { Remove-Item -LiteralPath $shortcut -Force }
$desktopShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'ChatGPT Bridge.lnk'
if (Test-Path -LiteralPath $desktopShortcut) { Remove-Item -LiteralPath $desktopShortcut -Force }
if (Test-Path -LiteralPath $HermesExe) {
    & $HermesExe gateway restart
    if ($LASTEXITCODE -ne 0) { Write-Warning "Bridge stopped, but Hermes restart failed." }
}
Write-Host "ChatGPT Bridge disabled and profile configuration restored. History and browser profiles were preserved."
