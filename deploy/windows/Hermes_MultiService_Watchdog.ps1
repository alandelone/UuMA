# Unified Multi-Service Watchdog for Windows
# Supervises existing services plus Scholar Web and UuMA Observatory.
# -ServiceName restricts a manual check to named services; -DryRun performs checks without recovery.

[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Daemon,
    [int]$IntervalSeconds = 60,
    [string[]]$ServiceName = @()
)

$ErrorActionPreference = "SilentlyContinue"
$BaseDir = "C:\Users\Alandelone\AppData\Local\hermes\gateway-service"
$LogFile = Join-Path $BaseDir "watchdog.log"
$PauseFlag = Join-Path $BaseDir "watchdog.disabled"

function Write-WatchdogLog([string]$Message) {
    $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $entry = "[$timestamp] $Message"
    Add-Content -Path $LogFile -Value $entry -ErrorAction SilentlyContinue
    Write-Host $entry
}

function Test-LocalPort([int]$Port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

if (-not (Test-Path $BaseDir)) {
    New-Item -ItemType Directory -Path $BaseDir -Force | Out-Null
}

function Start-ManagedTask([string]$Name) {
    $task = Get-ScheduledTask -TaskName $Name -ErrorAction Stop
    if ($task.State -eq 'Disabled') {
        Write-WatchdogLog "$Name is intentionally disabled; leaving it disabled."
        return
    }
    if ($task.State -eq 'Running') {
        Write-WatchdogLog "$Name is already starting or supervised; see its service log."
        return
    }
    Start-ScheduledTask -TaskName $Name -ErrorAction Stop
}

$Services = @(
    @{
        Name = "Wisdom Knowledge Graph"
        TaskName = "UuMA Wisdom Document View"
        Check = {
            try {
                $health = Invoke-RestMethod -Uri "http://127.0.0.1:8767/health" -TimeoutSec 3 -ErrorAction Stop
                return ($health.status -eq "ok" -and $health.service -eq "wisdom-view")
            } catch { return $false }
        }
        Revive = { Start-ManagedTask "UuMA Wisdom Document View" }
    },
    @{
        Name = "Scholar Web"
        TaskName = "UuMA Scholar Web"
        Check = { return (Test-LocalPort 8875) }
        Revive = { Start-ManagedTask "UuMA Scholar Web" }
    },
    @{
        Name = "UuMA Observatory"
        Check = { return (Test-LocalPort 8790) }
        Revive = {
            $supervisor = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction Stop |
                Where-Object { $_.CommandLine -match '-File.*run-observatory-service.ps1' }
            if ($supervisor) {
                Write-WatchdogLog "Observatory supervisor exists; inspect observatory.stderr.log for child startup errors."
                return
            }
            Start-ManagedTask "UuMA All-in-One Observatory Watchdog"
        }
    },

    @{
        Name  = "Hermes Gateway"
        Check = {
            $procs = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%' AND CommandLine LIKE '%hermes_cli.main gateway run%'" -ErrorAction SilentlyContinue
            return ($procs | Measure-Object).Count -gt 0
        }
        Revive = {
            $task = Get-ScheduledTask -TaskName "Hermes_Gateway" -ErrorAction SilentlyContinue
            if ($task) {
                Start-ScheduledTask -TaskName "Hermes_Gateway" -ErrorAction SilentlyContinue
            } else {
                Start-Process "wscript.exe" "//B //Nologo `"$BaseDir\Hermes_Gateway.vbs`"" -WindowStyle Hidden
            }
        }
    },
    @{
        Name  = "Hermes Web Dashboard"
        Check = {
            return (Test-LocalPort 9119)
        }
        Revive = {
            Start-Process "wscript.exe" "//B //Nologo `"$BaseDir\Hermes_Dashboard.vbs`"" -WindowStyle Hidden
        }
    },
    @{
        Name  = "Unlimited LLM API Router"
        Check = {
            try {
                $resp = Invoke-RestMethod -Uri "https://api.95963210.xyz/health" -TimeoutSec 3 -ErrorAction Stop
                return ($resp.status -eq "ok")
            } catch {
                try {
                    $resp2 = Invoke-RestMethod -Uri "http://192.168.55.2:8080/health" -TimeoutSec 3 -ErrorAction Stop
                    return ($resp2.status -eq "ok")
                } catch {
                    return $false
                }
            }
        }
        Revive = {
            Write-WatchdogLog "Unlimited LLM API Router is hosted on Ubuntu (systemd: unlimited-router.service). Please check server at https://api.95963210.xyz"
        }
    },
    @{
        Name  = "Cloudflared Agent"
        Check = {
            return (Get-Service -Name "Cloudflared" -ErrorAction SilentlyContinue).Status -eq "Running"
        }
        Revive = {
            Start-Service -Name "Cloudflared" -ErrorAction SilentlyContinue
        }
    },
    @{
        Name  = "UuMA ChatGPT Bridge"
        Check = {
            if (Test-LocalPort 8787) { return $true }
            $starting = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%' AND CommandLine LIKE '%uuma.chatgpt_cli%'" -ErrorAction SilentlyContinue
            return ($starting | Measure-Object).Count -gt 0
        }
        Revive = {
            Start-ScheduledTask -TaskName "UuMA ChatGPT Bridge" -ErrorAction SilentlyContinue
        }
    },
    @{
        Name  = "Phoenix Observability"
        Check = {
            return (Test-LocalPort 6006)
        }
        Revive = {
            Start-ScheduledTask -TaskName "UuMA Phoenix" -ErrorAction SilentlyContinue
        }
    },
    @{
        Name  = "Graph App"
        Check = {
            return (Test-LocalPort 8766)
        }
        Revive = {
            $yoncLauncher = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Yonc UI.vbs"
            if (Test-Path $yoncLauncher) {
                Start-Process "wscript.exe" "//B //Nologo `"$yoncLauncher`"" -WindowStyle Hidden
            } else {
                $yoncScript = "C:\Users\Alandelone\CodeSpace_Local\yonc_agent\scripts\start-yonc.ps1"
                if (Test-Path $yoncScript) {
                    Start-Process conhost.exe -ArgumentList "--headless powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$yoncScript`" -Port 8766" -WindowStyle Hidden
                }
            }
        }
    },
    @{
        Name  = "Live Agent (Voice UI & Runtime)"
        TaskName = "UuMA Live Agent"
        Check = {
            $uiOk = $false
            try {
                $resp = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:5173/live/" -TimeoutSec 2 -ErrorAction SilentlyContinue
                $uiOk = ($resp.StatusCode -eq 200)
            } catch { $uiOk = $false }
            if (-not $uiOk) { return $false }
            return (Test-LocalPort 8765)
        }
        Revive = {
            Start-ManagedTask "UuMA Live Agent"
        }
    },
    @{
        Name  = "Xiaohongshu Extension Bridge"
        Check = {
            return (Test-LocalPort 17863)
        }
        Revive = {
            $bridgeVbs = "C:\Users\Alandelone\CodeSpace_Local\multimode_data_process\start_bridge.vbs"
            if (Test-Path $bridgeVbs) {
                Start-Process "wscript.exe" "//B //Nologo `"$bridgeVbs`"" -WindowStyle Hidden
            }
        }
    },

    @{
        Name  = "Dashboard Windows Node Reporter"
        Check = {
            return (Test-NetConnection 127.0.0.1 -Port 8780 -WarningAction SilentlyContinue).TcpTestSucceeded
        }
        Revive = {
            $agent = "C:\Users\Alandelone\CodeSpace_Local\deepseek_dash\windows_node_agent.py"
            $py = "C:\Users\Alandelone\AppData\Local\Programs\Python\Python312\python.exe"
            if ((Test-Path $agent) -and (Test-Path $py)) {
                Start-Process "conhost.exe" "--headless `"$py`" `"$agent`"" -WindowStyle Hidden
            }
        }
    }
)

function Invoke-WatchdogCycle {
    if (Test-Path $PauseFlag) {
        Write-WatchdogLog "Watchdog is paused (found watchdog.disabled). Skipping cycle."
        return
    }

    foreach ($svc in $Services) {
        if ($ServiceName.Count -gt 0 -and $svc.Name -notin $ServiceName) { continue }
        if ($svc.ContainsKey('TaskName')) {
            $managedTask = Get-ScheduledTask -TaskName $svc.TaskName -ErrorAction SilentlyContinue
            if ($managedTask -and $managedTask.State -eq 'Disabled') {
                if ($DryRun) { Write-Host "[PAUSED] $($svc.Name) is intentionally disabled." }
                continue
            }
        }
        $isHealthy = $false
        try {
            $isHealthy = & $svc.Check
        } catch {
            $isHealthy = $false
        }

        if ($isHealthy) {
            if ($DryRun) {
                Write-Host "[OK] $($svc.Name) is running." -ForegroundColor Green
            }
        } else {
            if ($DryRun) {
                Write-Host "[DOWN] $($svc.Name) is NOT running (DryRun - no restart action taken)." -ForegroundColor Yellow
            } else {
                Write-WatchdogLog "WARNING: $($svc.Name) is down! Attempting restart..."
                try {
                    & $svc.Revive
                    Write-WatchdogLog "Recovery action evaluated for $($svc.Name); health is checked separately."
                } catch {
                    Write-WatchdogLog "ERROR: Failed to restart $($svc.Name): $($_.Exception.Message)"
                }
            }
        }
    }
}

if ($Daemon) {
    Write-WatchdogLog "Multi-service watchdog daemon started. Monitoring $($Services.Count) services every $IntervalSeconds seconds."
    while ($true) {
        Invoke-WatchdogCycle
        Start-Sleep -Seconds $IntervalSeconds
    }
} else {
    Invoke-WatchdogCycle
}
