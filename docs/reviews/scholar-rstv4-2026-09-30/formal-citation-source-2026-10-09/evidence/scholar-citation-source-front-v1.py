from pathlib import Path
import os,subprocess,json
repo=Path.cwd();front=repo.parent/'writing-studio'
checks=[['node','node_modules/typescript/bin/tsc','--noEmit'],[str(front/'node_modules/.bin/oxlint.cmd'),'--type-aware','--deny-warnings','lib/studio-types.ts','lib/studio-downloads.ts','components/studio-source-context.tsx','components/studio-workspace.tsx'],['node','tests/unit/studio-downloads.cjs'],['git','diff','--check']]
results=[]
with (repo/'.tmp/scholar-citation-source-front-v1.log').open('x',encoding='utf-8') as log:
 for args in checks:
  log.write('RUN '+repr(args)+'\n');log.flush()
  result=subprocess.run(args,cwd=front,env={**os.environ,'NODE_OPTIONS':'--max-old-space-size=512'},stdout=log,stderr=subprocess.STDOUT)
  results.append({'args':args,'exit_code':result.returncode});print(json.dumps(results[-1]),flush=True)
  if result.returncode:break
(repo/'.tmp/scholar-citation-source-front-v1.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print((repo/'.tmp/scholar-citation-source-front-v1.log').read_text(encoding='utf-8')[-3200:])
assert len(results)==len(checks) and all(r['exit_code']==0 for r in results)
