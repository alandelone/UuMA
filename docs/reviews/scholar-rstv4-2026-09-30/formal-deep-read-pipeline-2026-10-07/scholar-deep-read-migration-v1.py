import ast,hashlib,json,sqlite3,subprocess,time
from contextlib import closing
from pathlib import Path
from rstv4.database import initialize_catalog
repo=Path(__file__).resolve().parents[1]
cat=repo/'.tmp/scholar-overview-services.json';st=repo/'.tmp/scholar-ui-fixes-services.json'
c=json.loads(cat.read_text(encoding='utf-8'));root=Path(c['root']).resolve();assert root.name.startswith('scholar-ui-fixes-2026-10-03-')
db=root/'data/catalog.db';sha=lambda raw:hashlib.sha256(raw).hexdigest()
parent=json.loads((repo/'.tmp/scholar-frontier-original-final-v2.json').read_text(encoding='utf-8'));assert sha(db.read_bytes())==parent['database_sha256']
with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as conn:
 before={row[0]:conn.execute('SELECT * FROM "'+row[0]+'" ORDER BY rowid').fetchall() for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
 old_schema=conn.execute('SELECT * FROM sqlite_master ORDER BY name').fetchall()
 assert len(before)==105 and conn.execute("SELECT version FROM schema_version WHERE component='catalog'").fetchone()[0]==10
 for table in ['studio_jobs','research_discussion_jobs']:assert conn.execute('SELECT COUNT(*) FROM '+table+" WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')").fetchone()[0]==0
 with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as jobs:
  assert jobs.execute("SELECT COUNT(*) FROM acquisition_jobs WHERE queue_class LIKE 'MODEL%' AND status IN ('READY','RUNNING','RETRY_WAIT')").fetchone()[0]==0
backup=repo/'.tmp/scholar-deep-read-original-v10-v1';backup.mkdir(exist_ok=False)
for p in [cat,st,db]:
 with (backup/p.name).open('xb') as h:h.write(p.read_bytes())
with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(backup/'consistent-catalog-v10.db')) as target:src.backup(target)
script=r'''
$ErrorActionPreference='Stop'
$c=Get-Content -LiteralPath '.tmp/scholar-overview-services.json' -Raw|ConvertFrom-Json
$s=Get-Content -LiteralPath '.tmp/scholar-ui-fixes-services.json' -Raw|ConvertFrom-Json
$all=@(Get-CimInstance Win32_Process)
$catalog=$all|Where-Object ProcessId -eq ([int]$c.catalog_process)
$studio=$all|Where-Object ProcessId -eq ([int]$s.owned_processes.studio)
if(!$catalog -or $catalog.CommandLine -notlike '*scholar-overview-server.py*--root*scholar-ui-fixes-2026-10-03-8pn_4t3h*--port 8885*'){throw 'Catalog ownership unverified'}
if(!$studio -or $studio.CommandLine -notlike '*scholar-ui-fixes-services.py studio*'){throw 'Studio ownership unverified'}
$owned=@($catalog,$studio)
$consoleCompanions=@()
foreach($parent in @($catalog,$studio)){
 foreach($child in @($all|Where-Object ParentProcessId -eq $parent.ProcessId)){
  if($child.Name -eq 'conhost.exe' -and $child.ExecutablePath -eq (Join-Path $env:SystemRoot 'System32/conhost.exe')){$consoleCompanions+= $child;continue}
  if($child.CommandLine -ne $parent.CommandLine -and (($parent.ProcessId -eq $catalog.ProcessId -and $child.CommandLine -notlike '*scholar-overview-server.py*--root*scholar-ui-fixes-2026-10-03-8pn_4t3h*--port 8885*') -or ($parent.ProcessId -eq $studio.ProcessId -and $child.CommandLine -notlike '*scholar-ui-fixes-services.py studio*'))){throw 'Unexpected preview descendant'}
  $owned+= $child
 }
}
$verifiedIds=@($owned.ProcessId)+@($consoleCompanions.ProcessId)
foreach($p in $owned){foreach($child in @($all|Where-Object ParentProcessId -eq $p.ProcessId)){if($child.ProcessId -notin $verifiedIds){throw 'Unknown nested descendant; refuse maintenance'}}}
$listeners=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue|Where-Object LocalPort -in 8885,8874)
if($listeners.Count -ne 2){throw 'Expected two owned backend listeners'}
foreach($listener in $listeners){if($listener.OwningProcess -notin $owned.ProcessId){throw 'Listener belongs to another process'}}
[System.IO.File]::WriteAllText((Join-Path (Get-Location) '.tmp/scholar-deep-read-restart-authority-v1.json'),(@{processes=@($owned|Select-Object ProcessId,ParentProcessId,CommandLine);consoleCompanions=@($consoleCompanions|Select-Object ProcessId,ParentProcessId,CommandLine,ExecutablePath);listeners=@($listeners|Select-Object LocalPort,OwningProcess)}|ConvertTo-Json -Depth 10),[System.Text.UTF8Encoding]::new($false))
foreach($process in @($owned|Sort-Object ParentProcessId -Descending)){
 $fresh=Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ProcessId)"
 if($fresh){if($fresh.CommandLine -ne $process.CommandLine -or $fresh.ParentProcessId -ne $process.ParentProcessId){throw 'Ownership changed before restart'};Stop-Process -Id $process.ProcessId -ErrorAction Stop}
}
$closeDeadline=([DateTime]::UtcNow).AddSeconds(5)
while(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue|Where-Object LocalPort -in 8885,8874){if([DateTime]::UtcNow -ge $closeDeadline){throw 'Backend listeners did not close'};Start-Sleep -Milliseconds 200}
'''
subprocess.run(['powershell','-NoProfile','-Command',script],cwd=repo,check=True)
assert sha(db.read_bytes())==parent['database_sha256'], 'Original database changed before migration'
initialize_catalog(db)
with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as conn:
 after={row[0]:conn.execute('SELECT * FROM "'+row[0]+'" ORDER BY rowid').fetchall() for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
 for name,rows in before.items():
  if name=='schema_version':
   prior=[r for r in rows if r[0]!='catalog'];now=[r for r in after[name] if r[0]!='catalog'];assert now==prior
  else:assert after[name]==rows,name
 assert set(after)-set(before)=={'acquisition_model_call_events'} and len(after)==106
 assert all(not after[name] for name in set(after)-set(before))
 actual_schema=conn.execute('SELECT * FROM sqlite_master ORDER BY name').fetchall()
 assert all(row in actual_schema for row in old_schema if row[2]!='skeleton_runs')
 assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
 assert 'UNIQUE(parse_run_id, prompt_version, context_builder_version)' not in conn.execute("SELECT sql FROM sqlite_master WHERE name='skeleton_runs'").fetchone()[0]
 assert conn.execute("SELECT version FROM schema_version WHERE component='catalog'").fetchone()[0]==11
 canonical=lambda v:sha(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode())
 baseline={'database_sha256':sha(db.read_bytes()),'all_table_sha256':{name:canonical(rows) for name,rows in after.items()},'schema_sha256':canonical(actual_schema)}
with (repo/'.tmp/scholar-deep-read-post-migration-baseline-v1.json').open('x',encoding='utf-8') as h:json.dump(baseline,h,indent=2)
resume=r'''
$ErrorActionPreference='Stop'
$c=Get-Content -LiteralPath '.tmp/scholar-overview-services.json' -Raw|ConvertFrom-Json
$s=Get-Content -LiteralPath '.tmp/scholar-ui-fixes-services.json' -Raw|ConvertFrom-Json
if(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue|Where-Object LocalPort -in 8885,8874){throw 'A backend port has a new owner'}
$python=(Resolve-Path -LiteralPath '../RSTV4/.venv/Scripts/python.exe').Path
$backend=(Resolve-Path -LiteralPath '../RSTV4').Path
$rootPath=(Resolve-Path -LiteralPath $c.root).Path
$logs=(Resolve-Path -LiteralPath '.tmp').Path
foreach($name in @('catalog','studio')){if(Test-Path -LiteralPath (Join-Path $logs "scholar-deep-read-resumed-$name-v1.log")){throw 'Preserve resume logs'}}
$catalog=Start-Process -FilePath $python -ArgumentList @('-u',(Join-Path $logs 'scholar-overview-server.py'),'--root',$rootPath,'--port','8885') -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'scholar-deep-read-resumed-catalog-v1.log') -RedirectStandardError (Join-Path $logs 'scholar-deep-read-resumed-catalog-v1-error.log')
$studio=Start-Process -FilePath $python -ArgumentList @('-u',(Join-Path $logs 'scholar-ui-fixes-services.py'),'studio') -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'scholar-deep-read-resumed-studio-v1.log') -RedirectStandardError (Join-Path $logs 'scholar-deep-read-resumed-studio-v1-error.log')
$c.catalog_process=$catalog.Id;$c.catalog_mode='collection_frontier_budget_preview';$s.owned_processes.studio=$studio.Id
[System.IO.File]::WriteAllText((Join-Path $logs 'scholar-overview-services.json'),($c|ConvertTo-Json -Depth 20),[System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText((Join-Path $logs 'scholar-ui-fixes-services.json'),($s|ConvertTo-Json -Depth 20),[System.Text.UTF8Encoding]::new($false))
Write-Output 'Verified owned idle backends refreshed; frontend retained.'
'''
subprocess.run(['powershell','-NoProfile','-Command',resume],cwd=repo,check=True)
receipt={'status':'PASS_CONTROLLED_ORIGINAL_10_TO_11_MIGRATION','root':str(root),'old_table_count':105,'current_table_count':106,'old_tables_unchanged_except_catalog_schema_version':True,'old_schema_objects_preserved_except_declared_skeleton_run_history_constraint':True,'new_model_call_table_empty':True,'original_database_sha256':parent['database_sha256'],'current_database_sha256':baseline['database_sha256'],'models_added':0,'actual_scientific_approval':False}
with (repo/'.tmp/scholar-deep-read-migration-v1.json').open('x',encoding='utf-8') as h:json.dump(receipt,h,indent=2)
print(json.dumps(receipt))
