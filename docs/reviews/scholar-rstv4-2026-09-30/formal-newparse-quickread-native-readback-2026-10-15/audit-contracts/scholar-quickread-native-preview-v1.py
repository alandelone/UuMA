from pathlib import Path
from contextlib import closing
import hashlib,json,os,socket,sqlite3,subprocess,sys,threading,time,uuid
import psutil

repo=Path(__file__).resolve().parents[1]
source=repo.parent/'RSTV4'
here=repo/'.tmp/scholar-quickread-native-preview-v1'
root=Path('C:/Users/Alandelone/AppData/Local/Temp/scui-g11-native-22n_zg_d')
db=root/'data/catalog.db'
sys.path[:0]=[str(source/'src'),str(repo/'.tmp/scholar-g11-parallel-v1')]
from runtime_copy_and_serve import snapshot
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(name,value):
    with (here/name).open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
def snap():
    value=snapshot(db);value['schema']=[list(r) for r in value['schema']];return value
def files():return {p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file() and not p.name.endswith(('-wal','-shm'))}
def identity(pid):
    p=psutil.Process(pid)
    return {'pid':pid,'create_time':p.create_time(),'cmdline':p.cmdline(),'cwd':p.cwd(),'parent_pid':p.ppid()}
def exact(saved):
    try:p=psutil.Process(saved['pid'])
    except psutil.NoSuchProcess:return None
    assert p.create_time()==saved['create_time'] and p.cmdline()==saved['cmdline'] and p.cwd()==saved['cwd'],'PID reused; do not signal'
    return p
def guard():
    frozen=read(repo/'.tmp/scholar-quickread-authorized-v3/source-vector-311.json')
    assert len(frozen)==311 and all(sha(source/p)==h for p,h in frozen.items())
    assert snap()==read(here/'before106-all-tables.json'),'Original result/source/schema changed during read-only preview'
    assert files()==read(here/'before-all-files.json'),'Original non-sidecar file bytes changed'
    return frozen
class Deny:
    def analyze(self,*a,**kw):raise RuntimeError('This read-only acceptance preview denies all model operations')
    operation_id=analyze
    analyze_for_operation=analyze
def prepare():
    here.mkdir(exist_ok=False)
    before=snap();assert len(before['tables'])==106
    assert before==read(repo/'.tmp/scholar-quickread-authorized-v4/after-all-tables.json')
    put('before106-all-tables.json',before);put('before-all-files.json',files())
    with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as conn:
        with closing(sqlite3.connect(here/'catalog-before.db')) as backup:conn.backup(backup)
    assert snapshot(here/'catalog-before.db')['tables']==before['tables']
    guard()
    put('receipt.json',{'status':'PREPARED_ORIGINAL_QUICKREAD_READ_ONLY_NATIVE_PREVIEW','root':str(root),'source_root':str(source),'tables':106,'source_files':311,'model_operations':0,'workers':0,'job_executions':0,'stop_nonce':uuid.uuid4().hex,'stop_file':str(here/'stop.request.json'),'models_or_budget_replayed':False,'original_result_preserved':True})
    print('PREPARED_ORIGINAL106_READ_ONLY_CURRENT311',flush=True)
def serve():
    import uvicorn
    from fastapi.responses import JSONResponse
    from rstv4.catalog_web import create_app
    receipt=read(here/'receipt.json');guard()
    app=create_app(root)
    app.state.discussions.gateway=Deny();app.state.fieldkg_semantics.gateway=Deny()
    guard()
    request_lock=threading.Lock();serial=0
    @app.middleware('http')
    async def readonly_boundary(request,call_next):
        nonlocal serial
        method=request.method;path=request.url.path
        allowed=method in {'GET','HEAD','OPTIONS'} or (method=='POST' and path in {'/api/catalog/discussion/context','/api/catalog/discussion/history'})
        with request_lock:
            serial+=1;count=serial
        body=await request.body()
        put(f'request-{count:03d}.json',{'method':method,'path':path,'query':request.url.query,'body_utf8':body.decode('utf-8') if body else None,'allowed':allowed})
        if not allowed:
            put(f'response-{count:03d}.json',{'status_code':403,'write_denied':True})
            return JSONResponse({'detail':'Read-only acceptance preview; no model, worker, job, budget, collection, review or manuscript mutation is allowed.'},status_code=403)
        response=await call_next(request)
        put(f'response-{count:03d}.json',{'status_code':response.status_code,'content_type':response.headers.get('content-type')})
        return response
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
    port=sock.getsockname()[1]
    ready={'identity':identity(os.getpid()),'port':port,'url':f'http://127.0.0.1:{port}/?view=all','root':str(root),'current311':True,'no_models_workers_or_writes':True}
    put('ready.json',ready)
    server=uvicorn.Server(uvicorn.Config(app,log_level='warning',lifespan='off'))
    done=threading.Event()
    def monitor():
        while not done.wait(.2):
            path=here/'stop.request.json'
            if path.exists() and read(path).get('nonce')==receipt['stop_nonce']:
                server.should_exit=True;return
    watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
    try:server.run(sockets=[sock])
    finally:
        done.set();watcher.join(timeout=2);sock.close();app.state.discussions.shutdown()
        guard();put('terminal106-all-tables.json',snap());put('terminal-all-files.json',files())
        put('terminal.json',{'status':'READ_ONLY_NATIVE_PREVIEW_TERMINAL_ORIGINAL106_AND_FILES_EXACT','identity':ready['identity'],'port':port,'all106_exact':True,'all_files_exact':True,'source311_exact':True,'models_workers_jobs_budget_mutations':0})
def launch():
    guard();assert not (here/'launched.json').exists(),'Never duplicate a pending preview launch'
    argv=[str(repo/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'),'-X','utf8',str(Path(__file__).resolve()),'serve']
    with (here/'server.log').open('x',encoding='utf-8') as log:
        p=subprocess.Popen(argv,cwd=repo,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    put('launched.json',{'identity':identity(p.pid),'argv':argv})
    deadline=time.monotonic()+25
    while time.monotonic()<deadline:
        if p.poll() is not None:raise RuntimeError('Preview exited; inspect retained server.log')
        if (here/'ready.json').exists():break
        time.sleep(.1)
    assert (here/'ready.json').exists(),'Keep original live handle; do not relaunch on observation timeout'
    print(json.dumps(read(here/'ready.json')),flush=True)
def stop():
    ready=read(here/'ready.json');receipt=read(here/'receipt.json')
    p=exact(ready['identity'])
    if p:
        assert not p.children(recursive=True),'Unexpected owned child; no broad kill'
        put('stop.request.json',{'nonce':receipt['stop_nonce'],'source':'identity-verified-owned-stop'})
        p.wait(timeout=30)
    launcher=exact(read(here/'launched.json')['identity'])
    if launcher:launcher.wait(timeout=10)
    assert exact(ready['identity']) is None
    with socket.socket() as check:check.bind(('127.0.0.1',ready['port']))
    guard();assert read(here/'terminal.json')['all106_exact']
    put('owned-stop-terminal.json',{'status':'EXACT_OWNED_API_STOPPED_PORT_FREE_ORIGINAL106_FILES311_EXACT','port':ready['port'],'root_preserved':str(root),'no_other_processes_stopped':True})
    print(json.dumps(read(here/'owned-stop-terminal.json')),flush=True)
if __name__=='__main__':
    {'prepare':prepare,'launch':launch,'serve':serve,'stop':stop}[sys.argv[1]]()
