from pathlib import Path
import hashlib,json,subprocess,os,time,socket,sqlite3,sys
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();build=json.loads((repo/'.tmp/scholar-g01-loading-build-v1.json').read_text(encoding='utf-8'))
assert build['status']=='PASS' and build['original_source_and_dist_unchanged']
checks=json.loads((repo/'.tmp/scholar-g01-loading-front-v1.json').read_text(encoding='utf-8'));assert len(checks)==4 and all(r['exit_code']==0 for r in checks)
root=Path(build['root']);front=repo.parent/'writing-studio';assert root.parent.name.startswith('scui-g01-loading-build-')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(root/'components/studio-workspace.tsx')==sha(front/'components/studio-workspace.tsx')
db=Path('C:/Users/Alandelone/AppData/Local/Temp/scui-citation-source-native-du6504t2/data/catalog.db');before=sha(db)
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as conn:
    assert all(r[0] not in {'QUEUED','RUNNING'} for table in ['studio_jobs','research_discussion_jobs'] for r in conn.execute(f'SELECT status FROM {table}'))
def ps(code):
    r=subprocess.run(['powershell','-NoProfile','-Command',code],capture_output=True,encoding='utf-8-sig',check=True);assert not r.stderr.strip(),r.stderr
    return json.loads(r.stdout or 'null')
def row(pid):return ps(f"Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | Select-Object ProcessId,ParentProcessId,CommandLine,CreationDate | ConvertTo-Json")
inventory=json.loads((repo/'.tmp/scholar-preview-memory-cleanup-v1/inventory-before.json').read_text(encoding='utf-8'))
chain=inventory['chains']['3008'];backend=inventory['chains']['8881']
for saved in chain+backend:
    fresh=row(saved['ProcessId']);assert all(fresh[k]==saved[k] for k in ['ProcessId','ParentProcessId','CommandLine','CreationDate'])
assert ps('(Get-NetTCPConnection -LocalPort 3008 -State Listen).OwningProcess | ConvertTo-Json')==chain[0]['ProcessId']
stops=[]
for saved in chain:
    pid=saved['ProcessId'];cmd=saved['CommandLine'].replace("'","''");epoch=int(saved['CreationDate'].split('(')[1].split(')')[0])
    result=ps(f"$taskProcess=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}'; if ($null -eq $taskProcess) {{ '{{\"state\":\"ALREADY_EXITED\"}}' }} else {{ if ($taskProcess.CommandLine -cne '{cmd}' -or $taskProcess.ParentProcessId -ne {saved['ParentProcessId']} -or ([DateTimeOffset]$taskProcess.CreationDate).ToUnixTimeMilliseconds() -ne {epoch}) {{ throw 'Owned frontend identity changed' }}; Stop-Process -Id {pid} -Force -ErrorAction Stop; '{{\"state\":\"STOPPED_VERIFIED\"}}' }}")
    stops.append({'pid':pid,**result})
env={**os.environ,'NEXT_PUBLIC_RSTV4_API':'http://127.0.0.1:8881/api','NODE_OPTIONS':'--max-old-space-size=512','RAYON_NUM_THREADS':'1','UV_THREADPOOL_SIZE':'1'}
with (repo/'.tmp/scholar-g01-loading-runtime-v1.log').open('x',encoding='utf-8') as log:
    process=subprocess.Popen(['cmd.exe','/c','npm.cmd','run','start','--','--port','3008','--hostname','127.0.0.1'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
deadline=time.monotonic()+20;ready=False
while not ready and time.monotonic()<deadline:
    try:
        with socket.create_connection(('127.0.0.1',3008),timeout=1):ready=True
    except OSError:time.sleep(.2)
assert ready and process.poll() is None
pid=ps('(Get-NetTCPConnection -LocalPort 3008 -State Listen).OwningProcess | ConvertTo-Json');new=[]
while True:
    item=row(pid);new.append(item);assert len(new)<=5
    if pid==process.pid:break
    pid=item['ParentProcessId']
assert 'scui-g01-loading-build-1ou2ff1y' in new[0]['CommandLine']
assert all(row(saved['ProcessId'])=={k:saved[k] for k in ['ProcessId','ParentProcessId','CommandLine','CreationDate']} for saved in backend)
assert sha(db)==before
receipt={'status':'PASS_NEW_OWNED_FRONTEND_READY','new_frontend_root_pid':process.pid,'new_verified_port3008_chain':new,'old_verified_frontend_stops':stops,'production_root':str(root),'database_bytes_preserved':True,'current_backend_identity_unchanged':True,'all_other_runtime_processes_untouched':True,'frontend_source_sha256':sha(front/'components/studio-workspace.tsx')}
(repo/'.tmp/scholar-g01-loading-runtime-refresh-v1.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps(receipt),flush=True)
