import hashlib
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import closing
from pathlib import Path
import sqlite3

import httpx
import uvicorn
from rstv4.approval import capture_user_approval
from rstv4.catalog_web import create_app
from rstv4.models import DecisionProposalInput,ExperimentPlanInput
from rstv4.track_first import TrackFirstService

repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo.parent/'RSTV4/tests'))
from test_track_first_fieldkg import create_hierarchy

root=Path(tempfile.mkdtemp(prefix='scui-artifact-')).resolve()
service=TrackFirstService(root)
_,_,track,project=create_hierarchy(service)
work=root/'projects'/project['slug'];work.mkdir(parents=True)
script=work/'experiment.py'
script.write_text("import json\nfrom pathlib import Path\nprint('Actual software execution output ' + 'x'*2200)\nPath('metrics.json').write_text(json.dumps({'software_value':1}))\nPath('result.txt').write_text('Original native artifact')\n",encoding='utf-8')
method=service.propose_decision(track['track_id'],DecisionProposalInput(kind='method',statement='Isolated software execution fixture',rationale='Software approval and artifact path only'))
capture_user_approval(root,profile='scholar',session_id='software-fixture',message_id='method-approval-fixture',user_message=method['approval_phrase'])
service.approve_decision(method['proposal_id'],1)
plan=service.propose_experiment_plan(track['track_id'],ExperimentPlanInput(method_node_id=method['node_id'],argv=[sys.executable,str(script)],script_path='experiment.py',script_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),metrics_json_path='metrics.json'),project['project_id'])
capture_user_approval(root,profile='scholar',session_id='software-fixture',message_id='plan-approval-fixture',user_message=plan['approval_phrase'])
service.approve_experiment_plan(plan['plan_id'],1)
run=service.run_experiment(plan['plan_id'])
assert run['exit_code']==0
app=create_app(root);sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
server=uvicorn.Server(uvicorn.Config(app,log_level='warning'))
thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
trace=[]
sha=lambda raw:hashlib.sha256(raw).hexdigest()
try:
    deadline=time.monotonic()+15
    while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.05)
    assert server.started
    with closing(sqlite3.connect(service.db_path.as_uri()+'?mode=ro',uri=True)) as conn:
        scientific={name:conn.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall() for name in ['research_nodes','decisions','approval_grants','evidence']}
    with httpx.Client(base_url=f'http://127.0.0.1:{sock.getsockname()[1]}',timeout=10) as client:
        response=client.get(f"/api/catalog/tracks/{track['track_id']}/workspace");trace.append({'path':str(response.request.url),'status':response.status_code});assert response.status_code==200
        recorded=next(r for r in response.json()['runs'] if r['run_id']==run['run_id'])
        assert recorded['status']=='COMPLETED' and len(recorded['detail']['stdout'])>2200
        assert recorded['detail']['environment']['python_version'] and recorded['detail']['cwd']==str(work.resolve())
        artifact=recorded['detail']['artifacts'][0]
        endpoint=f"/api/catalog/tracks/{track['track_id']}/runs/{run['run_id']}/artifacts/0"
        download=client.get(endpoint);trace.append({'path':endpoint,'status':download.status_code});assert download.status_code==200
        assert sha(download.content)==artifact['sha256']
        wrong=client.get(endpoint.replace(track['track_id'],'wrong-track'));trace.append({'path':'wrong-track-artifact','status':wrong.status_code});assert wrong.status_code==404
        metrics=work/'metrics.json';metrics.write_text('Changed artifact',encoding='utf-8')
        changed=client.get(endpoint);trace.append({'path':endpoint,'status':changed.status_code});assert changed.status_code==409
    with closing(sqlite3.connect(service.db_path.as_uri()+'?mode=ro',uri=True)) as conn:
        assert scientific=={name:conn.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall() for name in scientific}
finally:
    server.should_exit=True;thread.join(10);sock.close()
proof={'status':'PASS_ACTUAL_SCRIPT_AND_HTTP_ARTIFACT_READBACK_SOFTWARE_APPROVAL_FIXTURE','root':str(root),'run_id':run['run_id'],'plan_id':plan['plan_id'],
       'actual_http_requests':len(trace),'requests':trace,'script_actually_executed':True,'approval_is_isolated_software_fixture':True,'scientific_approval':False,'browser_verified':False,'new_model_calls':0}
with (repo/'.tmp/scholar-experiment-artifacts-native-v1.json').open('x',encoding='utf-8') as handle:json.dump(proof,handle,indent=2)
print(json.dumps({k:v for k,v in proof.items() if k!='requests'}),flush=True)
