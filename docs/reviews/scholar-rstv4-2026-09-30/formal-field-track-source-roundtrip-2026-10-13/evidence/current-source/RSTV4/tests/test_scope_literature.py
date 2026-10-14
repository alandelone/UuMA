from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_catalog_paper_selection import chosen, gateway, library
from test_collection_workspace import fingerprint
from test_fieldkg_workspace import act, review_all, seal
from test_fieldkg_workspace import setup as field_setup

from rstv4.acquisition import AcquisitionService
from rstv4.acquisition_worker import AcquisitionWorker
from rstv4.catalog_web import create_app
from rstv4.models import CollectionCreateInput


def query(client, kind="field", field="f1", object_id="f1", **values):
    response = client.post('/api/catalog/papers/query', json={
        'scope': {'kind': kind, 'field_id': field, 'object_id': object_id,
                  'include_excluded': values.pop('include_excluded', False)}, **values,
    })
    assert response.status_code == 200, response.text
    return response.json()


def collection(root, key, **changes):
    return AcquisitionService(root).create_collection(CollectionCreateInput.model_validate(
        chosen(idempotency_key='scope-literature-' + key, **changes)))


@pytest.fixture
def fieldkg_setup(tmp_path):
    return field_setup.__wrapped__(tmp_path)


def test_shared_topic_is_field_scoped_and_parent_union_deduplicates(tmp_path: Path):
    db, _ = library(tmp_path)
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("INSERT INTO field_topics VALUES('f2','t1','now')")
    one = collection(tmp_path, 'one')
    two = collection(tmp_path, 'two', track_id='tr1', paper_ids=['existing', 'other'])
    foreign = collection(tmp_path, 'foreign', field_id='f2', topic_id='t1', paper_ids=['other'])
    with TestClient(create_app(tmp_path)) as client:
        before = fingerprint(db)
        assert query(client)['total'] == 2
        topic = query(client, 'topic', object_id='t1')
        assert topic['total'] == 2
        existing = next(row for row in topic['items'] if row['paper_id'] == 'existing')
        assert {r['collection_id'] for r in existing['scope_association']['reasons']} == {one['collection_id'], two['collection_id']}
        assert existing['scope_association']['association_status'] == 'CONFIRMED'
        assert query(client, 'track', object_id='tr1')['total'] == 2
        other = query(client, 'topic', field='f2', object_id='t1')
        assert other['total'] == 1 and other['items'][0]['paper_id'] == 'other'
        assert other['items'][0]['scope_association']['reasons'][0]['collection_id'] == foreign['collection_id']
        overview = client.get('/api/catalog/research-overview').json()
        counts = {(r['kind'], r['field_id'], r['object_id']): r['paper_count'] for r in overview['literature_counts']}
        assert counts['field', 'f1', 'f1'] == 2 and counts['field', 'f2', 'f2'] == 1
        assert counts['topic', 'f1', 't1'] == 2 and counts['topic', 'f2', 't1'] == 1
        assert fingerprint(db) == before


def test_candidate_exclusion_and_stale_screening_are_distinct(tmp_path: Path):
    db, _ = library(tmp_path)
    created = collection(tmp_path, 'one')
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("UPDATE collection_memberships SET discovery_kind='REFERENCE' WHERE collection_id=?", (created['collection_id'],))
    worker = AcquisitionWorker(tmp_path, 'model', model_gateway=gateway(category='IRRELEVANT'))
    assert worker.run_once()['status'] == 'SUCCEEDED'
    with TestClient(create_app(tmp_path)) as client:
        before = fingerprint(db)
        normal = query(client)
        assert normal['total'] == 0 and normal['scope']['excluded_count'] == 1
        excluded = query(client, include_excluded=True)['items'][0]['scope_association']
        assert excluded['excluded'] and excluded['association_status'] == 'CANDIDATE'
        assert excluded['reasons'][0]['screening']['category'] == 'IRRELEVANT'
        assert fingerprint(db) == before
        with closing(sqlite3.connect(db)) as conn, conn:
            conn.execute("UPDATE papers SET abstract='Changed metadata' WHERE paper_id='existing'")
        stale = query(client)['items'][0]['scope_association']
        assert not stale['excluded'] and stale['reasons'][0]['screening'] is None
        assert stale['association_status'] == 'CANDIDATE'


def test_one_excluded_collection_does_not_remove_another_live_association(tmp_path: Path):
    library(tmp_path)
    collection(tmp_path, 'excluded')
    worker = AcquisitionWorker(tmp_path, 'model', model_gateway=gateway(category='IRRELEVANT'))
    assert worker.run_once()['status'] == 'SUCCEEDED'
    collection(tmp_path, 'kept', track_id='tr1')
    with TestClient(create_app(tmp_path)) as client:
        result = query(client)
        assert result['total'] == 1 and result['scope']['excluded_count'] == 0
        reasons = result['items'][0]['scope_association']['reasons']
        assert len(reasons) == 2 and sum(r['excluded'] for r in reasons) == 1


@pytest.mark.parametrize('scope', [
    {'kind': 'field', 'field_id': 'f1', 'object_id': 'f2'},
    {'kind': 'track', 'field_id': 'f2', 'object_id': 'tr1'},
    {'kind': 'topic', 'field_id': 'f2', 'object_id': 't1'},
    {'kind': 'question', 'field_id': 'f1', 'object_id': 'missing'},
])
def test_wrong_scope_never_falls_back_to_all_catalog(tmp_path: Path, scope: dict):
    db, _ = library(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        before = fingerprint(db)
        assert client.post('/api/catalog/papers/query', json={'scope': scope}).status_code == 404
        assert fingerprint(db) == before


def test_scoped_filter_sort_paging_and_quarantine_match_visible_count(tmp_path: Path):
    db, _ = library(tmp_path)
    collection(tmp_path, 'both', paper_ids=['existing', 'other'])
    with TestClient(create_app(tmp_path)) as client:
        first = query(client, page_size=1, sorts=[{'field': 'title', 'direction': 'asc'}])
        second = query(client, page_size=1, page=2, sorts=[{'field': 'title', 'direction': 'asc'}])
        assert first['total'] == second['total'] == 2 and first['has_more']
        assert first['items'][0]['paper_id'] != second['items'][0]['paper_id']
        filtered = query(client, filter={'type': 'rule', 'field': 'title', 'operator': 'contains', 'value': 'Other'})
        assert filtered['total'] == 1 and filtered['scope']['paper_count'] == 2
        with closing(sqlite3.connect(db)) as conn, conn:
            conn.execute("INSERT INTO catalog_quarantine VALUES('other','software exclusion','fixture','now')")
        assert query(client)['total'] == 1
        assert client.get('/api/catalog/research-overview').json()['literature_counts'][0]['paper_count'] == 1


def test_adopted_snapshot_uses_frozen_sources_and_reports_invalid_sources(fieldkg_setup):
    client, db, field, _, track, build = fieldkg_setup
    review_all(client, field, build)
    sealed = seal(client, field, build)
    context = client.get(f'/api/catalog/tracks/{track}/workspace').json()
    snapshot = sealed['snapshot']
    response = act(client, field, 'ADOPT_SNAPSHOT', 'adopt-literature', track_id=track,
                   snapshot_id=snapshot['snapshot_id'], expected_context_sha256=context['context_sha256'],
                   expected_snapshot_digest=snapshot['content_digest'])
    assert response.status_code == 200, response.text
    before = fingerprint(db)
    result = query(client, 'track', field, track)
    assert result['total'] == 1
    source = result['items'][0]['scope_association']['reasons'][0]
    assert source['kind'] == 'adopted_snapshot' and source['snapshot_id'] == snapshot['snapshot_id']
    assert fingerprint(db) == before
    with closing(sqlite3.connect(db)) as conn, conn:
        manifest = json.loads(conn.execute('SELECT manifest_json FROM fieldkg_snapshots WHERE snapshot_id=?', (snapshot['snapshot_id'],)).fetchone()[0])
        manifest['source_records'] = []
        conn.execute('UPDATE fieldkg_snapshots SET manifest_json=? WHERE snapshot_id=?', (json.dumps(manifest), snapshot['snapshot_id']))
    unavailable = query(client, 'track', field, track)
    assert unavailable['total'] == 0 and len(unavailable['scope']['unavailable_sources']) == 1
    assert query(client, 'field', field, field)['total'] == 1  # Living remains separate.
