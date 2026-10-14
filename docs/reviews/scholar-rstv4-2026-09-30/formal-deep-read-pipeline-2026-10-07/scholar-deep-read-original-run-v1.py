import subprocess,time
from pathlib import Path
import httpx
repo=Path(__file__).resolve().parents[1];python=repo.parent/'RSTV4/.venv/Scripts/python.exe'
with (repo/'.tmp/scholar-deep-read-original-run-v1.log').open('x',encoding='utf-8') as log:
 command=[str(python),'-X','utf8',str(repo/'.tmp/scholar-deep-read-migration-v1.py')]
 log.write('RUN '+repr(command)+'\n');log.flush();result=subprocess.run(command,cwd=repo,stdout=log,stderr=subprocess.STDOUT);log.flush();print('Original migration result',result.returncode,flush=True)
 if result.returncode:raise SystemExit(result.returncode)
 deadline=time.monotonic()+25
 for url in ['http://127.0.0.1:8885/','http://127.0.0.1:8874/api/health','http://127.0.0.1:3000/']:
  while True:
   try:
    response=httpx.get(url,timeout=2);assert response.status_code==200,response.text[:200];log.write('ACTUAL_READY '+url+' 200\n');log.flush();break
   except (httpx.HTTPError,AssertionError):
    if time.monotonic()>deadline:raise
    time.sleep(.2)
 command=[str(python),'-X','utf8',str(repo/'.tmp/scholar-deep-read-original-final-v1.py')]
 log.write('RUN '+repr(command)+'\n');log.flush();result=subprocess.run(command,cwd=repo,stdout=log,stderr=subprocess.STDOUT);log.flush();print('Original readback result',result.returncode,flush=True)
 if result.returncode:raise SystemExit(result.returncode)
