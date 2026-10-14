from pathlib import Path
import json
import os
import subprocess
import time
repo=Path(__file__).resolve().parents[1]
here=repo/'.tmp/scholar-gpu-health-probe-v2';here.mkdir()
records=[]
commands=[
 ['C:/Windows/System32/nvidia-smi.exe','--query-gpu=name,driver_version,memory.total,memory.used,memory.free,utilization.gpu','--format=csv,noheader,nounits'],
 ['C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe','-NoProfile','-NonInteractive','-Command','Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory | Select-Object AvailableMBytes,CommittedBytes,CommitLimit,PercentCommittedBytesInUse | ConvertTo-Json -Compress'],
 ['C:/Users/Alandelone/anaconda3/envs/ragent-mineru122/python.exe','-X','utf8','-c',
  "import json,torch; r={'torch_version':torch.__version__,'cuda_build':torch.version.cuda,'cuda_available':torch.cuda.is_available(),'gpu_count':torch.cuda.device_count()}; print(json.dumps(r),flush=True); assert r['cuda_available']; r['gpu_name']=torch.cuda.get_device_name(0); free,total=torch.cuda.mem_get_info(0); r.update(free_bytes=free,total_bytes=total); x=torch.arange(256,dtype=torch.float32,device='cuda').reshape(16,16); y=torch.eye(16,device='cuda')@x; torch.cuda.synchronize(); assert torch.equal(y.cpu(),torch.arange(256,dtype=torch.float32).reshape(16,16)); r['actual_cuda_matrix_exact']=True; print(json.dumps(r),flush=True)"],
]
env=os.environ.copy();env.update(PYTHONUTF8='1',OMP_NUM_THREADS='1',CUDA_MODULE_LOADING='LAZY')
for n,argv in enumerate(commands,1):
    start=time.monotonic()
    try:
        r=subprocess.run(argv,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=25,creationflags=subprocess.CREATE_NO_WINDOW)
        row={'probe':n,'exit_code':r.returncode,'seconds':time.monotonic()-start,'stdout':r.stdout.decode('utf-8',errors='replace'),'stderr':r.stderr.decode('utf-8',errors='replace')}
    except subprocess.TimeoutExpired as e:
        row={'probe':n,'status':'OWNED_PROBE_TIMED_OUT_AND_TERMINATED','seconds':time.monotonic()-start,'stdout':(e.stdout or b'').decode('utf-8',errors='replace'),'stderr':(e.stderr or b'').decode('utf-8',errors='replace')}
    records.append(row);print(json.dumps(row),flush=True)
receipt={'observed_unix':time.time(),'probes':records,'parser_attempts_started':0,'models_loaded':0,'global_settings_changed':False,'gpu_health_passed':records[-1].get('exit_code')==0,'no_cpu_fallback':True}
(here/'receipt.json').open('x',encoding='utf-8').write(json.dumps(receipt,indent=2))
