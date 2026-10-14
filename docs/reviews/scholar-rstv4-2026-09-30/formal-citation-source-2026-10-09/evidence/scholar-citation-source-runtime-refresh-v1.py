from pathlib import Path
import json,os,subprocess,sys,time,sqlite3
repo=Path.cwd();fixture_path=repo/'.tmp/scholar-citation-source-native-v1.json';fixture=json.loads(fixture_path.read_text(encoding='utf-8'))
db=Path(fixture['root'])/'data/catalog.db'
def snapshot():
 with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as conn:
  return {r[0]:conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid').fetchall() for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
before=snapshot()
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as conn:
 jobs=conn.execute('SELECT manuscript_id,status FROM studio_jobs').fetchall()
 calls=conn.execute('SELECT manuscript_id,status FROM studio_model_calls').fetchall()
 assert len(jobs)==len(calls)==1 and all(row==(fixture['manuscript_id'],'SUCCEEDED') for row in jobs)
 assert all(row==(fixture['manuscript_id'],'VALIDATED') for row in calls)
def ps(command):
 return subprocess.check_output(['powershell','-NoProfile','-Command',command],text=True,encoding='utf-8-sig')
raw=ps("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*scholar-citation-source-native-v1.py*serve*' } | Select-Object ProcessId,ParentProcessId,CommandLine,CreationDate | ConvertTo-Json -Depth 3")
owned=json.loads(raw);owned=owned if isinstance(owned,list) else [owned]
ids={int(p['ProcessId']) for p in owned};assert fixture['processes']['backend'] in ids
listener=int(ps("(Get-NetTCPConnection -LocalPort 8881 -State Listen).OwningProcess"))
assert listener in ids
for p in owned:
 assert 'scholar-citation-source-native-v1.py' in p['CommandLine'] and p['CommandLine'].rstrip().endswith('serve')
 assert p['ProcessId']==fixture['processes']['backend'] or p['ParentProcessId'] in ids
ps('Stop-Process -Id '+','.join(str(i) for i in sorted(ids))+' -ErrorAction Stop')
env={**os.environ,'PYTHONPATH':str(repo.parent/'RSTV4/src'),'PYTHONUTF8':'1','NODE_OPTIONS':'--max-old-space-size=512','RAYON_NUM_THREADS':'1','UV_THREADPOOL_SIZE':'1'}
with (repo/'.tmp/scholar-citation-source-backend-runtime-v2.log').open('x',encoding='utf-8') as log:
 process=subprocess.Popen([sys.executable,str(repo/'.tmp/scholar-citation-source-native-v1.py'),'serve'],cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
import httpx
with httpx.Client(timeout=2) as client:
 deadline=time.monotonic()+20;ready=False
 while not ready and time.monotonic()<deadline:
  try:ready=client.get(f"http://127.0.0.1:8881/api/manuscripts/{fixture['manuscript_id']}/workspace").status_code==200
  except httpx.HTTPError:pass
  if not ready:time.sleep(.3)
 assert ready
assert snapshot()==before
receipt={'status':'PASS','verified_owned_processes':owned,'prior_jobs':len(jobs),'prior_model_calls':len(calls),'all_database_rows_preserved':True,'new_backend_pid':process.pid,'all_other_runtimes_untouched':True}
(repo/'.tmp/scholar-citation-source-runtime-refresh-v1.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps(receipt),flush=True)
