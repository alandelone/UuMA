from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_catalog_review_workflow import act, fixture, state

from rstv4.acquisition_worker import AcquisitionWorker
from rstv4.catalog_web import create_app
from rstv4.models import DecisionProposalInput
from rstv4.service import RevisionConflictError
from rstv4.track_first import TrackFirstService


def dependencies(root: Path):
    service,collection,paper,file=fixture(root)
    published=service.publish_parse_result(collection['collection_id'],paper['paper_id'],file['file_version_id'],
        parser_name='software',parser_version='1',config={},manifest={},blocks=[{'text':'Software source body. '*8}],references=[])
    with closing(sqlite3.connect(service.db_path)) as conn,conn:
        conn.execute("INSERT INTO topics VALUES('topic','topic','Topic',NULL,'now','now')")
        conn.execute("INSERT INTO field_topics VALUES(?, 'topic','now')",(collection['field_id'],))
        conn.execute("INSERT INTO research_tracks(track_id,field_id,primary_topic_id,title,research_type,status,mapping_status,created_at,updated_at) VALUES('track',?,'topic','Software Track','conceptual_framework','ACTIVE','MAPPED','now','now')",(collection['field_id'],))
        conn.execute("INSERT INTO evidence VALUES('evidence','FIELDKG',?,NULL,?,?,NULL,'Software fixture evidence','Exact fixture source','{}','SUPPORTS',1.0,'fixture','fixture','evidence-sha','now')",
                     (collection['field_id'],paper['paper_id'],published['paper_version_id']))
        for node,kind in [('root','claim'),('child','method'),('untouched','claim')]:
            conn.execute("INSERT INTO research_nodes VALUES(?,'track',?,'APPROVED',?,'Software fixture','{}',1,'now','now')",(node,kind,node))
        conn.execute("INSERT INTO node_evidence VALUES('root','evidence')")
        conn.execute("INSERT INTO research_edges VALUES('edge','track','root','child','MOTIVATES','now')")
        conn.execute("INSERT INTO manuscripts(manuscript_id,track_id,title,research_type,writing_status,needs_scientific_review,revision,created_at,updated_at) VALUES('ms','track','Software MS','conceptual_framework','DRAFTING',0,1,'now','now')")
        conn.execute("INSERT INTO manuscript_nodes VALUES('ms','child',NULL,1)")
        conn.execute("INSERT INTO manuscript_evidence VALUES('ms','evidence','evidence-sha')")
        conn.execute("INSERT INTO manuscript_versions VALUES('old-version','ms',1,'Frozen software manuscript','{}','now')")
    return service,collection,paper,file,published


def test_reopening_preserves_versions_invalidates_descendants_and_fences_running_job(tmp_path: Path):
    service,collection,paper,file,published=dependencies(tmp_path)
    running=service.claim_job('controlled-model-worker',['MODEL_READ'])
    assert running['job_type']=='QUICK_READ'
    with closing(sqlite3.connect(service.db_path)) as conn:
        frozen={table:conn.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall() for table in ['paper_versions','parse_runs','document_blocks','evidence','manuscript_versions','manuscript_nodes','manuscript_evidence']}
    with TestClient(create_app(tmp_path)) as client:
        case=file['file_version_id']
        context=client.get(f'/api/catalog/review/cases/{case}/workflow').json()
        assert 'REOPEN_IDENTITY' in context['allowed_actions']
        response=act(client,case,'REOPEN_IDENTITY','reopen-source-fixture')
        assert response.status_code==201,response.text
        result=response.json()['result'];assert result['status']=='IDENTITY_REOPENED'
        assert result['invalidated_nodes']==['child','root']
        assert result['affected_manuscripts']==['ms'] and running['job_id'] in result['stopped_jobs']
        stopped=service.get_job(running['job_id'])
        assert stopped['status']=='NEEDS_HUMAN' and stopped['fencing_token']==running['fencing_token']+1
        with pytest.raises(ValueError,match='lease'):
            service.complete_job(running['job_id'],'controlled-model-worker',running['fencing_token'],{'unsafe':'result'})
        with pytest.raises(ValueError,match='identity|lease'):
            service.record_assessment(collection['collection_id'],paper['paper_id'],'QUICK_READ',{},[],rule_version='test',input_digest='test',
                parse_run_id=published['parse_run_id'],job_id=running['job_id'],worker_id='controlled-model-worker',fencing_token=running['fencing_token'])
        before=state(service.db_path)
        body={k:v for k,v in response.json()['request'].items() if k!='case_id'}
        assert client.post(f'/api/catalog/review/cases/{case}/actions',json=body).json()==response.json()
        assert state(service.db_path)==before
    with closing(sqlite3.connect(service.db_path)) as conn:
        assert all(conn.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall()==rows for table,rows in frozen.items())
        assert conn.execute("SELECT status FROM research_nodes WHERE node_id='untouched'").fetchone()[0]=='APPROVED'
        assert conn.execute("SELECT needs_scientific_review FROM manuscripts WHERE manuscript_id='ms'").fetchone()[0]==1


def test_identity_reapproval_does_not_restore_scientific_decisions_or_old_evidence(tmp_path: Path):
    service,_,_,file,_=dependencies(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        case=file['file_version_id']
        assert act(client,case,'REOPEN_IDENTITY','first-source-reopen').status_code==201
        assert act(client,case,'APPROVE_IDENTITY','new-identity-review').json()['result']['status']=='APPROVED_IDENTITY'
    track=TrackFirstService(tmp_path)
    with pytest.raises(RevisionConflictError,match='source|review'):
        track.propose_decision('track',DecisionProposalInput(kind='claim',statement='New statement',rationale='Reusing held evidence',evidence_ids=['evidence']))
    with pytest.raises(RevisionConflictError,match='review'):
        track.compile_manuscript('ms','No automatic restoration')
    with closing(sqlite3.connect(service.db_path)) as conn:
        assert conn.execute("SELECT status FROM research_nodes WHERE node_id='child'").fetchone()[0]=='STALE'
        assert conn.execute("SELECT needs_scientific_review FROM manuscripts WHERE manuscript_id='ms'").fetchone()[0]==1


def test_parse_quality_hold_survives_identity_reopen_and_reapproval(tmp_path: Path):
    service,_,_,file=fixture(tmp_path)
    job=service.claim_job('parser',['PARSER'])
    service.defer_job(job['job_id'],'parser',job['fencing_token'],status='NEEDS_HUMAN',error_code='QUALITY',detail='Original quality issue',retry_after_seconds=86400,
        review_context={'kind':'PARSE_QUALITY','file_version_id':file['file_version_id'],'pdf_sha256':hashlib.sha256(Path(file['storage_path']).read_bytes()).hexdigest(),'correction_action_ids':['original-proof']})
    before=service.get_job(job['job_id'])
    with TestClient(create_app(tmp_path)) as client:
        case=file['file_version_id'];assert act(client,case,'REOPEN_IDENTITY','quality-source-reopen').status_code==201
        approved=act(client,case,'APPROVE_IDENTITY','quality-source-reapprove')
        assert job['job_id'] not in approved.json()['result']['resumed_jobs']
    current=service.get_job(job['job_id'])
    assert current['status']=='NEEDS_HUMAN' and current['last_error_code']=='QUALITY'
    assert current['result_json']==before['result_json']


def test_withdrawn_parse_cannot_be_consumed_by_worker(tmp_path: Path):
    _service,_,_,file,published=dependencies(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        assert act(client,file['file_version_id'],'REOPEN_IDENTITY','worker-source-reopen').status_code==201
    worker=AcquisitionWorker(tmp_path,'model')
    with pytest.raises(RuntimeError,match='identity'):
        worker._parse_blocks(published['parse_run_id'])
