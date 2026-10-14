import copy
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import httpx

from rstv4.acquisition import AcquisitionService
from rstv4.acquisition_worker import AcquisitionWorker
from rstv4.models import PdfRegistrationInput
from rstv4.paper_parser import MinerUParser

repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo.parent/'RSTV4/tests'))
from test_catalog_review_workflow import pdf

phase=sys.argv[1]
receipt=json.loads((repo/'.tmp/scholar-review-recovery-services-v1.json').read_text(encoding='utf-8'))
root=Path(receipt['root']).resolve();service=AcquisitionService(root)
subprocess.run(['powershell','-NoProfile','-Command',(repo/'.tmp/scholar-review-recovery-guard-v1.ps1').read_text(encoding='utf-8')],cwd=repo,check=True)
out=repo/'.tmp/scholar-review-recovery-native-v1.json'
if phase=='prepare':
    assert not out.exists();proof={'status':'STARTED','root':str(root),'responses':[], 'browser_verified':False,'scientific_approval':False,'network_providers_executed':False,'scientific_models_executed':False}
else:proof=json.loads(out.read_text(encoding='utf-8'))
def save():out.write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
def call(client,method,path,expected=200,**kwargs):
    response=client.request(method,path,**kwargs);body=response.json()
    proof['responses'].append({'method':method,'path':path,'status':response.status_code,'body':body});save()
    assert response.status_code==expected,response.text[:2000];return body
with httpx.Client(base_url='http://127.0.0.1:8887',timeout=30) as client:
    if phase=='prepare':
        def metadata(operation,request_id,**values):return call(client,'POST','/api/catalog/research-actions',json={'operation':operation,'request_id':request_id,**values})
        field=metadata('CREATE_FIELD','review-native-field-v1',name='审核恢复软件 Field')['object_id']
        topic=metadata('CREATE_TOPIC','review-native-topic-v1',field_id=field,name='审核恢复软件 Topic')['object_id']
        collection=call(client,'POST','/api/catalog/collections',201,json={'field_id':field,'topic_id':topic,'name':'审核恢复软件 Collection','dois':['10.1234/original'],'idempotency_key':'review-native-collection-v1'})
        seed_job=service.claim_job('owned-setup-worker',['NETWORK']);assert seed_job['job_type']=='RESOLVE_SEED'
        paper=service.resolve_seed(collection['seeds'][0]['seed_id'],{'doi':'10.1234/original','title':'Wrong catalogue identity'})
        service.complete_job(seed_job['job_id'],'owned-setup-worker',seed_job['fencing_token'],{'paper_id':paper['paper_id']})
        source=pdf(service.import_root,'Software review identity title','10.1234/corrected')
        file=service.register_pdf(collection['collection_id'],PdfRegistrationInput(paper_id=paper['paper_id'],path=str(source),acquisition_method='SOFTWARE_FIXTURE',idempotency_key='review-native-file-v1'))
        assert file['identity_status']=='NEEDS_REVIEW'
        located=AcquisitionWorker(root,'network',worker_id='owned-review-network').run_once()
        assert located['status']=='NEEDS_HUMAN' and json.loads(located['result_json'])['review']['file_version_id']==file['file_version_id']
        cases=call(client,'GET','/api/catalog/review/cases');assert len(cases)==1 and cases[0]['kind']=='PDF_IDENTITY'
        case=file['file_version_id'];words=call(client,'GET',f'/api/catalog/files/{case}/pages/1/text')['words']
        title=next(i for i,w in enumerate(words) if w['text']=='Software');doi=next(i for i,w in enumerate(words) if '10.1234/corrected' in w['text'])
        for kind,start,end in [('TITLE',title,title+3),('DOI',doi,doi)]:
            call(client,'POST',f'/api/catalog/review/cases/{case}/annotations',201,json={'submission_id':'native-source-'+kind,'field_name':kind,'decision':'FOUND','page_number':1,'word_start':start,'word_end':end})
        proof.update(status='READY_FOR_EXPLICIT_IDENTITY_REVIEW',file_version_id=case,paper_id=paper['paper_id'],collection_id=collection['collection_id'],source_path=file['storage_path'],locator_job_id=located['job_id']);save()
    elif phase=='stop_parse':
        assert proof['status']=='READY_FOR_EXPLICIT_IDENTITY_REVIEW'
        identity=json.loads((repo/'.tmp/scholar-review-controller-identity-v1.json').read_text(encoding='utf-8'))
        assert identity['receipt']['result']['status']=='APPROVED_IDENTITY'
        assert proof['locator_job_id'] in identity['receipt']['result']['resumed_jobs']
        parsed={'parser':'controlled-incomplete-parser','parser_version':'1','manifest':{'quality':{'reference_page_alignment':{'missing_source_numbered_references':[6]}}},
                'blocks':[{'text':'Controlled software source body. '*8,'page_number':1,'location':{'source':'explicit software fixture'}}],
                'references':[{'raw_text':f'[{n}] Reference author {n}. Distinct software citation experiment validation {n}. 2026.','page_number':2,'location':{}} for n in range(1,6)]}
        class Incomplete:
            def parse(self,*_):return copy.deepcopy(parsed)
        stopped=AcquisitionWorker(root,'parser',parser=Incomplete(),worker_id='owned-controlled-parser').run_once()
        assert stopped['status']=='NEEDS_HUMAN';review=json.loads(stopped['result_json'])['review']
        context=call(client,'GET',f"/api/catalog/review/cases/{stopped['job_id']}/workflow")
        assert context['candidate']['available'] and context['candidate']['quality']['reference_page_alignment']['missing_source_numbered_references']==[6]
        page=call(client,'GET',f"/api/catalog/files/{proof['file_version_id']}/pages/2/text")['words']
        start=next(i for i,w in enumerate(page) if w['text']=='[6]')
        proof.update(status='READY_FOR_EXPLICIT_PARSER_CORRECTION',parser_job_id=stopped['job_id'],candidate=review['candidate'],
                     reference_selection={'page_number':2,'word_start':start,'word_end':len(page)-1,'text':' '.join(w['text'] for w in page[start:])});save()
    elif phase=='real_parse':
        correction=json.loads((repo/'.tmp/scholar-review-controller-parser-v1.json').read_text(encoding='utf-8'))
        assert correction['receipt']['result']['quality_approved'] is False
        assert service.get_job(proof['parser_job_id'])['status']=='READY'
        os.environ['RSTV4_MINERU_ARTIFACT_ROOT']=str(root/'mineru-attempts')
        parser=MinerUParser(repo.parent/'RSTV4');readiness=parser.check();proof['actual_parser_readiness']=readiness;save()
        if not readiness['available']:
            proof['status']='REAL_PARSER_RUNTIME_UNAVAILABLE';save();raise RuntimeError('Actual parser runtime is unavailable; do not substitute a successful fixture')
        execution=AcquisitionWorker(root,'parser',parser=parser,worker_id='owned-actual-mineru-parser').run_once()
        proof['actual_parser_execution']=execution;save()
        assert execution['status']=='SUCCEEDED',execution
        published=json.loads(execution['result_json'])
        with sqlite3.connect(service.db_path) as conn:
            runs=conn.execute('SELECT * FROM parse_runs').fetchall();versions=conn.execute('SELECT * FROM paper_versions').fetchall()
            assert len(runs)==1 and len(versions)==1
            assert conn.execute('SELECT COUNT(*) FROM catalog_review_actions').fetchone()[0]==2
            assert conn.execute('SELECT COUNT(*) FROM paper_assessments').fetchone()[0]==0
        paper=call(client,'GET',f"/api/catalog/papers/{proof['paper_id']}")
        assert len(paper['references'])==6 and len(paper['parse_runs'])==1
        assert call(client,'GET','/api/catalog/summary')['parser_review_cases']==0
        assert call(client,'GET','/api/catalog/review/cases')==[]
        proof.update(status='PASS_ACTUAL_IDENTITY_REVIEW_AND_REAL_MINERU_PARSER_RECOVERY',published=published,
                     actual_local_mineru_executed=True,quick_read_status='QUEUED_NOT_EXECUTED',scientific_models_executed=False);save()
    else:raise ValueError('Unknown controlled native phase')
print('Actual review-recovery phase completed:',proof['status'])
