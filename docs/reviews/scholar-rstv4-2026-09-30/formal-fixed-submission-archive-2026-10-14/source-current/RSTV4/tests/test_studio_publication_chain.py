from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from rstv4.service import NotFoundError, RevisionConflictError, RSTV4Error
from rstv4.studio import StudioService
from rstv4.studio_api import create_app
from test_studio_submission_events import current_generated, database_state
from test_writing_studio import create_studio, wait_for_job


@pytest.fixture
def paper(tmp_path: Path):
    service, _, manuscript_id = create_studio(tmp_path)
    current_generated(service, manuscript_id)
    workspace = service.get_workspace(manuscript_id)
    service.set_stage(
        manuscript_id, 'FINALIZATION_SUBMISSION',
        expected_revision=workspace['manuscript']['revision'], reason='Software finalization',
    )
    yield service, manuscript_id, workspace['active_generated_version_id']
    service._executor.shutdown(wait=True)


def event(paper, status, **fields):
    service, manuscript_id, version_id = paper
    return service.record_submission_event(
        manuscript_id, venue=fields.pop('venue', 'Software venue'),
        round_number=fields.pop('round_number', 1), status=status,
        detail=fields.pop('detail', 'Software fixture; no external journal actions'),
        generated_version_id=fields.pop('generated_version_id', version_id), **fields,
    )


def files(paper):
    service, manuscript_id, _ = paper
    return [service.store_asset(manuscript_id, name, 'text/plain', text) for name, text in [
        ('software-final.txt', b'Author final software fixture'),
        ('software-proof.txt', b'Author checked proof software fixture'),
    ]]


def archive(paper, **fields):
    final, proof = files(paper)
    return event(paper, 'ARCHIVED', **{
        'final_asset_id': final['asset_id'], 'proof_asset_id': proof['asset_id'],
        'acknowledged': True, **fields,
    })


@pytest.mark.parametrize('route', ['stage', 'event'])
def test_current_generation_alone_does_not_authorize_publication(paper, route):
    service, manuscript_id, _ = paper
    before = database_state(service)
    with pytest.raises(RSTV4Error, match='acceptance'):
        if route == 'event':
            event(paper, 'PUBLISHED')
        else:
            workspace = service.get_workspace(manuscript_id)
            service.set_stage(manuscript_id, 'PUBLICATION',
                              expected_revision=workspace['manuscript']['revision'], reason='No acceptance')
    assert database_state(service) == before


@pytest.mark.parametrize('difference', ['venue', 'round', 'withdrawn', 'revision_requested'])
def test_acceptance_must_remain_valid_for_the_same_venue_round_and_version(paper, difference):
    service, _, _ = paper
    event(paper, 'ACCEPTED')
    fields = {}
    if difference == 'venue':
        fields['venue'] = 'Another software venue'
    elif difference == 'round':
        fields['round_number'] = 2
    else:
        event(paper, 'WITHDRAWN' if difference == 'withdrawn' else 'REVISION_REQUESTED')
    before = database_state(service)
    with pytest.raises(RSTV4Error, match='acceptance'):
        event(paper, 'PUBLISHED', **fields)
    assert database_state(service) == before


def test_explicit_version_events_are_fixed_and_old_metadata_is_not_backfilled(paper):
    service, manuscript_id, version_id = paper
    with sqlite3.connect(service.db_path) as conn:
        conn.execute('INSERT INTO submission_events VALUES(?,?,?,?,?,?,?)',
                     ('legacy-event', manuscript_id, 'Old venue', 1, 'ACCEPTED', 'Original metadata', '2000'))
    submitted = event(paper, 'SUBMITTED', operation_id='submission-round-one')
    frozen = submitted['binding']['snapshot']['generated_version']
    assert frozen['manuscript_version_id'] == version_id
    assert frozen['document_revision'] == 1
    assert frozen['template_manifest']['status'] == 'RECORDED'
    original_snapshot = submitted['binding']
    author = service.get_workspace(manuscript_id)['document']
    author['abstract'] = 'New author revision for another submission'
    service.save_document(manuscript_id, base_revision=1, operation_id='new-author-for-resubmission', document=author)
    job = wait_for_job(service, service.create_job(manuscript_id, 'GENERATE', input_revision=2))
    assert job['status'] == 'SUCCEEDED'
    current = service.get_workspace(manuscript_id)
    assert current['active_generated_version_id'] != version_id
    assert next(e for e in current['manuscript']['submissions'] if e['event_id'] == submitted['event_id'])['binding'] == original_snapshot
    assert next(e for e in current['manuscript']['submissions'] if e['event_id'] == 'legacy-event')['binding'] == {'status': 'UNBOUND'}
    event(paper, 'ACCEPTED')  # A late editorial event may explicitly describe the earlier version.
    before = database_state(service)
    with pytest.raises(RevisionConflictError, match='active'):
        event(paper, 'PUBLISHED')
    assert database_state(service) == before


def test_operation_retry_returns_exact_original_event_without_duplicate_or_revalidation(paper):
    service, manuscript_id, _ = paper
    recorded = event(paper, 'SUBMITTED', operation_id='one-submission-operation')
    author = service.get_workspace(manuscript_id)['document']
    author['abstract'] = 'New unsent author input'
    service.save_document(manuscript_id, base_revision=1, operation_id='new-unsent-author-input', document=author)
    before = database_state(service)
    assert event(paper, 'SUBMITTED', operation_id='one-submission-operation') == recorded
    assert database_state(service) == before
    with pytest.raises(RevisionConflictError, match='different request'):
        event(paper, 'SUBMITTED', operation_id='one-submission-operation', detail='Changed intent')
    assert database_state(service) == before


def test_author_checked_files_and_completion_are_fixed_and_refreshable(paper):
    service, manuscript_id, version_id = paper
    submitted = event(paper, 'SUBMITTED')
    reviewing = event(paper, 'UNDER_REVIEW')
    assert reviewing['binding']['snapshot']['parent_event_id'] == submitted['event_id']
    accepted = event(paper, 'ACCEPTED')
    published = event(paper, 'PUBLISHED')
    assert published['binding']['snapshot']['accepted_event_id'] == accepted['event_id']
    assert service.get_workspace(manuscript_id)['publication']['completion'] is None
    completed = archive(paper, operation_id='archive-complete-operation')
    current = StudioService(service.root).get_workspace(manuscript_id)
    completion = current['publication']['completion']
    assert current['workflow_stage'] == 'PUBLICATION'
    assert completion['status'] == 'CURRENT'
    assert completion['event_id'] == completed['event_id']
    assert completion['generated_version_id'] == version_id
    assert completed['binding']['snapshot']['parent_event_id'] == published['event_id']
    assert completed['binding']['snapshot']['accepted_event_id'] == accepted['event_id']
    assert len(completion['files']['proof']['sha256']) == 64
    assert len(completion['files']['final']['sha256']) == 64
    author = current['document']
    author['abstract'] = 'Later author input must not silently update the archive'
    service.save_document(manuscript_id, base_revision=1, operation_id='after-completed-archive', document=author)
    stale = service.get_workspace(manuscript_id)['publication']['completion']
    assert stale == {**completion, 'status': 'STALE'}
    assert archive(paper, operation_id='archive-complete-operation') == completed


@pytest.mark.parametrize('missing', ['ack', 'final', 'proof', 'publication'])
def test_archive_cannot_finish_from_uploads_or_stage_alone(paper, missing):
    service, manuscript_id, _ = paper
    event(paper, 'ACCEPTED')
    if missing != 'publication':
        event(paper, 'PUBLISHED')
    else:
        workspace = service.get_workspace(manuscript_id)
        service.set_stage(manuscript_id, 'PUBLICATION',
                          expected_revision=workspace['manuscript']['revision'], reason='Accepted stage')
    final, proof = files(paper)
    kwargs = {'final_asset_id': final['asset_id'], 'proof_asset_id': proof['asset_id'], 'acknowledged': True}
    if missing == 'ack':
        kwargs['acknowledged'] = False
    elif missing in {'final', 'proof'}:
        kwargs[missing + '_asset_id'] = None
    before = database_state(service)
    with pytest.raises((RSTV4Error, ValueError)):
        event(paper, 'ARCHIVED', **kwargs)
    assert database_state(service) == before
    assert service.get_workspace(manuscript_id)['publication']['completion'] is None


@pytest.mark.parametrize('damage', ['other_owner', 'tampered', 'missing'])
def test_archive_requires_owned_intact_files_and_retains_unavailable_history(paper, damage):
    service, _manuscript_id, _ = paper
    event(paper, 'ACCEPTED')
    event(paper, 'PUBLISHED')
    final, proof = files(paper)
    if damage == 'other_owner':
        _, _, other_id = create_studio(service.root)
        proof = service.store_asset(other_id, 'other.txt', 'text/plain', b'Another owner proof')
    else:
        with sqlite3.connect(service.db_path) as conn:
            stored = conn.execute('SELECT storage_path FROM studio_assets WHERE asset_id=?', (proof['asset_id'],)).fetchone()[0]
        path = Path(stored)
        if damage == 'missing':
            # Reversible test-only move preserves the original fixture file.
            path.rename(path.with_suffix('.retained'))
        else:
            path.write_bytes(b'X' * path.stat().st_size)
    before = database_state(service)
    with pytest.raises((RSTV4Error, NotFoundError)):
        event(paper, 'ARCHIVED', final_asset_id=final['asset_id'], proof_asset_id=proof['asset_id'], acknowledged=True)
    assert database_state(service) == before


def test_completed_archive_reports_unavailable_without_erasing_receipt(paper):
    service, manuscript_id, _ = paper
    event(paper, 'ACCEPTED')
    event(paper, 'PUBLISHED')
    completed = archive(paper)
    asset = completed['binding']['snapshot']['files']['proof']
    with sqlite3.connect(service.db_path) as conn:
        path = Path(conn.execute('SELECT storage_path FROM studio_assets WHERE asset_id=?', (asset['asset_id'],)).fetchone()[0])
    path.write_bytes(b'Changed proof')
    before = database_state(service)
    state = service.get_workspace(manuscript_id)
    assert state['publication']['completion']['status'] == 'UNAVAILABLE'
    assert state['publication']['completion']['files']['proof'] == asset
    assert state['manuscript']['submissions'][-1] == completed
    assert database_state(service) == before


def test_binding_insert_failure_rolls_back_event_stage_and_history(paper):
    service, _, _ = paper
    event(paper, 'ACCEPTED')
    with sqlite3.connect(service.db_path) as conn:
        conn.execute("""CREATE TRIGGER fixture_fail_binding BEFORE INSERT ON studio_submission_bindings
                        BEGIN SELECT RAISE(ABORT, 'fixture binding failure'); END""")
    before = database_state(service)
    with pytest.raises(sqlite3.IntegrityError, match='fixture binding failure'):
        event(paper, 'PUBLISHED')
    assert database_state(service) == before


def test_http_exact_request_replay_and_invalid_archive_confirmation_preserve_database(paper):
    service, manuscript_id, version_id = paper
    app = create_app(service.root)
    request = {'venue': 'Software venue', 'round_number': 1, 'status': 'SUBMITTED',
               'generated_version_id': version_id, 'operation_id': 'http-submission-fixed-request'}
    with TestClient(app) as client:
        first = client.post(f'/api/manuscripts/{manuscript_id}/submission-events', json=request)
        assert first.status_code == 201
        before = database_state(service)
        repeated = client.post(f'/api/manuscripts/{manuscript_id}/submission-events', json=request)
        assert repeated.status_code == 201 and repeated.json() == first.json()
        assert database_state(service) == before
        mismatch = client.post(f'/api/manuscripts/{manuscript_id}/submission-events',
                               json={**request, 'status': 'ACCEPTED'})
        assert mismatch.status_code == 409
        assert database_state(service) == before
        invalid = client.post(f'/api/manuscripts/{manuscript_id}/submission-events',
                              json={**request, 'status': 'ARCHIVED', 'acknowledged': 'yes'})
        assert invalid.status_code == 422
        assert database_state(service) == before


def test_migration_preserves_old_unbound_event_and_reinitialization_is_idempotent(paper):
    service, manuscript_id, _ = paper
    from rstv4.database import initialize_catalog
    with sqlite3.connect(service.db_path) as conn:
        conn.execute('INSERT INTO submission_events VALUES(?,?,?,?,?,?,?)',
                     ('unbound-before-migration', manuscript_id, 'Old venue', 1, 'ACCEPTED', 'Exact old event', '2001'))
        conn.execute('DROP TABLE studio_submission_bindings')
        conn.execute("UPDATE schema_version SET version=13 WHERE component='catalog'")
        original = tuple(conn.execute('SELECT * FROM submission_events').fetchall())
    initialize_catalog(service.db_path)
    with sqlite3.connect(service.db_path) as conn:
        assert tuple(conn.execute('SELECT * FROM submission_events').fetchall()) == original
        assert conn.execute('SELECT COUNT(*) FROM studio_submission_bindings').fetchone()[0] == 0
    before = database_state(service)
    initialize_catalog(service.db_path)
    assert database_state(service) == before
    workspace = service.get_workspace(manuscript_id)
    assert workspace['manuscript']['submissions'][-1]['binding'] == {'status': 'UNBOUND'}
    assert workspace['publication']['accepted_event_id'] is None


def test_legacy_generation_scientific_hold_invalidates_completion_without_rewriting_history(paper):
    service, manuscript_id, version_id = paper
    # Explicit legacy-generation fixture: no saved scientific binding stamp.
    import json
    with sqlite3.connect(service.db_path) as conn:
        row = conn.execute('SELECT inputs_json FROM manuscript_versions WHERE manuscript_version_id=?', (version_id,)).fetchone()
        inputs = json.loads(row[0])
        inputs.pop('scientific_binding', None)
        conn.execute('UPDATE manuscript_versions SET inputs_json=? WHERE manuscript_version_id=?',
                     (json.dumps(inputs), version_id))
    event(paper, 'ACCEPTED')
    event(paper, 'PUBLISHED')
    completed = archive(paper)
    assert service.get_workspace(manuscript_id)['publication']['completion']['status'] == 'CURRENT'
    with sqlite3.connect(service.db_path) as conn:
        conn.execute('UPDATE manuscripts SET needs_scientific_review=1 WHERE manuscript_id=?', (manuscript_id,))
    before = database_state(service)
    after = service.get_workspace(manuscript_id)
    assert after['publication']['completion']['status'] == 'STALE'
    assert after['manuscript']['submissions'][-1] == completed
    assert database_state(service) == before


def test_bound_event_original_timestamp_is_part_of_provenance(paper):
    service, manuscript_id, _ = paper
    recorded = event(paper, 'SUBMITTED')
    with sqlite3.connect(service.db_path) as conn:
        conn.execute('UPDATE submission_events SET created_at=? WHERE event_id=?', ('damaged', recorded['event_id']))
    before = database_state(service)
    with pytest.raises(RSTV4Error, match='provenance'):
        service.get_workspace(manuscript_id)
    assert database_state(service) == before
