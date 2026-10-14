from pathlib import Path
import hashlib,json,os,subprocess,time
repo=Path.cwd();backend=repo.parent/'RSTV4';front=repo.parent/'writing-studio';python=repo/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
def source_snapshot():
 return {str(p.relative_to(repo.parent)):hashlib.sha256(p.read_bytes()).hexdigest() for project,folders in [(backend,['src','tests']),(front,['app','components','lib','tests'])] for folder in folders for p in (project/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.tsbuildinfo'}}
before=source_snapshot(); results=[];start=time.time()
checks=[(backend,[str(python),'-m','ruff','check','src/rstv4/studio_sources.py','src/rstv4/studio.py','src/rstv4/studio_api.py','src/rstv4/studio_read_views.py','tests/test_studio_source_context.py']),(backend,[str(python),'-m','pytest','tests','-q','--basetemp',str(repo/'.tmp/scholar-citation-source-full-v1-pytest')])]
env={**os.environ,'PYTHONUTF8':'1','NODE_OPTIONS':'--max-old-space-size=512','RAYON_NUM_THREADS':'1','GOMAXPROCS':'2','GOMEMLIMIT':'512MiB'}
with (repo/'.tmp/scholar-citation-source-full-v1.log').open('x',encoding='utf-8') as log:
 for cwd,args in checks:
  log.write('RUN '+repr(args)+'\n');log.flush();r=subprocess.run(args,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
  results.append({'args':args,'exit_code':r.returncode});print(json.dumps(results[-1]),flush=True)
  if r.returncode:break
after=source_snapshot();receipt={'results':results,'before':before,'after':after,'source_files':len(before),'source_stable':before==after,'seconds':time.time()-start}
(repo/'.tmp/scholar-citation-source-full-v1.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print((repo/'.tmp/scholar-citation-source-full-v1.log').read_text(encoding='utf-8')[-2800:])
assert before==after and len(results)==len(checks) and all(r['exit_code']==0 for r in results)
