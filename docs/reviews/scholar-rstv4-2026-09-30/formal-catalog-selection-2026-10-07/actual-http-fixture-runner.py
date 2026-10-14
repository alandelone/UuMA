import hashlib,json,os,socket,sqlite3,subprocess,sys,tempfile,threading,time
from contextlib import closing
from pathlib import Path
import uvicorn
repo=Path(__file__).resolve().parents[1];project=repo.parent/'RSTV4';sys.path.insert(0,str(project/'tests'))
from test_catalog_paper_selection import library,gateway
from rstv4.acquisition import AcquisitionService
from rstv4.acquisition_worker import AcquisitionWorker
from rstv4.catalog_web import create_app
root=Path(tempfile.mkdtemp(prefix='scui-select-')).resolve();assert root.name.startswith('scui-select-')
db,pdf=library(root)
with closing(sqlite3.connect(db)) as conn:
 frozen={name:conn.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall() for name in ['papers','source_file_versions']}
app=create_app(root);trace=[]
@app.middleware('http')
async def retain_http(request,call_next):
 response=await call_next(request);trace.append({'method':request.method,'path':str(request.url),'status':response.status_code});return response
sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128);port=sock.getsockname()[1];base=f'http://127.0.0.1:{port}'
server=uvicorn.Server(uvicorn.Config(app,log_level='warning'));thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
fixture_path=repo/'.tmp/scholar-existing-paper-fixture-v1.json'
try:
 deadline=time.monotonic()+20
 while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.05)
 assert server.started
 fixture={'root':str(root),'port':port,'process_id':os.getpid(),'collection_source':str(project/'src/rstv4/catalog_collections.js'),'synthetic_file_identity':True,'simulated_screen_model':True,'scientific_approval':False,'browser_verified':False}
 with fixture_path.open('x',encoding='utf-8') as h:json.dump(fixture,h,indent=2)
 subprocess.run(['node',str(repo/'.tmp/scholar-existing-paper-native-v1.mjs'),base,'select',str(fixture_path),str(repo/'.tmp/scholar-existing-paper-selected-v1.json')],check=True)
 selected=json.loads((repo/'.tmp/scholar-existing-paper-selected-v1.json').read_text(encoding='utf-8'));fixture.update({'created':selected['created'],'input':selected['input']})
 fixture_path.write_text(json.dumps(fixture,indent=2),encoding='utf-8')
 model=AcquisitionWorker(root,'model',model_gateway=gateway(),worker_id='explicit-software-screen');screen=model.run_once();assert screen['status']=='SUCCEEDED',screen
 network=AcquisitionWorker(root,'network',worker_id='explicit-software-file-reuse');file_job=network.run_once();assert file_job['status']=='SUCCEEDED',file_job
 subprocess.run(['node',str(repo/'.tmp/scholar-existing-paper-native-v1.mjs'),base,'progress',str(fixture_path),str(repo/'.tmp/scholar-existing-paper-progress-v1.json')],check=True)
 progress=json.loads((repo/'.tmp/scholar-existing-paper-progress-v1.json').read_text(encoding='utf-8'))
 service=AcquisitionService(root);service.pause_collection(fixture['created']['collection_id'],1)
 with closing(sqlite3.connect(db)) as conn:
  assert all(conn.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall()==rows for name,rows in frozen.items())
  assert conn.execute('SELECT COUNT(*) FROM screening_input_snapshots').fetchone()[0]==1
  assert conn.execute('SELECT COUNT(*) FROM source_file_versions').fetchone()[0]==1
  snapshot=dict(zip([col[0] for col in conn.execute('SELECT * FROM screening_input_snapshots').description],conn.execute('SELECT * FROM screening_input_snapshots').fetchone()))
  assert json.loads(snapshot['context_json'])['paper']['doi'] is None
 result={'status':'PASS_ACTUAL_CATALOG_SELECTION_SCOPE_SCREEN_AND_FILE_REUSE','root':str(root),'actual_http_requests':len(trace),'trace':trace,'selected':selected,'progress':progress,'screen_job':screen,'file_job':file_job,'screening_input_snapshot':snapshot,'original_paper_and_file_rows_unchanged':True,'collection_paused':True,'real_model_calls':0,'software_screen_calls':1,'parser_executed':False,'scientific_approval':False,'browser_verified':False}
 with (repo/'.tmp/scholar-existing-paper-native-v1.json').open('x',encoding='utf-8') as h:json.dump(result,h,ensure_ascii=False,indent=2)
 print(json.dumps({k:v for k,v in result.items() if k not in {'trace','selected','progress','screen_job','file_job','screening_input_snapshot'}},ensure_ascii=False))
finally:
 server.should_exit=True;thread.join(10);sock.close()
