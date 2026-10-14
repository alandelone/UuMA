import json,sqlite3
from pathlib import Path
from rstv4.acquisition import AcquisitionService
from rstv4.acquisition_worker import AcquisitionWorker,ROLE_QUEUES
from rstv4.model_gateway import UnlimitedLLMGateway
repo=Path(__file__).resolve().parents[1]
meta=json.loads((repo/'.tmp/scholar-durable-model-native-v2.json').read_text(encoding='utf-8'))
root=Path(meta['root']);service=AcquisitionService(root)
ROLE_QUEUES['model']=['MODEL_SKELETON']
job=service.get_job(meta['job_id'])
if job['status'] in {'RESOURCE_WAIT','RETRY_WAIT'}:
 service.retry_step(job['job_id'],job['fencing_token'],expected_status=job['status'],expected_updated_at=job['updated_at'])
worker=AcquisitionWorker(root,'model',model_gateway=UnlimitedLLMGateway(root),worker_id='actual-located-intent-v2')
result=worker.run_once()
assert result is None or result['job_id']==meta['job_id']
calls=[c for c in service.get_paper(meta['request']['paper_id'])['model_calls'] if c['job_id']==meta['job_id']]
proof={'root':str(root),'job':service.get_job(meta['job_id']),'step':result,'calls':calls,'scientific_approval':False}
Path(__file__).with_suffix('.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'job_status':proof['job']['status'],'calls':[{'task':c['task'],'status':c['status'],'run':(c.get('contract') or {}).get('router_run_id')} for c in calls]}),flush=True)
