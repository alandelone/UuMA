import json,os,subprocess
from pathlib import Path
repo=Path(__file__).resolve().parents[1];front=repo.parent/'writing-studio'
env=os.environ.copy();env.update(NODE_OPTIONS='--max-old-space-size=512',GOMAXPROCS='2',GOMEMLIMIT='512MiB')
checks=[['cmd.exe','/c','node_modules\\.bin\\tsc.cmd','--noEmit'],['cmd.exe','/c','node_modules\\.bin\\oxlint.cmd','--threads=1','components/studio-workspace.tsx','components/studio-response-review.tsx','lib/studio-api.ts','lib/studio-downloads.ts','app/api/studio-files'],['git','diff','--check']]
results=[]
with (repo/'.tmp/scholar-material-download-final-static-v1.log').open('x',encoding='utf-8') as log:
    for cmd in checks:
        log.write('RUN '+repr(cmd)+'\n');log.flush()
        r=subprocess.run(cmd,cwd=front,env=env,stdout=log,stderr=subprocess.STDOUT)
        results.append({'command':cmd,'exit_code':r.returncode});print(f'Check {len(results)}: {r.returncode}',flush=True)
        if r.returncode:break
with (repo/'.tmp/scholar-material-download-final-static-v1.json').open('x',encoding='utf-8') as h:json.dump(results,h,indent=2)
assert len(results)==len(checks) and all(v['exit_code']==0 for v in results)
