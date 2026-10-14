$ErrorActionPreference='Stop'
$receipt=Get-Content -LiteralPath '.tmp/scholar-review-recovery-services-v1.json' -Raw|ConvertFrom-Json
if(!$receipt.software_fixture_only -or $receipt.port -ne 8887){throw 'Wrong review fixture identity.'}
$all=@(Get-CimInstance Win32_Process)
$root=$all|Where-Object ProcessId -eq ([int]$receipt.catalog_process)
if(!$root -or $root.CommandLine -notlike '*scholar-review-recovery-server-v1.py*--root*scholar-review-recovery-2026-10-06-*--port 8887*' -or $root.CommandLine -notlike "*$($receipt.root)*"){throw 'Review fixture process identity is unverified.'}
$owned=[System.Collections.Generic.List[int]]::new();$owned.Add([int]$root.ProcessId)
do{$changed=$false;foreach($item in $all){if($owned.Contains([int]$item.ParentProcessId) -and !$owned.Contains([int]$item.ProcessId)){$owned.Add([int]$item.ProcessId);$changed=$true}}}while($changed)
$listeners=@(Get-NetTCPConnection -LocalPort 8887 -State Listen -ErrorAction SilentlyContinue)
if(!$listeners.Count){throw 'Owned review fixture is not listening.'}
foreach($item in $listeners){if(!$owned.Contains([int]$item.OwningProcess)){throw 'Review port has another owner.'}}
Write-Output 'Actual owned review-recovery process and listener verified.'
