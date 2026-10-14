"""Restart only the verified, owned isolated Catalog to load discussion routes."""
import ast
import json
import os
import sqlite3
import subprocess
from pathlib import Path

repo=Path(__file__).resolve().parents[1]
os.environ.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
tree=ast.parse((repo/'.tmp/scholar-overview-native-v1.py').read_text(encoding='utf-8'))
guard=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='process_guard' for target in node.targets))
for check in [(repo/'.tmp/scholar-current-preview-proof.ps1').read_text(encoding='utf-8'),guard]:
 subprocess.run(['powershell','-NoProfile','-Command',check],cwd=repo,check=True)
receipt=json.loads((repo/'.tmp/scholar-overview-services.json').read_text(encoding='utf-8'))
root=Path(receipt['root']).resolve()
assert root.name.startswith('scholar-ui-fixes-2026-10-03-')
with sqlite3.connect(f'{(root/"data/catalog.db").as_uri()}?mode=ro',uri=True) as conn:
 if conn.execute("SELECT 1 FROM sqlite_master WHERE name='research_discussion_jobs'").fetchone():
  assert conn.execute("SELECT COUNT(*) FROM research_discussion_jobs WHERE status IN ('QUEUED','RUNNING')").fetchone()[0]==0,'Do not restart while a discussion may be live'
backup=repo/'.tmp/scholar-conversation-prior-catalog-v2.json'
with backup.open('xb') as out:out.write((repo/'.tmp/scholar-overview-services.json').read_bytes())
script=r'''
$ErrorActionPreference='Stop'
$receipt=Get-Content -LiteralPath '.tmp/scholar-overview-services.json' -Raw | ConvertFrom-Json
$all=@(Get-CimInstance Win32_Process)
$owned=[System.Collections.Generic.List[int]]::new();$owned.Add([int]$receipt.catalog_process)
do {$changed=$false;foreach($item in $all){if($owned.Contains([int]$item.ParentProcessId)-and !$owned.Contains([int]$item.ProcessId)){$owned.Add([int]$item.ProcessId);$changed=$true}}}while($changed)
$logs=(Resolve-Path -LiteralPath '.tmp').Path
foreach($name in @('scholar-conversation-catalog-v2.log','scholar-conversation-catalog-v2-error.log')){if(Test-Path -LiteralPath (Join-Path $logs $name)){throw 'Preserve the exclusive service log'}}
foreach($processId in ($owned|Sort-Object -Descending)){if(Get-Process -Id $processId -ErrorAction SilentlyContinue){Stop-Process -Id $processId -ErrorAction Stop}}
$python=(Resolve-Path -LiteralPath '../RSTV4/.venv/Scripts/python.exe').Path
$backend=(Resolve-Path -LiteralPath '../RSTV4').Path
$helper=(Resolve-Path -LiteralPath '.tmp/scholar-overview-server.py').Path
$rootPath=(Resolve-Path -LiteralPath $receipt.root).Path
$newCatalog=Start-Process -FilePath $python -ArgumentList @('-u',$helper,'--root',$rootPath,'--port','8885') -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'scholar-conversation-catalog-v2.log') -RedirectStandardError (Join-Path $logs 'scholar-conversation-catalog-v2-error.log')
$newReceipt=@{root=$rootPath;catalog_process=$newCatalog.Id;catalog_port=8885;production_data_changed=$false;catalog_mode='fixed_conversation_discussion_preview'}
[System.IO.File]::WriteAllText((Join-Path $logs 'scholar-overview-services.json'),($newReceipt|ConvertTo-Json -Depth 20),[System.Text.UTF8Encoding]::new($false))
Write-Output "Loaded discussion preview in original isolated root, Catalog process $($newCatalog.Id)."
'''
subprocess.run(['powershell','-NoProfile','-Command',script],cwd=repo,check=True)
