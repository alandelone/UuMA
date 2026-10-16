from __future__ import annotations
from pathlib import Path
from contextlib import closing
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile

REPO=Path(__file__).resolve().parents[1]
HERE=REPO/'.tmp/scholar-re10-native-v1'
PLAN=json.loads((REPO/'.tmp/scholar-re10-archive-prepare-v1/target.json').read_text(encoding='utf-8'))
sys.path.insert(0,str(REPO/'.tmp/scholar-g11-parallel-v1'))
from runtime_copy_and_serve_v9 import product_guard,snapshot,digest,exclusive_json,read_json
COMMENT=PLAN['comment_id']

def snap(db):return json.loads(json.dumps(snapshot(db),ensure_ascii=False))
def files(root):return {p.relative_to(root).as_posix():digest(p) for p in root.rglob('*') if p.is_file() and not p.name.endswith(('-wal','-shm'))}
def guard(receipt):
    assert product_guard()==receipt['source_vector']
    source=Path(receipt['source'])
    assert files(source)==read_json(HERE/'protected-source-files.json')
    assert snap(source/'data/catalog.db')==read_json(HERE/'before-all-tables.json')

def prepare():
    assert not (HERE/'allocated.json').exists()
    source=Path(PLAN['recommended_source_root']).resolve()
    assert source.name=='scui-native-import-n01cagy6'
    assert digest(source/'data/catalog.db')==PLAN['source_raw_sha256']
    protected=files(source); before=snap(source/'data/catalog.db')
    assert len(before['tables'])==109
    comments=before['tables']['review_comments']
    target=next(dict(zip(comments['columns'],r)) for r in comments['rows'] if dict(zip(comments['columns'],r))['comment_id']==COMMENT)
    assert target==PLAN['original_comment'] and target['response_text'].strip()
    root=Path(tempfile.mkdtemp(prefix='scui-re10-native-')).resolve()
    exclusive_json(HERE/'allocated.json',{'root':str(root),'source':str(source)})
    shutil.copytree(source/'data',root/'data',ignore=lambda _p,names:[n for n in names if n in {'catalog.db','catalog.db-wal','catalog.db-shm'}])
    with closing(sqlite3.connect((source/'data/catalog.db').as_uri()+'?mode=ro',uri=True)) as src:
        with closing(sqlite3.connect(root/'data/catalog.db')) as dst:src.backup(dst)
    assert snap(root/'data/catalog.db')==before
    for name,sha in protected.items():
        if name.startswith('data/') and name!='data/catalog.db':assert digest(root/name)==sha
    exclusive_json(HERE/'before-all-tables.json',before)
    exclusive_json(HERE/'protected-source-files.json',protected)
    ports=[]
    for _ in range(2):
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));ports.append(sock.getsockname()[1])
    assert ports[0]!=ports[1]
    receipt={'status':'PASS_EXACT_COPY_NATIVE_NOT_EXECUTED','root':str(root),'source':str(source),
             'source_vector':product_guard(),'backend_port':ports[0],'frontend_port':ports[1],
             'models_allowed':0,'workers_started':0,'manuscript_id':PLAN['manuscript_id'],'comment_id':COMMENT}
    exclusive_json(HERE/'copy-receipt.json',receipt);guard(receipt)
    with (HERE/'backend.log').open('x',encoding='utf-8') as log:
        proc=subprocess.Popen([str(REPO/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'),'-X','utf8',str(Path(__file__).resolve()),'serve'],cwd=REPO,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    exclusive_json(HERE/'backend-launched.json',{'pid':proc.pid})
    print(json.dumps({k:v for k,v in receipt.items() if k!='source_vector'}),flush=True)

def serve():
    import uvicorn
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse,Response
    sys.path.insert(0,str(REPO.parent/'RSTV4/src'))
    from rstv4.studio_api import create_app
    receipt=read_json(HERE/'copy-receipt.json');guard(receipt)
    root=Path(receipt['root']);before=snap(root/'data/catalog.db')
    app=create_app(root)
    class Deny:
        def analyze(self,*_a,**_k):raise RuntimeError('RE10 archive fixture denies model calls')
        def operation_id(self,*_a,**_k):raise RuntimeError('RE10 archive fixture denies model calls')
        def analyze_for_operation(self,*_a,**_k):raise RuntimeError('RE10 archive fixture denies model calls')
    app.state.studio.gateway=Deny();app.state.discussions.gateway=Deny()
    assert snap(root/'data/catalog.db')==before
    used=0
    @app.middleware('http')
    async def bound(request,call_next):
        nonlocal used
        path=request.url.path
        if request.method in {'GET','HEAD','OPTIONS'}:return await call_next(request)
        if request.method=='POST' and path in {'/api/research/discussion/context','/api/research/discussion/history'}:return await call_next(request)
        expected=[('DELETE',f'/api/comments/{COMMENT}'),('POST',f'/api/comments/{COMMENT}/restore')]
        if used<2 and (request.method,path)==expected[used]:
            used+=1;step=used
            exclusive_json(HERE/f'action-{step}-request.json',{'method':request.method,'path':path})
            response=await call_next(request)
            raw=b''.join([p async for p in response.body_iterator])
            exclusive_json(HERE/f'action-{step}-response.json',{'status_code':response.status_code,'body':json.loads(raw)})
            exclusive_json(HERE/f'action-{step}-all-tables.json',snap(root/'data/catalog.db'))
            return Response(raw,status_code=response.status_code,headers=dict(response.headers))
        return JSONResponse({'detail':'RE10 permits only the declared archive and restore actions; no author edits/checks/models.'},status_code=403)
    app.add_middleware(CORSMiddleware,allow_origins=[f"http://127.0.0.1:{receipt['frontend_port']}"],allow_credentials=False,allow_methods=['GET','POST','DELETE','OPTIONS'],allow_headers=['Content-Type','If-Match','X-Operation-Id'])
    sock=socket.socket();sock.bind(('127.0.0.1',receipt['backend_port']));sock.listen(128)
    exclusive_json(HERE/'backend-ready.json',{'pid':os.getpid(),'port':receipt['backend_port'],'root':str(root),'model_calls_allowed':0})
    uvicorn.Server(uvicorn.Config(app,log_level='warning')).run(sockets=[sock])

def build():
    receipt=read_json(HERE/'copy-receipt.json');guard(receipt)
    code=(REPO/'.tmp/scholar-template-build-v3.py').read_text(encoding='utf-8')
    code=code.replace('scholar-template-build-v3','scholar-re10-build-v1').replace('scui-template-build-','scui-re10-build-')
    code=code.replace('127.0.0.1:8877',f"127.0.0.1:{receipt['backend_port']}")
    code=code.replace('--max-old-space-size=1536','--max-old-space-size=512').replace("RAYON_NUM_THREADS='2', UV_THREADPOOL_SIZE='2'","RAYON_NUM_THREADS='1', UV_THREADPOOL_SIZE='1'")
    exec(compile(code,__file__,'exec'),{'__file__':__file__,'__name__':'isolated_build'})

def launch_front():
    receipt=read_json(HERE/'copy-receipt.json');guard(receipt)
    build=read_json(REPO/'.tmp/scholar-re10-build-v1.json')
    assert build['status']=='PASS' and build['original_source_and_dist_unchanged']
    root=Path(build['root'])
    for name,sha in build['dist_files'].items():assert digest(root/name)==sha
    with socket.socket() as sock:sock.bind(('127.0.0.1',receipt['frontend_port']))
    env=os.environ.copy();env.update(RSTV4_API=f"http://127.0.0.1:{receipt['backend_port']}/api",NODE_OPTIONS='--max-old-space-size=512')
    argv=['cmd.exe','/c','npm.cmd','run','start','--','--port',str(receipt['frontend_port']),'--hostname','127.0.0.1']
    with (HERE/'frontend.log').open('x',encoding='utf-8') as log:
        proc=subprocess.Popen(argv,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    url=f"http://127.0.0.1:{receipt['frontend_port']}/?manuscript={PLAN['manuscript_id']}&view=revision&left=0&right=0&chat=1&round={PLAN['round']['review_round_id']}"
    exclusive_json(HERE/'frontend-launched.json',{'pid':proc.pid,'port':receipt['frontend_port'],'root':str(root),'argv':argv,'url':url})
    print(json.dumps({'url':url,'pid':proc.pid}),flush=True)

def audit():
    receipt=read_json(HERE/'copy-receipt.json');guard(receipt)
    baseline=read_json(HERE/'before-all-tables.json')
    def records(state,name,key):
        table=state['tables'][name]
        return {v[key]:v for r in table['rows'] if (v:=dict(zip(table['columns'],r))) is not None}
    for stage,revision in [(1,7),(2,8)]:
        state=read_json(HERE/f'action-{stage}-all-tables.json')
        assert state['schema']==baseline['schema'] and state['tables'].keys()==baseline['tables'].keys()
        for name,table in baseline['tables'].items():
            if name not in {'review_comments','studio_comment_response_state'}:assert state['tables'][name]==table,name
        old=records(baseline,'review_comments','comment_id');new=records(state,'review_comments','comment_id')
        assert old.keys()==new.keys()
        for ident,row in old.items():
            if ident!=COMMENT:assert new[ident]==row
            else:
                assert {k:v for k,v in row.items() if k not in {'archived_at','updated_at'}}=={k:v for k,v in new[ident].items() if k not in {'archived_at','updated_at'}}
                assert bool(new[ident]['archived_at'])==(stage==1)
                assert new[ident]['updated_at']!=row['updated_at']
        old=records(baseline,'studio_comment_response_state','comment_id');new=records(state,'studio_comment_response_state','comment_id')
        assert old.keys()==new.keys()
        assert old[COMMENT]['revision']==6 and new[COMMENT]=={**old[COMMENT],'revision':revision}
        assert all(new[k]==v for k,v in old.items() if k!=COMMENT)
        response=read_json(HERE/f'action-{stage}-response.json')
        assert response['status_code']==200 and response['body']['comment_id']==COMMENT
        assert response['body']['response_text']==PLAN['original_comment']['response_text']
    final=snap(Path(receipt['root'])/'data/catalog.db')
    assert final==read_json(HERE/'action-2-all-tables.json')
    protected=read_json(HERE/'protected-source-files.json')
    for name,sha in protected.items():
        if name.startswith('data/') and name!='data/catalog.db':assert digest(Path(receipt['root'])/name)==sha
    exclusive_json(HERE/'final-all-tables.json',final)
    exclusive_json(HERE/'audit.json',{'status':'PASS_RE10_NATIVE_ARCHIVE_RESTORE_NONEMPTY_REPLY_TWO_CHECKS_AND_109_TABLE_AUDIT',
                    'schema_exact':True,'unchanged_tables':107,'comment_id':COMMENT,'same_display_label':'A206',
                    'reply_text_and_two_checks_four_links_exact':True,'response_revision':[6,7,8],
                    'old_checks_intentionally_stale':True,'new_models_jobs_checks_generations':0,
                    'source_original_files_and_rows_exact':True,'all11_complete':False})
    print('PASS_RE10_NATIVE_ARCHIVE_RESTORE_NONEMPTY_REPLY_TWO_CHECKS_AND_109_TABLE_AUDIT')

if __name__=='__main__':{'prepare':prepare,'serve':serve,'build':build,'launch-front':launch_front,'audit':audit}[sys.argv[1]]()
