from __future__ import annotations

import json
import sqlite3
from contextlib import closing

import pytest
from test_catalog_paper_selection import chosen, library
from test_native_paperpool import FakeGateway

from rstv4.acquisition import AcquisitionService
from rstv4.acquisition_worker import ROLE_QUEUES, AcquisitionWorker
from rstv4.database import transaction
from rstv4.models import CollectionCreateInput, DeepReadRequestInput


@pytest.fixture(autouse=True)
def select_only_skeleton_queue(monkeypatch):
    # Isolate the requested stage; the existing pipeline suite exercises cross-queue scheduling.
    monkeypatch.setitem(ROLE_QUEUES, "model", ["MODEL_SKELETON"])


def setup(root):
    db, pdf = library(root)
    service = AcquisitionService(root)
    collection = service.create_collection(CollectionCreateInput.model_validate(chosen(paper_ids=['existing','other'])))
    return service, collection['collection_id'], db, pdf


def parse(service, cid, text='Original source block'):
    return service.publish_parse_result(cid,'existing','existing-file',parser_name='software',parser_version='1',config={},manifest={},blocks=[{'text':text,'page_number':1,'section':'Body'}],references=[])


def request(service,cid,key='original-deep-read',**values):
    return service.request_deep_read(cid,DeepReadRequestInput(paper_id='existing',reason='Explicit deep read',idempotency_key=key,**values))


def units(text='Original source block'):
    return [{'block_id':'block','raw_text':text,'layer1':{'triplets':[]},'layer2':{},'layer3':{},'layer4':{'role':'Evidence'}}]


def snapshot(db, tables):
    with closing(sqlite3.connect(db)) as conn:
        return {name:conn.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall() for name in tables}


def test_requested_deep_read_keeps_original_parse_across_new_publication_and_retry(tmp_path):
    service,cid,db,_=setup(tmp_path)
    first=parse(service,cid);job=request(service,cid)
    assert json.loads(job['input_json'])['parse_run_id']==first['parse_run_id']
    second=parse(service,cid,'Newly parsed source block')
    assert request(service,cid)==job
    worker=AcquisitionWorker(tmp_path,'model',model_gateway=FakeGateway(),worker_id='deep-source-test')
    completed=worker.run_once();assert completed['job_id']==job['job_id'] and completed['status']=='SUCCEEDED'
    with closing(sqlite3.connect(db)) as conn:
        published=json.loads(completed['result_json'])
        assert conn.execute('SELECT paper_version_id FROM paper_skeletons WHERE skeleton_id=?',(published['skeleton_id'],)).fetchone()[0]==first['paper_version_id']
        assert first['paper_version_id']!=second['paper_version_id']


def test_same_request_key_cannot_change_reason_or_source(tmp_path):
    service,cid,db,_=setup(tmp_path);first=parse(service,cid);request(service,cid)
    before=snapshot(db,['acquisition_jobs'])
    with pytest.raises(ValueError,match='request key'):
        service.request_deep_read(cid,DeepReadRequestInput(paper_id='existing',reason='Changed reason',idempotency_key='original-deep-read'))
    with pytest.raises(ValueError,match='request key'):
        request(service,cid,parse_run_id=first['parse_run_id'])
    assert snapshot(db,['acquisition_jobs'])==before


def test_request_without_completed_parse_creates_no_deep_read_job(tmp_path):
    service,cid,db,_=setup(tmp_path);before=snapshot(db,['acquisition_jobs'])
    with pytest.raises(ValueError,match='completed parse'):request(service,cid)
    assert snapshot(db,['acquisition_jobs'])==before


def test_skeleton_republication_keeps_all_original_runs_and_checkpoints(tmp_path):
    service,cid,db,_=setup(tmp_path);parsed=parse(service,cid)
    first=service.publish_skeleton_result(parsed['parse_run_id'],units(),model_name='software-model-a')
    tables=['skeleton_runs','skeleton_checkpoints','paper_skeletons','skeleton_units'];before=snapshot(db,tables)
    changed=units();changed[0]['layer3']={'intent':'A different interpretation'}
    second=service.publish_skeleton_result(parsed['parse_run_id'],changed,model_name='software-model-b')
    assert first['skeleton_run_id']!=second['skeleton_run_id'] and first['skeleton_id']!=second['skeleton_id']
    after=snapshot(db,tables)
    assert all(row in after[name] for name,rows in before.items() for row in rows)
    assert service.publish_skeleton_result(parsed['parse_run_id'],changed,model_name='software-model-b')==second
    assert snapshot(db,tables)==after


class RecordedGateway(FakeGateway):
    def analyze(self,task,payload):
        result=super().analyze(task,payload);result['_contract']['actual_model']='explicit-software-'+task
        return result


def test_each_layer_retains_exact_model_input_output_contract_and_parse_source(tmp_path):
    service,cid,db,_=setup(tmp_path);parsed=parse(service,cid);job=request(service,cid)
    completed=AcquisitionWorker(tmp_path,'model',model_gateway=RecordedGateway(),worker_id='recorded-model').run_once()
    assert completed['status']=='SUCCEEDED'
    calls=service.get_paper('existing')['model_calls'];assert len(calls)==4
    assert [c['task'] for c in calls]==[f'skeleton_layer_{n}' for n in range(1,5)]
    for n,call in enumerate(calls,1):
        assert call['status']=='RETURNED' and call['source']['parse_run_id']==parsed['parse_run_id']
        assert call['input']['raw_text']=='Original source block' and call['job_id']==job['job_id']
        assert call['contract']['actual_model']==f'explicit-software-skeleton_layer_{n}'
        assert call['output']['_contract']==call['contract']
        if n>1:
            assert call['input'][f'layer{n-1}']=={k:v for k,v in calls[n-2]['output'].items() if k!='_contract'}
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute('SELECT COUNT(*) FROM acquisition_model_call_events').fetchone()[0]==8
        checkpoints=conn.execute('SELECT layer,model_name,prompt_version FROM skeleton_checkpoints ORDER BY layer').fetchall()
        assert checkpoints==[(n,f'explicit-software-skeleton_layer_{n}',f'skeleton_layer_{n}-fixture') for n in range(1,5)]


def test_failed_model_call_retains_failed_receipt_without_scientific_publication(tmp_path):
    service,cid,db,_=setup(tmp_path);parse(service,cid);request(service,cid)
    class Failure:
        def analyze(self,*_):raise RuntimeError('PRIVATE_CREDENTIAL_TEST_NOT_TO_BE_PERSISTED')
    job=AcquisitionWorker(tmp_path,'model',model_gateway=Failure(),worker_id='failed-model').run_once()
    assert job['status']=='RETRY_WAIT'
    calls=service.get_paper('existing')['model_calls'];assert calls[0]['status']=='FAILED'
    assert calls[0]['error_type']=='RuntimeError' and 'PRIVATE_CREDENTIAL' not in json.dumps(calls)
    assert snapshot(db,['skeleton_runs'])['skeleton_runs']==[]


def test_foreign_parse_is_rejected_before_any_model_call(tmp_path):
    service,cid,db,_=setup(tmp_path);parsed=parse(service,cid)
    with transaction(db) as conn:
        service._enqueue(conn,collection_id=cid,paper_id='other',job_type='SKELETON',queue_class='MODEL_SKELETON',payload={'parse_run_id':parsed['parse_run_id']},rule_version='foreign-source-test',priority=300)
    class Never:
        def analyze(self,*_):raise AssertionError('Must not call model for foreign source')
    job=AcquisitionWorker(tmp_path,'model',model_gateway=Never(),worker_id='foreign-source-model').run_once()
    assert job['status']=='NEEDS_HUMAN'
    assert service.get_paper('other')['model_calls']==[]
    assert snapshot(db,['skeleton_runs'])['skeleton_runs']==[]


def test_source_change_during_model_retains_receipts_but_rejects_publication(tmp_path):
    service,cid,db,pdf=setup(tmp_path);parse(service,cid);request(service,cid)
    class Change(RecordedGateway):
        def analyze(self,task,payload):
            result=super().analyze(task,payload)
            if task=='skeleton_layer_1':pdf.write_bytes(pdf.read_bytes()+b'changed')
            return result
    job=AcquisitionWorker(tmp_path,'model',model_gateway=Change(),worker_id='changed-source-model').run_once()
    assert job['status']=='NEEDS_HUMAN'
    assert snapshot(db,['skeleton_runs'])['skeleton_runs']==[]
    calls=service.get_paper('existing')['model_calls'];assert len(calls)==1 and calls[0]['status']=='RETURNED'


def test_legacy_unique_constraint_migration_keeps_rows_and_foreign_keys(tmp_path):
    from rstv4.database import initialize_catalog
    service,cid,db,_=setup(tmp_path);parsed=parse(service,cid)
    with closing(sqlite3.connect(db)) as conn:
        conn.execute('PRAGMA foreign_keys=OFF')
        sql=conn.execute("SELECT sql FROM sqlite_master WHERE name='skeleton_runs'").fetchone()[0]
        legacy=sql.replace('skeleton_runs','legacy_skeleton_runs',1)
        legacy=legacy.rsplit(')',1)[0].rstrip()+', UNIQUE(parse_run_id, prompt_version, context_builder_version))'
        conn.execute(legacy);conn.execute('DROP TABLE skeleton_runs');conn.execute('ALTER TABLE legacy_skeleton_runs RENAME TO skeleton_runs');conn.commit()
    first=service.publish_skeleton_result(parsed['parse_run_id'],units(),model_name='software-legacy')
    before=snapshot(db,['skeleton_runs','skeleton_checkpoints'])
    initialize_catalog(db)
    assert snapshot(db,['skeleton_runs','skeleton_checkpoints'])==before
    changed=units();changed[0]['layer4']={'role':'A second immutable interpretation'}
    second=service.publish_skeleton_result(parsed['parse_run_id'],changed,model_name='software-new')
    assert second['skeleton_run_id']!=first['skeleton_run_id']
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert conn.execute('SELECT COUNT(*) FROM skeleton_runs').fetchone()[0]==2


def test_formal_deep_read_endpoint_and_original_call_readback_are_scoped_and_read_only(tmp_path):
    from fastapi.testclient import TestClient

    from rstv4.catalog_web import create_app
    service,cid,db,_=setup(tmp_path);parsed=parse(service,cid)
    body={'paper_id':'existing','parse_run_id':parsed['parse_run_id'],'reason':'Explicit HTTP request','idempotency_key':'formal-deep-read-request'}
    with TestClient(create_app(tmp_path)) as client:
        first=client.post(f'/api/catalog/collections/{cid}/deep-read',json=body)
        assert first.status_code==202,first.text
        assert client.post(f'/api/catalog/collections/{cid}/deep-read',json=body).json()==first.json()
        assert client.post(f'/api/catalog/collections/{cid}/deep-read',json={**body,'reason':'Changed contents'}).status_code==409
        assert AcquisitionWorker(tmp_path,'model',model_gateway=RecordedGateway(),worker_id='http-model').run_once()['status']=='SUCCEEDED'
        before=snapshot(db,['acquisition_model_call_events','paper_assessments','skeleton_runs'])
        details=client.get('/api/catalog/papers/existing').json();assert len(details['model_calls'])==4
        assert 'input' not in details['model_calls'][0]
        call_id=details['model_calls'][0]['call_id'];original=client.get(f'/api/catalog/papers/existing/model-calls/{call_id}')
        assert original.status_code==200 and original.json()['input']['raw_text']=='Original source block'
        assert client.get(f'/api/catalog/papers/other/model-calls/{call_id}').status_code==404
        assert snapshot(db,['acquisition_model_call_events','paper_assessments','skeleton_runs'])==before
