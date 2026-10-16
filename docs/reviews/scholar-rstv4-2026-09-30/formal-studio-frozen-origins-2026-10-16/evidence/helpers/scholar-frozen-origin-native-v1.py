"""Read-only native provenance acceptance on the preserved v7; no generation or checks."""
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
code = (repo / '.tmp/scholar-layout-native-v1.py').read_text(encoding='utf8')
code = code[:code.index("if __name__=='__main__':{'prepare':prepare_layout")]
code = code.replace('scholar-layout-native-v1', 'scholar-frozen-origin-native-v1')
exec(compile(code, __file__, 'exec'))
ROUND = 'review_round_e4845ca796d74594b33b86fb529b4404'


def prepare_readonly():
    HERE.mkdir()
    previous = REPO / '.tmp/scholar-layout-native-v4'
    assert read(previous/'owned-stop-terminal.json')['status'] == 'EXACT_OWNED_FRONTEND_AND_BACKEND_STOPPED_PORTS_FREE'
    r = read(previous/'receipt.json')
    root = Path(r['root'])
    current = snap(root/'data/catalog.db')
    assert current == read(previous/'backend-terminal.json')['copy_final_all_tables']
    build = read(REPO/'.tmp/scholar-frozen-origin-build-v1.json')
    assert build['status'] == 'PASS'
    for p in (RST/'tests').glob('test_studio_frozen_origins.py'):
        r['backend_source_vector'][str(p.relative_to(RST))] = sha(p)
    r['backend_source_vector'] = {n: sha(RST/n) for n in r['backend_source_vector']}
    with socket.socket() as s:
        s.bind(('127.0.0.1',0))
        port = s.getsockname()[1]
    r.update(status='SAME_V7_FROZEN_ORIGINS_READONLY', frontend_port=port,
             frontend_root=build['root'], frontend_dist_vector=build['dist_files'],
             frontend_product_vector={n: sha(REPO.parent/'writing-studio'/n) for n in r['frontend_product_vector']},
             stop_nonce=uuid.uuid4().hex, stop_file=str(HERE/'stop.request.json'))
    guard(r)
    write('receipt.json',r)
    write('before110-all-tables.json',current)
    write('before110-all-files.json',filemap(root))
    write('previous-owned-identity-audit.json',read(previous/'owned-stop-terminal.json'))
    write('reuse-preflight.json',{'same_v7_and_all110_exact':True,'existing_A212_only':True,
                                'models_jobs_checks_author_mutations_denied':True,'source_backend_count':len(r['backend_source_vector'])})
    print(json.dumps({'status':'PREPARED_READONLY','port':port}),flush=True)


def serve():
    import uvicorn
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, Response
    sys.path.insert(0,str(RST/'src'))
    from rstv4.studio_api import create_app
    r = read(HERE/'receipt.json')
    guard(r)
    root = Path(r['root'])
    baseline = read(HERE/'before110-all-tables.json')
    assert snap(root/'data/catalog.db') == baseline
    app = create_app(root)
    app.state.studio.gateway = Deny()
    app.state.discussions.gateway = Deny()
    assert snap(root/'data/catalog.db') == baseline
    count = 0

    @app.middleware('http')
    async def boundary(request,call_next):
        nonlocal count
        method, path = request.method, request.url.path
        allowed = method in {'GET','HEAD','OPTIONS'} or (method == 'POST' and path in {
            '/api/research/discussion/context','/api/research/discussion/history'})
        if not allowed:
            return JSONResponse({'detail':'Read-only frozen-origin acceptance: mutations denied'},status_code=403)
        count += 1
        index = count
        started = time.monotonic()
        response = await call_next(request)
        content = b''.join([part async for part in response.body_iterator])
        write(f'http-{index:04d}.json',{'method':method,'path':path,'query':str(request.url.query),
                                     'status':response.status_code,'seconds':time.monotonic()-started,
                                     'response_sha256':hashlib.sha256(content).hexdigest(),
                                     'origin':request.headers.get('origin')})
        if 'response-review' in path:
            (HERE/f'http-{index:04d}-response.json').write_bytes(content)
        return Response(content,status_code=response.status_code,headers=dict(response.headers))

    app.add_middleware(CORSMiddleware,allow_origins=[f"http://127.0.0.1:{r['frontend_port']}"],
                       allow_credentials=False,allow_methods=['GET','HEAD','POST','OPTIONS'],
                       allow_headers=['Content-Type','If-Match','X-Operation-Id'])
    sock = socket.socket()
    sock.bind(('127.0.0.1',8877))
    sock.listen(128)
    write('backend-ready.json',{'pid':os.getpid(),'identity':identity(os.getpid()),'port':8877,
                              'root':str(root),'models_allowed':0,'workers_started':0,'stop_file':r['stop_file']})
    server = uvicorn.Server(uvicorn.Config(app,log_level='warning',lifespan='off'))
    done = threading.Event()
    def monitor():
        while not done.wait(.2):
            p = Path(r['stop_file'])
            if p.exists() and read(p).get('nonce') == r['stop_nonce']:
                server.should_exit = True
                return
    watch = threading.Thread(target=monitor,daemon=True)
    watch.start()
    try:
        server.run(sockets=[sock])
    finally:
        done.set()
        watch.join(timeout=2)
        app.state.discussions.shutdown()
        app.state.studio._executor.shutdown(wait=True)
        sock.close()
        guard(r)
        final = snap(root/'data/catalog.db')
        assert final == baseline, 'Native readonly interval changed table records'
        expected = read(HERE/'before110-all-files.json')
        actual = filemap(root)
        omit = {'data/catalog.db-wal','data/catalog.db-shm'}
        assert {k:v for k,v in expected.items() if k not in omit} == {k:v for k,v in actual.items() if k not in omit}
        write('backend-terminal.json',{'pid':os.getpid(),'server_stopped':True,'originals_exact':True,
                                      'all110_exact':True,'all_non_sidecar_bytes_exact':True,
                                      'models_jobs_checks_started':0,'copy_final_all_tables':final})


if __name__ == '__main__':
    {'prepare':prepare_readonly,'launch':launch,'serve':serve,'stop':stop}[sys.argv[1]]()
