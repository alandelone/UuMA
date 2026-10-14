from pathlib import Path
import json,os,subprocess,time,socket
repo=Path.cwd();fixture=json.loads((repo/'.tmp/scholar-citation-source-native-v1.json').read_text(encoding='utf-8'))
def ps(command):return subprocess.check_output(['powershell','-NoProfile','-Command',command],text=True,encoding='utf-8-sig')
listener=int(ps('(Get-NetTCPConnection -LocalPort 3008 -State Listen).OwningProcess'));chain=[];current=listener
while True:
 row=json.loads(ps(f'Get-CimInstance Win32_Process -Filter "ProcessId={current}" | Select-Object ProcessId,ParentProcessId,CommandLine,CreationDate | ConvertTo-Json'))
 chain.append(row)
 assert len(chain)<=8
 if current==fixture['processes']['frontend']:break
 current=int(row['ParentProcessId'])
assert '--port 3008' in chain[-1]['CommandLine'] and 'npm.cmd run start' in chain[-1]['CommandLine']
assert all(1791540884000<=int(p['CreationDate'].split('(')[1].split(')')[0])<=1791540910000 for p in chain)
source=(repo/'.tmp/scholar-template-build-v3.py').read_text(encoding='utf-8').replace('scholar-template-build-v3.','scholar-citation-source-build-v2.').replace('scui-template-build-','scui-citation-source-build-').replace('127.0.0.1:8877','127.0.0.1:8881').replace('--max-old-space-size=1536','--max-old-space-size=512').replace("RAYON_NUM_THREADS='2', UV_THREADPOOL_SIZE='2'","RAYON_NUM_THREADS='1', UV_THREADPOOL_SIZE='1'")
exec(compile(source,str(repo/'.tmp/scholar-template-build-v3.py'),'exec'),{'__file__':str(repo/'.tmp/scholar-template-build-v3.py')})
build=json.loads((repo/'.tmp/scholar-citation-source-build-v2.json').read_text(encoding='utf-8'));assert build['status']=='PASS'
ps('Stop-Process -Id '+','.join(str(p['ProcessId']) for p in chain)+' -ErrorAction SilentlyContinue')
env={**os.environ,'NEXT_PUBLIC_RSTV4_API':'http://127.0.0.1:8881/api','NODE_OPTIONS':'--max-old-space-size=512','RAYON_NUM_THREADS':'1','UV_THREADPOOL_SIZE':'1'}
with (repo/'.tmp/scholar-citation-source-frontend-runtime-v2.log').open('x',encoding='utf-8') as log:
 process=subprocess.Popen(['cmd.exe','/c','npm.cmd','run','start','--','--port','3008','--hostname','127.0.0.1'],cwd=Path(build['root']),env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
import httpx
with httpx.Client(timeout=3) as client:
 deadline=time.monotonic()+20;ready=False
 while not ready and time.monotonic()<deadline:
  try:ready=client.get('http://127.0.0.1:3008/').status_code==200
  except httpx.HTTPError:pass
  if not ready:time.sleep(.3)
 assert ready
(repo/'.tmp/scholar-citation-source-build-refresh-v2.json').write_text(json.dumps({'status':'PASS','verified_owned_chain':chain,'new_frontend_pid':process.pid,'production_root':build['root'],'all_other_runtimes_untouched':True},indent=2),encoding='utf-8')
print(json.dumps({'status':'PASS','new_frontend_pid':process.pid,'production_root':build['root']}),flush=True)
