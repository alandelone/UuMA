"""Software contracts: author hierarchy and argument edges never approve science."""
from __future__ import annotations

import json
import sqlite3
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from test_studio_templates import fixture
from test_writing_studio import complete_document, create_studio, wait_for_job

from rstv4.studio import StudioService
from rstv4.studio_api import create_app
from rstv4.studio_context import structure_object
from rstv4.studio_read_views import generated_markdown
from rstv4.studio_structure import argument_context, section_levels


def nested_fixture(root):
    service, ms, original, _, request = fixture(root)
    document = deepcopy(original)
    parent = document['sections'][0]
    child = deepcopy(document['sections'][1])
    child.update(title='Author child', parent_section_id=parent['id'])
    child['paragraphs'] = [parent['paragraphs'].pop()]
    parent['block_order'].remove(child['paragraphs'][0]['id'])
    # Move the existing second section into a real author-selected parent, preserving all IDs.
    document['sections'][1] = child
    nodes = [p for s in document['sections'] for p in s['paragraphs']]
    edge = {'id':'argument-author-edge','source_id':nodes[0]['id'],
            'target_id':nodes[-1]['intents'][0]['thoughts'][0]['id'],
            'relation':'Contrasts under the author condition','condition':'Software fixture Ω only'}
    document['argument_relations'] = [edge]
    return service, ms, original, document, request


def test_hierarchy_and_argument_save_historical_context_and_undo(tmp_path):
    service, ms, original, doc, _ = nested_fixture(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        response = client.put(f'/api/manuscripts/{ms}/document',json={
            'base_revision':1,'operation_id':'author-hierarchy-save','document':doc})
        assert response.status_code == 200, response.text
    assert service.get_workspace(ms)['document'] == doc
    title, text = structure_object(doc,'section',doc['sections'][0]['id'])
    assert title == original['sections'][0]['title'] and 'Author child' in text
    assert doc['sections'][1]['paragraphs'][0]['intents'][0]['thoughts'][0]['text'] in text
    service.save_document(ms,base_revision=2,operation_id='author-hierarchy-undo',
                          operation_kind='UNDO',document=original)
    with sqlite3.connect(service.db_path) as conn:
        row = conn.execute("SELECT before_json,after_json,is_compensating FROM studio_changes WHERE operation_id='author-hierarchy-undo'").fetchone()
        assert json.loads(row[0]) == doc and json.loads(row[1]) == original and row[2] == 1
        assert conn.execute('SELECT COUNT(*) FROM studio_model_calls').fetchone()[0] == 0
    assert service.get_workspace(ms)['document'] == original


@pytest.mark.parametrize('defect',['foreign_parent','cycle','noncontiguous','different_placement',
                                    'foreign_endpoint','self_edge','duplicate_edge_id','structural_edge_id',
                                    'empty_relation','bad_condition','bad_edge_shape','too_deep'])
def test_invalid_hierarchy_or_argument_rejects_without_any_database_write(tmp_path,defect):
    service, ms, _, doc, _ = nested_fixture(tmp_path)
    if defect == 'foreign_parent': doc['sections'][1]['parent_section_id'] = 'another-manuscript-section'
    elif defect == 'cycle': doc['sections'][0]['parent_section_id'] = doc['sections'][1]['id']
    elif defect == 'noncontiguous': doc['sections'].reverse()
    elif defect == 'different_placement': doc['sections'][1]['placement_status'] = 'UNPLACED'
    elif defect == 'foreign_endpoint': doc['argument_relations'][0]['target_id'] = 'foreign-thought'
    elif defect == 'self_edge': doc['argument_relations'][0]['target_id'] = doc['argument_relations'][0]['source_id']
    elif defect == 'duplicate_edge_id': doc['argument_relations'] *= 2
    elif defect == 'structural_edge_id': doc['argument_relations'][0]['id'] = doc['sections'][0]['id']
    elif defect == 'empty_relation': doc['argument_relations'][0]['relation'] = '   '
    elif defect == 'bad_condition': doc['argument_relations'][0]['condition'] = {'unsupported':'condition'}
    elif defect == 'bad_edge_shape': doc['argument_relations'] = ['bad edge']
    elif defect == 'too_deep':
        for i in range(5): doc['sections'].append({'id':f'deep-{i}','parent_section_id':doc['sections'][-1]['id'],'title':'deep','role':'','paragraphs':[]})
    with TestClient(create_app(tmp_path)) as client:
        before = service.db_path.read_bytes()
        response = client.put(f'/api/manuscripts/{ms}/document',json={
            'base_revision':1,'operation_id':'rejected-hierarchy','document':doc})
        assert response.status_code == 422, response.text
        assert service.db_path.read_bytes() == before


@pytest.mark.parametrize('scope',['parent','child'])
@pytest.mark.parametrize('mode',['INSERT','REPLACE'])
def test_template_section_adoption_preserves_explicit_subtree_and_argument_ids(tmp_path,scope,mode):
    service, ms, _, doc, request = nested_fixture(tmp_path)
    service.save_document(ms,base_revision=1,operation_id='author-nesting-initial',document=doc)
    target = doc['sections'][0 if scope == 'parent' else 1]
    request.update(base_revision=2,scope_type='section',scope_id=target['id'],mode=mode,replace_confirmed=mode=='REPLACE')
    result = service.apply_template(ms,request)
    adopted = result['document']
    section_levels(adopted['sections'])
    assert adopted['argument_relations'] == doc['argument_relations']
    assert all(any(p == original for s in adopted['sections'] for p in s['paragraphs'])
               for old in doc['sections'] for original in old['paragraphs'])
    if mode == 'REPLACE':
        old = next(s for s in adopted['sections'] if s['id']==target['id'])
        assert old['placement_status']=='UNPLACED'
        if scope=='child':
            assert old['unplaced_parent_section_id']==doc['sections'][0]['id']
            assert 'parent_section_id' not in old
        else:
            child=next(s for s in adopted['sections'] if s['id']==doc['sections'][1]['id'])
            assert child['placement_status']=='UNPLACED' and child['parent_section_id']==old['id']
    service.save_document(ms,base_revision=3,operation_id='nested-template-undo',document=doc,operation_kind='UNDO')
    before = service.db_path.read_bytes()
    replay = service.apply_template(ms,request)
    assert replay['document_revision']==4 and replay['document']==doc and replay['idempotent_replay']
    assert service.db_path.read_bytes()==before


def test_l2_context_freezes_full_both_endpoints_without_claiming_approval(tmp_path):
    _, _, _, doc, _ = nested_fixture(tmp_path)
    source = doc['sections'][0]['paragraphs'][0]
    edges = argument_context(doc,source)
    assert len(edges)==1 and edges[0]['origin']=='AUTHOR_ARGUMENT_RELATION'
    assert source['intents'][0]['thoughts'][0]['text'] in edges[0]['source']['author_text']
    assert edges[0]['target']['author_text']==doc['sections'][1]['paragraphs'][0]['intents'][0]['thoughts'][0]['text']
    assert edges[0]['condition']=='Software fixture Ω only'
    assert 'approval' not in edges[0] and 'scientific_decision' not in edges[0]


def test_immutable_generated_markdown_and_latex_use_true_heading_levels():
    original={'title':'Fixture','abstract':'','sections':[{'section_id':'root','title':'Root','paragraphs':[]},
              {'section_id':'child','parent_section_id':'root','section_depth':1,'title':'Child','paragraphs':[{'text':'Exact author text','formulas':[]}]}]}
    assert generated_markdown(original)=='# Fixture\n\n## Root\n\n### Child\n\nExact author text\n'
    tex=StudioService._latex(original,[])
    assert r'\section{Root}' in tex and r'\subsection{Child}' in tex
    flat=deepcopy(original)
    del flat['sections'][1]['parent_section_id'];del flat['sections'][1]['section_depth']
    assert generated_markdown(flat)=='# Fixture\n\n## Root\n\n## Child\n\nExact author text\n'


def test_actual_generation_worker_freezes_child_path_and_author_relations(tmp_path):
    service, _, ms = create_studio(tmp_path)
    doc = complete_document(service.get_workspace(ms))
    root = doc['sections'][0]
    paragraph = root['paragraphs'].pop()
    paragraph['logical_relation'] = 'Author-defined conditional sequence'
    child = {'id':'author-child','title':'Explicit author child','role':'',
             'parent_section_id':root['id'],'paragraphs':[paragraph]}
    doc['sections'].append(child)
    intent = paragraph['intents'][0]
    thought = intent['thoughts'][0]
    doc['argument_relations'] = [{'id':'author-worker-edge','source_id':intent['id'],
        'target_id':thought['id'],'relation':'Specifies','condition':'Only under author scope Ω'}]
    service.save_document(ms,base_revision=0,operation_id='worker-hierarchy',document=doc)
    captured = []
    compiled = []

    def software_gateway(task, payload):
        captured.append(deepcopy(payload))
        return {'paragraph':thought['text'],
                'sentence_mappings':[{'sentence':0,'thought_ids':[thought['id']]}]}

    def software_compile(job, generated):
        compiled.append(deepcopy(generated))
        return []

    service.gateway.analyze = software_gateway
    service._compile_artifacts = software_compile
    job = wait_for_job(service, service.create_job(ms,'GENERATE',input_revision=1))
    assert job['status']=='SUCCEEDED', job
    assert len(captured)==len(compiled)==1
    assert captured[0]['section_path']==[root['title'],child['title']]
    assert captured[0]['logical_relation']==paragraph['logical_relation']
    edge = captured[0]['argument_relations'][0]
    assert edge['origin']=='AUTHOR_ARGUMENT_RELATION'
    assert edge['source']['id']==intent['id'] and thought['text'] in edge['source']['author_text']
    assert edge['target']['author_text']==thought['text']
    assert edge['condition']==doc['argument_relations'][0]['condition']
    assert compiled[0]['argument_relations']==doc['argument_relations']
    assert compiled[0]['sections'][0]['paragraphs']==[]
    assert compiled[0]['sections'][1]['section_depth']==1
    assert service.get_workspace(ms)['document']==doc
    with sqlite3.connect(service.db_path) as conn:
        request = json.loads(conn.execute('SELECT input_json FROM studio_model_calls').fetchone()[0])
        assert request['argument_relations']==captured[0]['argument_relations']
