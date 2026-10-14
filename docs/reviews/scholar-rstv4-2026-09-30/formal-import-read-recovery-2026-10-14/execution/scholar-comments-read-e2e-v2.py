from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

repo=Path(__file__).resolve().parents[1]
here=repo/'.tmp/scholar-native-import-v1/comments-read-recovery-v1/e2e-v2'
here.mkdir()
build=json.loads((repo/'.tmp/scholar-native-import-build-v2.json').read_text())
assert build['status']=='PASS'
root=Path(build['root'])
source=Path(build['source'])
spec=source/'tests/e2e/review-read-recovery.spec.ts'
assert hashlib.sha256(spec.read_bytes()).hexdigest()=='b93b08b69b413e198fe9394c83cfb1fc01f37f94f20756b61327a74389acc67e'
assert (root/'components/studio-workspace.tsx').read_bytes()==(source/'components/studio-workspace.tsx').read_bytes()
config=root/'review-read-recovery-v2.config.ts'
config.open('x',encoding='utf-8').write("import { defineConfig } from '@playwright/test';\nexport default defineConfig("+json.dumps({
    'testDir':str(spec.parent),'testMatch':spec.name,'timeout':60000,'workers':1,'retries':0,
    'outputDir':str(here/'test-results'),'reporter':[['list'],['json',{'outputFile':str(here/'results.json')}]],
    'use':{'baseURL':'http://127.0.0.1:3009','channel':'msedge','headless':True,'screenshot':'only-on-failure','trace':'retain-on-failure'},
})+");\n")
env=os.environ.copy();env['NODE_OPTIONS']='--max-old-space-size=512'
started=time.time()
with (here/'run.log').open('xb') as log:
    result=subprocess.run(['node',str(root/'node_modules/@playwright/test/cli.js'),'test','--config',str(config)],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
receipt={'status':'PASS' if result.returncode==0 else 'FAIL','exit_code':result.returncode,'seconds':time.time()-started,'build':str(root),'spec':str(spec),'database_access':'All API mocked; no writes/models/jobs','product_source_exact':(root/'components/studio-workspace.tsx').read_bytes()==(source/'components/studio-workspace.tsx').read_bytes()}
(here/'receipt.json').open('x',encoding='utf-8').write(json.dumps(receipt,indent=2))
print(json.dumps(receipt));print((here/'run.log').read_text(encoding='utf-8',errors='replace')[-6500:])
raise SystemExit(result.returncode)
