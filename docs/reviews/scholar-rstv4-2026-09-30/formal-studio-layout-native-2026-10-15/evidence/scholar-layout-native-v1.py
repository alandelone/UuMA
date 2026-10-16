"""One layout-only native recompile on preserved complex fixture; models denied."""
from pathlib import Path
import itertools
from copy import deepcopy

repo=Path(__file__).resolve().parents[1]
code=(repo/'.tmp/scholar-studio-current-native-restart-v10.py').read_text(encoding='utf8')
code=code[:code.index("if __name__=='__main__'")]
code=code.replace("HERE=REPO/'.tmp/scholar-studio-current-native-restart-v10'","HERE=REPO/'.tmp/scholar-layout-native-v1'")
code=code.replace("workspace['document_revision']==workspace['last_generated_revision']==62","workspace['document_revision']==r['expected_document_revision'] and workspace['last_generated_revision']==r['expected_generated_revision']")
code=code.replace("workspace['manuscript']['revision']==6","workspace['manuscript']['revision']==r['expected_workflow_revision']")
code=code.replace('scui-publication-chain-build-mlpu7aqn','scui-layout-build-4pfou5jy')
code=code.replace("str(REPO/'.tmp/scholar-studio-current-native-restart-v10-stop-owned.py')","str(REPO/'.tmp/scholar-layout-native-v1-stop.py')")
exec(compile(code,__file__,'exec'))
ROUND='review_round_e4845ca796d74594b33b86fb529b4404'
SOURCE='manuscript_version_e1c764ab2d5a4e97898eda9f5d815d01'
canon=lambda value:json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def prepare_layout():
    HERE.mkdir(exist_ok=True)
    assert not any(HERE.iterdir()), 'Never overwrite a prepared runtime or replay preparation'
    previous=REPO/'.tmp/scholar-block-menu-native-v1'
    assert read(previous/'owned-stop-terminal.json')['status']=='EXACT_OWNED_FRONTEND_AND_BACKEND_STOPPED_PORTS_FREE'
    r=read(previous/'receipt.json');root=Path(r['root']);before=snap(root/'data/catalog.db')
    assert before==read(previous/'after-explicit-delete-undo110.json')
    document=next(x for x in records(before,'studio_documents') if x['manuscript_id']==MS)
    manuscript=next(x for x in records(before,'manuscripts') if x['manuscript_id']==MS)
    assert document['revision']==83 and document['last_generated_revision']==79 and document['active_generated_version_id']==SOURCE
    source_change=next(c for c in records(before,'studio_changes') if any(o['operation_id']==c['operation_id'] and o['resulting_revision']==79 for o in records(before,'studio_operations')))
    original=json.loads(source_change['after_json']);current=json.loads(document['document_json'])
    allowed=[]
    for relation_restored,label_restored,narrow in itertools.product([False,True],repeat=3):
        d=deepcopy(current)
        if relation_restored:d['argument_relations'][0]['condition']=original['argument_relations'][0]['condition']
        if label_restored:
            for s in d['sections']:
                for p in s['paragraphs']:
                    for i in p['intents']:
                        if i['id']=='intent_7e9e321878984056975695ce719e3555':i['label']='Research Context — SOFTWARE_FIXTURE intent label only'
        if narrow:d['layout']={'page_margin':'narrow'}
        allowed.append(d)
    assert allowed[6]==original
    r['backend_source_vector']={n:sha(RST/n) for n in r['backend_source_vector']}
    for n in ['src/rstv4/studio_layout.py','tests/test_studio_layout.py','tests/test_studio_layout_integration.py']:r['backend_source_vector'][n]=sha(RST/n)
    build=read(REPO/'.tmp/scholar-layout-build-v1.json');assert build['status']=='PASS'
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    r.update(status='PRESERVED_R83_V6_ONE_LAYOUT_RECOMPILE_MODELS_DENIED',frontend_root=str(Path(build['root']).resolve()),frontend_port=port,
             frontend_product_vector={n:sha(REPO.parent/'writing-studio'/n) for n in r['frontend_product_vector']},frontend_dist_vector=build['dist_files'],expected_document_revision=83,expected_generated_revision=79,
             expected_workflow_revision=manuscript['revision'],stop_nonce=uuid.uuid4().hex,stop_file=str(HERE/'stop.request.json'))
    guard(r);write('receipt.json',r);write('before110-all-tables.json',before);write('before110-all-files.json',filemap(root))
    write('previous-owned-identity-audit.json',read(previous/'owned-stop-terminal.json'))
    write('allowed-author-documents.json',allowed);write('source-v6-author79.json',original)
    write('reuse-preflight.json',{'same_preserved_root':str(root),'author_revision':83,'generated_input_revision':79,'fixed_source':SOURCE,'only_document_variants':8,
                                'one_layout_recompile_only':True,'one_new_round_and_import_only':True,'one_new_package_only':True,'models_workers_gpu':0,'new_schema_or_database_copies':0})
    print(json.dumps({'frontend_port':port,'root':str(root),'status':'PREPARED'}))

def serve():
    import uvicorn
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse,Response
    sys.path.insert(0,str(RST/'src'))
    from rstv4.studio_api import create_app
    r=read(HERE/'receipt.json');guard(r);root=Path(r['root']);baseline=read(HERE/'before110-all-tables.json')
    assert snap(root/'data/catalog.db')==baseline
    app=create_app(root);app.state.studio.gateway=Deny();app.state.discussions.gateway=Deny()
    assert snap(root/'data/catalog.db')==baseline
    allowed_documents={canon(d) for d in read(HERE/'allowed-author-documents.json')}
    count=0
    @app.middleware('http')
    async def boundary(request,call_next):
        nonlocal count
        method=request.method;path=request.url.path
        if method in {'GET','HEAD','OPTIONS'}:return await call_next(request)
        base=f'/api/manuscripts/{MS}';raw=await request.body()
        try:body=json.loads(raw)
        except Exception:body=None
        allowed=method=='POST' and path in {'/api/research/discussion/context','/api/research/discussion/history'}
        if method=='PUT' and path==base+'/document':allowed=isinstance(body,dict) and canon(body.get('document')) in allowed_documents
        once=None
        if method=='POST' and path==base+'/review-rounds':
            allowed=isinstance(body,dict) and body.get('round_number')==4 and body.get('baseline_manuscript_version_id')==SOURCE
            once='new-round-post-once.json'
        if method=='POST' and re.fullmatch(r'/api/review-rounds/[^/]+/comments',path):
            rid=path.split('/')[3]
            with closing(sqlite3.connect((root/'data/catalog.db').as_uri()+'?mode=ro',uri=True)) as c:
                allowed=c.execute('SELECT 1 FROM review_rounds WHERE review_round_id=? AND manuscript_id=? AND round_number=4',(rid,MS)).fetchone() is not None
            once='new-import-post-once.json'
        if method=='PATCH' and re.fullmatch(r'/api/comments/[^/]+',path):
            cid=path.rsplit('/',1)[1]
            with closing(sqlite3.connect((root/'data/catalog.db').as_uri()+'?mode=ro',uri=True)) as c:
                allowed=c.execute('SELECT 1 FROM review_comments a JOIN review_rounds r USING(review_round_id) WHERE a.comment_id=? AND r.manuscript_id=? AND r.round_number=4',(cid,MS)).fetchone() is not None
        if method=='POST' and path==base+'/jobs':
            allowed=False
            if isinstance(body,dict) and body.get('job_kind')=='GENERATE' and body.get('request')=={'layout_replay_version_id':SOURCE}:
                current=app.state.studio.get_workspace(MS)
                expected=deepcopy(read(HERE/'source-v6-author79.json'));expected['layout']={'page_margin':'narrow'}
                allowed=current['document']==expected and body.get('input_revision')==current['document_revision']
                once='layout-generate-post-once.json'
            elif isinstance(body,dict) and body.get('job_kind')=='SUBMISSION_PACKAGE':
                current=app.state.studio.get_workspace(MS)
                rid=body.get('request',{}).get('review_round_id')
                with closing(sqlite3.connect((root/'data/catalog.db').as_uri()+'?mode=ro',uri=True)) as c:
                    valid=c.execute('SELECT 1 FROM review_rounds WHERE review_round_id=? AND manuscript_id=? AND round_number=4',(rid,MS)).fetchone() is not None
                allowed=valid and current['last_generated_revision']==current['document_revision'] and current['active_generated_version_id']!=SOURCE and body.get('input_revision')==current['document_revision']
                once='layout-package-post-once.json'
        if not allowed:return JSONResponse({'detail':'This isolated acceptance permits only the eight declared restoration/layout documents, one fixed-v6 layout replay, round4 review and one resulting package; all models and other execution denied.'},status_code=403)
        if once:
            if (HERE/once).exists():return JSONResponse({'detail':'The single declared operation is already consumed; inspect its original receipt.'},status_code=409)
            write(once,{'method':method,'path':path,'body':body,'body_sha256':hashlib.sha256(raw).hexdigest()})
        count+=1;serial=count
        write(f'action-{serial:03d}-request.json',{'method':method,'path':path,'body_utf8':raw.decode('utf8'),'body_sha256':hashlib.sha256(raw).hexdigest()})
        response=await call_next(request);content=b''.join([chunk async for chunk in response.body_iterator])
        try:result=json.loads(content)
        except Exception:result={'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)}
        write(f'action-{serial:03d}-response.json',{'status_code':response.status_code,'body':result});write(f'action-{serial:03d}-all-tables.json',snap(root/'data/catalog.db'))
        return Response(content,status_code=response.status_code,headers=dict(response.headers))
    app.add_middleware(CORSMiddleware,allow_origins=[f"http://127.0.0.1:{r['frontend_port']}"],allow_credentials=False,allow_methods=['GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS'],allow_headers=['Content-Type','If-Match','X-Operation-Id'])
    sock=socket.socket();sock.bind(('127.0.0.1',8877));sock.listen(128)
    write('backend-ready.json',{'pid':os.getpid(),'identity':identity(os.getpid()),'port':8877,'root':str(root),'models_allowed':0,'workers_started':0,'stop_file':r['stop_file']})
    server=uvicorn.Server(uvicorn.Config(app,log_level='warning',lifespan='off'));done=threading.Event()
    def monitor():
        while not done.wait(.2):
            p=Path(r['stop_file'])
            if p.exists() and read(p).get('nonce')==r['stop_nonce']:server.should_exit=True;return
    watch=threading.Thread(target=monitor,daemon=True);watch.start()
    try:server.run(sockets=[sock])
    finally:
        done.set();watch.join(timeout=2);app.state.discussions.shutdown();app.state.studio._executor.shutdown(wait=True);sock.close();guard(r)
        write('backend-terminal.json',{'pid':os.getpid(),'server_stopped':True,'originals_exact':True,'models_allowed':0,'workers_started':0,'copy_final_all_tables':snap(root/'data/catalog.db')})

if __name__=='__main__':{'prepare':prepare_layout,'launch':launch,'serve':serve,'stop':stop}[sys.argv[1]]()
