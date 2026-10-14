from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

here=Path(__file__).resolve().parent
context=here/'gpu-health-retry-context-v1'
assert not (here/'actual-mineru-gpu-health-retry-v1').exists(),'Never replay an observed parser attempt'
prepared=json.loads((context/'prepared.json').read_text(encoding='utf-8'))
assert prepared['before_attempts']==5 and prepared['allowed_next_attempt']==6
health=json.loads((context/'latest-health.json').read_text(encoding='utf-8'))
assert health['gpu_health_passed'] and time.time()-health['observed_unix']<1200
failure=json.loads((context/'failed-attempt5-result.json').read_text(encoding='utf-8'))
assert failure['execution']['attempts']==5 and failure['execution']['status']=='RETRY_WAIT'
config_receipt=failure['gpu_config_receipt']
config=Path(config_receipt['owned_config'])
assert hashlib.sha256(config.read_bytes()).hexdigest()==config_receipt['owned_sha256']
assert json.loads(config.read_text(encoding='utf-8'))['device-mode']=='cuda'
assert hashlib.sha256(Path(config_receipt['original_path']).read_bytes()).hexdigest()==config_receipt['original_sha256']
# Recheck available commit immediately before the single possible claim.
memory_probe=subprocess.run(['C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe','-NoProfile','-NonInteractive','-Command','Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory | Select-Object CommittedBytes,CommitLimit | ConvertTo-Json -Compress'],capture_output=True,timeout=15,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
current_memory=json.loads(memory_probe.stdout.decode('utf-8'))
assert current_memory['CommitLimit']-current_memory['CommittedBytes']>5.5*1024**3,'Current headroom fell; do not claim'
(context/'immediately-before-worker-memory.json').open('x',encoding='utf-8').write(json.dumps(current_memory,indent=2))
settings=dict(failure['memory_settings'])
assert settings['RSTV4_MINERU_MMAP_WEIGHTS']=='1'
os.environ.update(settings)
code=(here/'owned_worker_once.py').read_text(encoding='utf-8')
code=code.replace('from runtime_copy_and_serve import','from runtime_copy_and_serve_v8 import')
code=code.replace("result_path=HERE/(args.phase+'-result.json')","phase_dir=HERE/'actual-mineru-gpu-health-retry-v1';phase_dir.mkdir()\n    result_path=phase_dir/(args.phase+'-result.json')")
code=code.replace('exclusive_json(HERE/(args.phase','exclusive_json(phase_dir/(args.phase')
code=code.replace("assert job['queue_class']==queue","assert job['queue_class']==queue\n        assert args.phase=='actual-mineru-once' and job['attempts']==5 and job['fencing_token']==5")
code=code.replace("worker_id='g11-single-owned-'+args.phase","worker_id='g11-single-owned-gpu-health-attempt6'")
code=code.replace("proof={'status':","proof={'gpu_config_receipt':config_receipt,'device_mode':'cuda','memory_settings':settings,'fresh_gpu_health_receipt':'gpu-health-retry-context-v1/latest-health.json','immediate_commit':current_memory,'status':")
exec(compile(code,__file__,'exec'))
