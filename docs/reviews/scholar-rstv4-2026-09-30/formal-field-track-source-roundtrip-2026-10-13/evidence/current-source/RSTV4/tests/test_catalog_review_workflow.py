from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from rstv4.acquisition_worker import AcquisitionWorker
from rstv4.catalog_web import create_app
from rstv4.models import CollectionCreateInput, FieldInput, PdfRegistrationInput
from rstv4.track_first import TrackFirstService


def pdf(root: Path, title: str, doi: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    font = DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    for texts in [
        [title, 'DOI '+doi, 'Software fixture body preserves source, ownership and exact references. '*3],
        ['References', *[f'[{n}] Reference author {n}. Distinct software citation experiment validation {n}. 2026.' for n in range(1,7)]],
    ]:
        page=writer.add_blank_page(width=1000,height=1000)
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        content=DecodedStreamObject()
        commands=['BT /F1 12 Tf 30 950 Td']
        for text in texts:
            commands.append('('+text+') Tj 0 -30 Td')
        commands.append('ET');content.set_data(' '.join(commands).encode())
        page[NameObject('/Contents')]=writer._add_object(content)
    target=root/'source.pdf';writer.write(target);return target


def fixture(root: Path, *, mismatch=False):
    track=TrackFirstService(root)
    field=track.create_field(FieldInput(name='Software review fixture'))
    service=track.paperpool
    collection=service.create_collection(CollectionCreateInput(field_id=field['field_id'],name='Fixture collection',dois=['10.1234/original'],idempotency_key='review-fixture-collection'))
    paper=service.resolve_seed(collection['seeds'][0]['seed_id'],{'doi':'10.1234/original','title':'Wrong catalogue identity' if mismatch else 'Software review identity title'})
    source=pdf(service.import_root,'Software review identity title','10.1234/corrected' if mismatch else '10.1234/original')
    file=service.register_pdf(collection['collection_id'],PdfRegistrationInput(paper_id=paper['paper_id'],path=str(source),acquisition_method='TEST',idempotency_key='review-fixture-registration'))
    return service,collection,paper,file


def state(db: Path):
    with closing(sqlite3.connect(db)) as conn:
        rows=list(conn.iterdump())
    return hashlib.sha256(db.read_bytes()).hexdigest(),rows


def act(client,case,action,request_id,**values):
    context=client.get(f'/api/catalog/review/cases/{case}/workflow').json()
    return client.post(f'/api/catalog/review/cases/{case}/actions',json={
        'request_id':request_id,'action':action,'expected_context_sha256':context['context_sha256'],'reason':'Explicit software fixture review',**values})


def test_identity_annotations_then_explicit_review_approves_and_queues_exact_parse(tmp_path: Path):
    service,_collection,paper,file=fixture(tmp_path,mismatch=True)
    assert file['identity_status']=='NEEDS_REVIEW'
    with TestClient(create_app(tmp_path)) as client:
        case=file['file_version_id'];url=f'/api/catalog/review/cases/{case}'
        original=client.get(url+'/workflow').json();before=state(service.db_path)
        assert client.get(url+'/workflow').json()==original
        assert state(service.db_path)==before
        foreign=client.post(url+'/actions',headers={'origin':'https://foreign.test'},json={
            'request_id':'cross-origin-review','action':'APPROVE_IDENTITY','expected_context_sha256':original['context_sha256'],'reason':'No'})
        assert foreign.status_code==403 and state(service.db_path)==before
        words=client.get(f'/api/catalog/files/{case}/pages/1/text').json()['words']
        title_start=next(i for i,w in enumerate(words) if w['text']=='Software')
        doi_index=next(i for i,w in enumerate(words) if '10.1234/corrected' in w['text'])
        for field,start,end in [('TITLE',title_start,title_start+3),('DOI',doi_index,doi_index)]:
            saved=client.post(url+'/annotations',json={'submission_id':'annotation-'+field,'field_name':field,'decision':'FOUND','page_number':1,'word_start':start,'word_end':end})
            assert saved.status_code==201,saved.text
        assert service.get_paper(paper['paper_id'])['doi']=='10.1234/corrected'
        approved=act(client,case,'APPROVE_IDENTITY','identity-review-confirmation')
        assert approved.status_code==201,approved.text
        assert approved.json()['result']['status']=='APPROVED_IDENTITY'
        assert len(approved.json()['result']['parse_jobs'])==1
        assert client.get('/api/catalog/review/cases').json()==[]
        before=state(service.db_path)
        # The stored request includes its route owner; submit only the original request body.
        body={k:v for k,v in approved.json()['request'].items() if k!='case_id'}
        assert client.post(url+'/actions',json=body).json()==approved.json()
        assert client.post(url+'/actions',json={**body,'reason':'Changed decision'}).status_code==409
        assert state(service.db_path)==before


def test_wrong_pdf_and_changed_source_cannot_be_approved(tmp_path: Path):
    service,_,_,file=fixture(tmp_path,mismatch=True)
    with TestClient(create_app(tmp_path)) as client:
        case=file['file_version_id'];url=f'/api/catalog/review/cases/{case}'
        context=client.get(url+'/workflow').json()
        assert client.post(url+'/annotations',json={'submission_id':'wrong-file-fixture','field_name':'PDF','decision':'WRONG_PDF'}).status_code==201
        before=state(service.db_path)
        rejected=client.post(url+'/actions',json={'request_id':'stale-file-approval','action':'APPROVE_IDENTITY','expected_context_sha256':context['context_sha256'],'reason':'Stale review'})
        assert rejected.status_code==409 and state(service.db_path)==before
        assert act(client,case,'APPROVE_IDENTITY','wrong-file-approval').status_code==409
        path=Path(file['storage_path']);path.write_bytes(path.read_bytes()+b'changed')
        assert client.get(url+'/workflow').json()['integrity_verified'] is False
        assert act(client,case,'APPROVE_IDENTITY','tampered-file-approval').status_code==409


def test_parser_source_correction_is_rechecked_then_publishes_and_keeps_history(tmp_path: Path):
    service,_collection,_paper,file=fixture(tmp_path)
    assert file['identity_status']=='VERIFIED'
    parsed={'parser':'explicit-fixture-parser','parser_version':'1','manifest':{'quality':{'reference_page_alignment':{'missing_source_numbered_references':[6]}}},
            'blocks':[{'text':'Exact software source body. '*8,'page_number':1,'location':{'source':'controlled parser'}}],
            'references':[{'raw_text':f'[{n}] Reference author {n}. Distinct software citation experiment validation {n}. 2026.','page_number':2,'location':{}} for n in range(1,6)]}
    class Parser:
        def parse(self,*_):return copy.deepcopy(parsed)
    worker=AcquisitionWorker(tmp_path,'parser',parser=Parser(),worker_id='fixture-parser-worker')
    stopped=worker.run_once();assert stopped['status']=='NEEDS_HUMAN'
    candidate=json.loads(stopped['result_json'])['review']['candidate']
    original_candidate=Path(candidate['path']).read_bytes()
    case=stopped['job_id']
    with TestClient(create_app(tmp_path)) as client:
        summary=client.get('/api/catalog/summary').json();assert summary['parser_review_cases']==1
        context=client.get(f'/api/catalog/review/cases/{case}/workflow').json()
        assert context['candidate']['available'] and context['candidate']['quality']['reference_page_alignment']['missing_source_numbered_references']==[6]
        words=client.get(f"/api/catalog/files/{file['file_version_id']}/pages/2/text").json()['words']
        start=next(i for i,w in enumerate(words) if w['text']=='[6]')
        selection={'page_number':2,'word_start':start,'word_end':len(words)-1}
        queued=act(client,case,'RECHECK_PARSE','parser-source-correction',reference_selections=[selection])
        assert queued.status_code==201,queued.text
        assert queued.json()['result']['quality_approved'] is False
        assert service.get_job(case)['status']=='READY'
        assert Path(candidate['path']).read_bytes()==original_candidate
        completed=worker.run_once();assert completed['status']=='SUCCEEDED',completed
        result=json.loads(completed['result_json']);assert result['references']==6
        with closing(sqlite3.connect(service.db_path)) as conn:
            assert conn.execute('SELECT COUNT(*) FROM paper_versions').fetchone()[0]==1
            assert conn.execute('SELECT COUNT(*) FROM reference_entries').fetchone()[0]==6
            assert conn.execute("SELECT COUNT(*) FROM acquisition_jobs WHERE job_type='QUICK_READ'").fetchone()[0]==1
        receipt_body={k:v for k,v in queued.json()['request'].items() if k!='case_id'}
        before=state(service.db_path)
        assert client.post(f'/api/catalog/review/cases/{case}/actions',json=receipt_body).json()==queued.json()
        assert state(service.db_path)==before
        assert client.get('/api/catalog/summary').json()['parser_review_cases']==0


def test_changed_parse_output_creates_new_version_and_exact_replay_does_not_replace_old(tmp_path: Path):
    service,collection,paper,file=fixture(tmp_path)
    params={'parser_name':'fixture','parser_version':'1','config':{},'manifest':{},'references':[]}
    first=service.publish_parse_result(collection['collection_id'],paper['paper_id'],file['file_version_id'],blocks=[{'text':'Original source body'}],**params)
    with closing(sqlite3.connect(service.db_path)) as conn:
        old_run=conn.execute('SELECT * FROM parse_runs').fetchall()
        old_block=conn.execute('SELECT * FROM document_blocks').fetchall()
        old_version=conn.execute('SELECT * FROM paper_versions').fetchall()
    second=service.publish_parse_result(collection['collection_id'],paper['paper_id'],file['file_version_id'],blocks=[{'text':'Corrected source body'}],**params)
    assert first['paper_version_id']!=second['paper_version_id']
    before=state(service.db_path)
    assert service.publish_parse_result(collection['collection_id'],paper['paper_id'],file['file_version_id'],blocks=[{'text':'Corrected source body'}],**params)==second
    assert state(service.db_path)==before
    with closing(sqlite3.connect(service.db_path)) as conn:
        assert old_run[0] in conn.execute('SELECT * FROM parse_runs').fetchall()
        assert old_block[0] in conn.execute('SELECT * FROM document_blocks').fetchall()
        assert old_version[0] in conn.execute('SELECT * FROM paper_versions').fetchall()
        assert [row[0] for row in conn.execute('SELECT version FROM paper_versions ORDER BY version')]==[1,2]
