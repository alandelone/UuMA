$ErrorActionPreference='Stop'
$receipt=Get-Content -LiteralPath '.tmp/scholar-withdrawal-services-v1.json' -Raw|ConvertFrom-Json
if(!$receipt.software_fixture_only -or $receipt.port -ne 8888){throw 'Wrong withdrawal fixture.'}
$all=@(Get-CimInstance Win32_Process)
$root=$all|Where-Object ProcessId -eq ([int]$receipt.catalog_process)
if(!$root -or $root.CommandLine -notlike '*scholar-withdrawal-server-v1.py*--root*scholar-source-withdrawal-2026-10-06-*--port 8888*' -or $root.CommandLine -notlike "*$($receipt.root)*"){throw 'Withdrawal fixture ownership is unverified.'}
$owned=[System.Collections.Generic.List[int]]::new();$owned.Add([int]$root.ProcessId)
do{$changed=$false;foreach($item in $all){if($owned.Contains([int]$item.ParentProcessId) -and !$owned.Contains([int]$item.ProcessId)){$owned.Add([int]$item.ProcessId);$changed=$true}}}while($changed)
$listeners=@(Get-NetTCPConnection -LocalPort 8888 -State Listen -ErrorAction SilentlyContinue)
if(!$listeners.Count){throw 'Withdrawal fixture not listening.'}
foreach($item in $listeners){if(!$owned.Contains([int]$item.OwningProcess)){throw 'Withdrawal port has another owner.'}}
Write-Output 'Owned withdrawal fixture and listener verified.'
