from pathlib import Path
import json
import os
import socket
import sys
repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo/'.tmp/scholar-g11-parallel-v1'))
from runtime_copy_and_serve_v8 import product_guard,check_sources,read_json,RECEIPT,snapshot
product_guard();receipt=read_json(RECEIPT);check_sources(receipt)
root=Path(receipt['root']);before=snapshot(root/'data/catalog.db')
sys.path.insert(0,str(repo.parent/'RSTV4/src'))
from rstv4.catalog_web import create_app
from fastapi.responses import JSONResponse
app=create_app(root)
class Deny:
    def analyze(self,*_args,**_kwargs):raise RuntimeError('G11 recovery UI denies every language-model call')
app.state.discussions.gateway=Deny();app.state.fieldkg_semantics.gateway=Deny()
assert snapshot(root/'data/catalog.db')==before
target='/api/catalog/collections/collection_62ca47c927342115eb5f8fd870af9ca6/jobs/job_76d39031d8cc329ec431e6a896a08f54/retry'
used=False
@app.middleware('http')
async def bounded(request,call_next):
    global used
    if request.method in {'GET','HEAD','OPTIONS'}:return await call_next(request)
    if request.method=='POST' and request.url.path in {'/api/catalog/discussion/context','/api/catalog/discussion/history'}:return await call_next(request)
    if request.method=='POST' and request.url.path==target and not used:
        body=await request.json()
        assert body['expected_fencing_token']==5 and body['expected_status']=='RETRY_WAIT'
        used=True
        return await call_next(request)
    return JSONResponse({'detail':'This owned recovery page allows only the declared single retry and read operations'},status_code=403)
sock=socket.socket();sock.bind(('127.0.0.1',8887));sock.listen(128)
here=repo/'.tmp/scholar-g11-parallel-v1/gpu-health-retry-context-v1'
(here/'service-start.json').open('x',encoding='utf-8').write(json.dumps({'pid':os.getpid(),'port':8887,'root':str(root),'worker_started':False,'language_models_denied':True,'one_retry_target':target},indent=2))
import uvicorn
uvicorn.Server(uvicorn.Config(app,log_level='warning')).run(sockets=[sock])
