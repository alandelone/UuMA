from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_collection_workspace import fingerprint, payload, setup

from rstv4.acquisition import AcquisitionService
from rstv4.acquisition_worker import AcquisitionWorker
from rstv4.catalog_web import create_app
from rstv4.models import CollectionCreateInput, CollectionScopeInput


def library(root: Path, *, identity='VERIFIED', doi=None):
    db = setup(root)
    pdf = root/'registered.pdf';pdf.write_bytes(b'%PDF-1.4 isolated software source')
    with closing(sqlite3.connect(db)) as conn, conn:
        for paper_id, title, paper_doi in [('existing','Catalog selected source',doi),('other','Other selected source','10.1234/other')]:
            conn.execute('INSERT INTO papers VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (paper_id,paper_id,paper_doi,title.lower(),title,'["Fixture Author"]',2026,None,None,None,'now','now'))
        conn.execute('INSERT INTO source_file_versions VALUES(?,?,?,?,?,?,?,?,?,?,?)', ('existing-file','existing',hashlib.sha256(pdf.read_bytes()).hexdigest(),pdf.stat().st_size,'application/pdf',str(pdf),'SOFTWARE_FIXTURE',None,identity,'{}','now'))
    return db,pdf


def chosen(**changes):
    values={'dois':[],'paper_ids':['existing']};values.update(changes)
    return payload(**values)


def gateway(callback=None,category='DIRECT'):
    class Control:
        def analyze(self,task,body):
            assert task=='screen'
            if callback:callback(body)
            return {'category':category,'evidence_quotes':[], '_contract':{'prompt_version':'explicit-software-control'}}
    return Control()


def test_catalog_only_preview_and_paginated_choices_are_read_only(tmp_path: Path):
    db,_=library(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        before=fingerprint(db)
        result=client.get('/api/catalog/collections/paper-options',params={'field_id':'f1','topic_id':'t1','q':'Fixture Author','limit':1})
        assert result.status_code==200 and result.json()['total']==2 and result.json()['has_more']
        page2=client.get('/api/catalog/collections/paper-options',params={'field_id':'f1','topic_id':'t1','q':'Fixture Author','limit':1,'offset':1}).json()
        assert result.json()['papers'][0]['paper_id']!=page2['papers'][0]['paper_id']
        preview=client.post('/api/catalog/collections/preview',json=chosen())
        assert preview.status_code==200,preview.text
        assert preview.json()['counts']['catalog_selected']==1 and preview.json()['counts']['reusable_pdfs']==1
        assert preview.json()['matched_papers'][0]['paper_id']=='existing'
        assert fingerprint(db)==before


def test_catalog_selection_keeps_paper_identity_and_raw_inputs_without_resolve_jobs(tmp_path: Path):
    db,_=library(tmp_path,doi='10.1234/seed')
    with TestClient(create_app(tmp_path)) as client:
        with closing(sqlite3.connect(db)) as conn:
            old={name:conn.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall() for name in ['papers','source_file_versions']}
        body=chosen(dois=['10.1234/seed'],bibtex='@article{x, title={Catalog selected source}, doi={10.1234/seed}}')
        response=client.post('/api/catalog/collections',json=body);assert response.status_code==201,response.text
        created=response.json();assert created['counts']=={'papers':1,'jobs':1}
        assert {seed['paper_id'] for seed in created['seeds']}=={'existing'}
        assert {seed['seed_type'] for seed in created['seeds']}=={'CATALOG_PAPER','DOI'}
        assert json.loads(created['creation_request_json'])['paper_ids']==['existing']
        before=fingerprint(db)
        assert client.post('/api/catalog/collections',json=body).json()==created and fingerprint(db)==before
        assert client.post('/api/catalog/collections',json={**body,'paper_ids':['other']}).status_code==409
        assert fingerprint(db)==before
        with closing(sqlite3.connect(db)) as conn:
            assert all(conn.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall()==rows for name,rows in old.items())
            assert conn.execute('SELECT job_type FROM acquisition_jobs').fetchall()==[('SCREEN',)]


@pytest.mark.parametrize('changes',[{'paper_ids':['missing']},{'paper_ids':['existing','existing']},{'field_id':'f2','topic_id':'t1'},{'dois':['invalid']}])
def test_bad_catalog_selection_or_owner_is_atomic(tmp_path: Path,changes: dict):
    db,_=library(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        before=fingerprint(db)
        for route in ['/preview','']:
            response=client.post('/api/catalog/collections'+route,json=chosen(**changes))
            assert response.status_code in (404,422),response.text
        assert fingerprint(db)==before


@pytest.mark.parametrize('identity,expected',[('VERIFIED','SUCCEEDED'),('NEEDS_REVIEW','NEEDS_HUMAN')])
def test_catalog_no_doi_reuses_only_intact_verified_file_after_scope_screen(tmp_path: Path,identity: str,expected: str):
    db,_=library(tmp_path,identity=identity)
    service=AcquisitionService(tmp_path);created=service.create_collection(CollectionCreateInput.model_validate(chosen()))
    assert service.claim_job('before-screen',['NETWORK']) is None
    model=AcquisitionWorker(tmp_path,'model',model_gateway=gateway(),worker_id='software-screen')
    screened=model.run_once();assert screened['status']=='SUCCEEDED',screened
    network=AcquisitionWorker(tmp_path,'network',worker_id='software-file-reuse')
    processed=network.run_once();assert processed['status']==expected,processed
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute('SELECT COUNT(*) FROM papers').fetchone()[0]==2
        assert conn.execute('SELECT COUNT(*) FROM source_file_versions').fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM screening_input_snapshots').fetchone()[0]==1
        parse=conn.execute("SELECT input_json FROM acquisition_jobs WHERE job_type='PARSE_PDF'").fetchall()
        assert bool(parse)==(identity=='VERIFIED')
        if parse:assert json.loads(parse[0][0])['file_version_id']=='existing-file'
        assert conn.execute("SELECT status FROM collection_memberships WHERE collection_id=?",(created['collection_id'],)).fetchone()[0]=='DISCOVERED'


def test_scope_change_before_screen_stops_before_model_and_rescreens_actual_scope_version(tmp_path: Path):
    db,_=library(tmp_path);service=AcquisitionService(tmp_path)
    created=service.create_collection(CollectionCreateInput.model_validate(chosen()));cid=created['collection_id']
    service.pause_collection(cid,1);service.resume_collection(cid,2)
    service.update_scope(cid,CollectionScopeInput(scope={'topic':'New scope'},expected_revision=3))
    model=AcquisitionWorker(tmp_path,'model',model_gateway=gateway(lambda body:pytest.fail('Stale source must stop before model')),worker_id='software-screen')
    old=model.run_once();assert old['status']=='NEEDS_HUMAN',old
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute('SELECT COUNT(*) FROM paper_assessments').fetchone()[0]==0
        fresh=conn.execute("SELECT input_json,rule_version FROM acquisition_jobs WHERE status='READY'").fetchone()
        assert json.loads(fresh[0])['scope_version']==2 and fresh[1]=='screen-v1-scope-2'


@pytest.mark.parametrize('change',['SCOPE','METADATA','LEASE'])
def test_screen_context_or_lease_change_during_model_does_not_publish(tmp_path: Path,change: str):
    db,_=library(tmp_path);service=AcquisitionService(tmp_path)
    created=service.create_collection(CollectionCreateInput.model_validate(chosen()));cid=created['collection_id']
    def mutate(body):
        assert body['title']=='Catalog selected source'
        if change=='SCOPE':service.update_scope(cid,CollectionScopeInput(scope={'changed':True},expected_revision=1))
        else:
            with closing(sqlite3.connect(db)) as conn, conn:
                if change=='METADATA':conn.execute("UPDATE papers SET title='Changed after actual model input' WHERE paper_id='existing'")
                else:conn.execute("UPDATE acquisition_jobs SET lease_owner='another-worker' WHERE status='RUNNING'")
    model=AcquisitionWorker(tmp_path,'model',model_gateway=gateway(mutate),worker_id='software-screen')
    job=service.claim_job('software-screen',['MODEL_SCREEN'])
    with pytest.raises(ValueError,match='changed|lease'):
        model._handle_screen(job,json.loads(job['input_json']))
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute('SELECT COUNT(*) FROM paper_assessments').fetchone()[0]==0
        assert conn.execute('SELECT COUNT(*) FROM screening_input_snapshots').fetchone()[0]==0
        assert conn.execute("SELECT COUNT(*) FROM acquisition_jobs WHERE job_type='LOCATE_PDF'").fetchone()[0]==0


def test_same_paper_different_collection_scope_keeps_independent_screening_records(tmp_path: Path):
    db,_=library(tmp_path);service=AcquisitionService(tmp_path)
    first=service.create_collection(CollectionCreateInput.model_validate(chosen(idempotency_key='scope-source-first',scope={'topic':'A'})))
    second=service.create_collection(CollectionCreateInput.model_validate(chosen(idempotency_key='scope-source-second',scope={'topic':'B'})))
    a=service.record_assessment(first['collection_id'],'existing','SCREEN',{'category':'DIRECT'},[],rule_version='same-rule',input_digest='same-raw-input')
    b=service.record_assessment(second['collection_id'],'existing','SCREEN',{'category':'IRRELEVANT'},[],rule_version='same-rule',input_digest='same-raw-input')
    assert a['assessment_id']!=b['assessment_id']
    assert json.loads(a['result_json'])=={'category':'DIRECT'} and json.loads(b['result_json'])=={'category':'IRRELEVANT'}
    candidates_a=service.get_core_candidates(first['collection_id'])
    candidates_b=service.get_core_candidates(second['collection_id'])
    assert candidates_a[0]['relevance_group']=='DIRECT' and candidates_b[0]['relevance_group']=='IRRELEVANT'
    with closing(sqlite3.connect(db)) as conn:
        rows=conn.execute('SELECT collection_id,context_json FROM screening_input_snapshots').fetchall()
        assert {r[0] for r in rows}=={first['collection_id'],second['collection_id']}
        assert {json.loads(r[1])['collection']['scope']['topic'] for r in rows}=={'A','B'}


def test_existing_doi_only_creation_payload_keeps_exact_legacy_request_shape(tmp_path: Path):
    db,_=library(tmp_path);service=AcquisitionService(tmp_path)
    body=payload();created=service.create_collection(CollectionCreateInput.model_validate(body))
    assert 'paper_ids' not in json.loads(created['creation_request_json'])
    before=fingerprint(db)
    assert service.create_collection(CollectionCreateInput.model_validate(body))==created and fingerprint(db)==before


def test_scope_change_preserves_old_ranking_and_creates_new_current_record(tmp_path: Path):
    db,_=library(tmp_path);service=AcquisitionService(tmp_path)
    created=service.create_collection(CollectionCreateInput.model_validate(chosen()));cid=created['collection_id']
    service.record_assessment(cid,'existing','SCREEN',{'category':'DIRECT'},[],rule_version='software-ranking',input_digest='input')
    assert service.get_core_candidates(cid)[0]['relevance_group']=='DIRECT'
    with closing(sqlite3.connect(db)) as conn:old=conn.execute('SELECT * FROM core_rankings').fetchall()
    service.update_scope(cid,CollectionScopeInput(scope={'topic':'Changed actual author scope'},expected_revision=1))
    service.record_assessment(cid,'existing','SCREEN',{'category':'IRRELEVANT'},[],rule_version='software-ranking',input_digest='input')
    assert service.get_core_candidates(cid)[0]['relevance_group']=='IRRELEVANT'
    with closing(sqlite3.connect(db)) as conn:
        current=conn.execute('SELECT * FROM core_rankings ORDER BY rowid').fetchall()
        assert len(current)==2 and current[0]==old[0] and current[0][0]!=current[1][0]
