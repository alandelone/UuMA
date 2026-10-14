from pathlib import Path
import os,subprocess,json,tempfile,uuid,time
repo=Path.cwd();backend=repo.parent/'RSTV4';python=repo/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
base=Path(tempfile.gettempdir())/('scdis-focused-'+uuid.uuid4().hex[:8]);assert not base.exists()
checks=[[str(python),'-m','ruff','check','src/rstv4/studio_discussions.py','tests/test_studio_discussion_fixed_references.py'],[str(python),'-m','pytest','tests/test_studio_discussion_fixed_references.py','tests/test_studio_source_context.py','tests/test_studio_shared_discussions.py','tests/test_research_conversation.py','tests/test_studio_context.py','-q','--basetemp',str(base)]]
results=[];start=time.time()
with (repo/'.tmp/scholar-citation-discussion-focused-v1.log').open('x',encoding='utf-8') as log:
 for args in checks:
  r=subprocess.run(args,cwd=backend,env={**os.environ,'PYTHONUTF8':'1'},stdout=log,stderr=subprocess.STDOUT);results.append({'args':args,'exit_code':r.returncode})
  if r.returncode:break
text=(repo/'.tmp/scholar-citation-discussion-focused-v1.log').read_text(encoding='utf-8');print(text[-5500:])
(repo/'.tmp/scholar-citation-discussion-focused-v1.json').write_text(json.dumps({'results':results,'basetemp':str(base),'seconds':time.time()-start},indent=2),encoding='utf-8')
assert len(results)==len(checks) and all(r['exit_code']==0 for r in results)
