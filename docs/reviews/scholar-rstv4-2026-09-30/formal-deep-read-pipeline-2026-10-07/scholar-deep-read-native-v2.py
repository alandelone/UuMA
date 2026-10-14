import hashlib,json,os,socket,sqlite3,subprocess,tempfile,threading,time
from contextlib import closing
from pathlib import Path
import uvicorn
from rstv4.acquisition import AcquisitionService
from rstv4.acquisition_worker import AcquisitionWorker
from rstv4.catalog_web import create_app
from rstv4.model_gateway import UnlimitedLLMGateway
repo=Path(__file__).resolve().parents[1];project=repo.parent/'RSTV4';parent_path=repo/'.tmp/scholar-review-recovery-native-v1.json';parent=json.loads(parent_path.read_text(encoding='utf-8'))
assert parent['status']=='PASS_ACTUAL_IDENTITY_REVIEW_AND_REAL_MINERU_PARSER_RECOVERY' and parent['actual_local_mineru_executed']
sha=lambda raw:hashlib.sha256(raw).hexdigest();source=Path(parent['root']).resolve()/'data/catalog.db';original_sha=sha(source.read_bytes())
previous=json.loads((repo/'.tmp/scholar-deep-read-native-v1.json').read_text(encoding='utf-8'));root=Path(previous['root']).resolve();assert root.name.startswith('scui-deep-') and root.is_relative_to(Path(tempfile.gettempdir()).resolve());db=root/'data/catalog.db'
assert original_sha==previous['original_source_database_sha256']
assert sha(source.read_bytes())==original_sha
service=AcquisitionService(root);app=create_app(root);trace=[]
with closing(sqlite3.connect(db)) as initial:
 frozen_tables={name:initial.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall() for name in ['papers','source_file_versions','parse_runs','paper_versions','document_blocks','reference_entries','catalog_review_actions','approval_grants','manuscript_scientific_review_requests','manuscript_scientific_review_events']}
scientific_before={name:frozen_tables[name] for name in ['approval_grants','manuscript_scientific_review_requests','manuscript_scientific_review_events']}
@app.middleware('http')
async def trace_http(request,call_next):
 response=await call_next(request);trace.append({'method':request.method,'path':str(request.url),'status':response.status_code});return response
sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128);port=sock.getsockname()[1];base=f'http://127.0.0.1:{port}'
server=uvicorn.Server(uvicorn.Config(app,log_level='warning'));thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
fixture_path=repo/'.tmp/scholar-deep-read-fixture-v2.json';out=repo/'.tmp/scholar-deep-read-native-v2.json'
proof={'status':'STARTED_ACTUAL_MODEL_PIPELINE','root':str(root),'original_source_database_sha256':original_sha,'source_database':str(source),'parent_parse_receipt_sha256':sha(parent_path.read_bytes()),'scientific_approval':False,'browser_verified':False,'native_parser_reexecuted':False,'real_model_gateway':'http','jobs':[]}
def save():out.write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
def phase(name):
 target=repo/('.tmp/scholar-deep-read-'+name+'-v2.json');subprocess.run(['node',str(repo/'.tmp/scholar-deep-read-native-v2.mjs'),base,name,str(fixture_path),str(target)],check=True);return json.loads(target.read_text(encoding='utf-8'))
try:
 deadline=time.monotonic()+20
 while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.05)
 assert server.started
 fixture={'root':str(root),'port':port,'process_id':os.getpid(),'collection_source':str(project/'src/rstv4/catalog_collections.js'),'paper_id':parent['paper_id'],'collection_id':parent['collection_id'],'parse_run_id':parent['published']['parse_run_id'],'source_is_explicit_software_document':True}
 with fixture_path.open('x',encoding='utf-8') as h:json.dump(fixture,h,indent=2)
 requested=phase('request');fixture['request']=requested;fixture_path.write_text(json.dumps(fixture,indent=2),encoding='utf-8');proof['request']=requested;save()
 os.environ['RSTV4_LLM_MODE']='http';gateway=UnlimitedLLMGateway(root);assert gateway.mode=='http';worker=AcquisitionWorker(root,'model',model_gateway=gateway,worker_id='actual-quickread-skeleton-assessment')
 for iteration in range(8):
  execution=worker.run_once()
  if execution is None:break
  proof['jobs'].append(execution);save();print(json.dumps({'stage':execution['job_type'],'status':execution['status'],'completed_jobs':len(proof['jobs'])}),flush=True)
  assert execution['status']=='SUCCEEDED', 'Actual model stage failed; retain original receipt and task'
 else:raise RuntimeError('Actual model pipeline exceeded bounded verification jobs')
 with closing(sqlite3.connect(db)) as conn:
  before_counts=conn.execute('SELECT COUNT(*) FROM acquisition_model_call_events').fetchone()[0]
 before=sha(db.read_bytes());verified=phase('readback');assert sha(db.read_bytes())==before
 with closing(sqlite3.connect(db)) as conn:
  assert conn.execute('SELECT COUNT(*) FROM acquisition_model_call_events').fetchone()[0]==before_counts
  for name,rows in frozen_tables.items():assert conn.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall()==rows
  assert not scientific_before['manuscript_scientific_review_requests'] and not scientific_before['manuscript_scientific_review_events']
 collection=service.get_collection(fixture['collection_id']);service.pause_collection(fixture['collection_id'],collection['revision'])
 assert sha(source.read_bytes())==original_sha
 proof.update(status='PASS_ACTUAL_QUICKREAD_SKELETON_ASSESSMENT_AND_FORMAL_READBACK',actual_http_requests=len(trace),trace=trace,readback=verified,real_model_calls=len(verified['original_calls']),original_source_database_unchanged=True,collection_paused=True,scientific_tables_unchanged=True);save();print(json.dumps({k:v for k,v in proof.items() if k in {'status','root','actual_http_requests','real_model_calls','original_source_database_unchanged','collection_paused','scientific_approval','browser_verified','native_parser_reexecuted'}}),flush=True)
finally:
 server.should_exit=True;thread.join(10);sock.close()
