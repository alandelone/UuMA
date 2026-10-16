from pathlib import Path
import hashlib
import json
import os
import subprocess
import tempfile
import time

repo=Path.cwd(); rst=repo.parent/'RSTV4'; front=repo.parent/'writing-studio'
folder=repo/'.tmp/scholar-frozen-origin-full-v1';folder.mkdir(exist_ok=False)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def snapshot():
    return {str(p):sha(p) for root,bases in [(rst,['src','tests']),(front,['app','components','lib','tests'])]
            for base in bases for p in (root/base).rglob('*') if p.is_file() and p.suffix in {'.py','.js','.mjs','.cjs','.html','.ts','.tsx','.css'}}
before=snapshot();(folder/'source-before.json').write_text(json.dumps(before,indent=2),encoding='utf8')
python=repo/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
environment={**os.environ,'PYTHONPATH':str(rst/'src'),'PYTHONIOENCODING':'utf-8','GOMAXPROCS':'2','GOMEMLIMIT':'512MiB'}
base=Path(tempfile.mkdtemp(prefix='scui-frozen-origin-full-')).resolve()
commands=[([str(python),'-X','utf8','-m','pytest','tests','-q','--tb=short','--basetemp',str(base)],rst)]
commands.extend([(['node',str(p)],rst) for p in sorted((rst/'tests').glob('catalog_*.mjs'))])
commands.extend([(['node',str(p)],front) for p in sorted((front/'tests/unit').glob('*.cjs'))])
commands.append(([str(python),'-m','ruff','check','src/rstv4/studio.py','src/rstv4/studio_layout.py','src/rstv4/studio_context.py','src/rstv4/studio_read_views.py','src/rstv4/studio_revision_mapping.py','tests/test_studio_layout.py','tests/test_studio_layout_integration.py','tests/test_studio_frozen_origins.py'],rst))
results=[];started=time.monotonic()
for index,(command,cwd) in enumerate(commands):
    log=folder/f'check-{index:02d}.log'
    t=time.monotonic()
    with log.open('x',encoding='utf8') as output:
        result=subprocess.run(command,cwd=cwd,env=environment,stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW,check=False)
    item={'command':command,'cwd':str(cwd),'exit_code':result.returncode,'seconds':time.monotonic()-t,'log':str(log),'log_sha256':sha(log)}
    results.append(item);print(json.dumps(item),flush=True)
    (folder/'progress.json').write_text(json.dumps(results,indent=2),encoding='utf8')
    if result.returncode:break
after=snapshot();changed=[p for p in before.keys()|after.keys() if before.get(p)!=after.get(p)]
receipt={'status':'PASS' if len(results)==len(commands) and all(x['exit_code']==0 for x in results) and not changed else 'FAIL',
         'seconds':time.monotonic()-started,'results':results,'source_count':len(before),'source_before':str(folder/'source-before.json'),
         'changed_during_run':changed,'commands_completed':len(results),'commands_expected':len(commands),'final11_complete':False}
(folder/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf8');print(json.dumps(receipt),flush=True)
assert receipt['status']=='PASS'
