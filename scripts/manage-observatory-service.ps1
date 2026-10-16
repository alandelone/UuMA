# Manage UuMA All-in-One Observatory Service & Watchdog
param(
    [switch]$Status,
    [switch]$Start,
    [switch]$Stop,
    [switch]$Restart,
    [switch]$Logs,
    [switch]$Open,
    [int]$Port = 8790,
    [string]$TaskName = "UuMA All-in-One Observatory Watchdog"
)

$ErrorActionPreference = "Continue"

$logDir = "$env:LOCALAPPDATA\UuMA\logs"
$logFile = Join-Path $logDir "observatory-service.log"
$tokenFile = Join-Path "$env:LOCALAPPDATA\UuMA" "observatory.token"

function Get-ObservatoryProcesses {
    return @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -in @("python.exe", "pythonw.exe") -and
        $_.CommandLine -match '(?i)uuma\.observatory'
    })
}

if ($Stop -or $Restart) {
    Write-Host "Stopping Observatory processes..." -ForegroundColor Yellow
    New-Item -ItemType File -Path (Join-Path $logDir ".stop_observatory") -Force | Out-Null
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    foreach ($p in (Get-ObservatoryProcesses)) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Observatory stopped." -ForegroundColor Green
    if ($Stop) { exit 0 }
    Start-Sleep -Seconds 2
}

if ($Start -or $Restart) {
    Remove-Item -Path (Join-Path $logDir ".stop_observatory") -Force -ErrorAction SilentlyContinue
    Write-Host "Starting Observatory via Scheduled Task: $TaskName..." -ForegroundColor Yellow
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Start-ScheduledTask -TaskName $TaskName
    } else {
        # Fallback to direct run if task not installed
        $vbs = Join-Path (Split-Path -Parent $PSScriptRoot) "scripts\start-observatory.vbs"
        Start-Process "wscript.exe" -ArgumentList "//B //Nologo `"$vbs`" `"$Port`""
    }
    Start-Sleep -Seconds 3
}

if ($Logs) {
    if (Test-Path $logFile) {
        Get-Content -Path $logFile -Tail 30
    } else {
        Write-Host "No log file found at $logFile"
    }
    exit 0
}

# Default / Status output
$procs = Get-ObservatoryProcesses
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$occupied = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "🔭 UuMA All-in-One Observatory Service Status" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "计划任务看门狗 : " -NoNewline
if ($task) {
    Write-Host "$TaskName ($($task.State))" -ForegroundColor Green
} else {
    Write-Host "未安装 (运行 .\scripts\install-observatory-watchdog.ps1 安装)" -ForegroundColor Yellow
}

Write-Host "端口监听 ($Port): " -NoNewline
if ($occupied) {
    Write-Host "正在监听 (PID $($occupied.OwningProcess))" -ForegroundColor Green
} else {
    Write-Host "未监听" -ForegroundColor Red
}

Write-Host "运行进程数     : " -NoNewline
if ($procs.Count -gt 0) {
    Write-Host "$($procs.Count) 个活跃进程 ($($procs.ProcessId -join ', '))" -ForegroundColor Green
} else {
    Write-Host "0 个" -ForegroundColor Gray
}

# Health Probe
try {
    $url = "http://127.0.0.1:$Port/"
    Write-Host "访问入口       : $url (本地免密直连)" -ForegroundColor Yellow

    if ($Open) {
        Start-Process $url
    }
} catch {
    Write-Host "访问入口       : http://127.0.0.1:$Port/"
}
