from pathlib import Path
import hashlib,json,os,socket,subprocess,sys,tempfile,time
repo=Path(__file__).resolve().parents[1];receipt_path=repo/'.tmp/scholar-citation-source-native-v1.json'
if len(sys.argv)>1:
 import uvicorn
 from fastapi.middleware.cors import CORSMiddleware
 from rstv4.studio_api import create_app
 fixture=json.loads(receipt_path.read_text(encoding='utf-8'))
 app=create_app(fixture['root'])
 app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:3008'],allow_methods=['*'],allow_headers=['*'])
 def software_realization(task,payload):
  if task=='writing_chat':
   references=[item for item in payload['retrieved_evidence'] if item.get('reference_snapshot_source')=='generation_input' and (item.get('source_context') or {}).get('available') is True]
   assert len(references)==2 and all('parsed_blocks' not in item['source_context'] for item in references)
   return {'answer':'Software source check: keep this original generated paragraph and source version. No author change is applied.',
           'evidence_ids':[item['evidence_id'] for item in references],
           '_contract':{'actual_model':'TEST_FIXTURE_SOURCE_NATIVE','task':task,'fixture':True}}
  assert task=='paragraph_realization'
  evidence=payload['selected_evidence'];assert len(evidence)==2
  thoughts=[t for i in payload['intents'] for t in i['thoughts']]
  return {'paragraph':f"First source [@{evidence[1]['evidence_id']}]. Next [@{evidence[0]['evidence_id']}]. Repeat [@{evidence[1]['evidence_id']}].",
          'sentence_mappings':[{'sentence':0,'thought_ids':[t['id'] for t in thoughts]}],
          '_contract':{'actual_model':'TEST_FIXTURE_SOURCE_NATIVE','task':task}}
 app.state.studio.gateway.analyze=software_realization
 from types import SimpleNamespace
 app.state.discussions.gateway=SimpleNamespace(analyze=software_realization)
 uvicorn.run(app,host='127.0.0.1',port=8881,log_level='warning');raise SystemExit()
for port in [3008,8881]:
 with socket.socket() as handle:assert handle.connect_ex(('127.0.0.1',port))!=0
root=Path(tempfile.mkdtemp(prefix='scui-citation-source-native-')).resolve()
assert root.parent==Path(tempfile.gettempdir()).resolve()
sys.path.insert(0,str(repo.parent/'RSTV4/tests'))
from test_studio_source_context import source_studio
service,ms,evidence,source,pdf,document=source_studio(root,compile_pdf=True)
service._executor.shutdown(wait=True)
receipt={'root':str(root),'manuscript_id':ms,'initial_document':document,'evidence':evidence,'original_source':source,'original_pdf':str(pdf),
         'original_pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'software_fixture':True,'scientific_acceptance':False,'actual_remote_model_calls':0,
         'download_testing_resumed':True,'old_runtime_not_modified':True}
with receipt_path.open('x',encoding='utf-8') as handle:json.dump(receipt,handle,ensure_ascii=False,indent=2)
source_code=(repo/'.tmp/scholar-template-build-v3.py').read_text(encoding='utf-8').replace('scholar-template-build-v3.','scholar-citation-source-build-v1.').replace('scui-template-build-','scui-citation-source-build-').replace('127.0.0.1:8877','127.0.0.1:8881').replace('--max-old-space-size=1536','--max-old-space-size=512').replace("RAYON_NUM_THREADS='2', UV_THREADPOOL_SIZE='2'","RAYON_NUM_THREADS='1', UV_THREADPOOL_SIZE='1'")
exec(compile(source_code,str(repo/'.tmp/scholar-template-build-v3.py'),'exec'),{'__file__':str(repo/'.tmp/scholar-template-build-v3.py')})
build=json.loads((repo/'.tmp/scholar-citation-source-build-v1.json').read_text(encoding='utf-8'));assert build['status']=='PASS'
processes={};env={**os.environ,'PYTHONPATH':str(repo.parent/'RSTV4/src'),'PYTHONUTF8':'1','NODE_OPTIONS':'--max-old-space-size=512','RAYON_NUM_THREADS':'1','UV_THREADPOOL_SIZE':'1'}
for name,command,cwd in [('backend',[sys.executable,str(Path(__file__).resolve()),'serve'],repo),('frontend',['cmd.exe','/c','npm.cmd','run','start','--','--port','3008','--hostname','127.0.0.1'],Path(build['root']))]:
 with (repo/f'.tmp/scholar-citation-source-{name}-runtime-v1.log').open('x',encoding='utf-8') as log:
  process=subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
 processes[name]=process.pid
import httpx
ready=set()
with httpx.Client(timeout=3) as client:
 deadline=time.monotonic()+45
 while len(ready)<2 and time.monotonic()<deadline:
  for name,url in [('backend',f'http://127.0.0.1:8881/api/manuscripts/{ms}/workspace'),('frontend','http://127.0.0.1:3008/')]:
   if name in ready:continue
   try:
    if client.get(url).status_code==200:ready.add(name)
   except httpx.HTTPError:pass
  if len(ready)<2:time.sleep(.3)
receipt.update(production_root=build['root'],processes=processes,ready=sorted(ready),url=f'http://127.0.0.1:3008/?manuscript={ms}&view=reading&left=0&right=0&chat=0')
receipt_path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
assert ready=={'backend','frontend'}
print(json.dumps({k:receipt[k] for k in ['root','manuscript_id','production_root','processes','ready','url','original_pdf_sha256']}),flush=True)
