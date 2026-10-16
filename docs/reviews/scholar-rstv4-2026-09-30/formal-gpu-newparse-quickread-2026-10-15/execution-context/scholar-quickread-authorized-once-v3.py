from pathlib import Path
from contextlib import closing
import hashlib,json,math,sqlite3,sys,traceback

repo=Path(__file__).resolve().parents[1]
source=repo.parent/'RSTV4'
sys.path[:0]=[str(source/'src'),str(repo/'.tmp/scholar-g11-parallel-v1')]
from runtime_copy_and_serve import snapshot
from rstv4.acquisition import AcquisitionService
from rstv4.acquisition_worker import AcquisitionWorker,instance_lock
from rstv4.models import CollectionBudgetUpdateInput
from rstv4.model_gateway import UnlimitedLLMGateway
from rstv4 import collection_runtime

root=Path('C:/Users/Alandelone/AppData/Local/Temp/scui-g11-native-22n_zg_d')
db=root/'data/catalog.db'
here=repo/'.tmp/scholar-quickread-authorized-v3'
target='job_fe4651959298eab54d88abd9edaf6760'
gpu='job_76d39031d8cc329ec431e6a896a08f54'
cid='collection_62ca47c927342115eb5f8fd870af9ca6'
parse_id='parse_run_bb2661e7c11bb18dd684661073472d71'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(name,value):
    with (here/name).open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
def snap():
    value=snapshot(db)
    value['schema']=[list(row) for row in value['schema']]
    return value
def rows(s,name):
    t=s['tables'][name]
    return [dict(zip(t['columns'],r)) for r in t['rows']]
def check_source():
    frozen=read(repo/'.tmp/scholar-studio-current-native-restart-v10/receipt.json')['backend_source_vector']
    assert len(frozen)==311 and all(sha(source/p)==v for p,v in frozen.items())
    return frozen
def conn_ro():
    c=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c
def inputs():
    with closing(conn_ro()) as conn:
        j=dict(conn.execute('SELECT * FROM acquisition_jobs WHERE job_id=?',(target,)).fetchone())
        g=dict(conn.execute('SELECT * FROM acquisition_jobs WHERE job_id=?',(gpu,)).fetchone())
        assert j['status']=='READY' and j['attempts']==j['fencing_token']==0 and j['lease_owner'] is None
        assert j['collection_id']==cid and j['job_type']=='QUICK_READ' and j['queue_class']=='MODEL_READ'
        assert json.loads(j['input_json'])=={'parse_run_id':parse_id}
        assert g['status']=='SUCCEEDED' and g['attempts']==6
        c=dict(conn.execute('SELECT * FROM collections WHERE collection_id=?',(cid,)).fetchone())
        assert c['status']=='ACTIVE'
        assert all(r['state']=='STOPPED' for r in conn.execute('SELECT * FROM acquisition_worker_presence'))
        candidates=[dict(r) for r in conn.execute("SELECT j.* FROM acquisition_jobs j JOIN collections c ON c.collection_id=j.collection_id WHERE c.status='ACTIVE' AND j.queue_class='MODEL_READ' AND j.status IN ('READY','RETRY_WAIT','RESOURCE_WAIT','RUNNING')")]
        assert [r['job_id'] for r in candidates]==[target], 'Other MODEL_READ target exists; no dispatch'
        assert not list(conn.execute('SELECT * FROM acquisition_model_call_events WHERE job_id=?',(target,)))
        f=dict(conn.execute('SELECT sf.* FROM source_file_versions sf JOIN parse_runs pr ON pr.file_version_id=sf.file_version_id WHERE pr.parse_run_id=?',(parse_id,)).fetchone())
        assert f['identity_status']=='VERIFIED' and f['size_bytes']==1827
        assert sha(Path(f['storage_path']))==f['sha256']=='85f4078a0ae99a5c0b13894ce4bbf511c7e9302958512e738b7180dae1110f99'
        blocks=[dict(r) for r in conn.execute('SELECT * FROM document_blocks WHERE parse_run_id=? ORDER BY sequence',(parse_id,))]
        assert len(blocks)==3
        member=dict(conn.execute('SELECT * FROM collection_memberships WHERE collection_id=? AND paper_id=?',(cid,j['paper_id'])).fetchone())
        return {'job':j,'gpu':g,'collection':c,'file':f,'blocks':blocks,'membership':member}

assert read(here/'gateway-health.json')['status']==200
assert not (here/'execution-started.json').exists(), 'Do not repeat original execution'
put('execution-started.json',{'human_recovery_and_1800_seconds_authorized':True,'job_id':target})
frozen=check_source();put('source-vector-311.json',frozen)
before=snap();assert len(before['tables'])==105
put('before-all-105-tables.json',before)
historical=read(repo/'.tmp/scholar-downstream-quickread-v1/before-all-105-tables.json')
assert before==historical, 'Original root changed since protected preflight'
with closing(conn_ro()) as conn:
    with closing(sqlite3.connect(here/'catalog-before.db')) as backup:conn.backup(backup)
assert snapshot(here/'catalog-before.db')['tables']==before['tables']
files={p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file() and not p.name.endswith(('-wal','-shm'))}
put('before-files.json',files)
protected=inputs();put('pre-execution-inputs.json',protected)
proof={'status':'STARTED','job_id':target,'collection_id':cid,'gpu_reexecuted':False,'deep_read_executed':False,'scientific_approval':False,'budget_changed':False,'worker_run_once_calls':0}
try:
    service=AcquisitionService(root)
    migrated=snap();put('after-initialization-all-tables.json',migrated)
    assert set(before['tables'])<=set(migrated['tables'])
    additions=sorted(set(migrated['tables'])-set(before['tables']))
    assert all(not migrated['tables'][name]['rows'] for name in additions)
    for name,old in before['tables'].items():
        new=migrated['tables'][name]
        assert old['columns']==new['columns'],name
        if name!='schema_version':assert old==new,name
        else:
            a={r['component']:r for r in rows(before,name)};b={r['component']:r for r in rows(migrated,name)}
            assert a.keys()==b.keys() and all(b[k]['version']>=v['version'] for k,v in a.items())
    put('declared-migration.json',{'new_empty_tables':additions,'old105_rows_exact_except_schema_version':True,'before_versions':rows(before,'schema_version'),'after_versions':rows(migrated,'schema_version')})
    worker=AcquisitionWorker(root,'model',model_gateway=UnlimitedLLMGateway(root),worker_id='g11-original-newparse-quickread-once-v3')
    assert snap()==migrated,'Worker construction unexpectedly changed rows'
    claim=worker.service.claim_job
    # Harness narrows scheduling to the authorized queue; production claim/lease logic is unchanged.
    def claim_only_authorized(worker_id,queues,**kwargs):
        assert worker_id==worker.worker_id
        inputs()
        return claim(worker_id,['MODEL_READ'],**kwargs)
    worker.service.claim_job=claim_only_authorized
    with instance_lock(root,'model','g11-original-newparse-quickread-v3'):
        inputs()
        with closing(conn_ro()) as conn:
            latest=dict(conn.execute('SELECT * FROM collections WHERE collection_id=?',(cid,)).fetchone())
            usage=collection_runtime.usage(conn,cid)
            oldlimits=collection_runtime.current_limits(conn,cid)
            assert oldlimits=={'max_papers':500,'max_registered_pdf_bytes':10737418240,'max_active_seconds':86400,'max_task_attempts':None}
            assert not conn.execute('SELECT 1 FROM collection_budget_events WHERE request_id=?',('g11-newparse-quickread-time-budget-v1',)).fetchone()
        limits={**oldlimits,'max_active_seconds':math.ceil(usage['active_seconds'])+1800}
        payload=CollectionBudgetUpdateInput(request_id='g11-newparse-quickread-time-budget-v1',expected_revision=latest['revision'],limits=limits,reason='Human explicitly approved 30 additional runnable minutes for this original QuickRead after service recovery. Preserve all other limits and accumulated history; no GPU or deep read replay.')
        put('authorized-budget-request.json',{'usage_observed_immediately_before_update':usage,'request':payload.model_dump(),'original_limits':oldlimits})
        result=service.update_collection_budget(cid,payload)
        proof['budget_changed']=True
        put('authorized-budget-response.json',result)
        assert result['revision']==latest['revision']+1 and result['limits']==limits
        put('after-budget-all-tables.json',snap())
        proof['worker_run_once_calls']=1
        execution=worker.run_once()
        put('worker-execution.json',execution)
        assert execution is not None and execution['job_id']==target
        proof['actual_job_status']=execution['status']
        proof['status']='ACTUAL_SINGLE_AUTHORIZED_EXECUTION_RECORDED'
except BaseException as error:
    proof.update(status='FAILED_RETAIN_ACTUAL_CONTEXT_NO_REPLAY',error_type=type(error).__name__,error=str(error))
    raise
finally:
    after=snap();put('after-execution-all-tables.json',after)
    put('after-files.json',{p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file() and not p.name.endswith(('-wal','-shm'))})
    check_source()
    actual_gpu=next(r for r in rows(after,'acquisition_jobs') if r['job_id']==gpu)
    assert actual_gpu==protected['gpu']
    assert sha(Path(protected['file']['storage_path']))==protected['file']['sha256']
    proof['gpu_job_and_original_pdf_exact']=True
    proof['changed_tables_vs_before_initialization']=[n for n in before['tables'] if before['tables'][n]!=after['tables'][n]]
    proof['model_events']=[r for r in rows(after,'acquisition_model_call_events') if r['job_id']==target]
    put('execution-receipt.json',proof)
    print(json.dumps({k:v for k,v in proof.items() if k!='model_events'},ensure_ascii=False),flush=True)
