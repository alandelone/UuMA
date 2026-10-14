from __future__ import annotations

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from test_fieldkg_workspace import get_field, review_all, seal
from test_fieldkg_workspace import setup as field_setup

from rstv4.database import CATALOG_VERSION
from rstv4.durable_model_delivery import ModelRunPending
from rstv4.fieldkg_semantics import source_windows, validate_output
from rstv4.model_gateway import UnlimitedLLMGateway
from rstv4.research_workspace import WorkspaceError
from rstv4.track_first import TrackFirstService

KINDS = ['CONCEPT','METHOD','FINDING','REPORTED_GAP','COUNTEREVIDENCE','DEBATE','IDEA_MERGER']


class FixtureGateway:
    def __init__(self, root):
        self.base=UnlimitedLLMGateway(root)
        self.pending=False
        self.bad_quote=False
        self.missing_unit=False
        self.calls=[]
    def operation_id(self, task, payload, scope):
        return self.base.operation_id(task,payload,scope)
    def analyze_for_operation(self, task, payload, operation_id):
        self.calls.append(operation_id)
        if self.pending:raise ModelRunPending('fixture_semantic_run','running')
        units=payload['units']
        refs=[{'unit_id':unit['unit_id'],'quote':unit['raw_text'],'role':'SUPPORTS','qualifications':[]} for unit in units]
        objects=[]
        for kind in KINDS:
            selected=[dict(refs[0])]
            if kind in {'DEBATE','IDEA_MERGER'}:selected.append({**refs[1],'role':'CONTRADICTS' if kind=='DEBATE' else 'SUPPORTS'})
            if kind=='COUNTEREVIDENCE':selected[0]['role']='CONTRADICTS'
            if self.bad_quote:selected[0]['quote']='Invented source passage'
            objects.append({'kind':kind,'statement':'Software fixture interpretation '+kind,
                'rationale':'Software controls only, not a scientific quality judgment',
                'references':selected,'conditions':[],'confidence':.8})
        return {'objects':objects,'observed_unit_ids':[u['unit_id'] for u in units][1:] if self.missing_unit else [u['unit_id'] for u in units],
                '_contract':{'task':task,'actual_model':'software-fixture','prompt_version':'fieldkg-semantics-v1-located-objects',
                             'router_run_id':'fixture_semantic_run','transport_operation_id':operation_id}}


@pytest.fixture
def setup(tmp_path):
    client,db,field,other,track,build=field_setup.__wrapped__(tmp_path)
    pool=tmp_path/'pool.db'
    with sqlite3.connect(pool) as conn:
        row=list(conn.execute('SELECT * FROM paper WHERE id=1').fetchone())
        row[0]=2;row[1]='Second located source';row[5]='10.1000/second'
        semantics=json.loads(row[-1]);semantics[0]['raw_text']='A larger trial reports strong validation under dry conditions.'
        semantics[0]['layer1']['coref_resolved']=semantics[0]['raw_text']
        semantics[0]['layer3']['intent']='Objective_Finding'
        row[-1]=json.dumps(semantics)
        conn.execute('INSERT INTO paper VALUES('+','.join('?' for _ in row)+')',row)
    TrackFirstService(tmp_path).import_paperpool(build,str(pool),[2])
    gateway=FixtureGateway(tmp_path)
    client.app.state.fieldkg_semantics.gateway=gateway
    return client,db,field,other,track,build,gateway


def create(client,field,build,key='semantic-request-original'):
    row=next(b for b in get_field(client,field)['builds'] if b['build_id']==build)
    body={'request_id':key,'field_id':field,'build_id':build,'expected_context_sha256':row['context_sha256'],'confirmed':True}
    response=client.post('/api/catalog/fieldkg-semantic-runs',json=body)
    assert response.status_code==201,response.text
    return response.json(),body


def advance(client,field,run):
    response=client.post(f"/api/catalog/fields/{field}/semantic-runs/{run['run_id']}/advance",json={})
    assert response.status_code==200,response.text
    return response.json()


def objects(client,field):
    return get_field(client,field)['semantic_objects']


def review(client,field,obj,decision='ACCEPTED'):
    body={'request_id':'review-'+obj['object_id'],'field_id':field,'expected_context_sha256':obj['context_sha256'],
          'decision':decision,'rationale':'Software fixture source review, not scientific approval','confirmed':True}
    response=client.post(f"/api/catalog/fieldkg-semantic-objects/{obj['object_id']}/review",json=body)
    assert response.status_code==200,response.text
    return response.json(),body


def test_extract_all_seven_types_keeps_locations_and_scientific_state_distinct(setup):
    client,db,field,_,_,build,_=setup
    before={name:None for name in ['research_nodes','decisions','approval_grants']}
    with sqlite3.connect(db) as conn:
        before={name:conn.execute('SELECT * FROM '+name).fetchall() for name in before}
    run,_=create(client,field,build)
    result=advance(client,field,run)
    assert result['status']=='COMPLETED'
    assert {o['kind'] for o in objects(client,field)}==set(KINDS)
    for obj in objects(client,field):
        assert obj['status']=='PROPOSED' and not obj['scientific_approval']
        ref=obj['references'][0]
        assert ref['quote']==ref['original_text'] and ref['unit_digest']
        assert ref['location']['page_idx']==3 and ref['source']['paper_version_id']
        assert ref['source']['file_version_id'] is None
    with sqlite3.connect(db) as conn:
        assert before=={name:conn.execute('SELECT * FROM '+name).fetchall() for name in before}


def test_request_retry_is_same_original_and_conflicting_content_rejected(setup):
    client,db,field,other,_,build,_=setup
    run,body=create(client,field,build)
    assert client.post('/api/catalog/fieldkg-semantic-runs',json=body).json()==run
    before=db.read_bytes()
    assert client.post('/api/catalog/fieldkg-semantic-runs',json={**body,'field_id':other}).status_code==409
    assert db.read_bytes()==before


def test_waiting_run_and_duplicate_advance_keep_one_interpretation_set(setup):
    client,_db,field,_,_,build,gateway=setup
    gateway.pending=True
    run,_=create(client,field,build)
    waiting=advance(client,field,run)
    assert waiting['status']=='WAITING' and waiting['router_run_id']=='fixture_semantic_run'
    assert not objects(client,field)
    gateway.pending=False
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:advance(client,field,run),range(2)))
    assert all(r['status']=='COMPLETED' for r in results)
    assert len(objects(client,field))==7 and len(set(gateway.calls))==1
    count=len(gateway.calls)
    assert advance(client,field,run)['status']=='COMPLETED' and len(gateway.calls)==count


@pytest.mark.parametrize('defect',['bad_quote','missing_unit'])
def test_invalid_model_output_is_retained_without_publishing_objects(setup,defect):
    client,_,field,_,_,build,gateway=setup
    setattr(gateway,defect,True)
    run,_=create(client,field,build)
    failed=advance(client,field,run)
    assert failed['status']=='FAILED' and failed['result'][0]['valid'] is False
    assert failed['result'][0]['output']['_contract']['actual_model']=='software-fixture'
    assert not objects(client,field)


def test_source_change_after_request_retains_old_output_without_current_publication(setup):
    client,db,field,_,_,build,_=setup
    run,_=create(client,field,build)
    old=run['input']['sources'][0]['units'][0]['raw_text']
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE skeleton_units SET raw_text='Changed source' WHERE unit_id=?",(run['input']['sources'][0]['units'][0]['unit_id'],))
    stale=advance(client,field,run)
    assert stale['status']=='STALE' and stale['input']['sources'][0]['units'][0]['raw_text']==old
    assert stale['result'] and not objects(client,field)


def test_review_is_idempotent_and_frozen_snapshot_and_chat_keep_original_sources(setup):
    client,db,field,other,track,build,_=setup
    run,_=create(client,field,build);advance(client,field,run)
    for obj in objects(client,field):
        result,body=review(client,field,obj)
        assert client.post(f"/api/catalog/fieldkg-semantic-objects/{obj['object_id']}/review",json=body).json()==result
    review_all(client,field,build)
    sealed=seal(client,field,build)
    fixed=get_field(client,field,sealed['object_id'])['selected_snapshot']
    assert fixed['members_match'] and len(fixed['frozen_semantic_objects'])==7
    obj=fixed['frozen_semantic_objects'][0]
    target={'module':'FIELDKG','field_id':field,'object_kind':'semantic','object_id':obj['object_id'],'snapshot_id':sealed['object_id']}
    context=client.post('/api/research/discussion/context',json=target)
    assert context.status_code==200,context.text
    original=context.json()
    assert obj['references'][0]['quote'] in original['object_text']
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE skeleton_units SET raw_text='Later Living text'")
    assert client.post('/api/research/discussion/context',json=target).json()==original
    assert client.post('/api/research/discussion/context',json={**target,'field_id':other}).status_code in {404,410}
    relation={**target,'object_kind':'relationship','object_id':json.dumps(['semantic-source',obj['object_id']+'|0'])}
    selected=client.post('/api/research/discussion/context',json=relation)
    assert selected.status_code==200 and selected.json()['object_text']==obj['references'][0]['quote']
    assert client.post('/api/research/discussion/context',json={**relation,'object_id':json.dumps(['semantic-source',obj['object_id']+'|99'])}).status_code==404
    assert track


def test_unreviewed_objects_block_sealing_and_abandoned_run_preserves_records(setup):
    client,db,field,_,_,build,gateway=setup
    gateway.pending=True;run,_=create(client,field,build);waiting=advance(client,field,run)
    body={'request_id':'abandon-semantic-original','field_id':field,'expected_updated_at':waiting['updated_at'],
          'rationale':'Explicitly retain and end this incomplete software extraction','confirmed':True}
    endpoint=f"/api/catalog/fields/{field}/semantic-runs/{run['run_id']}/abandon"
    result=client.post(endpoint,json=body)
    assert result.status_code==200,result.text
    assert result.json()['run']['status']=='ABANDONED'
    before=db.read_bytes()
    assert client.post(endpoint,json=body).json()==result.json()
    assert advance(client,field,run)['status']=='ABANDONED'
    assert db.read_bytes()==before
    review_all(client,field,build)
    assert seal(client,field,build)['snapshot']['status']=='SEALED'


def test_semantic_source_windows_cover_every_unit_and_do_not_silently_truncate(setup):
    client,_,field,_,_,build,_=setup
    sources=next(b for b in get_field(client,field)['builds'] if b['build_id']==build)['sources']
    windows=source_windows(sources)
    assert {u['unit_id'] for w in windows for u in w['units']}=={u['unit_id'] for s in sources for u in s['units']}
    with pytest.raises(WorkspaceError,match='exceeds'):
        source_windows([{**sources[0],'units':[{**sources[0]['units'][0],'raw_text':'x'*30000}]}])


def test_debate_or_merger_cannot_invent_a_second_paper(setup):
    client,_,field,_,_,build,gateway=setup
    sources=next(b for b in get_field(client,field)['builds'] if b['build_id']==build)['sources']
    window=source_windows(sources)[0]
    raw=gateway.analyze_for_operation('fieldkg_semantics',window,'fixture-operation')
    debate=next(o for o in raw['objects'] if o['kind']=='DEBATE')
    debate['references'][1]=dict(debate['references'][0],role='CONTRADICTS')
    with pytest.raises(ValueError,match='different papers'):
        validate_output(raw,window,sources)


def test_schema_upgrade_preserves_all_preexisting_rows_and_stable_reinitialization(setup):
    client,db,_,_,_,_,_=setup
    before=hashlib.sha256(db.read_bytes()).hexdigest()
    TrackFirstService(db.parent.parent)
    assert hashlib.sha256(db.read_bytes()).hexdigest()==before
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT version FROM schema_version WHERE component='catalog'").fetchone()[0]==CATALOG_VERSION
    assert client.get('/api/catalog/summary').status_code==200


def test_repeated_quote_requires_explicit_original_position(setup):
    client,_,field,_,_,build,gateway=setup
    sources=next(b for b in get_field(client,field)['builds'] if b['build_id']==build)['sources']
    unit=sources[0]['units'][0]
    unit['raw_text']='Repeat. Other. Repeat.'
    window=source_windows(sources)[0]
    raw=gateway.analyze_for_operation('fieldkg_semantics',window,'fixture-operation')
    raw['objects']=raw['objects'][:1]
    raw['objects'][0]['references'][0]['quote']='Repeat.'
    with pytest.raises(ValueError,match='Repeated'):
        validate_output(raw,window,sources)
    raw['objects'][0]['references'][0].update(start=15,end=22)
    result=validate_output(raw,window,sources)
    assert result[0]['references'][0]['location']['start']==15
    raw['objects'][0]['references'][0]['end']=21
    with pytest.raises(ValueError,match='offsets'):
        validate_output(raw,window,sources)


def test_late_result_after_explicit_abandonment_keeps_output_without_objects(setup):
    client,_,field,_,_,build,gateway=setup
    started=Event();release=Event();original=gateway.analyze_for_operation
    def delayed(task,payload,operation):
        started.set();assert release.wait(10)
        return original(task,payload,operation)
    gateway.analyze_for_operation=delayed
    run,_=create(client,field,build)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(advance,client,field,run)
        assert started.wait(10)
        body={'request_id':'abandon-late-output','field_id':field,'expected_updated_at':run['updated_at'],
              'rationale':'End original extraction before the late response is applied','confirmed':True}
        response=client.post(f"/api/catalog/fields/{field}/semantic-runs/{run['run_id']}/abandon",json=body)
        assert response.status_code==200,response.text
        release.set();late=future.result()
    assert late['status']=='ABANDONED' and late['result'][0]['publication']=='ABANDONED'
    assert late['result'][0]['output']['_contract']['actual_model']=='software-fixture'
    assert not objects(client,field)
