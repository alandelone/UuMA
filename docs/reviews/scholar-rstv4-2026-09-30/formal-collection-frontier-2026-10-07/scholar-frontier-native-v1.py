import json,os,socket,sqlite3,subprocess,sys,tempfile,threading,time
from contextlib import closing
from pathlib import Path
import uvicorn
repo=Path(__file__).resolve().parents[1];project=repo.parent/'RSTV4';sys.path.insert(0,str(project/'tests'))
from test_catalog_paper_selection import library,gateway
from rstv4.acquisition import AcquisitionService
from rstv4.acquisition_worker import AcquisitionWorker
from rstv4.catalog_web import create_app
root=Path(tempfile.mkdtemp(prefix='scui-frontier-')).resolve();assert root.is_relative_to(Path(tempfile.gettempdir()).resolve()) and root.name.startswith('scui-frontier-')
db,pdf=library(root);service=AcquisitionService(root)
with closing(sqlite3.connect(db)) as conn:
 frozen={name:conn.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall() for name in ['papers','source_file_versions']}
app=create_app(root);trace=[]
@app.middleware('http')
async def retain_http(request,call_next):
 response=await call_next(request);trace.append({'method':request.method,'path':str(request.url),'status':response.status_code});return response
sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128);port=sock.getsockname()[1];base=f'http://127.0.0.1:{port}'
server=uvicorn.Server(uvicorn.Config(app,log_level='warning'));thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
fixture_path=repo/'.tmp/scholar-frontier-fixture-v1.json';stop=threading.Event();idle=None
try:
 deadline=time.monotonic()+20
 while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.05)
 assert server.started
 fixture={'root':str(root),'port':port,'process_id':os.getpid(),'collection_source':str(project/'src/rstv4/catalog_collections.js'),'synthetic_file_identity':True,'simulated_screen_model':True,'software_parse_publication':True,'scientific_approval':False,'browser_verified':False}
 with fixture_path.open('x',encoding='utf-8') as h:json.dump(fixture,h,indent=2)
 def phase(name):
  target=repo/('.tmp/scholar-frontier-'+name+'-v1.json');subprocess.run(['node',str(repo/'.tmp/scholar-frontier-native-v1.mjs'),base,name,str(fixture_path),str(target)],check=True);return json.loads(target.read_text(encoding='utf-8'))
 created=phase('create');fixture['created']=created['created'];fixture_path.write_text(json.dumps(fixture,indent=2),encoding='utf-8');cid=fixture['created']['collection_id']
 screen=AcquisitionWorker(root,'model',model_gateway=gateway(),worker_id='actual-software-screen').run_once();assert screen['status']=='SUCCEEDED',screen
 assert service.claim_job('actual-budget-check',['NETWORK']) is None
 published=service.publish_parse_result(cid,'existing','existing-file',parser_name='explicit-software-fixture',parser_version='1',config={},manifest={},blocks=[{'text':'Original software source body'}],references=[{'raw_text':'Original reference 10.1234/frontier-native','page_number':4,'location':{'section':'References','line':9}}])
 worker=AcquisitionWorker(root,'parser',worker_id='actual-idle-parser');idle=threading.Thread(target=worker.run_forever,kwargs={'idle_seconds':.1,'stop_event':stop},daemon=True);idle.start()
 deadline=time.monotonic()+10
 while time.monotonic()<deadline:
  rows=service.collection_progress(cid)['workers']
  if any(w['worker_id']=='actual-idle-parser' and w['state']=='IDLE' for w in rows):break
  time.sleep(.05)
 assert idle.is_alive()
 recovered=phase('recover');stop.set();idle.join(10);assert not idle.is_alive();stopped=phase('stopped')
 with closing(sqlite3.connect(db)) as conn:
  for name,rows in frozen.items():
   actual=conn.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall();assert all(row in actual for row in rows)
  assert conn.execute('SELECT COUNT(*) FROM collection_budget_events WHERE collection_id=?',(cid,)).fetchone()[0]==2
  assert conn.execute('SELECT COUNT(*) FROM acquisition_attempts').fetchone()[0]==1
  assert conn.execute('SELECT COUNT(*) FROM manuscript_scientific_review_requests').fetchone()[0]==0
 result={'status':'PASS_ACTUAL_BUDGET_REFERENCE_FRONTIER_AND_IDLE_WORKER','root':str(root),'trace':trace,'actual_http_requests':len(trace),'screen_job':screen,'software_parse_publication':published,'created':created,'recovered':recovered,'stopped':stopped,'original_paper_and_file_rows_preserved':True,'real_model_calls':0,'software_screen_calls':1,'actual_parser_executed':False,'scientific_approval':False,'browser_verified':False,'collection_paused':True}
 with (repo/'.tmp/scholar-frontier-native-v1.json').open('x',encoding='utf-8') as h:json.dump(result,h,ensure_ascii=False,indent=2)
 print(json.dumps({k:v for k,v in result.items() if k not in {'trace','screen_job','software_parse_publication','created','recovered','stopped'}},ensure_ascii=False))
finally:
 stop.set()
 if idle:idle.join(10)
 server.should_exit=True;thread.join(10);sock.close()
