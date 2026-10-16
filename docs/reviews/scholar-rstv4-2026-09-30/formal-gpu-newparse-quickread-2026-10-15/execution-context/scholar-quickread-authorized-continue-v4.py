from pathlib import Path
common=Path(__file__).with_name('scholar-quickread-authorized-once-v3.py').read_text(encoding='utf-8').split("assert read(here/'gateway-health.json')")[0]
exec(compile(common,__file__,'exec'))
prior=here
here=repo/'.tmp/scholar-quickread-authorized-v4'
here.mkdir(exist_ok=False)
previous=read(prior/'execution-receipt.json')
assert previous['budget_changed'] and previous['model_events']==[]
protected=inputs()
before=snap();put('before-all-tables.json',before)
assert before==read(prior/'after-execution-all-tables.json')
check_source()
proof={'status':'STARTED_PRECLAIM_CONTEXT_CORRECTION','job_id':target,'budget_changed_again':False,'gpu_reexecuted':False,'deep_read_executed':False,'scientific_approval':False,'prior_failure_before_claim_and_model':True}
try:
    worker=AcquisitionWorker(root,'model',model_gateway=UnlimitedLLMGateway(root),worker_id='g11-original-newparse-quickread-once-v4')
    assert snap()==before
    original_claim=worker.service.claim_job
    def claim_only_owned(worker_id,queues,**kwargs):
        assert worker_id==worker.worker_id
        with closing(conn_ro()) as conn:
            presence=[dict(r) for r in conn.execute('SELECT * FROM acquisition_worker_presence')]
            assert all(r['state']=='STOPPED' for r in presence if r['worker_id']!=worker_id)
            own=[r for r in presence if r['worker_id']==worker_id]
            assert len(own)==1 and own[0]['state']=='IDLE' and own[0]['instance_id']==worker._presence_instance
            candidates=[r['job_id'] for r in conn.execute("SELECT j.job_id FROM acquisition_jobs j JOIN collections c ON c.collection_id=j.collection_id WHERE c.status='ACTIVE' AND j.queue_class='MODEL_READ' AND j.status IN ('READY','RETRY_WAIT','RESOURCE_WAIT','RUNNING')")]
            assert candidates==[target]
            j=dict(conn.execute('SELECT * FROM acquisition_jobs WHERE job_id=?',(target,)).fetchone())
            assert j==protected['job']
            assert not list(conn.execute('SELECT * FROM acquisition_model_call_events WHERE job_id=?',(target,)))
        result=original_claim(worker_id,['MODEL_READ'],**kwargs)
        assert result and result['job_id']==target
        return result
    worker.service.claim_job=claim_only_owned
    with instance_lock(root,'model','g11-original-newparse-quickread-v3'):
        with closing(conn_ro()) as conn:
            event=dict(conn.execute('SELECT * FROM collection_budget_events WHERE request_id=?',('g11-newparse-quickread-time-budget-v1',)).fetchone())
            assert json.loads(event['limits_json'])==read(prior/'authorized-budget-response.json')['limits']
            usage=collection_runtime.usage(conn,cid)
            assert usage['active_seconds']<json.loads(event['limits_json'])['max_active_seconds']
            put('existing-authorized-budget-and-current-usage.json',{'event':event,'usage':usage})
        execution=worker.run_once()
        put('worker-execution.json',execution)
        assert execution and execution['job_id']==target
        proof.update(status='ACTUAL_ORIGINAL_JOB_EXECUTED_ONCE',actual_job_status=execution['status'],fencing_token=execution['fencing_token'],attempts=execution['attempts'])
except BaseException as error:
    proof.update(status='FAILED_RETAIN_CONTEXT_NO_REPLAY',error_type=type(error).__name__,error=str(error))
    raise
finally:
    after=snap();put('after-all-tables.json',after)
    check_source()
    assert next(r for r in rows(after,'acquisition_jobs') if r['job_id']==gpu)==protected['gpu']
    assert sha(Path(protected['file']['storage_path']))==protected['file']['sha256']
    proof['gpu_and_source_pdf_exact']=True
    proof['model_events']=[r for r in rows(after,'acquisition_model_call_events') if r['job_id']==target]
    proof['changed_tables']=[n for n in before['tables'] if before['tables'][n]!=after['tables'][n]]
    put('execution-receipt.json',proof)
    print(json.dumps({k:v for k,v in proof.items() if k!='model_events'}),flush=True)
