# Windows agent service recovery

Writing Studio 的 3000 前端与 8874 API 自 2026-10-21 起由独立登录任务管理，
包括子进程退出后自动恢复；见 [Writing Studio 启动与恢复](writing-studio-service-recovery.md)。

The Windows-only repair on 2026-10-19 restored Observatory (8790), Scholar Web
(8875), and Live Agent UI/gateway (5173/8765). The user explicitly chose to keep
Telegram reception on Hermes `forge-lab-bot`. The obsolete direct AntiGravity Telegram bridge was removed from tasks,
monitoring, recovery and installation on 2026-10-20. Hermes owns Telegram reception.

## Startup and recovery

- Observatory's existing login task runs `scripts/run-observatory-service.ps1`.
  The launcher now supplies the repository `src` path and UTF-8 environment.
- `UuMA Scholar Web` and `UuMA Live Agent` are login tasks with a 45-second delay,
  duplicate-instance suppression and three one-minute failure retries.
- The shared `Hermes_MultiService_Watchdog` task checks every two minutes. Its
  deployed script is preserved at `deploy/windows/Hermes_MultiService_Watchdog.ps1`.
  It covers Scholar and Observatory, and checks Live Agent
  ports even when deployment state is absent. Disabled managed tasks are PAUSED.
- Launches use a headless console and a per-service mutex. Running services are
  reused. Live recovery verifies process ownership, preserves old deployment state,
  and retains the shared Hermes dashboard and state daemon.
- New runner logs are under `.uuma-local/windows-service-logs/` to avoid packaged
  application redirection of LocalAppData. Existing Observatory logs stay under
  `%LOCALAPPDATA%/UuMA/logs/`. Live component logs stay in its repository's
  `.runtime-data/logs/`.

Install/update the two managed tasks using Windows PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-windows-agent-services.ps1
```

The installer preserves intentionally disabled active tasks. To deploy the saved watchdog, copy the script to
`%LOCALAPPDATA%/hermes/gateway-service/Hermes_MultiService_Watchdog.ps1` after
preserving any local changes to that deployed file.

For a Windows-only read-only health check in a PowerShell process with script
execution enabled:

```powershell
& .\deploy\windows\Hermes_MultiService_Watchdog.ps1 -DryRun -ServiceName @(
    "Scholar Web", "UuMA Observatory", "Live Agent (Voice UI & Runtime)",
    "AntiGravity Telegram Bridge"
)
```

## Verification and limits

`tests/windows/test-service-recovery.ps1` checks unrelated-process protection,
bridge invocation identity, readiness, absent-state behavior, dry-run safety and
disabled-task preservation with deterministic mocks. It does not touch real
processes or scheduled tasks.

Actual restoration was exercised by stopping verified owned Scholar/Vite
listeners and dispatching their startup tasks. Scholar returned HTTP 200 and a
new listener; Live Agent rebuilt successfully, retained Gemini mode and started a
new deployment with both ports available. Repeating the Live task while healthy
completed with code 0 and reused the existing stack. Observatory returned HTTP 200.
The Windows reporter then showed 14 UP and the direct bridge DOWN, which is its
expected intentionally paused state. The shared watchdog reports that item PAUSED.

No host reboot, speech/model inference, or Ubuntu 5050 deployment was performed.
The Windows-hosted Debian WSL dependency was used for Live Agent. Existing Live
Agent user changes were preserved; only startup cwd, distribution forwarding and
frontend error handling were adjusted. Original files, task XML and a pre-start
catalog backup are preserved under `.uuma-local/windows-service-repair-20261019/`.
The Scholar Web startup uses the existing authoritative RSTV4 catalog, rather than
starting a test copy or spawning PaperPool model workers.
