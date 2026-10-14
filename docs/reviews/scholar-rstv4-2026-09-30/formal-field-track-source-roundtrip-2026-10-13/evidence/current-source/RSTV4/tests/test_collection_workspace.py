from __future__ import annotations

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rstv4.acquisition import AcquisitionService, normalize_doi
from rstv4.acquisition_worker import AcquisitionWorker
from rstv4.catalog_web import create_app
from rstv4.collection_inputs import bibtex_records
from rstv4.database import CATALOG_VERSION, initialize_catalog
from rstv4.models import CollectionCreateInput


def setup(root: Path):
    db = root / "data/catalog.db"
    initialize_catalog(db)
    with closing(sqlite3.connect(db)) as conn, conn:
        for field in ["f1", "f2"]:
            conn.execute("INSERT INTO research_fields VALUES(?,?,?,?,?,?)",
                         (field, field, field, None, "now", "now"))
        for topic in ["t1", "t2"]:
            conn.execute("INSERT INTO topics VALUES(?,?,?,?,?,?)",
                         (topic, topic, topic, None, "now", "now"))
        conn.executemany("INSERT INTO field_topics VALUES(?,?,?)",
                         [("f1", "t1", "now"), ("f2", "t2", "now")])
        conn.execute("""INSERT INTO research_tracks
                     (track_id,field_id,primary_topic_id,title,research_type,status,
                      mapping_status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                     ("tr1", "f1", "t1", "Track", "EMPIRICAL", "ACTIVE", "MAPPED", "now", "now"))
    return db


def payload(**changes):
    return {"field_id": "f1", "topic_id": "t1", "track_id": None, "name": "Topic collection",
            "dois": ["10.1234/seed"], "idempotency_key": "workspace-collection-key", **changes}


def fingerprint(db):
    with closing(sqlite3.connect(db)) as conn, conn:
        logical = list(conn.iterdump())
    return hashlib.sha256(db.read_bytes()).hexdigest(), logical


def test_preview_is_read_only_checks_intact_pdf_and_preserves_human_branch(tmp_path: Path):
    db = setup(tmp_path)
    pdf = tmp_path / "fixture.pdf"
    pdf.write_bytes(b"%PDF-1.4 synthetic intact file fixture")
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("""INSERT INTO papers(paper_id,canonical_key,doi,normalized_title,title,
                     authors_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)""",
                     ("p1", "seed", "10.1234/seed", "seed", "Seed", "[]", "now", "now"))
        conn.execute("INSERT INTO source_file_versions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     ("file", "p1", hashlib.sha256(pdf.read_bytes()).hexdigest(), pdf.stat().st_size,
                      "application/pdf", str(pdf), "TEST", None, "NEEDS_REVIEW", "{}", "now"))
    with TestClient(create_app(tmp_path)) as client:
        before = fingerprint(db)
        preview = client.post("/api/catalog/collections/preview", json=payload())
        assert preview.status_code == 200
        assert preview.json()["counts"]["catalog_papers"] == 1
        assert preview.json()["counts"]["needs_review"] == 1
        assert preview.json()["counts"]["reusable_pdfs"] == 0
        assert preview.json()["creates_jobs"] is False
        assert fingerprint(db) == before
        with closing(sqlite3.connect(db)) as conn, conn:
            conn.execute("UPDATE source_file_versions SET identity_status='VERIFIED'")
        assert client.post("/api/catalog/collections/preview", json=payload()).json()["counts"]["reusable_pdfs"] == 1
        pdf.write_bytes(pdf.read_bytes() + b"changed")
        before = fingerprint(db)
        assert client.post("/api/catalog/collections/preview", json=payload()).json()["counts"]["reusable_pdfs"] == 0
        assert fingerprint(db) == before


def test_mixed_input_dedup_start_is_atomic_exactly_idempotent_and_retains_raw_input(tmp_path: Path):
    db = setup(tmp_path)
    body = payload(dois=["10.1234/seed", "https://doi.org/10.1234/SEED"],
                   bibtex='@article(x, title={Nested {title}}, doi={10.1234/seed}, year=2026)',
                   queries=["topic query", "topic query"])
    with TestClient(create_app(tmp_path)) as client:
        preview = client.post("/api/catalog/collections/preview", json=body).json()
        assert preview["counts"]["duplicate_inputs"] == 3
        assert preview["counts"]["unique_seeds"] == 1
        first = client.post("/api/catalog/collections", json=body)
        assert first.status_code == 201
        collection = first.json()
        assert collection["topic_id"] == "t1" and collection["track_id"] is None
        assert collection["counts"]["jobs"] == 2 and len(collection["seeds"]) == 1
        before = fingerprint(db)
        assert client.post("/api/catalog/collections", json=body).json() == collection
        assert fingerprint(db) == before
        assert client.post("/api/catalog/collections", json={**body, "name": "Other"}).status_code == 409
        assert client.post("/api/catalog/collections", json={**body, "queries": ["changed query"]}).status_code == 409
        assert fingerprint(db) == before
        assert "Nested {title}" in collection["creation_request_json"]
        overview = client.get("/api/catalog/research-overview").json()
        assert overview["collections"][0]["topic_id"] == "t1"


@pytest.mark.parametrize("changes", [
    {"topic_id": "t2"}, {"track_id": "tr1", "field_id": "f2", "topic_id": "t2"},
    {"track_id": "tr1", "topic_id": "t2"}, {"topic_id": None},
    {"dois": ["wrong"]}, {"bibtex": "@article{broken,"},
    {"dois": [], "queries": [" "]},
])
def test_invalid_input_or_wrong_owner_creates_nothing(tmp_path: Path, changes: dict):
    db = setup(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        before = fingerprint(db)
        for route in ["/preview", ""]:
            assert client.post("/api/catalog/collections" + route, json=payload(**changes)).status_code == 422
        assert fingerprint(db) == before


def test_pure_queries_track_owner_task_pages_pause_and_observed_lease(tmp_path: Path):
    db = setup(tmp_path)
    service = AcquisitionService(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        created = client.post("/api/catalog/collections", json=payload(
            track_id="tr1", dois=[], queries=["query one", "query two"])).json()
        collection_id = created["collection_id"]
        url = f"/api/catalog/collections/{collection_id}"
        assert created["topic_id"] == "t1" and created["counts"]["jobs"] == 2
        assert client.post(url + "/pause", json={"expected_revision": 1}).status_code == 200
        assert service.claim_job("fixture-worker", ["NETWORK"]) is None
        assert client.post(url + "/resume", json={"expected_revision": 1}).status_code == 409
        assert client.post(url + "/resume", json={"expected_revision": 2}).status_code == 200
        claimed = service.claim_job("fixture-worker", ["NETWORK"])
        before = fingerprint(db)
        page1 = client.get(url + "?limit=1").json()
        page2 = client.get(url + "?limit=1&offset=1").json()
        jobs = page1["jobs"] + page2["jobs"]
        assert len({job["job_id"] for job in jobs}) == 2
        running = next(job for job in jobs if job["job_id"] == claimed["job_id"])
        assert running["lease_state"] == "OBSERVED_ACTIVE"
        assert page1["recent_attempts"][0]["worker_id"] == "fixture-worker"
        assert page1["worker_observation"] == "JOB_LEASES_ONLY"
        assert fingerprint(db) == before


def test_retry_is_bound_to_owner_fencing_status_time_and_never_confirms_human_review(tmp_path: Path):
    db = setup(tmp_path)
    service = AcquisitionService(tmp_path)
    collection = service.create_collection(CollectionCreateInput(**payload()))
    job = service.claim_job("fixture-worker", ["NETWORK"])
    failed = service.fail_job(job["job_id"], "fixture-worker", job["fencing_token"],
                              error_code="TEST_FAIL", detail="Fixture failure")
    url = f"/api/catalog/collections/{collection['collection_id']}/jobs/{job['job_id']}/retry"
    body = {"expected_fencing_token": failed["fencing_token"], "expected_status": failed["status"],
            "expected_updated_at": failed["updated_at"]}
    with TestClient(create_app(tmp_path)) as client:
        before = fingerprint(db)
        assert client.post(url.replace(collection["collection_id"], "other"), json=body).status_code == 404
        assert client.post(url, json={**body, "expected_updated_at": "old"}).status_code == 409
        assert client.post(url, json={**body, "expected_fencing_token": 0}).status_code == 409
        assert fingerprint(db) == before
        retried = client.post(url, json=body)
        assert retried.status_code == 200 and retried.json()["status"] == "READY"
        assert client.post(url, json=body).status_code == 409
        human = service.claim_job("fixture-worker", ["NETWORK"])
        service.defer_job(human["job_id"], "fixture-worker", human["fencing_token"],
                          status="NEEDS_HUMAN", error_code="REVIEW", detail="Identity review required",
                          retry_after_seconds=86400)
        before = fingerprint(db)
        assert client.post(url, json={**body, "expected_status": "NEEDS_HUMAN"}).status_code == 422
        assert fingerprint(db) == before


def test_bibtex_preserves_common_literal_fields_and_rejects_incomplete_or_macro_input():
    assert normalize_doi('https://doi.org/10.1234/seed(1)') == '10.1234/seed(1)'
    assert normalize_doi('DOI: 10.1234/seed).') == '10.1234/seed'
    record = bibtex_records('@article(x, title={A {nested} title}, author="Doe, Jane", year=2026)')[0]
    assert record["title"] == "A {nested} title" and record["year"] == "2026"
    for invalid in ['@article{x,title={A}', '@article{x,title=macro}', '@article{x,title="A" year=2026}']:
        with pytest.raises(ValueError):
            bibtex_records(invalid)


def test_existing_catalog_identity_and_pdf_are_reused_without_network_or_metadata_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    db = setup(tmp_path)
    service = AcquisitionService(tmp_path)
    pdf = tmp_path / "existing.pdf"
    pdf.write_bytes(b"%PDF-1.4 synthetic reuse fixture; no scientific quality approval")
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("""INSERT INTO papers(paper_id,canonical_key,doi,normalized_title,title,
                     authors_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)""",
                     ("p1", "doi:10.1234/seed", "10.1234/seed", "original", "Original", "[]", "old", "old"))
        conn.execute("INSERT INTO source_file_versions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     ("file", "p1", hashlib.sha256(pdf.read_bytes()).hexdigest(), pdf.stat().st_size,
                      "application/pdf", str(pdf), "TEST", None, "VERIFIED", "{}", "old"))
        before = conn.execute("SELECT * FROM papers").fetchall()
    collection = service.create_collection(CollectionCreateInput(**payload()))
    monkeypatch.setattr("rstv4.acquisition_worker.resolve_doi", lambda *_: pytest.fail("Existing DOI must not be fetched again"))
    worker = AcquisitionWorker(tmp_path, "network", worker_id="reuse-fixture")
    assert worker.run_once()["status"] == "SUCCEEDED"
    second = worker.run_once()
    assert second["status"] == "SUCCEEDED"
    with closing(sqlite3.connect(db)) as conn, conn:
        assert conn.execute("SELECT * FROM papers").fetchall() == before
        assert conn.execute("SELECT COUNT(*) FROM source_file_versions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM acquisition_jobs WHERE collection_id=? AND job_type='PARSE_PDF'",
                            (collection["collection_id"],)).fetchone()[0] == 1


def test_version_six_migration_preserves_existing_collection_and_startup_is_stable(tmp_path: Path):
    db = setup(tmp_path)
    service = AcquisitionService(tmp_path)
    service.create_collection(CollectionCreateInput(**payload()))
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("ALTER TABLE collections DROP COLUMN topic_id")
        conn.execute("ALTER TABLE collections DROP COLUMN creation_request_json")
        conn.execute("UPDATE schema_version SET version=5 WHERE component='catalog'")
        before = conn.execute("SELECT * FROM collections").fetchall()
    initialize_catalog(db)
    with closing(sqlite3.connect(db)) as conn, conn:
        migrated = conn.execute("SELECT * FROM collections").fetchall()
        assert [row[:10] for row in migrated] == before
        assert all(row[10:] == (None, None) for row in migrated)
        assert conn.execute("SELECT version FROM schema_version WHERE component='catalog'").fetchone()[0] == CATALOG_VERSION
    before_bytes = fingerprint(db)
    initialize_catalog(db)
    assert fingerprint(db) == before_bytes


def test_concurrent_same_request_creates_exactly_one_collection_and_one_set_of_jobs(tmp_path: Path):
    db = setup(tmp_path)
    service = AcquisitionService(tmp_path)
    request = CollectionCreateInput(**payload(queries=['software query']))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: service.create_collection(request), range(8)))
    assert len({row['collection_id'] for row in results}) == 1
    assert all(row['counts']['jobs'] == 2 for row in results)
    with closing(sqlite3.connect(db)) as conn, conn:
        assert conn.execute('SELECT COUNT(*) FROM collections').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM acquisition_jobs').fetchone()[0] == 2


def test_exact_creation_receipt_survives_later_owner_mapping_change(tmp_path: Path):
    db = setup(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        created = client.post('/api/catalog/collections', json=payload()).json()
        with closing(sqlite3.connect(db)) as conn, conn:
            conn.execute("DELETE FROM field_topics WHERE field_id='f1' AND topic_id='t1'")
        before = fingerprint(db)
        assert client.post('/api/catalog/collections', json=payload()).json() == created
        assert client.post('/api/catalog/collections/preview', json=payload()).status_code == 422
        assert client.post('/api/catalog/collections', json=payload(idempotency_key='different-request-key')).status_code == 422
        assert fingerprint(db) == before
