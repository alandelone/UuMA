param(
    [string]$PythonExe = (Join-Path (Split-Path -Parent $PSScriptRoot) ".venv\Scripts\python.exe"),
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$DataDir = (Join-Path $env:LOCALAPPDATA "UuMA"),
    [string]$HermesHome = (Join-Path $env:LOCALAPPDATA "hermes"),
    [string]$HermesExe = (Join-Path $env:LOCALAPPDATA "hermes\hermes-agent\venv\Scripts\hermes.exe"),
    [int]$Port = 8787,
    [string]$TaskName = "UuMA ChatGPT Bridge",
    [string]$DashboardTaskName = "UuMA ChatGPT Bridge Dashboard",
    [string]$WatchdogTaskName = "UuMA ChatGPT Bridge Watchdog",
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"
$resolvedPython = (Resolve-Path -LiteralPath $PythonExe).Path
$resolvedProject = (Resolve-Path -LiteralPath $ProjectRoot).Path
$resolvedHermes = (Resolve-Path -LiteralPath $HermesHome).Path
$launcher = (Resolve-Path -LiteralPath (
    Join-Path $resolvedProject "scripts\start-chatgpt-bridge.ps1"
)).Path
$manager = (Resolve-Path -LiteralPath (
    Join-Path $resolvedProject "scripts\manage-chatgpt-bridge.ps1"
)).Path
$dashboardLauncher = (Resolve-Path -LiteralPath (
    Join-Path $resolvedProject "scripts\open-chatgpt-bridge-dashboard.ps1"
)).Path
$bridgeDir = Join-Path $DataDir "chatgpt-bridge"
New-Item -ItemType Directory -Path $bridgeDir -Force | Out-Null

& $resolvedPython -m pip install "playwright>=1.51,<2"
if ($LASTEXITCODE -ne 0) { throw "Failed to install the ChatGPT bridge dependency." }

$manifestMarker = Join-Path $bridgeDir "current-deployment.txt"
$currentManifest = if (Test-Path -LiteralPath $manifestMarker) {
    (Get-Content -LiteralPath $manifestMarker -Raw).Trim()
}
else { "" }
if (-not $currentManifest -or -not (Test-Path -LiteralPath $currentManifest)) {
    $manifest = (& $resolvedPython -m uuma.chatgpt_deploy `
        --project $resolvedProject --data-dir $DataDir --hermes-home $resolvedHermes --port $Port).Trim()
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $manifest)) {
        throw "ChatGPT bridge profile deployment failed."
    }
    Set-Content -LiteralPath $manifestMarker -Value $manifest -Encoding utf8
}

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    & $manager -Action migrate -TaskName $TaskName -DashboardTaskName $DashboardTaskName `
        -WatchdogTaskName $WatchdogTaskName
}
foreach ($name in @($WatchdogTaskName, $DashboardTaskName, $TaskName)) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
    }
}

$powershellExe = (Get-Command powershell.exe).Source
$serviceArguments = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
    "-File", ('"{0}"' -f $launcher),
    "-PythonExe", ('"{0}"' -f $resolvedPython),
    "-ProjectRoot", ('"{0}"' -f $resolvedProject),
    "-DataDir", ('"{0}"' -f $DataDir),
    "-Port", [string]$Port
) -join " "
$serviceAction = New-ScheduledTaskAction -Execute $powershellExe -Argument $serviceArguments
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
Register-ScheduledTask -TaskName $TaskName -InputObject (
    New-ScheduledTask -Action $serviceAction -Principal $principal -Settings $settings
) -Force | Out-Null

$dashboardArguments = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
    "-File", ('"{0}"' -f $dashboardLauncher),
    "-PythonExe", ('"{0}"' -f $resolvedPython),
    "-ProjectRoot", ('"{0}"' -f $resolvedProject),
    "-DataDir", ('"{0}"' -f $DataDir),
    "-ServiceTaskName", ('"{0}"' -f $TaskName),
    "-Port", [string]$Port
) -join " "
$dashboardAction = New-ScheduledTaskAction -Execute $powershellExe -Argument $dashboardArguments
Register-ScheduledTask -TaskName $DashboardTaskName -InputObject (
    New-ScheduledTask -Action $dashboardAction -Principal $principal -Settings $settings
) -Force | Out-Null

$shortcutDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\UuMA"
New-Item -ItemType Directory -Path $shortcutDir -Force | Out-Null
$shortcutPath = Join-Path $shortcutDir "ChatGPT Bridge.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = (Get-Command schtasks.exe).Source
$shortcut.Arguments = ('/Run /TN "{0}"' -f $DashboardTaskName)
$shortcut.WorkingDirectory = $resolvedProject
$shortcut.Description = "Start ChatGPT Bridge on demand and open its dashboard"
$shortcut.Save()
$desktopShortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'ChatGPT Bridge.lnk'))
$desktopShortcut.TargetPath = (Get-Command schtasks.exe).Source
$desktopShortcut.Arguments = ('/Run /TN "{0}"' -f $DashboardTaskName)
$desktopShortcut.WorkingDirectory = $resolvedProject
$desktopShortcut.Description = "Start ChatGPT Bridge on demand and open its dashboard"
$desktopShortcut.Save()

if (Test-Path -LiteralPath $HermesExe) {
    & $HermesExe gateway restart
    if ($LASTEXITCODE -ne 0) { Write-Warning "Profiles changed, but Hermes restart failed." }
}
if ($StartNow) {
    & $manager -Start -TaskName $TaskName -DashboardTaskName $DashboardTaskName `
        -WatchdogTaskName $WatchdogTaskName
}
Write-Host "Installed on-demand $TaskName on loopback port $Port. Open 'ChatGPT Bridge' from Start."
