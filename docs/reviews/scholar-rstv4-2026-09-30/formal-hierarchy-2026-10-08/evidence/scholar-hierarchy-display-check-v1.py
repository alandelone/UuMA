import json, os, subprocess
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
env=os.environ.copy();env.update(GOMAXPROCS='2',GOMEMLIMIT='512MiB')
commands=[['cmd.exe','/c','node_modules\\.bin\\tsc.cmd','--noEmit'],['cmd.exe','/c','node_modules\\.bin\\oxlint.cmd','--threads=1','components/studio-argument-relations.tsx','components/studio-workspace.tsx','lib/studio-blocks.ts','lib/studio-types.ts'],['git','diff','--check']]
results=[]
with (repo/'.tmp/scholar-hierarchy-display-check-v1.log').open('x',encoding='utf-8') as log:
    for command in commands:
        result=subprocess.run(command,cwd=repo.parent/'writing-studio',env=env,stdout=log,stderr=subprocess.STDOUT)
        results.append({'command':command,'exit_code':result.returncode})
        assert result.returncode==0
with (repo/'.tmp/scholar-hierarchy-display-check-v1.json').open('x',encoding='utf-8') as h:json.dump(results,h,indent=2)
print('PASS final TSC, configured type-aware lint and frontend diff check')
