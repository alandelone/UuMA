import json,os,subprocess
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
project=repo.parent/'RSTV4';front=repo.parent/'writing-studio'
python=repo/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
env=os.environ.copy();env.update(PYTHONPATH=str(project/'src'),GOMAXPROCS='2',GOMEMLIMIT='512MiB')
checks=[(front,['cmd.exe','/c','node_modules\\.bin\\tsc.cmd','--noEmit']),
        (front,['node','tests/unit/studio-structure.cjs']),
        (front,['node','tests/unit/studio-hierarchy.cjs']),
        (front,['node','tests/unit/studio-template-placement.cjs']),
        (front,['cmd.exe','/c','node_modules\\.bin\\oxlint.cmd','--threads=1','components/studio-workspace.tsx','components/studio-block-controls.tsx','components/studio-original-placement.tsx','lib/studio-blocks.ts']),
        (project,[str(python),'-X','utf8','-m','pytest','-q','tests/test_studio_hierarchy.py','tests/test_studio_templates.py','tests/test_studio_structure.py','tests/test_writing_studio.py'])]
results=[]
with (repo/'.tmp/scholar-template-mapping-check-v1.log').open('x',encoding='utf-8') as log:
    for cwd,command in checks:
        log.write('RUN '+repr(command)+'\n');log.flush()
        result=subprocess.run(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
        results.append({'command':command,'exit_code':result.returncode})
        print(f'Check {len(results)}: {result.returncode}',flush=True)
        if result.returncode:break
with (repo/'.tmp/scholar-template-mapping-check-v1.json').open('x',encoding='utf-8') as h:json.dump(results,h,indent=2)
assert len(results)==len(checks) and not any(r['exit_code'] for r in results)
