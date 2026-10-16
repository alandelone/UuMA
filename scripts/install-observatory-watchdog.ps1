﻿# Install/Manage Windows Scheduled Task Watchdog for UuMA All-in-One Observatory
param(
    [string]$TaskName = "UuMA All-in-One Observatory Watchdog",
    [int]$Port = 8790,
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$Uninstall,
    [switch]$Remove,
    [switch]$DoNotStart
)

$ErrorActionPreference = "Stop"

if ($Uninstall -or $Remove) {
    Write-Host "正在卸载 Windows 计划任务: $TaskName..." -ForegroundColor Yellow
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "已移除计划任务: $TaskName" -ForegroundColor Green
    } else {
        Write-Host "未找到正在运行的计划任务: $TaskName"
    }

    # Signal supervisor to stop and kill observatory processes
    $logDir = "$env:LOCALAPPDATA\UuMA\logs"
    if (Test-Path $logDir) {
        New-Item -ItemType File -Path (Join-Path $logDir ".stop_observatory") -Force | Out-Null
    }

    $procs = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -in @("python.exe", "pythonw.exe") -and
        $_.CommandLine -match '(?i)uuma\.observatory'
    }
    foreach ($p in $procs) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Observatory 后台守护与进程已完全清理。" -ForegroundColor Green
    exit 0
}

$resolvedProject = (Resolve-Path -LiteralPath $ProjectRoot).Path
$vbsLauncher = Join-Path $resolvedProject "scripts\start-observatory.vbs"
if (-not (Test-Path $vbsLauncher)) {
    throw "未找到 VBS 启动器: $vbsLauncher"
}

# Clean existing task before registering fresh
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$actionArguments = "//B //Nologo `"$vbsLauncher`" `"$Port`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $actionArguments -WorkingDirectory $resolvedProject

$principal = New-ScheduledTaskPrincipal `
    -UserId $userId `
    -LogonType Interactive `
    -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -Hidden `
    -MultipleInstances IgnoreNew `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId

$task = New-ScheduledTask `
    -Action $action `
    -Principal $principal `
    -Settings $settings `
    -Trigger $trigger `
    -Description "UuMA All-in-One Observatory Watchdog: Keeps the multi-agent observatory running silently on port $Port."

Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "[OK] 已成功注册 Windows 计划任务看门狗: $TaskName" -ForegroundColor Green
Write-Host "运行身份: $userId (登录自动拉起 + 崩溃自动重启)" -ForegroundColor Gray
Write-Host "服务端口: $Port" -ForegroundColor Gray
Write-Host "==========================================================" -ForegroundColor Cyan

if (-not $DoNotStart) {
    Write-Host "正在启动计划任务..." -ForegroundColor Yellow
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 3

    # Check health
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/observatory/sources" -TimeoutSec 3 -ErrorAction SilentlyContinue
        if ($resp) {
            Write-Host "[OK] Observatory 已成功在后台运行且健康响应！" -ForegroundColor Green
        }
    } catch {
        Write-Host "[INFO] 任务已调起，后台正在完成冷启动索引。" -ForegroundColor Gray
    }
}
