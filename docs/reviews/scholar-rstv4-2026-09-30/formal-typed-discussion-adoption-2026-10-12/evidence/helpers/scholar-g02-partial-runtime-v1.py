from pathlib import Path
import json,sys,sqlite3,hashlib,subprocess,socket,time,os
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();out=repo/'.tmp/scholar-g02-partial-native-v1';out.mkdir()
fixture=json.loads((repo/'.tmp/scholar-citation-source-native-v1.json').read_text(encoding='utf-8'));db=Path(fixture['root'])/'data/catalog.db';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();before=sha(db)
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as conn:
    conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON')
    tables={r[0]:[dict(x) for x in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
assert len(tables)==109 and tables['studio_documents'][0]['revision']==11
assert len(tables['studio_model_calls'])==11 and len(tables['studio_chat_messages'])==9
assert all(r['status'] not in {'QUEUED','RUNNING'} for table in ['studio_jobs','research_discussion_jobs'] for r in tables[table])
(out/'baseline-all-tables.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf-8')
def ps(code):
    r=subprocess.run(['powershell','-NoProfile','-Command',code],capture_output=True,encoding='utf-8-sig',check=True);assert not r.stderr.strip(),r.stderr
    return json.loads(r.stdout or 'null')
def row(pid):return ps(f"Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | Select-Object ProcessId,ParentProcessId,CommandLine,CreationDate | ConvertTo-Json")
inventory=json.loads((repo/'.tmp/scholar-preview-memory-cleanup-v1/inventory-before.json').read_text(encoding='utf-8'));backend=inventory['chains']['8881']
for saved in backend:assert row(saved['ProcessId'])=={k:saved[k] for k in ['ProcessId','ParentProcessId','CommandLine','CreationDate']}
front=json.loads((repo/'.tmp/scholar-g01-loading-runtime-refresh-v1.json').read_text(encoding='utf-8'))['new_verified_port3008_chain']
assert all(row(p['ProcessId'])==p for p in front)
assert ps('(Get-NetTCPConnection -LocalPort 8881 -State Listen).OwningProcess | ConvertTo-Json')==104544
stops=[]
for saved in backend:
    pid=saved['ProcessId'];cmd=saved['CommandLine'].replace("'","''");epoch=int(saved['CreationDate'].split('(')[1].split(')')[0])
    result=ps(f"$taskProcess=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}'; if ($null -eq $taskProcess) {{ '{{\"state\":\"ALREADY_EXITED\"}}' }} else {{ if ($taskProcess.CommandLine -cne '{cmd}' -or $taskProcess.ParentProcessId -ne {saved['ParentProcessId']} -or ([DateTimeOffset]$taskProcess.CreationDate).ToUnixTimeMilliseconds() -ne {epoch}) {{ throw 'Owned backend identity changed' }}; Stop-Process -Id {pid} -Force -ErrorAction Stop; '{{\"state\":\"STOPPED_VERIFIED\"}}' }}")
    stops.append({'pid':pid,**result})
helper=repo/'.tmp/scholar-g02-partial-native-server-v1.py'
with (out/'server.log').open('x',encoding='utf-8') as log:
    process=subprocess.Popen([str(repo/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'),str(helper)],cwd=repo,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
deadline=time.monotonic()+20;ready=False
while not ready and time.monotonic()<deadline:
    try:
        with socket.create_connection(('127.0.0.1',8881),timeout=1):ready=True
    except OSError:time.sleep(.2)
assert ready and process.poll() is None
listener=ps('(Get-NetTCPConnection -LocalPort 8881 -State Listen).OwningProcess | ConvertTo-Json');new=[row(listener),row(process.pid)]
assert new[0]['ParentProcessId']==process.pid and all('scholar-g02-partial-native-server-v1.py' in p['CommandLine'] for p in new)
assert all(row(p['ProcessId'])==p for p in front) and sha(db)==before
receipt={'status':'PASS_G02_SOFTWARE_GATEWAY_READY','root':fixture['root'],'manuscript_id':fixture['manuscript_id'],'old_verified_backend_stops':stops,'new_backend_root_pid':process.pid,'new_verified_port8881_chain':new,'frontend3008_exact_preserved':True,'all109tables_and_database_bytes_exact_before_any_g02_action':True,'no_remote_fallback':True,'no_other_processes_stopped':True}
(out/'runtime.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps(receipt),flush=True)
