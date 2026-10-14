import json
import os
import subprocess
from pathlib import Path

repo=Path(__file__).resolve().parents[1]
project=repo.parent/'RSTV4';frontend=repo.parent/'writing-studio'
python=repo/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
env=os.environ.copy();env.update(PYTHONPATH=str(project/'src'),GOMAXPROCS='2',GOMEMLIMIT='512MiB')
checks=[(project,[str(python),'-m','ruff','check','src/rstv4/studio.py','src/rstv4/studio_structure.py','src/rstv4/studio_context.py','src/rstv4/studio_templates.py','src/rstv4/studio_read_views.py','tests/test_studio_hierarchy.py']),
        (project,[str(python),'-X','utf8','-m','pytest','-q','tests/test_studio_hierarchy.py','tests/test_studio_templates.py','tests/test_studio_structure.py','tests/test_writing_studio.py']),
        (frontend,['cmd.exe','/c','node_modules\\.bin\\tsc.cmd','--noEmit']),
        (frontend,['node','tests/unit/studio-structure.cjs']),
        (frontend,['node','tests/unit/studio-hierarchy.cjs']),
        (frontend,['cmd.exe','/c','node_modules\\.bin\\oxlint.cmd','--threads=1','components/studio-argument-relations.tsx','components/studio-workspace.tsx','lib/studio-blocks.ts','lib/studio-types.ts'])]
results=[]
with (repo/'.tmp/scholar-hierarchy-check-v1.log').open('x',encoding='utf-8') as log:
    for cwd,command in checks:
        log.write('RUN '+repr(command)+'\n');log.flush()
        result=subprocess.run(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
        results.append({'command':command,'exit_code':result.returncode})
        print(f'Check {len(results)}: {result.returncode}',flush=True)
        if result.returncode:break
with (repo/'.tmp/scholar-hierarchy-check-v1.json').open('x',encoding='utf-8') as handle:json.dump(results,handle,indent=2)
assert len(results)==len(checks) and not any(r['exit_code'] for r in results)
