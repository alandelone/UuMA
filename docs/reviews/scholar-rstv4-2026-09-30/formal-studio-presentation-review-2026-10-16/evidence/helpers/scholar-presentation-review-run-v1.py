from pathlib import Path
import os,json,subprocess,time
repo=Path(__file__).resolve().parents[1];here=repo/'.tmp/scholar-presentation-review-v1'
python=repo/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe';rst=repo.parent/'RSTV4';front=repo.parent/'writing-studio'
commands=[([str(python),'-m','ruff','check','--fix','tests/test_studio_presentation_review.py'],rst),
 ([str(python),'-X','utf8','-m','pytest','tests/test_studio_presentation_review.py','-q','--tb=short'],rst),
 (['node','tests/unit/studio-response-review.cjs'],front),(['node','node_modules/typescript/bin/tsc','--noEmit'],front),
 ([str(python),'-m','ruff','check','src/rstv4/studio_response_checks.py','src/rstv4/studio_api.py','tests/test_studio_presentation_review.py'],rst)]
results=[];env={**os.environ,'PYTHONPATH':str(rst/'src'),'PYTHONIOENCODING':'utf8'}
for i,(cmd,cwd) in enumerate(commands):
    log=here/f'check-{i}.log';started=time.monotonic()
    with log.open('x',encoding='utf8') as output:
        result=subprocess.run(cmd,cwd=cwd,env=env,stdout=output,stderr=subprocess.STDOUT,check=False,creationflags=subprocess.CREATE_NO_WINDOW)
    results.append({'command':cmd,'cwd':str(cwd),'exit_code':result.returncode,'seconds':time.monotonic()-started,'log':str(log)})
    print(json.dumps(results[-1]),flush=True)
(here/'focused-receipt.json').write_text(json.dumps(results,indent=2),encoding='utf8')
assert all(r['exit_code']==0 for r in results)
