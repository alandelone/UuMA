from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_catalog_review_workflow import state
from test_source_review_withdrawal import dependencies
from test_writing_studio import complete_document, create_studio, wait_for_job

from rstv4.approval import capture_user_approval
from rstv4.catalog_web import create_app
from rstv4.manuscript_scientific_review import (
    ManuscriptScientificReview,
    ScientificBindingReviewInput,
    scientific_binding_stamp,
)
from rstv4.service import RevisionConflictError, RSTV4Error
from rstv4.studio import StudioService


def propose(client,context,request_id='scientific-review-request',**values):
    structure=context.get('author_structure')
    section=structure['sections'][0]['id'] if structure and structure['sections'] else None if structure else 'Introduction'
    return client.post('/api/catalog/manuscripts/ms/scientific-review/proposals',json={
        'request_id':request_id,'expected_revision':context['manuscript']['revision'],
        'expected_context_sha256':context['context_sha256'],'node_ids':['untouched'],'evidence_ids':[],
        'section_map':{section:['untouched']} if section else {},'reason':'Explicit synthetic review and complete binding replacement',**values})


def test_review_proposal_does_not_apply_without_trusted_grant_then_preserves_old_bindings(tmp_path: Path):
    service,*_=dependencies(tmp_path)
    with closing(sqlite3.connect(service.db_path)) as conn,conn:
        conn.execute("UPDATE manuscripts SET needs_scientific_review=1 WHERE manuscript_id='ms'")
    with TestClient(create_app(tmp_path)) as client:
        context=client.get('/api/catalog/manuscripts/ms/scientific-review').json()
        original=state(service.db_path)
        assert client.get('/api/catalog/manuscripts/ms/scientific-review').json()==context
        assert state(service.db_path)==original
        response=propose(client,context);assert response.status_code==201,response.text
        proposal=response.json();url='/api/catalog/manuscripts/ms/scientific-review/'+proposal['review_id']+'/apply'
        before=state(service.db_path)
        assert client.post(url).status_code==403
        assert state(service.db_path)==before
        assert capture_user_approval(tmp_path,profile='other-agent',session_id='fixture',message_id='wrong',user_message=proposal['approval_phrase']) is None
        grant=capture_user_approval(tmp_path,profile='scholar',session_id='explicit-software-fixture',message_id='actual-test-boundary-message',user_message=proposal['approval_phrase'])
        assert grant and grant['proposal_type']=='manuscript_scientific_review'
        applied=client.post(url);assert applied.status_code==201,applied.text
        event=applied.json()['event'];assert applied.json()['status']=='APPLIED'
        assert event['before']['bindings']==context['bindings']
        assert event['after']['bindings']['nodes'][0]['node_id']=='untouched'
        with closing(sqlite3.connect(service.db_path)) as conn:
            assert conn.execute("SELECT node_id FROM manuscript_nodes WHERE manuscript_id='ms'").fetchall()==[('untouched',)]
            assert conn.execute("SELECT COUNT(*) FROM manuscript_evidence WHERE manuscript_id='ms'").fetchone()[0]==0
            assert conn.execute("SELECT needs_scientific_review FROM manuscripts WHERE manuscript_id='ms'").fetchone()[0]==0
            assert conn.execute("SELECT content FROM manuscript_versions WHERE manuscript_version_id='old-version'").fetchone()[0]=='Frozen software manuscript'
            assert conn.execute('SELECT consumed_at FROM approval_grants WHERE grant_id=?',(grant['grant_id'],)).fetchone()[0]
        before=state(service.db_path);assert client.post(url).json()==applied.json();assert state(service.db_path)==before


def test_changed_source_after_proposal_rejects_before_consuming_grant(tmp_path: Path):
    service,*_=dependencies(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        context=client.get('/api/catalog/manuscripts/ms/scientific-review').json()
        proposal=propose(client,context).json()
        grant=capture_user_approval(tmp_path,profile='orchestrator',session_id='test',message_id='message',user_message=proposal['approval_phrase'])
        with closing(sqlite3.connect(service.db_path)) as conn,conn:
            conn.execute("UPDATE research_nodes SET status='STALE',revision=revision+1 WHERE node_id='untouched'")
        before=state(service.db_path)
        response=client.post('/api/catalog/manuscripts/ms/scientific-review/'+proposal['review_id']+'/apply')
        assert response.status_code==409 and state(service.db_path)==before
        with closing(sqlite3.connect(service.db_path)) as conn:
            assert conn.execute('SELECT consumed_at FROM approval_grants WHERE grant_id=?',(grant['grant_id'],)).fetchone()[0] is None
            assert conn.execute('SELECT COUNT(*) FROM manuscript_scientific_review_events').fetchone()[0]==0


def test_wrong_track_unknown_source_empty_or_changed_proposal_is_rejected(tmp_path: Path):
    service,*_=dependencies(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        context=client.get('/api/catalog/manuscripts/ms/scientific-review').json()
        for values in [{'node_ids':['missing'],'section_map':{}},{'node_ids':[],'evidence_ids':[],'section_map':{}},
                       {'evidence_ids':['missing']},{'section_map':{'Intro':['child']}}]:
            response=propose(client,context,**values);assert response.status_code in (409,422)
        proposal=propose(client,context);assert proposal.status_code==201
        before=state(service.db_path)
        assert propose(client,context,reason='Different content with same request').status_code==409
        assert state(service.db_path)==before


def test_scientific_binding_review_marks_old_generated_version_stale_without_author_edits(tmp_path: Path):
    service,*_=dependencies(tmp_path)
    studio=StudioService(tmp_path)
    before=studio.get_workspace('ms')
    with closing(sqlite3.connect(service.db_path)) as conn,conn:
        conn.execute("UPDATE studio_documents SET active_generated_version_id='old-version',last_generated_revision=revision WHERE manuscript_id='ms'")
    assert studio.get_workspace('ms')['generated_is_stale'] is False
    with TestClient(create_app(tmp_path)) as client:
        context=client.get('/api/catalog/manuscripts/ms/scientific-review').json();proposal=propose(client,context).json()
        capture_user_approval(tmp_path,profile='scholar',session_id='fixture',message_id='binding-review',user_message=proposal['approval_phrase'])
        assert client.post('/api/catalog/manuscripts/ms/scientific-review/'+proposal['review_id']+'/apply').status_code==201
    after=studio.get_workspace('ms')
    assert after['generated_is_stale'] is True
    assert after['document']==before['document'] and after['document_revision']==before['document_revision']
    assert after['active_generated_version_id']=='old-version'


def generation_fixture(root: Path):
    studio, track_id, manuscript_id = create_studio(root)
    document = complete_document(studio.get_workspace(manuscript_id))
    studio.save_document(manuscript_id, base_revision=0, operation_id='scientific-fixture-author', document=document)
    with closing(sqlite3.connect(studio.db_path)) as conn, conn:
        # Approved nodes and captured messages are isolated software controls, never production approval.
        for node in ['old-basis', 'new-basis']:
            conn.execute("INSERT INTO research_nodes VALUES(?,?,'claim','APPROVED',?,'Software fixture','{}',1,'now','now')", (node, track_id, node))
        conn.execute("INSERT INTO manuscript_nodes VALUES(?,'old-basis',NULL,1)", (manuscript_id,))
    studio.gateway.analyze = lambda task, payload: {
        'paragraph': 'The author decides the central scientific claim.',
        'sentence_mappings': [{'sentence': 0, 'thought_ids': ['thought_author_1']}],
    }
    studio._compile_artifacts = lambda job, generated: []
    return studio, manuscript_id, document


def replace_fixture_basis(studio, manuscript_id):
    review = ManuscriptScientificReview(studio.db_path)
    context = review.context(manuscript_id)
    proposal = review.propose(manuscript_id, ScientificBindingReviewInput(
        request_id='controlled-generation-binding-review',
        expected_revision=context['manuscript']['revision'], expected_context_sha256=context['context_sha256'],
        node_ids=['new-basis'], reason='Controlled complete software binding replacement',
    ))
    capture_user_approval(studio.root, profile='scholar', session_id='software-fixture-only',
                         message_id='simulated-user-message', user_message=proposal['approval_phrase'])
    return review.apply(manuscript_id, proposal['review_id'])


def test_regeneration_freezes_new_bindings_and_keeps_old_version_and_author_content(tmp_path: Path):
    studio, manuscript_id, document = generation_fixture(tmp_path)
    first = wait_for_job(studio, studio.create_job(manuscript_id, 'GENERATE', input_revision=1))
    assert first['status'] == 'SUCCEEDED', first
    old_id = studio.get_workspace(manuscript_id)['active_generated_version_id']
    old_version = studio.get_generated_version(manuscript_id, old_id)
    event = replace_fixture_basis(studio, manuscript_id)['event']
    assert studio.get_workspace(manuscript_id)['generated_is_stale'] is True
    second = wait_for_job(studio, studio.create_job(manuscript_id, 'GENERATE', input_revision=1))
    assert second['status'] == 'SUCCEEDED', second
    current = studio.get_workspace(manuscript_id)
    assert current['generated_is_stale'] is False and current['active_generated_version_id'] != old_id
    assert current['document'] == document and current['document_revision'] == 1
    assert studio.get_generated_version(manuscript_id, old_id) == old_version
    with closing(sqlite3.connect(studio.db_path)) as conn:
        conn.row_factory = sqlite3.Row
        inputs = json.loads(conn.execute('SELECT inputs_json FROM manuscript_versions WHERE manuscript_version_id=?', (current['active_generated_version_id'],)).fetchone()[0])
        assert inputs['scientific_binding'] == scientific_binding_stamp(conn, manuscript_id)
        assert inputs['scientific_binding']['event_id'] == event['event_id']


@pytest.mark.parametrize('phase', ['QUEUED', 'COMPILING'])
@pytest.mark.parametrize('change', ['WITHDRAWAL', 'REBINDING'])
def test_generation_does_not_promote_after_scientific_context_changes(tmp_path: Path, phase: str, change: str):
    studio, manuscript_id, document = generation_fixture(tmp_path)
    studio.run_job = lambda job_id: None
    job = studio.create_job(manuscript_id, 'GENERATE', input_revision=1)
    def mutate_basis():
        if change == 'REBINDING':
            replace_fixture_basis(studio, manuscript_id)
        else:
            with closing(sqlite3.connect(studio.db_path)) as conn, conn:
                conn.execute('UPDATE manuscripts SET needs_scientific_review=1 WHERE manuscript_id=?', (manuscript_id,))
    if phase == 'QUEUED':
        mutate_basis()
        studio.gateway.analyze = lambda *args: pytest.fail('Stale queued generation must stop before a model call')
    else:
        def compile_after_change(job, generated):
            mutate_basis()
            return []
        studio._compile_artifacts = compile_after_change
    with pytest.raises((RSTV4Error, RevisionConflictError), match='[Ss]cientific'):
        studio._generate(job)
    current = studio.get_workspace(manuscript_id)
    assert current['active_generated_version_id'] is None
    assert current['document'] == document and current['document_revision'] == 1
    with closing(sqlite3.connect(studio.db_path)) as conn:
        assert conn.execute('SELECT COUNT(*) FROM manuscript_versions').fetchone()[0] == 0


def test_pending_scientific_review_blocks_generation_before_job_or_model_write(tmp_path: Path):
    studio, manuscript_id, _ = generation_fixture(tmp_path)
    with closing(sqlite3.connect(studio.db_path)) as conn, conn:
        conn.execute('UPDATE manuscripts SET needs_scientific_review=1 WHERE manuscript_id=?', (manuscript_id,))
    before = state(studio.db_path)
    with pytest.raises(RSTV4Error, match='scientific dependencies'):
        studio.create_job(manuscript_id, 'GENERATE', input_revision=1)
    assert state(studio.db_path) == before
