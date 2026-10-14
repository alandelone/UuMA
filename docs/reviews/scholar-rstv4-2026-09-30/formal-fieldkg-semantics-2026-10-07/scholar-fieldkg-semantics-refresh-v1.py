import ast
import hashlib
import json
import sqlite3
import subprocess
import time
from contextlib import closing
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
authority = repo / '.tmp/scholar-overview-services.json'
owned = json.loads(authority.read_text(encoding='utf-8'))
root = Path(owned['root']).resolve()
assert root.name == 'scholar-ui-fixes-2026-10-03-8pn_4t3h'
db = root / 'data/catalog.db'
parent = json.loads((repo / '.tmp/scholar-durable-model-original-final-v1.json').read_text(encoding='utf-8'))
sha = lambda raw: hashlib.sha256(raw).hexdigest()
assert sha(db.read_bytes()) == parent['database_sha256']
with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as conn:
    for table in ['studio_jobs', 'research_discussion_jobs']:
        assert conn.execute('SELECT COUNT(*) FROM ' + table + " WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM acquisition_jobs WHERE status IN ('RUNNING')").fetchone()[0] == 0
backup = repo / '.tmp/scholar-fieldkg-semantics-preview-before-v1'
backup.mkdir(exist_ok=False)
for path in [authority, db]:
    with (backup / path.name).open('xb') as handle:
        handle.write(path.read_bytes())
with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as original, closing(sqlite3.connect(backup / 'consistent-catalog-v11.db')) as target:
    original.backup(target)
guard = r'''
$ErrorActionPreference='Stop'
$c=Get-Content -LiteralPath '.tmp/scholar-overview-services.json' -Raw|ConvertFrom-Json
$all=@(Get-CimInstance Win32_Process)
$catalog=$all|Where-Object ProcessId -eq ([int]$c.catalog_process)
if(!$catalog -or $catalog.CommandLine -notlike '*scholar-overview-server.py*--root*scholar-ui-fixes-2026-10-03-8pn_4t3h*--port 8885*'){throw 'Catalog ownership unverified'}
$owned=@($catalog);$console=@()
foreach($child in @($all|Where-Object ParentProcessId -eq $catalog.ProcessId)){
 if($child.Name -eq 'conhost.exe' -and $child.ExecutablePath -eq (Join-Path $env:SystemRoot 'System32/conhost.exe')){$console+=$child;continue}
 if($child.CommandLine -ne $catalog.CommandLine -and $child.CommandLine -notlike '*scholar-overview-server.py*--root*scholar-ui-fixes-2026-10-03-8pn_4t3h*--port 8885*'){throw 'Unexpected Catalog descendant'}
 $owned+=$child
}
$verified=@($owned.ProcessId)+@($console.ProcessId)
foreach($p in $owned){foreach($child in @($all|Where-Object ParentProcessId -eq $p.ProcessId)){if($child.ProcessId -notin $verified){throw 'Unknown nested descendant'}}}
$listeners=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue|Where-Object LocalPort -eq 8885)
if($listeners.Count -ne 1 -or $listeners[0].OwningProcess -notin $owned.ProcessId){throw 'Catalog listener ownership unverified'}
[System.IO.File]::WriteAllText((Join-Path (Get-Location) '.tmp/scholar-fieldkg-semantics-refresh-authority-v1.json'),(@{processes=@($owned|Select-Object ProcessId,ParentProcessId,CommandLine);console=@($console|Select-Object ProcessId,ParentProcessId,ExecutablePath);listeners=@($listeners|Select-Object LocalPort,OwningProcess)}|ConvertTo-Json -Depth 10),[System.Text.UTF8Encoding]::new($false))
foreach($p in @($owned|Sort-Object ParentProcessId -Descending)){
 $fresh=Get-CimInstance Win32_Process -Filter "ProcessId=$($p.ProcessId)"
 if($fresh){if($fresh.CommandLine -ne $p.CommandLine -or $fresh.ParentProcessId -ne $p.ParentProcessId){throw 'Ownership changed'};Stop-Process -Id $p.ProcessId -ErrorAction Stop}
}
$deadline=([DateTime]::UtcNow).AddSeconds(5)
while(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue|Where-Object LocalPort -eq 8885){if([DateTime]::UtcNow -gt $deadline){throw 'Catalog listener did not close'};Start-Sleep -Milliseconds 100}
'''
subprocess.run(['powershell', '-NoProfile', '-Command', guard], cwd=repo, check=True)
assert sha(db.read_bytes()) == parent['database_sha256']
from rstv4.database import initialize_catalog

def canonical(value):
    return sha(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as conn:
    old_tables=[row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    old_rows={name:conn.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall() for name in old_tables}
    old_schema={row[1]:row for row in conn.execute('SELECT * FROM sqlite_master ORDER BY name')}
assert len(old_tables)==106
initialize_catalog(db)
with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as conn:
    tables=[row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    current_rows={name:conn.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall() for name in tables}
    for name in old_tables:
        if name!='schema_version':assert current_rows[name]==old_rows[name],name
    assert [row for row in current_rows['schema_version'] if row[0]!='catalog']==[row for row in old_rows['schema_version'] if row[0]!='catalog']
    assert set(tables)-set(old_tables)=={'fieldkg_semantic_runs','fieldkg_semantic_objects'}
    assert not current_rows['fieldkg_semantic_runs'] and not current_rows['fieldkg_semantic_objects']
    current_schema={row[1]:row for row in conn.execute('SELECT * FROM sqlite_master ORDER BY name')}
    for name,row in old_schema.items():
        assert current_schema[name][0:3]==row[0:3] and current_schema[name][4:]==row[4:],name
    assert conn.execute("SELECT version FROM schema_version WHERE component='catalog'").fetchone()[0]==12
    baseline={'database_sha256':sha(db.read_bytes()),'all_table_sha256':{name:canonical(rows) for name,rows in current_rows.items()},'schema_sha256':canonical(conn.execute('SELECT * FROM sqlite_master ORDER BY name').fetchall())}
with (repo/'.tmp/scholar-fieldkg-semantics-post-migration-baseline-v1.json').open('x',encoding='utf-8') as handle:
    json.dump(baseline,handle,indent=2)
old_parent=parent
parent={**parent,'database_sha256':baseline['database_sha256']}
migration={'status':'PASS_ADDITIVE_SCHEMA11_TO12_PRESERVING_ALL106_OLD_TABLES','original_database_sha256':old_parent['database_sha256'],'current_database_sha256':parent['database_sha256'],'old_table_count':106,'current_table_count':108,'new_tables':['fieldkg_semantic_runs','fieldkg_semantic_objects'],'all_old_rows_preserved_except_declared_version':True,'all_old_schema_definitions_preserved':True,'no_semantic_objects_or_runs_added':True}
with (repo/'.tmp/scholar-fieldkg-semantics-migration-v1.json').open('x',encoding='utf-8') as handle:
    json.dump(migration,handle,indent=2)
resume = r'''
$ErrorActionPreference='Stop'
if(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue|Where-Object LocalPort -eq 8885){throw 'Catalog port acquired another owner'}
$c=Get-Content -LiteralPath '.tmp/scholar-overview-services.json' -Raw|ConvertFrom-Json
$python=(Resolve-Path -LiteralPath '../RSTV4/.venv/Scripts/python.exe').Path
$backend=(Resolve-Path -LiteralPath '../RSTV4').Path
$logs=(Resolve-Path -LiteralPath '.tmp').Path
foreach($name in @('scholar-fieldkg-semantics-resumed-catalog-v1.log','scholar-fieldkg-semantics-resumed-catalog-v1-error.log')){if(Test-Path -LiteralPath (Join-Path $logs $name)){throw 'Preserve existing restart logs'}}
$catalog=Start-Process -FilePath $python -ArgumentList @('-u',(Join-Path $logs 'scholar-overview-server.py'),'--root',$c.root,'--port','8885') -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'scholar-fieldkg-semantics-resumed-catalog-v1.log') -RedirectStandardError (Join-Path $logs 'scholar-fieldkg-semantics-resumed-catalog-v1-error.log')
$c.catalog_process=$catalog.Id;$c.catalog_mode='track_scientific_preview'
[System.IO.File]::WriteAllText((Join-Path $logs 'scholar-overview-services.json'),($c|ConvertTo-Json -Depth 20),[System.Text.UTF8Encoding]::new($false))
'''
subprocess.run(['powershell', '-NoProfile', '-Command', resume], cwd=repo, check=True)
deadline = time.monotonic() + 20
while True:
    try:
        response = httpx.get('http://127.0.0.1:8885/api/catalog/research-overview', timeout=2)
        assert response.status_code == 200
        overview = response.json()
        assert 'literature_counts' in overview
        break
    except (httpx.HTTPError, AssertionError):
        if time.monotonic() > deadline:
            raise
        time.sleep(.1)
assert sha(db.read_bytes()) == parent['database_sha256']
proof = {'status': 'PASS_OWNED_CATALOG_REFRESH_WITH_DECLARED_ADDITIVE_SCHEMA12', 'root': str(root),
         'database_sha256': parent['database_sha256'], 'literature_counts': overview['literature_counts'],
         'studio_and_frontend_retained': True, 'new_model_calls': 0, 'scientific_approval': False,
         'browser_verified': False}
with (repo / '.tmp/scholar-fieldkg-semantics-refresh-v1.json').open('x', encoding='utf-8') as handle:
    json.dump(proof, handle, ensure_ascii=False, indent=2)
print(json.dumps({'status': proof['status'], 'scope_count': len(overview['literature_counts'])}), flush=True)
