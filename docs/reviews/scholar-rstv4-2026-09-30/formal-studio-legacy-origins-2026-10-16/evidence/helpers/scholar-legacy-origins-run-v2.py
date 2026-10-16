from pathlib import Path
import json,os,subprocess,time
repo=Path(__file__).resolve().parents[1];here=repo/'.tmp/scholar-legacy-origins-v1';rst=repo.parent/'RSTV4';front=repo.parent/'writing-studio'
python=repo/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
commands=[([str(python),'-m','ruff','check','--fix','src/rstv4/studio.py','src/rstv4/studio_read_views.py','src/rstv4/studio_history_origins.py','src/rstv4/studio_api.py','src/rstv4/studio_revision_mapping.py','tests/test_studio_historical_origins.py'],rst),
 ([str(python),'-X','utf8','-m','pytest','tests/test_studio_historical_origins.py','tests/test_studio_revision_mapping.py','-q','--tb=short'],rst),
 (['node','tests/unit/studio-response-review.cjs'],front),(['node','node_modules/typescript/bin/tsc','--noEmit'],front)]
env={**os.environ,'PYTHONPATH':str(rst/'src'),'PYTHONIOENCODING':'utf8'};results=[]
for i,(cmd,cwd) in enumerate(commands):
    log=here/f'focused-v2-{i}.log';started=time.monotonic()
    with log.open('x',encoding='utf8') as output:r=subprocess.run(cmd,cwd=cwd,env=env,stdout=output,stderr=subprocess.STDOUT,check=False,creationflags=subprocess.CREATE_NO_WINDOW)
    results.append({'command':cmd,'exit_code':r.returncode,'seconds':time.monotonic()-started,'log':str(log)});print(json.dumps(results[-1]),flush=True)
(here/'focused-v2-receipt.json').write_text(json.dumps(results,indent=2),encoding='utf8');assert all(r['exit_code']==0 for r in results)
