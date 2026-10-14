import hashlib,json,os,socket,sqlite3,subprocess,sys,tempfile,threading,time
from contextlib import closing
from pathlib import Path
import httpx,uvicorn
repo=Path(__file__).resolve().parents[1]; project=repo.parent/'RSTV4';sys.path.insert(0,str(project/'tests'))
from test_source_review_withdrawal import dependencies
from test_catalog_review_workflow import act
from test_writing_studio import complete_document
from rstv4.approval import capture_user_approval
from rstv4.research_discussions import ResearchDiscussionService
from rstv4.catalog_web import create_app
from rstv4.studio_api import create_app as studio_app
root=Path(tempfile.mkdtemp(prefix='scholar-scientific-binding-2026-10-06-')).resolve()
assert root.name.startswith('scholar-scientific-binding-2026-10-06-')
service,collection,paper,file,published=dependencies(root)
discussions=ResearchDiscussionService(root)
with discussions._write():pass
discussions.shutdown()
app=create_app(root);subapp=studio_app(root);studio=subapp.state.studio
app.mount('/studio',subapp)
http_trace=[]
@app.middleware('http')
async def retain_actual_http(request,call_next):
 response=await call_next(request);http_trace.append({'method':request.method,'path':request.url.path,'status':response.status_code});return response
authored=studio.create_manuscript('track','Software author structure')
document=complete_document(authored)
document["manuscript_id"]="ms"
print("Isolated software HTTP fixture root:",root,flush=True)
with closing(sqlite3.connect(service.db_path)) as conn,conn:conn.execute("UPDATE collections SET status='PAUSED'")
sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
port=sock.getsockname()[1];base=f'http://127.0.0.1:{port}'
server=uvicorn.Server(uvicorn.Config(app,log_level='warning'));thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
fixture_path=repo/'.tmp/scholar-scientific-binding-fixture-v4.json'
result_path=repo/'.tmp/scholar-scientific-binding-native-v4.json'
try:
 deadline=time.monotonic()+20
 while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.05)
 assert server.started,'Actual HTTP server did not start'
 with httpx.Client(base_url=base,timeout=30) as client:
  opened=client.get('/studio/api/manuscripts/ms/workspace');assert opened.status_code==200,opened.text
  saved=client.put('/studio/api/manuscripts/ms/document',json={'base_revision':0,'operation_id':'actual-software-author-document','document':document});assert saved.status_code==200,saved.text
  with closing(sqlite3.connect(service.db_path)) as conn,conn:conn.execute("UPDATE studio_documents SET active_generated_version_id='old-version',last_generated_revision=revision WHERE manuscript_id='ms'")
  with closing(sqlite3.connect(service.db_path)) as conn:
   frozen={name:conn.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall() for name in ['paper_versions','parse_runs','document_blocks','evidence','manuscript_versions']}
  withdrawn=act(client,file['file_version_id'],'REOPEN_IDENTITY','binding-native-source-withdrawal');assert withdrawn.status_code==201,withdrawn.text
  reapproved=act(client,file['file_version_id'],'APPROVE_IDENTITY','binding-native-source-identity-reapproval');assert reapproved.status_code==201,reapproved.text
  fixture={'root':str(root),'port':port,'pid':os.getpid(),'controller_source':str(project/'src/rstv4/catalog_scientific_review.js'),'synthetic_approved_nodes':True,'simulated_user_boundary':True,'actual_scientific_approval':False,'browser_verified':False}
  with fixture_path.open('x',encoding='utf-8') as h:json.dump(fixture,h,indent=2)
  assets={}
  for name in ['catalog_web.html','catalog_research_overview.js','catalog_research_chat.js','catalog_research_workspaces.js','catalog_collections.js','catalog_review_workflow.js','catalog_scientific_review.js']:
   r=client.get('/' if name=='catalog_web.html' else '/'+name.replace('_','-'));assert r.status_code==200 and r.content==(project/'src/rstv4'/name).read_bytes();assets[name]=hashlib.sha256(r.content).hexdigest()
  subprocess.run(['node',str(repo/'.tmp/scholar-scientific-binding-native-v1.mjs'),base,'propose',str(fixture_path),str(repo/'.tmp/scholar-scientific-binding-proposed-v4.json')],check=True)
  proposed=json.loads((repo/'.tmp/scholar-scientific-binding-proposed-v4.json').read_text(encoding='utf-8'))
  fixture.update({'proposal':proposed['proposal'],'original_bindings':proposed['original_bindings']})
  fixture_path.write_text(json.dumps(fixture,indent=2),encoding='utf-8')
  grant=capture_user_approval(root,profile='scholar',session_id='explicit-isolated-software-fixture',message_id='simulated-user-message-only',user_message=fixture['proposal']['approval_phrase']);assert grant
  subprocess.run(['node',str(repo/'.tmp/scholar-scientific-binding-native-v1.mjs'),base,'apply',str(fixture_path),str(repo/'.tmp/scholar-scientific-binding-applied-v4.json')],check=True)
  applied=json.loads((repo/'.tmp/scholar-scientific-binding-applied-v4.json').read_text(encoding='utf-8'))
  with closing(sqlite3.connect(service.db_path)) as conn:
   assert all(conn.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall()==rows for name,rows in frozen.items())
   assert conn.execute("SELECT content FROM manuscript_versions WHERE manuscript_version_id='old-version'").fetchone()[0]=='Frozen software manuscript'
   assert conn.execute("SELECT COUNT(*) FROM studio_model_calls").fetchone()[0]==0
   assert conn.execute("SELECT COUNT(*) FROM research_discussion_jobs").fetchone()[0]==0
   assert conn.execute("SELECT COUNT(*) FROM manuscript_scientific_review_events").fetchone()[0]==1
   assert conn.execute("SELECT COUNT(*) FROM approval_grants WHERE consumed_at IS NOT NULL").fetchone()[0]==1
  receipt={'status':'PASS_ACTUAL_SCIENTIFIC_BINDING_CONTROLLER_HTTP','root':str(root),'actual_port':port,'http_requests':len(http_trace),'actual_http_trace':http_trace,'assets_sha256':assets,'proposed':proposed,'applied':applied,'source_withdrawal':withdrawn.json(),'file_identity_reapproval':reapproved.json(),'models_called':0,'actual_scientific_approval':False,'simulated_trusted_boundary':True,'browser_verified':False}
  with result_path.open('x',encoding='utf-8') as h:json.dump(receipt,h,ensure_ascii=False,indent=2)
  print(json.dumps({k:v for k,v in receipt.items() if k not in {'proposed','applied','source_withdrawal','file_identity_reapproval','assets_sha256'}},ensure_ascii=False))
finally:
 server.should_exit=True;thread.join(10);sock.close()
