from __future__ import annotations
from pathlib import Path
from contextlib import closing
import hashlib,json,os,re,shutil,socket,sqlite3,subprocess,sys,tempfile,time,urllib.request,threading,uuid
import psutil

REPO=Path(__file__).resolve().parents[1]
OLD=REPO/'.tmp/scholar-studio-current-native-v2'
HERE=REPO/'.tmp/scholar-studio-current-native-restart-v6'
RST=REPO.parent/'RSTV4'
PY=REPO/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'
MS='manuscript_56652adf9d054cb6ab3819efacf3475c'
COMMENT='comment_8ecd722c5ea041858723009b72fc4cce'
ROUND='review_round_b51564f0224e499081e58f341103b336'
sys.path.insert(0,str(REPO/'.tmp/scholar-g11-parallel-v1'))
from runtime_copy_and_serve import snapshot
read=lambda p:json.loads(p.read_text(encoding='utf8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
snap=lambda p:json.loads(json.dumps(snapshot(p),ensure_ascii=False))
def write(name,value):
    with (HERE/name).open('x',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
def filemap(root):return {p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
def records(state,name):
    t=state['tables'][name]
    return [dict(zip(t['columns'],r)) for r in t['rows']]
def guard(r):
    for n,h in r['backend_source_vector'].items():assert sha(RST/n)==h,n
    for n,h in r['protected_external_artifacts'].items():assert sha(Path(n))==h,n
    original=Path(r['original'])
    assert filemap(original)==read(OLD/'protected-original-files.json'),'Original files changed'
    assert snap(original/'data/catalog.db')==read(OLD/'original-all-tables.json'),'Original tables changed'
    build=Path(r['frontend_root']);front=REPO.parent/'writing-studio'
    for n,h in r['frontend_product_vector'].items():
        assert sha(front/n)==h,n
        assert sha(build/n)==h,n
    for n,h in r['frontend_dist_vector'].items():assert sha(build/n)==h,n
    assert {str(p.relative_to(build)) for p in (build/'dist').rglob('*') if p.is_file()}==set(r['frontend_dist_vector'])

def prepare():
    HERE.mkdir(exist_ok=False)
    previous=REPO/'.tmp/scholar-studio-current-native-restart-v3'
    assert sha(previous/'policy-stop-current-native-seal.json')=='2c513b764874d73aea3de721ec095b08eba306795781028afe95f68a1fe86b89'
    previous_manifest=read(previous/'preparation-manifest.json')
    for name,item in previous_manifest['files'].items():assert sha(Path(name))==item['sha256'],name
    ownership=read(previous/'ownership.json');identities=[ownership['backend'],ownership['frontend'],ownership['backend_launcher'],*ownership['frontend_windows_console_children']]
    audit=[]
    for old_identity in identities:
        try:
            proc=psutil.Process(old_identity['pid'])
            birth=proc.create_time()
            if birth==old_identity['create_time']:
                current=identity(proc.pid)
                same=current['cmdline']==old_identity['cmdline'] and current['cwd']==old_identity['cwd']
                assert not same,'Old owned process still alive; do not duplicate'
            audit.append({'pid':proc.pid,'old_identity_absent':True,'numeric_pid_reused':True,'old_create_time':old_identity['create_time'],'new_create_time':birth})
        except psutil.NoSuchProcess:audit.append({'pid':old_identity['pid'],'old_identity_absent':True,'numeric_pid_reused':False})
    write('previous-owned-identity-audit.json',{'old_owned_identities_absent':True,'entries':audit,'no_old_numeric_pid_termination':True,'previous_stop_seal_sha256':sha(previous/'policy-stop-current-native-seal.json')})
    assert sha(OLD/'old-baseline-stop-seal.json')=='34a32e0ff004de092bc6c6883c2825890729d93731906b60d77f6d86c5554e08'
    old=read(OLD/'receipt.json');oldvector=old['backend_source_vector']
    newpath=REPO/'.tmp/scholar-rv-prompt-fix-v1/source-after-new311.json';new=read(newpath)
    assert len(new)==311 and set(new)==set(oldvector)
    changed=[n for n,h in oldvector.items() if new[n]!=h]
    assert changed==['src/rstv4/catalog_web.html']
    assert new[changed[0]]=='e573c3771cc6f4723be6c2611eabfb81bae3200722ccdd1ccac9018924e18447'
    oldmanifest=read(OLD/'preparation-manifest.json')
    for name,item in oldmanifest['files'].items():assert sha(Path(name))==item['sha256'],name
    root=Path(old['root']);assert root.name=='scui-studio-current-native-v2-6jc613d4'
    assert snap(root/'data/catalog.db')==read(OLD/'startup-all-tables.json')
    assert read(OLD/'backend-terminal.json')['copy_final_all_tables']==read(OLD/'startup-all-tables.json')
    expected=read(OLD/'startup-all-files.json');actual=filemap(root);omit={'data/catalog.db-wal','data/catalog.db-shm'}
    assert {k:v for k,v in actual.items() if k not in omit}=={k:v for k,v in expected.items() if k not in omit}
    for port in [8877,63377]:
        with socket.socket() as sock:sock.bind(('127.0.0.1',port))
    r={**old,'status':'PREPARED_EXISTING_ROOT_RESTART_NOT_NATIVE_ACCEPTANCE','backend_source_vector':new,'stop_nonce':uuid.uuid4().hex,'stop_file':str(HERE/'stop.request.json'),'old_stop_seal':str(OLD/'old-baseline-stop-seal.json'),'old_stop_seal_sha256':sha(OLD/'old-baseline-stop-seal.json'),'new_source_vector_path':str(newpath),'new_source_vector_sha256':sha(newpath),'declared_source_changes':[{'path':name,'before':oldvector[name],'after':new[name]} for name in changed],'other_source_files_exact':310,'new_fixture_copies':0,'new_schema_migrations':0}
    guard(r)
    write('before110-all-tables.json',snap(root/'data/catalog.db'))
    write('before110-all-files.json',filemap(root))
    r.update(previous_policy_stop_seal=str(previous/'policy-stop-current-native-seal.json'),previous_policy_stop_seal_sha256=sha(previous/'policy-stop-current-native-seal.json'))
    write('receipt.json',r)
    write('reuse-preflight.json',{'root':str(root),'same_prepared110_tables_and_bytes_exact':True,'old_manifest16_payloads_exact':True,'old_109_schema_and_rows_and_external25_exact':True,'declared_source_changes':r['declared_source_changes'],'other_source_files_exact':310,'new_source_vector_sha256':sha(newpath),'new_fixture_copies':0,'new_builds':0,'business_posts':0,'models':0,'workers':0})
    print(json.dumps({'status':r['status'],'root':str(root),'backend_port':8877,'frontend_port':63377,'changed':changed,'other310_exact':True,'new_fixture_copies':0}),flush=True)

class Deny:
    def analyze(self,*a,**k):raise RuntimeError('Native studio preparation denies model calls')
    operation_id=analyze
    analyze_for_operation=analyze

def serve():
    import uvicorn
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse,Response
    sys.path.insert(0,str(RST/'src'))
    from rstv4.studio_api import create_app
    r=read(HERE/'receipt.json');guard(r);root=Path(r['root'])
    baseline=read(OLD/'startup-all-tables.json');assert snap(root/'data/catalog.db')==baseline
    app=create_app(root);app.state.studio.gateway=Deny();app.state.discussions.gateway=Deny()
    assert snap(root/'data/catalog.db')==baseline
    count=0
    @app.middleware('http')
    async def boundary(request,call_next):
        nonlocal count
        path=request.url.path;method=request.method
        if method in {'GET','HEAD','OPTIONS'}:return await call_next(request)
        base=f'/api/manuscripts/{MS}'
        allowed=(method=='DELETE' and path==f'/api/comments/{COMMENT}') or (method=='POST' and path in {f'/api/comments/{COMMENT}/restore',base+'/review-rounds',base+'/stage',base+'/submission-events',base+'/assets','/api/review-comments/preview-file','/api/research/discussion/context','/api/research/discussion/history'})
        if method=='PATCH' and re.fullmatch(r'/api/comments/[^/]+',path):
            cid=path.rsplit('/',1)[1]
            with closing(sqlite3.connect((root/'data/catalog.db').as_uri()+'?mode=ro',uri=True)) as c:
                allowed=c.execute('SELECT 1 FROM review_comments a JOIN review_rounds r ON r.review_round_id=a.review_round_id WHERE a.comment_id=? AND r.manuscript_id=?',(cid,MS)).fetchone() is not None
        if method=='POST' and re.fullmatch(r'/api/review-rounds/[^/]+/comments(?:/file)?',path):
            rid=path.split('/')[3]
            with closing(sqlite3.connect((root/'data/catalog.db').as_uri()+'?mode=ro',uri=True)) as c:
                allowed=c.execute('SELECT 1 FROM review_rounds WHERE review_round_id=? AND manuscript_id=?',(rid,MS)).fetchone() is not None
        if method=='POST' and re.fullmatch(re.escape(base)+r'/comments/[^/]+/response-checks',path):allowed=True
        if not allowed:return JSONResponse({'detail':'This isolated native acceptance permits only target review/archive/submission actions; no generation, model, document edits or other manuscript mutations.'},status_code=403)
        count+=1;serial=count
        raw=await request.body()
        write(f'action-{serial:03d}-request.json',{'method':method,'path':path,'content_type':request.headers.get('content-type'),'body_utf8':raw.decode('utf8',errors='replace') if 'multipart' not in request.headers.get('content-type','') else None,'body_sha256':hashlib.sha256(raw).hexdigest(),'body_bytes':len(raw)})
        response=await call_next(request);content=b''.join([chunk async for chunk in response.body_iterator])
        try:body=json.loads(content)
        except Exception:body={'body_sha256':hashlib.sha256(content).hexdigest(),'body_bytes':len(content)}
        write(f'action-{serial:03d}-response.json',{'status_code':response.status_code,'body':body})
        write(f'action-{serial:03d}-all-tables.json',snap(root/'data/catalog.db'))
        return Response(content,status_code=response.status_code,headers=dict(response.headers))
    app.add_middleware(CORSMiddleware,allow_origins=[f"http://127.0.0.1:{r['frontend_port']}"],allow_credentials=False,allow_methods=['GET','HEAD','POST','PATCH','DELETE','OPTIONS'],allow_headers=['Content-Type','If-Match','X-Operation-Id'])
    sock=socket.socket();sock.bind(('127.0.0.1',8877));sock.listen(128)
    write('backend-ready.json',{'pid':os.getpid(),'identity':identity(os.getpid()),'port':8877,'root':str(root),'source_files':311,'lifespan':'off','models_allowed':0,'workers_started':0,'stop_file':r['stop_file']})
    server=uvicorn.Server(uvicorn.Config(app,log_level='warning',lifespan='off'))
    monitor_done=threading.Event()
    def monitor():
        while not monitor_done.wait(.2):
            stop=Path(r['stop_file'])
            if not stop.exists():continue
            request=read(stop)
            if request.get('nonce')!=r['stop_nonce']:continue
            frontend=HERE/'frontend-launched.json'
            if frontend.exists():
                saved=read(frontend)['identity'];proc=same_process(saved)
                if proc:
                    children=proc.children(recursive=True)
                    assert not children,'Do not broadly terminate unexpected children'
                    proc.terminate();proc.wait(timeout=15)
            server.should_exit=True
            return
    watch=threading.Thread(target=monitor,daemon=True);watch.start()
    try:server.run(sockets=[sock])
    finally:
        monitor_done.set();watch.join(timeout=2)
        app.state.discussions.shutdown();app.state.studio._executor.shutdown(wait=True);sock.close()
        guard(r)
        write('backend-terminal.json',{'pid':os.getpid(),'server_stopped':True,'originals_exact':True,'models_allowed':0,'workers_started':0,'copy_final_all_tables':snap(root/'data/catalog.db')})

def identity(pid):
    p=psutil.Process(pid)
    return {'pid':p.pid,'create_time':p.create_time(),'cmdline':p.cmdline(),'cwd':p.cwd(),'parent_pid':p.ppid()}

def same_process(saved):
    try:
        fresh=identity(saved['pid'])
        assert fresh['create_time']==saved['create_time'] and fresh['cmdline']==saved['cmdline'] and fresh['cwd']==saved['cwd']
        return psutil.Process(saved['pid'])
    except psutil.NoSuchProcess:return None

def launch():
    r=read(HERE/'receipt.json');guard(r)
    root=Path(r['frontend_root']).resolve()
    for p in psutil.process_iter(['name','cmdline']):
        try:
            if 'node' in (p.info['name'] or '').lower():
                assert Path(p.cwd()).resolve()!=root and not any('scui-publication-chain-build-mlpu7aqn' in a for a in p.info['cmdline'] or []),'Existing matching compiled frontend must be reviewed for reuse'
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    for port in [8877,r['frontend_port']]:
        with socket.socket() as sock:sock.bind(('127.0.0.1',port))
    command=[str(PY),'-X','utf8',str(Path(__file__).resolve()),'serve']
    with (HERE/'backend.log').open('x',encoding='utf8') as log:
        back=subprocess.Popen(command,cwd=REPO,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    write('backend-launched.json',{'identity':identity(back.pid),'argv':command,'port':8877,'tool_observation':'Use backend-ready.json actual server PID, which may be a descendant of the Windows venv launcher.'})
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        if back.poll() is not None:raise RuntimeError('Backend exited; inspect backend.log; do not replay prepare')
        if (HERE/'backend-ready.json').exists():break
        time.sleep(.1)
    assert (HERE/'backend-ready.json').exists(),'Backend not ready; preserve handle, do not relaunch'
    env=os.environ.copy();env.update(RSTV4_API='http://127.0.0.1:8877/api',NEXT_PUBLIC_RSTV4_API='http://127.0.0.1:8877/api',NODE_OPTIONS='--max-old-space-size=512')
    argv=[shutil.which('node'),str(REPO.parent/'writing-studio/node_modules/vinext/dist/cli.js'),'start','--port',str(r['frontend_port']),'--hostname','127.0.0.1']
    with (HERE/'frontend.log').open('x',encoding='utf8') as log:
        front=subprocess.Popen(argv,cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    url=f"http://127.0.0.1:{r['frontend_port']}/?manuscript={MS}&view=revision&left=0&right=0&chat=1&round={ROUND}"
    write('frontend-launched.json',{'identity':identity(front.pid),'argv':argv,'port':r['frontend_port'],'url':url,'production_build_reused':True,'actual_vinext_ssr':True,'bootstrap_replacement':False})
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        if front.poll() is not None:raise RuntimeError('Frontend exited; inspect frontend.log; do not rebuild')
        try:
            with urllib.request.urlopen(url,timeout=2) as response:
                if response.status==200:
                    content=response.read();break
        except Exception:time.sleep(.2)
    else:raise RuntimeError('Frontend not confirmed ready; retain handle')
    with urllib.request.urlopen('http://127.0.0.1:8877/api/health',timeout=5) as response:health=json.loads(response.read())
    with urllib.request.urlopen(f'http://127.0.0.1:8877/api/manuscripts/{MS}/workspace',timeout=20) as response:workspace=json.loads(response.read())
    assert workspace['document_revision']==workspace['last_generated_revision']==62
    assert workspace['active_generated_version_id']==r['active_generated_version_id'] and workspace['manuscript']['revision']==6
    write('initial-workspace.json',workspace)
    assets={}
    for asset in set(re.findall(r'(?:src|href)="([^"?]+\.(?:js|css))"',content.decode())):
        with urllib.request.urlopen('http://127.0.0.1:'+str(r['frontend_port'])+asset,timeout=5) as response:raw=response.read()
        path=root/'dist/client'/asset.lstrip('/')
        assert raw==path.read_bytes();assets[asset]=sha(path)
    assert assets,'Real SSR response must reference current compiled assets'
    assert snap(Path(r['root'])/'data/catalog.db')==read(OLD/'startup-all-tables.json'),'Read-only startup changed baseline'
    expected=read(OLD/'startup-all-files.json');actual=filemap(Path(r['root']))
    omit={'data/catalog.db-wal','data/catalog.db-shm'}
    assert {k:v for k,v in actual.items() if k not in omit}=={k:v for k,v in expected.items() if k not in omit},'Read-only startup changed non-sidecar files'
    guard(r)
    backready=read(HERE/'backend-ready.json');frontidentity=identity(front.pid)
    listeners=[]
    for conn in psutil.net_connections(kind='inet'):
        if conn.status=='LISTEN' and conn.laddr.port in [8877,r['frontend_port']]:listeners.append({'pid':conn.pid,'address':conn.laddr.ip,'port':conn.laddr.port})
    assert len(listeners)==2
    assert next(x for x in listeners if x['port']==8877)['pid']==backready['pid']
    assert next(x for x in listeners if x['port']==r['frontend_port'])['pid']==front.pid
    ready={'status':'READY_NATIVE_ACTIONS_NOT_EXECUTED','url':url,'backend_url':'http://127.0.0.1:8877','backend_identity':backready['identity'],'frontend_identity':frontidentity,'backend_launch_pid':back.pid,'frontend_port':r['frontend_port'],'listeners':listeners,'health':health,'frontend_status':200,'frontend_html_sha256':hashlib.sha256(content).hexdigest(),'served_assets_sha256':assets,'startup_all_tables_exact':True,'startup_non_sidecar_files_exact':True,'original_all_files_and_tables_exact':True,'original_external_artifacts_exact':True,'backend_source_count':311,'frontend_source_count':91,'frontend_dist_count':76,'actual_vinext_ssr':True,'new_builds':0,'workers_started':0,'models_executed':0,'native_actions_executed':0,'stop_command':str(PY)+' -X utf8 '+str(Path(__file__).resolve())+' stop','stop_file':r['stop_file'],'all11_complete':False}
    children=[identity(p.pid) for p in psutil.Process(front.pid).children(recursive=True)]
    assert all(Path(p['cmdline'][0]).name.lower()=='conhost.exe' for p in children)
    write('ownership.json',{'backend':backready['identity'],'frontend':frontidentity,'backend_launcher':identity(back.pid),'frontend_windows_console_children':children,'ports':[8877,r['frontend_port']],'stop_file':r['stop_file'],'owned_scope':'current v5 identities only'})
    ready['stop_command']=str(PY)+' -X utf8 '+str(REPO/'.tmp/scholar-studio-current-native-restart-v6-stop-owned.py')
    write('ready.json',ready)
    names=['receipt.json','reuse-preflight.json','before110-all-tables.json','before110-all-files.json','previous-owned-identity-audit.json','ownership.json','ready.json','backend-launched.json','backend-ready.json','frontend-launched.json','initial-workspace.json']
    write('preparation-manifest.json',{'files':{str(HERE/n):{'sha256':sha(HERE/n)} for n in names},'v5_runner_sha256':sha(Path(__file__)),'prior_v4_failed_before_services':True})
    print(json.dumps(ready,ensure_ascii=False),flush=True)

def stop():
    subprocess.run([str(PY),'-X','utf8',str(REPO/'.tmp/scholar-studio-current-native-restart-v6-stop-owned.py')],cwd=REPO,check=True)

if __name__=='__main__':{'prepare':prepare,'serve':serve,'launch':launch,'stop':stop}[sys.argv[1]]()
