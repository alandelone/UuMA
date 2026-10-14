$ErrorActionPreference = 'Stop'
$receipt = Get-Content -LiteralPath '.tmp/scholar-collection-fixture-services-v3.json' -Raw | ConvertFrom-Json
if(!$receipt.software_fixture_only -or $receipt.port -ne 8886){throw 'Wrong Collection fixture identity.'}
$all = @(Get-CimInstance Win32_Process)
$root = $all | Where-Object ProcessId -eq ([int]$receipt.catalog_process)
if(!$root -or $root.CommandLine -notlike '*scholar-collection-server-v1.py*--root*scholar-collection-2026-10-05-*--port 8886*'){throw 'Collection fixture root identity is unverified.'}
if($root.CommandLine -notlike "*$($receipt.root)*"){throw 'Collection fixture checkout does not match its receipt.'}
$owned = [System.Collections.Generic.List[int]]::new();$owned.Add([int]$root.ProcessId)
do{$changed=$false;foreach($item in $all){if($owned.Contains([int]$item.ParentProcessId) -and !$owned.Contains([int]$item.ProcessId)){$owned.Add([int]$item.ProcessId);$changed=$true}}}while($changed)
$listeners = @(Get-NetTCPConnection -LocalPort 8886 -State Listen -ErrorAction SilentlyContinue)
if(!$listeners.Count){throw 'Owned Collection fixture is not listening.'}
foreach($item in $listeners){if(!$owned.Contains([int]$item.OwningProcess)){throw 'Collection port has another owner.'}}
Write-Output 'Actual isolated Collection root and listener verified.'
