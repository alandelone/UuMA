# Native task definition contracts with isolated scheduler doubles and real admission fixtures.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Python,
    [Parameter(Mandatory = $true)][string]$FixtureRoot
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'test-scholar-catalog-reading.ps1') -Python $Python -FixtureRoot $FixtureRoot
$installer = Join-Path $repo 'scripts/install-scholar-catalog-reading.ps1'
$global:CatalogReadingTaskFixture = @{ Existing = $null; Registered = 0; Disabled = 0; Lookups = 0; Started = 0 }
function Get-ScheduledTask {
    [CmdletBinding()]param($TaskName)
    $global:CatalogReadingTaskFixture.Lookups++
    return $global:CatalogReadingTaskFixture.Existing
}
function New-ScheduledTaskPrincipal {
    param($UserId,$LogonType,$RunLevel)
    return [pscustomobject]@{ UserId=$UserId; LogonType=$LogonType; RunLevel=$RunLevel }
}
function New-ScheduledTaskSettingsSet {
    param([switch]$AllowStartIfOnBatteries,[switch]$DontStopIfGoingOnBatteries,$MultipleInstances,
        $ExecutionTimeLimit,$RestartCount,$RestartInterval,[switch]$StartWhenAvailable)
    return [pscustomobject]$PSBoundParameters
}
function New-ScheduledTaskTrigger {
    param([switch]$AtLogOn,$User,[switch]$Daily,$At)
    return [pscustomobject]@{ AtLogOn=$AtLogOn.IsPresent; User=$User; Daily=$Daily.IsPresent; At=$At; Delay='' }
}
function New-ScheduledTaskAction {
    param($Execute,$WorkingDirectory,$Argument)
    return [pscustomobject]@{ Execute=$Execute; WorkingDirectory=$WorkingDirectory; Arguments=$Argument }
}
function Register-ScheduledTask {
    param($TaskName,$Action,$Trigger,$Principal,$Settings,[switch]$Force)
    $global:CatalogReadingTaskFixture.Registered++
    $global:CatalogReadingTaskFixture.Definition = [pscustomobject]@{
        TaskName=$TaskName; Action=$Action; Trigger=$Trigger; Principal=$Principal; Settings=$Settings }
}
function Export-ScheduledTask { param($TaskName) return '<Task fixture="true" />' }
function Disable-ScheduledTask { param($TaskName) $global:CatalogReadingTaskFixture.Disabled++ }
function Start-ScheduledTask { param($TaskName) throw 'Installer must never start a task.' }

$case = New-WorkerCase 'task preview with spaces'
$preview = (& $installer -ManifestPath $case.Path -DataRoot $case.Owner -ProjectRoot $repo) | ConvertFrom-Json
Assert-True (-not $preview.installed -and -not $preview.started) 'Preview changed task state.'
Assert-True ($global:CatalogReadingTaskFixture.Lookups -eq 0 -and $global:CatalogReadingTaskFixture.Registered -eq 0) 'Preview accessed scheduler state.'
Assert-True ($preview.automatic_window -eq '00:00-08:00 Asia/Kuala_Lumpur' -and $preview.manual_priority) 'Task changed the authorized reading policy.'
Assert-True ($preview.daily_start -eq '00:00') 'Preview omitted the daily recovery trigger.'
$receipts = Join-Path $FixtureRoot 'task receipts'
$installed = (& $installer -ManifestPath $case.Path -DataRoot $case.Owner -ProjectRoot $repo -ReceiptRoot $receipts -Apply) | ConvertFrom-Json
$definition = $global:CatalogReadingTaskFixture.Definition
Assert-True ($installed.installed -and -not $installed.started -and $global:CatalogReadingTaskFixture.Registered -eq 1) 'Explicit installation did not register exactly one unstarted task.'
Assert-True ($definition.TaskName -eq 'UuMA Scholar Catalog Reading') 'Installer targeted another service.'
Assert-True ($definition.Action.Execute -eq 'conhost.exe' -and $definition.Action.Arguments -like '*-WindowStyle Hidden*') 'Task does not use a hidden foreground supervisor.'
Assert-True ($definition.Settings.MultipleInstances -eq 'IgnoreNew' -and $definition.Settings.RestartCount -eq 3) 'Task lost singleton or bounded restart supervision.'
Assert-True ($definition.Settings.RestartInterval.TotalSeconds -eq 60 -and $definition.Settings.ExecutionTimeLimit.TotalSeconds -eq 0) 'Task lost its persistent-worker timing contract.'
$logonTriggers = @($definition.Trigger | Where-Object { $_.AtLogOn })
$dailyTriggers = @($definition.Trigger | Where-Object { $_.Daily })
Assert-True (@($definition.Trigger).Count -eq 2 -and $logonTriggers.Count -eq 1 -and $dailyTriggers.Count -eq 1) 'Task must recover at midnight as well as at login.'
Assert-True ($dailyTriggers[0].At -eq '00:00') 'Daily recovery must start at the night window boundary.'
Assert-True ($logonTriggers[0].Delay -eq 'PT45S' -and $definition.Principal.LogonType -eq 'Interactive') 'Task lost the explicit user startup identity.'
Assert-True (Test-Path -LiteralPath (Join-Path $installed.receipt_root 'installed.xml')) 'Installation receipt is missing.'

$global:CatalogReadingTaskFixture.Existing = [pscustomobject]@{ State='Ready'; Actions=@([pscustomobject]@{
    Execute='unexpected.exe'; Arguments=''; WorkingDirectory=$repo }) }
$rejected = $false
try { $null = & $installer -ManifestPath $case.Path -DataRoot $case.Owner -ProjectRoot $repo -ReceiptRoot $receipts -Apply }
catch {
    if ($_.Exception.Message -notlike '*unexpected action*') { throw }
    $rejected = $true
}
Assert-True ($rejected -and $global:CatalogReadingTaskFixture.Registered -eq 1) 'Installer overwrote an unexpected existing task.'
$global:CatalogReadingTaskFixture.Existing = [pscustomobject]@{ State='Disabled'; Actions=@($definition.Action) }
$disabled = (& $installer -ManifestPath $case.Path -DataRoot $case.Owner -ProjectRoot $repo -ReceiptRoot $receipts -Apply) | ConvertFrom-Json
Assert-True ($global:CatalogReadingTaskFixture.Registered -eq 2 -and $global:CatalogReadingTaskFixture.Disabled -eq 1 -and -not $disabled.started) 'Installer did not preserve the disabled state.'
[ordered]@{ task_installer_cases=4; passed=4; real_scheduler_mutations=0; real_services_started=0;
    real_model_calls=0; real_catalog_modified=$false } | ConvertTo-Json -Depth 6
