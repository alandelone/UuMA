# Deterministic regression checks: no real processes, tasks or endpoints are changed.
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$runner = Join-Path $repo "scripts\run-windows-agent-service.ps1"
$watchdog = Join-Path $repo "deploy\windows\Hermes_MultiService_Watchdog.ps1"
$tokens = $null
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($runner, [ref]$tokens, [ref]$errors)
if ($errors) { throw ($errors | Out-String) }
foreach ($name in @("Get-Listener", "Test-LiveReady", "Stop-OwnedListener")) {
    $definition = $ast.Find({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name }, $true)
    if (-not $definition) { throw "Missing function $name" }
    . ([scriptblock]::Create($definition.Extent.Text))
}

function Assert-True([bool]$Value, [string]$Message) { if (-not $Value) { throw $Message } }
function Write-ServiceLog([string]$Message) {}
$global:RecoveryFixture = @{ ListenerPresent = $true; OwnerCommand = "unrelated-process.exe"; Stopped = @() }
function Get-NetTCPConnection { param($State, $LocalPort, $ErrorAction) if ($global:RecoveryFixture.ListenerPresent) { [pscustomobject]@{ OwningProcess = 4242 } } }
function Get-CimInstance { param($ClassName, $Filter) [pscustomobject]@{ ProcessId = 4242; CommandLine = $global:RecoveryFixture.OwnerCommand } }
function Stop-Process { param($Id, $ErrorAction) $global:RecoveryFixture.Stopped += $Id }
function Invoke-WebRequest { param([switch]$UseBasicParsing, $Uri, $TimeoutSec, $ErrorAction) [pscustomobject]@{ StatusCode = 200 } }

$rejected = $false
try { Stop-OwnedListener 5173 'C:\live\vite.js' } catch { $rejected = $_.Exception.Message -like '*unexpected process*' }
Assert-True $rejected "An unrelated port owner must be rejected."
Assert-True ($global:RecoveryFixture.Stopped.Count -eq 0) "An unrelated process must never be stopped."
$global:RecoveryFixture.OwnerCommand = 'node.exe C:\live\vite.js preview'
Stop-OwnedListener 5173 'C:\live\vite.js'
Assert-True ($global:RecoveryFixture.Stopped.Count -eq 1 -and $global:RecoveryFixture.Stopped[0] -eq 4242) "Only a verified listener may be stopped."
$global:RecoveryFixture.ListenerPresent = $false
Assert-True (-not (Test-LiveReady)) "An HTTP response alone cannot make a missing gateway healthy."
$global:RecoveryFixture.ListenerPresent = $true
Assert-True (Test-LiveReady) "Both listeners and HTTP 200 should establish startup readiness."

# Reproduce the absent-state bug while both ports are down; dry run must report DOWN.
function Test-Path { param($Path) if ($Path -like '*state.json' -or $Path -like '*.disabled') { return $false }; return $true }
function New-Item { throw "Unexpected filesystem mutation" }
function Start-ScheduledTask { throw "Dry run must not start tasks" }
function Get-ScheduledTask { param($TaskName, $ErrorAction) [pscustomobject]@{ State = 'Ready' } }
$global:RecoveryFixture.ListenerPresent = $false
function Invoke-WebRequest { throw "Mock endpoint unavailable" }
$down = & $watchdog -DryRun -ServiceName @("Live Agent (Voice UI & Runtime)") 6>&1 | Out-String
$ErrorActionPreference = "Stop"
Assert-True ($down -match '\[DOWN\].*Live Agent') "Missing state plus missing ports must report DOWN."
$global:RecoveryFixture.ListenerPresent = $true
function Invoke-WebRequest { param([switch]$UseBasicParsing, $Uri, $TimeoutSec, $ErrorAction) [pscustomobject]@{ StatusCode = 200 } }
$up = & $watchdog -DryRun -ServiceName @("Live Agent (Voice UI & Runtime)") 6>&1 | Out-String
$ErrorActionPreference = "Stop"
Assert-True ($up -match '\[OK\].*Live Agent') "Healthy ports and UI must report OK. Captured: $up"

$watchAst = [Management.Automation.Language.Parser]::ParseFile($watchdog, [ref]$tokens, [ref]$errors)
if ($errors) { throw ($errors | Out-String) }
$start = $watchAst.Find({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Start-ManagedTask' }, $true)
. ([scriptblock]::Create($start.Extent.Text))
function Get-ScheduledTask { param($TaskName, $ErrorAction) [pscustomobject]@{ State = 'Disabled' } }
function Write-WatchdogLog([string]$Message) {}
Start-ManagedTask "Intentionally disabled service"

# Fresh installs register active services and preserve intentionally disabled tasks.
$global:RecoveryFixture.Installed = @()
$global:RecoveryFixture.Disabled = @()
$global:RecoveryFixture.ExistingDisabled = $false
function New-ScheduledTaskPrincipal { [pscustomobject]@{} }
function New-ScheduledTaskSettingsSet { [pscustomobject]@{} }
function New-ScheduledTaskTrigger { [pscustomobject]@{ Delay = '' } }
function New-ScheduledTaskAction { [pscustomobject]@{} }
function Get-ScheduledTask {
    param($TaskName, $ErrorAction)
    if ($global:RecoveryFixture.ExistingDisabled) { [pscustomobject]@{ State = 'Disabled' } }
}
function Register-ScheduledTask {
    param($TaskName, $Action, $Trigger, $Principal, $Settings, [switch]$Force)
    $global:RecoveryFixture.Installed += $TaskName
}
function Disable-ScheduledTask { param($TaskName) $global:RecoveryFixture.Disabled += $TaskName }
$installer = Join-Path $repo 'scripts\install-windows-agent-services.ps1'
& $installer -ProjectRoot $repo
Assert-True ($global:RecoveryFixture.Installed.Count -eq 2) "Only the two active service tasks must be registered."
Assert-True ($global:RecoveryFixture.Disabled.Count -eq 0) "Fresh active tasks should remain enabled."
$global:RecoveryFixture.Disabled = @()
$global:RecoveryFixture.ExistingDisabled = $true
& $installer -ProjectRoot $repo
Assert-True ('UuMA Scholar Web' -in $global:RecoveryFixture.Disabled -and 'UuMA Live Agent' -in $global:RecoveryFixture.Disabled) "Other intentionally disabled tasks must remain disabled."
Write-Host "PASS: owner protection, readiness, absent-state recovery, dry-run safety and active service installation policy."
