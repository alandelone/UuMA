from pathlib import Path
import os,subprocess,json
repo=Path.cwd();backend=repo.parent/'RSTV4';python=repo/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
checks=[['-m','ruff','check','src/rstv4/studio_sources.py','src/rstv4/studio.py','src/rstv4/studio_api.py','src/rstv4/studio_read_views.py','tests/test_studio_source_context.py'],['-m','pytest','tests/test_studio_source_context.py','tests/test_studio_context.py','tests/test_skeleton_source_outline.py','-q','--basetemp',str(repo/'.tmp/scholar-citation-source-focused-v2-pytest')]]
results=[]
with (repo/'.tmp/scholar-citation-source-focused-v2.log').open('x',encoding='utf-8') as log:
 for args in checks:
  log.write('RUN '+repr(args)+'\n');log.flush()
  result=subprocess.run([str(python),*args],cwd=backend,env={**os.environ,'PYTHONUTF8':'1'},stdout=log,stderr=subprocess.STDOUT)
  results.append({'args':args,'exit_code':result.returncode});print(json.dumps(results[-1]),flush=True)
  if result.returncode:break
(repo/'.tmp/scholar-citation-source-focused-v2.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print((repo/'.tmp/scholar-citation-source-focused-v2.log').read_text(encoding='utf-8')[-5000:])
assert len(results)==len(checks) and all(r['exit_code']==0 for r in results)
