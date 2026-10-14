from pathlib import Path
import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from contextlib import closing
repo=Path(__file__).resolve().parents[1]
here=repo/'.tmp/scholar-g11-parallel-v1/gpu-health-retry-context-v1';here.mkdir()
sys.path.insert(0,str(here.parent))
from runtime_copy_and_serve_v8 import product_guard,check_sources,read_json,RECEIPT,snapshot
vector=product_guard();prepared=read_json(RECEIPT);check_sources(prepared)
health=read_json(repo/'.tmp/scholar-gpu-health-probe-v2/receipt.json')
assert health['gpu_health_passed'] and time.time()-health['observed_unix']<600
assert all(p['exit_code']==0 for p in health['probes'])
cuda=json.loads(health['probes'][2]['stdout'].strip().splitlines()[-1])
memory=json.loads(health['probes'][1]['stdout'])
assert cuda['actual_cuda_matrix_exact'] and cuda['free_bytes']>10*1024**3
assert memory['CommitLimit']-memory['CommittedBytes']>5.5*1024**3
root=Path(prepared['root']);db=root/'data/catalog.db'
with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as c:
    c.row_factory=sqlite3.Row
    job=dict(c.execute('SELECT * FROM acquisition_jobs WHERE job_id=?',('job_76d39031d8cc329ec431e6a896a08f54',)).fetchone())
    assert job['status']=='RETRY_WAIT' and job['attempts']==5 and job['fencing_token']==5
    assert job['lease_owner'] is None and job['lease_expires_at'] is None
failure=read_json(here.parent/'actual-mineru-gpu-mmap-v1/actual-mineru-once-result.json')
assert failure['execution']['attempts']==5 and failure['execution']['status']=='RETRY_WAIT'
config=failure['gpu_config_receipt']
assert hashlib.sha256(Path(config['owned_config']).read_bytes()).hexdigest()==config['owned_sha256']
assert hashlib.sha256(Path(config['original_path']).read_bytes()).hexdigest()==config['original_sha256']
assert json.loads(Path(config['owned_config']).read_text(encoding='utf-8'))['device-mode']=='cuda'
with socket.socket() as probe:probe.bind(('127.0.0.1',8887))
(here/'before-native-retry-all-tables.json').open('x',encoding='utf-8').write(json.dumps(snapshot(db),indent=2))
(here/'latest-health.json').open('x',encoding='utf-8').write(json.dumps(health,indent=2))
(here/'failed-attempt5-result.json').open('xb').write((here.parent/'actual-mineru-gpu-mmap-v1/actual-mineru-once-result.json').read_bytes())
note='''

2026-10-14 G11 next GPU context: attempt5 is terminal RETRY_WAIT/fence5/no lease.
The 02:17Z NVML error was retained. Current actual NVIDIA query and pinned Torch
CUDA matrix compute both pass, GPU free >10GiB and measured Windows commit
headroom >5.5GiB (prior attempt3 approximately4GiB). These are fresh conditions,
not a successful parser claim. Permit exactly one native-retried original job
attempt6 under the same CUDA/sequential/LAZY/auto_growth/mmap settings and all
original models; no CPU fallback, remote language models, original data replay,
weaker six-reference quality assertions, global configuration or driver changes.
Preserve failed attempts1-5, corrected reference6 action/candidate, old versions,
and source/science/model history. A failed/timed-out observation never authorizes
another execution; inspect the same live handle and terminal receipt instead.
'''
for name in ['rules/testing-contracts.md','repomemory/findings.md']:
    p=repo/name;(here/(p.name+'.prior.raw')).open('xb').write(p.read_bytes())
    with p.open('a',encoding='utf-8',newline='') as f:f.write(note)
argv=[str(repo/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'),'-X','utf8',str(repo/'.tmp/scholar-g11-gpu-healthy-serve-v1.py')]
with (here/'service-stdout.log').open('xb') as out,(here/'service-stderr.log').open('xb') as err:
    proc=subprocess.Popen(argv,cwd=repo,env=os.environ.copy(),stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
(here/'launched.json').open('x',encoding='utf-8').write(json.dumps({'pid':proc.pid,'argv':argv,'port':8887,'worker_started':False},indent=2))
end=time.monotonic()+25
while True:
    try:
        with urllib.request.urlopen('http://127.0.0.1:8887/',timeout=2) as response:assert response.status==200
        break
    except Exception:
        assert time.monotonic()<end,'Inspect exact child, do not replay preparation'
        time.sleep(.2)
assert json.loads(json.dumps(snapshot(db)))==read_json(here/'before-native-retry-all-tables.json')
receipt={'status':'PASS_FRESH_GPU_CONDITIONS_READY_FOR_SINGLE_NATIVE_RETRY','root':str(root),'port':8887,'job_id':job['job_id'],'before_attempts':5,'allowed_next_attempt':6,'gpu_smoke_passed':True,'models_and_full_quality_preserved':True,'cpu_retry_executed':False,'source_vector':vector}
(here/'prepared.json').open('x',encoding='utf-8').write(json.dumps(receipt,indent=2))
print(json.dumps({k:v for k,v in receipt.items() if k!='source_vector'}))
