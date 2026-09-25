<#
.SYNOPSIS
    Manages the Wisdom-Oldman Question Orbit runner lifecycle on demand.

.DESCRIPTION
    Provides clean on-demand control over the Question Orbit background runner:
    - Status: Inspects running process, Windows task state, lock file, and pending orbit tasks.
    - Start: Launches the runner on demand in the background.
    - Stop: Gracefully stops the runner process and task, ensuring no unintended restarts.
    - RunOnce: Executes a single research cycle in the foreground and exits.
    - Restart: Stops and immediately restarts the runner.

.EXAMPLE
    .\scripts\manage-orbit-runner.ps1 -Status
    .\scripts\manage-orbit-runner.ps1 -Start
    .\scripts\manage-orbit-runner.ps1 -Stop
    .\scripts\manage-orbit-runner.ps1 -RunOnce
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet("status", "start", "stop", "run-once", "run_once", "once", "restart")]
    [string]$Action = "status",
    [switch]$Start,
    [switch]$Stop,
    [switch]$Status,
    [switch]$RunOnce,
    [switch]$Restart,
    [string]$PythonExe,
    [string]$ProjectRoot,
    [string]$DataDir = "$env:LOCALAPPDATA\UuMA",
    [string]$ProfileHome = "$env:LOCALAPPDATA\hermes\profiles\wisdom-oldman",
    [string]$TaskName = "UuMA Question Orbit Runner"
)

$ErrorActionPreference = "Stop"

$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Definition }
if (-not $ProjectRoot) {
    $ProjectRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
}
if (-not $PythonExe) {
    $PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}

if ($Start) { $Action = "start" }
elseif ($Stop) { $Action = "stop" }
elseif ($RunOnce) { $Action = "run-once" }
elseif ($Restart) { $Action = "restart" }
elseif ($Status) { $Action = "status" }
if ($Action -in @("run_once", "once")) { $Action = "run-once" }

$resolvedPython = (Resolve-Path -LiteralPath $PythonExe).Path
$resolvedProject = (Resolve-Path -LiteralPath $ProjectRoot).Path
$resolvedProfile = (Resolve-Path -LiteralPath $ProfileHome).Path

function Resolve-EffectiveDataDir {
    param([string]$Candidate)

    if (-not (Test-Path -LiteralPath $Candidate)) {
        return $Candidate
    }
    $resolved = (Resolve-Path -LiteralPath $Candidate).Path
    foreach ($marker in @("wisdom.db", "uuma.db")) {
        $markerPath = Join-Path $resolved $marker
        if (-not (Test-Path -LiteralPath $markerPath)) { continue }
        $item = Get-Item -LiteralPath $markerPath
        $targets = @(@($item.Target) | Where-Object { $_ })
        if ($targets.Count -gt 0) {
            return (Split-Path -Parent ([IO.Path]::GetFullPath($targets[0])))
        }
    }
    return $resolved
}

$resolvedDataDir = Resolve-EffectiveDataDir -Candidate $DataDir
$lifecycleLog = Join-Path $resolvedDataDir "orbit-runner-lifecycle.log"

function Write-Lifecycle {
    param([string]$Message)
    if (Test-Path -LiteralPath $resolvedDataDir) {
        $timestamp = (Get-Date).ToUniversalTime().ToString("o")
        Add-Content -LiteralPath $lifecycleLog -Value "$timestamp $Message" -Encoding utf8 -ErrorAction SilentlyContinue
    }
}

function Get-RunnerProcesses {
    param([string]$ProfilePath)

    $profilePattern = [regex]::Escape($ProfilePath)
    return @(
        Get-CimInstance Win32_Process | Where-Object {
            $_.Name -in @("python.exe", "pythonw.exe") -and
            $_.CommandLine -match '(?i)-m\s+uuma\.orbit_runner(?:\s|$)' -and
            $_.CommandLine -match $profilePattern
        }
    )
}

function Stop-RunnerProcessesSafe {
    param([string]$ProfilePath)

    $procs = Get-RunnerProcesses -ProfilePath $ProfilePath
    foreach ($p in ($procs | Sort-Object ParentProcessId -Descending)) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    if ($procs.Count -gt 0) {
        Start-Sleep -Milliseconds 500
    }
    $remaining = Get-RunnerProcesses -ProfilePath $ProfilePath
    if ($remaining.Count -gt 0) {
        foreach ($p in $remaining) {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Get-DatabaseStats {
    param([string]$DatabaseDir)

    $dbPath = Join-Path $DatabaseDir "wisdom.db"
    if (-not (Test-Path -LiteralPath $dbPath)) {
        return @{ Found = $false; ActiveOrbits = 0; TotalOrbits = 0; PendingFrontier = 0 }
    }
    try {
        $pySnippet = @"
import sqlite3, json, sys
try:
    conn = sqlite3.connect(sys.argv[1])
    cur = conn.cursor()
    active = cur.execute("SELECT COUNT(*) FROM question_orbits WHERE status IN ('QUEUED', 'ACTIVE')").fetchone()[0]
    total = cur.execute("SELECT COUNT(*) FROM question_orbits").fetchone()[0]
    frontier = cur.execute("SELECT COUNT(*) FROM orbit_frontier WHERE status = 'PENDING'").fetchone()[0]
    print(json.dumps({'found': True, 'active': active, 'total': total, 'frontier': frontier}))
except Exception as e:
    print(json.dumps({'found': True, 'error': str(e), 'active': 0, 'total': 0, 'frontier': 0}))
"@
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($pySnippet)
        $b64 = [Convert]::ToBase64String($bytes)
        $raw = & $resolvedPython -c "import base64, sys; exec(base64.b64decode('$b64').decode('utf-8'))" "$dbPath"
        $res = $raw | ConvertFrom-Json
        return @{
            Found = $true
            ActiveOrbits = $res.active
            TotalOrbits = $res.total
            PendingFrontier = $res.frontier
        }
    }
    catch {
        return @{ Found = $true; ActiveOrbits = "?"; TotalOrbits = "?"; PendingFrontier = "?" }
    }
}

switch ($Action) {
    "status" {
        Write-Host "=== Wisdom-Oldman Question Orbit Runner Status ===" -ForegroundColor Cyan
        
        # 1. Check Processes
        $procs = Get-RunnerProcesses -ProfilePath $resolvedProfile
        if ($procs.Count -gt 0) {
            $pids = ($procs.ProcessId) -join ", "
            Write-Host "  Process State     : " -NoNewline
            Write-Host "RUNNING (PID: $pids)" -ForegroundColor Green
        }
        else {
            Write-Host "  Process State     : " -NoNewline
            Write-Host "STOPPED" -ForegroundColor Yellow
        }

        # 2. Check Windows Scheduled Task
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($task) {
            $triggerDesc = if ($task.Triggers.Count -eq 0) {
                "On-Demand (No schedule/logon triggers)"
            } else {
                ($task.Triggers | ForEach-Object { $_.CimClass.CimClassName }) -join ", "
            }
            Write-Host "  Scheduled Task    : " -NoNewline
            Write-Host "$($task.State) [$TaskName]" -ForegroundColor Cyan
            Write-Host "  Task Triggers     : $triggerDesc"
        }
        else {
            Write-Host "  Scheduled Task    : Not registered" -ForegroundColor Gray
        }

        # 3. Check Legacy Watchdog Task
        $legacyWatchdog = Get-ScheduledTask -TaskName "UuMA Question Orbit Watchdog" -ErrorAction SilentlyContinue
        if ($legacyWatchdog) {
            Write-Host "  Legacy Watchdog   : " -NoNewline
            Write-Host "ACTIVE (Warning: 1-min polling task still present)" -ForegroundColor Red
        }
        else {
            Write-Host "  Legacy Watchdog   : " -NoNewline
            Write-Host "None (Clean on-demand architecture)" -ForegroundColor Green
        }

        # 4. Check Lock File
        $lockFile = Join-Path $resolvedDataDir "orbit-runner.lock"
        if (Test-Path -LiteralPath $lockFile) {
            try {
                $lockContent = Get-Content -LiteralPath $lockFile -Raw -ErrorAction SilentlyContinue
                Write-Host "  Lock File         : Present ($lockContent)"
            } catch {
                Write-Host "  Lock File         : Present (Locked by process)"
            }
        }
        else {
            Write-Host "  Lock File         : None"
        }

        # 5. Database queue stats
        $stats = Get-DatabaseStats -DatabaseDir $resolvedDataDir
        if ($stats.Found) {
            Write-Host "  Queue Stats       : $($stats.ActiveOrbits) active orbits, $($stats.PendingFrontier) pending frontier items (Total: $($stats.TotalOrbits) orbits)"
        }
        Write-Host ""
        Write-Host "Controls:"
        Write-Host "  Start in background : .\scripts\manage-orbit-runner.ps1 -Start"
        Write-Host "  Stop runner         : .\scripts\manage-orbit-runner.ps1 -Stop"
        Write-Host "  Run single cycle    : .\scripts\manage-orbit-runner.ps1 -RunOnce"
        Write-Host "===================================================" -ForegroundColor Cyan
    }

    "start" {
        $procs = Get-RunnerProcesses -ProfilePath $resolvedProfile
        if ($procs.Count -gt 0) {
            $pids = ($procs.ProcessId) -join ", "
            Write-Host "Question Orbit runner is already running (PID: $pids)." -ForegroundColor Yellow
            return
        }

        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($task) {
            Write-Host "Starting Question Orbit runner via Task Scheduler..." -ForegroundColor Cyan
            Start-ScheduledTask -TaskName $TaskName
        }
        else {
            Write-Host "Launching Question Orbit runner launcher in background..." -ForegroundColor Cyan
            $launcher = Join-Path $resolvedProject "scripts\start-orbit-runner.ps1"
            $psi = New-Object System.Diagnostics.ProcessStartInfo
            $psi.FileName = "powershell.exe"
            $psi.Arguments = "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$launcher`" -PythonExe `"$resolvedPython`" -ProjectRoot `"$resolvedProject`" -DataDir `"$resolvedDataDir`" -ProfileHome `"$resolvedProfile`""
            $psi.CreateNoWindow = $true
            $psi.UseShellExecute = $false
            [System.Diagnostics.Process]::Start($psi) | Out-Null
        }

        # Wait and verify
        Start-Sleep -Seconds 1
        $runningProcs = Get-RunnerProcesses -ProfilePath $resolvedProfile
        if ($runningProcs.Count -gt 0) {
            $pids = ($runningProcs.ProcessId) -join ", "
            Write-Lifecycle "control_plane_started_runner task=$TaskName pids=$pids"
            Write-Host "Question Orbit runner started successfully (PID: $pids)." -ForegroundColor Green
        }
        else {
            Write-Host "Question Orbit runner start command issued. Check 'manage-orbit-runner.ps1 -Status'." -ForegroundColor Yellow
        }
    }

    "stop" {
        Write-Host "Stopping Question Orbit runner..." -ForegroundColor Cyan
        
        # Stop scheduled task if running
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($task -and $task.State -eq "Running") {
            Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        }

        # Stop processes
        Stop-RunnerProcessesSafe -ProfilePath $resolvedProfile

        # Verify
        $remaining = Get-RunnerProcesses -ProfilePath $resolvedProfile
        if ($remaining.Count -eq 0) {
            Write-Lifecycle "control_plane_stopped_runner task=$TaskName"
            Write-Host "Question Orbit runner stopped cleanly." -ForegroundColor Green
        }
        else {
            Write-Warning "Could not terminate all runner processes: $($remaining.ProcessId -join ', ')"
        }
    }

    "restart" {
        & $MyInvocation.MyCommand.Path -Stop `
            -PythonExe $PythonExe `
            -ProjectRoot $ProjectRoot `
            -DataDir $DataDir `
            -ProfileHome $ProfileHome `
            -TaskName $TaskName
        Start-Sleep -Milliseconds 800
        & $MyInvocation.MyCommand.Path -Start `
            -PythonExe $PythonExe `
            -ProjectRoot $ProjectRoot `
            -DataDir $DataDir `
            -ProfileHome $ProfileHome `
            -TaskName $TaskName
    }

    "run-once" {
        $procs = Get-RunnerProcesses -ProfilePath $resolvedProfile
        if ($procs.Count -gt 0) {
            $pids = ($procs.ProcessId) -join ", "
            Write-Host "Notice: A background Question Orbit runner is already active (PID: $pids)." -ForegroundColor Yellow
            Write-Host "Running an additional cycle directly..." -ForegroundColor Gray
        }

        Write-Host "Executing single Question Orbit research cycle..." -ForegroundColor Cyan
        $env:UUMA_DATA_DIR = $resolvedDataDir
        $sourcePath = Join-Path $resolvedProject "src"
        $env:PYTHONPATH = if ($env:PYTHONPATH) {
            "$sourcePath$([IO.Path]::PathSeparator)$env:PYTHONPATH"
        } else {
            $sourcePath
        }
        & $resolvedPython -m uuma.orbit_runner --profile-home $resolvedProfile --once
        $exitCode = $LASTEXITCODE
        if ($exitCode -eq 0) {
            Write-Host "Question Orbit single cycle completed successfully." -ForegroundColor Green
        } else {
            Write-Host "Question Orbit single cycle finished with exit code $exitCode." -ForegroundColor Yellow
        }
    }
}
