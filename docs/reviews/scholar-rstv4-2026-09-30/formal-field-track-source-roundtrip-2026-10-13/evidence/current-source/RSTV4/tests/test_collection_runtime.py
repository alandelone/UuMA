from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_catalog_paper_selection import chosen, library
from test_collection_workspace import fingerprint, payload, setup

from rstv4 import collection_runtime
from rstv4.acquisition import AcquisitionService
from rstv4.acquisition_worker import AcquisitionWorker
from rstv4.catalog_web import create_app
from rstv4.models import (
    CollectionBudgetUpdateInput,
    CollectionCreateInput,
    SourceCandidate,
)
from rstv4.sources import ProviderResult


def limits(**values):
    return {"max_papers": None, "max_registered_pdf_bytes": None,
            "max_active_seconds": None, "max_task_attempts": None, **values}


def update(service, collection, budget, request_id="budget-change-test"):
    return service.update_collection_budget(collection["collection_id"], CollectionBudgetUpdateInput(
        request_id=request_id, expected_revision=collection["revision"], limits=budget,
        reason="Explicit software fixture resource change"))


def test_legacy_progress_is_read_only_and_does_not_invent_budget_or_worker(tmp_path: Path):
    db=setup(tmp_path);service=AcquisitionService(tmp_path)
    collection=service.create_collection(CollectionCreateInput.model_validate(payload()))
    # Model an existing pre-budget Collection while preserving its original task and rows.
    with closing(sqlite3.connect(db)) as conn,conn:
        conn.execute("DELETE FROM collection_budget_events WHERE collection_id=?",(collection["collection_id"],))
        conn.execute("DELETE FROM collection_runtime_state WHERE collection_id=?",(collection["collection_id"],))
    with TestClient(create_app(tmp_path)) as client:
        before=fingerprint(db)
        progress=client.get(f"/api/catalog/collections/{collection['collection_id']}/progress").json()
        assert progress["budget"]["configuration"]=="LEGACY_UNRECORDED"
        assert progress["workers"]==[] and progress["fixed_depth_cutoff"] is None
        assert progress["frontier_jobs"]==1 and progress["completion"]=="PROCESSING"
        assert fingerprint(db)==before


def test_attempt_budget_pauses_durably_preserves_frontier_and_requires_explicit_resume(tmp_path: Path):
    db=setup(tmp_path);service=AcquisitionService(tmp_path)
    collection=service.create_collection(CollectionCreateInput.model_validate(payload(
        dois=[],queries=["first query","second query"],budget=limits(max_task_attempts=1))))
    cid=collection["collection_id"]
    first=service.claim_job("worker",["NETWORK"]);assert first
    assert service.claim_job("other-worker",["NETWORK"]) is None
    progress=service.collection_progress(cid)
    assert progress["status"]=="PAUSED" and progress["completion"]=="PARTIAL_BUDGET"
    assert progress["frontier_jobs"]==2 and progress["budget"]["usage"]["task_attempts"]==1
    assert service.get_job(first["job_id"])["status"]=="RUNNING"
    with pytest.raises(ValueError,match="budget"):
        service.resume_collection(cid,progress["revision"])
    current=service.get_collection(cid)
    changed=update(service,current,limits(max_task_attempts=3))
    assert service.get_collection(cid)["status"]=="PAUSED"
    before=fingerprint(db)
    assert update(service,current,limits(max_task_attempts=3))==changed
    assert fingerprint(db)==before
    with pytest.raises(ValueError,match="request key"):
        update(service,current,limits(max_task_attempts=4))
    service.resume_collection(cid,changed["revision"])
    service.complete_job(first["job_id"],"worker",first["fencing_token"],{"software":"checkpoint"})
    assert service.claim_job("next-worker",["NETWORK"])
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM collection_budget_events").fetchone()[0]==2


def test_budget_exhausted_collection_does_not_starve_other_collection(tmp_path: Path):
    setup(tmp_path);service=AcquisitionService(tmp_path)
    limited=service.create_collection(CollectionCreateInput.model_validate(payload(
        budget=limits(max_task_attempts=1))))
    first=service.claim_job("worker",["NETWORK"])
    service.fail_job(first["job_id"],"worker",first["fencing_token"],error_code="CONTROL",detail="Software failure",retry_after_seconds=0)
    other=service.create_collection(CollectionCreateInput.model_validate(payload(idempotency_key="other-resource-collection")))
    claimed=service.claim_job("next",["NETWORK"])
    assert claimed["collection_id"]==other["collection_id"]
    assert service.get_collection(limited["collection_id"])["status"]=="PAUSED"


def test_active_time_budget_excludes_pause_and_stops_before_claim(tmp_path: Path,monkeypatch):
    setup(tmp_path);service=AcquisitionService(tmp_path)
    collection=service.create_collection(CollectionCreateInput.model_validate(payload(budget=limits(max_active_seconds=10))))
    cid=collection["collection_id"]
    with closing(sqlite3.connect(service.db_path)) as conn:
        started=datetime.fromisoformat(conn.execute("SELECT active_since FROM collection_runtime_state").fetchone()[0])
    observed=started+timedelta(seconds=12);monkeypatch.setattr(collection_runtime,"now",lambda:observed)
    assert service.claim_job("worker",["NETWORK"]) is None
    progress=service.collection_progress(cid);assert progress["budget"]["usage"]["active_seconds"]==12
    observed=started+timedelta(days=2)
    assert service.collection_progress(cid)["budget"]["usage"]["active_seconds"]==12


def test_paper_budget_preserves_raw_reference_and_resumes_without_depth_cutoff(tmp_path: Path):
    db,_=library(tmp_path);service=AcquisitionService(tmp_path)
    collection=service.create_collection(CollectionCreateInput.model_validate(chosen(budget=limits(max_papers=1))))
    cid=collection["collection_id"]
    published=service.publish_parse_result(cid,"existing","existing-file",parser_name="software",parser_version="1",
        config={},manifest={},blocks=[{"text":"Original software source body"}],
        references=[{"raw_text":"Original reference 10.1234/frontier-new","page_number":4,"location":{"section":"References","line":9}}])
    progress=service.collection_progress(cid)
    assert progress["status"]=="PAUSED" and progress["completion"]=="PARTIAL_BUDGET"
    ref=progress["references"][0]
    assert ref["resolution_status"]=="DEFERRED_BUDGET" and ref["target_paper_id"] is None
    assert ref["raw_text"]=="Original reference 10.1234/frontier-new" and ref["page_number"]==4
    assert ref["location"]=={"section":"References","line":9}
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]==2
    changed=update(service,service.get_collection(cid),limits(max_papers=2))
    service.resume_collection(cid,changed["revision"])
    after=service.collection_progress(cid)
    assert after["references"][0]["reference_entry_id"]==ref["reference_entry_id"]
    assert after["references"][0]["resolution_status"]=="RESOLVED"
    assert after["budget"]["usage"]["papers"]==2 and after["fixed_depth_cutoff"] is None
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM paper_versions WHERE paper_version_id=?",(published["paper_version_id"],)).fetchone()[0]==1


def test_unknown_reference_outside_first_page_prevents_false_complete(tmp_path: Path):
    db,_=library(tmp_path);service=AcquisitionService(tmp_path)
    collection=service.create_collection(CollectionCreateInput.model_validate(chosen()))
    cid=collection["collection_id"]
    with closing(sqlite3.connect(db)) as conn,conn:
        conn.execute("UPDATE acquisition_jobs SET status='SUCCEEDED'")
        for key,target,status in [("a","other","RESOLVED"),("z",None,"UNRESOLVED")]:
            conn.execute("INSERT INTO reference_entries VALUES(?,?,?,?,?,?,?,?,?,?)",(key,"existing","existing-file",key,1,"{}",target,status,key,"now"))
    progress=service.collection_progress(cid,reference_limit=1)
    assert progress["references"][0]["resolution_status"]=="RESOLVED"
    assert progress["unresolved_references"]==1 and progress["completion"]=="PARTIAL_UNRESOLVED_REFERENCES"


def test_independent_worker_presence_is_visible_when_no_job_is_running(tmp_path: Path):
    setup(tmp_path);service=AcquisitionService(tmp_path)
    collection=service.create_collection(CollectionCreateInput.model_validate(payload()))
    service.report_worker_presence("idle-worker","instance","parser","software-host",1234,"IDLE")
    progress=service.collection_progress(collection["collection_id"])
    assert progress["workers"][0]["observation"]=="RECENT_HEARTBEAT"
    assert progress["workers"][0]["job_id"] is None
    service.report_worker_presence("idle-worker","instance","parser","software-host",1234,"STOPPED")
    assert service.collection_progress(collection["collection_id"])["workers"][0]["observation"]=="STOPPED"


def test_run_once_reports_stopped_presence_even_with_no_claim(tmp_path: Path):
    setup(tmp_path);worker=AcquisitionWorker(tmp_path,"parser",worker_id="one-shot-parser")
    assert worker.run_once() is None
    with closing(sqlite3.connect(worker.service.db_path)) as conn:
        row=conn.execute("SELECT state,job_id FROM acquisition_worker_presence").fetchone()
    assert row==("STOPPED",None)


def test_new_collection_records_bounded_defaults_without_changing_legacy_input_shape(tmp_path: Path):
    setup(tmp_path);service=AcquisitionService(tmp_path)
    collection=service.create_collection(CollectionCreateInput.model_validate(payload()))
    progress=service.collection_progress(collection["collection_id"])
    assert progress["budget"]["limits"]=={"max_papers":500,"max_registered_pdf_bytes":10*1024**3,
                                         "max_active_seconds":86400,"max_task_attempts":None}
    assert '"budget"' not in collection["creation_request_json"]
    assert len(progress["budget"]["history"])==1


def test_shared_reference_budget_is_scoped_to_its_collection(tmp_path: Path):
    db,_=library(tmp_path);service=AcquisitionService(tmp_path)
    first=service.create_collection(CollectionCreateInput.model_validate(chosen(idempotency_key="first-reference-scope",budget=limits(max_papers=1))))
    second=service.create_collection(CollectionCreateInput.model_validate(chosen(idempotency_key="second-reference-scope",budget=limits(max_papers=3))))
    values={"parser_name":"software","parser_version":"1","config":{},"manifest":{},
            "blocks":[{"text":"Identical software source body"}],
            "references":[{"raw_text":"Shared source 10.1234/shared-frontier","page_number":3,"location":{"line":2}}]}
    service.publish_parse_result(first["collection_id"],"existing","existing-file",**values)
    service.publish_parse_result(second["collection_id"],"existing","existing-file",**values)
    a=service.collection_progress(first["collection_id"]);b=service.collection_progress(second["collection_id"])
    assert a["references"][0]["resolution_status"]=="DEFERRED_BUDGET"
    assert b["references"][0]["resolution_status"]=="RESOLVED"
    assert a["references"][0]["reference_entry_id"]==b["references"][0]["reference_entry_id"]
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM reference_entries").fetchone()[0]==1
        assert conn.execute("SELECT resolution_status FROM reference_entries").fetchone()[0]=="RESOLVED"


def test_file_budget_is_measured_once_per_digest_and_stops_before_dispatch(tmp_path: Path):
    db,pdf=library(tmp_path);service=AcquisitionService(tmp_path)
    collection=service.create_collection(CollectionCreateInput.model_validate(chosen(budget=limits(max_registered_pdf_bytes=1))))
    assert service.claim_job("worker",["MODEL_SCREEN"]) is None
    progress=service.collection_progress(collection["collection_id"])
    assert progress["completion"]=="PARTIAL_BUDGET"
    assert progress["budget"]["usage"]["registered_pdf_bytes"]==pdf.stat().st_size
    assert progress["budget"]["usage"]["task_attempts"]==0
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM source_file_versions").fetchone()[0]==1


def test_worker_heartbeat_expiry_is_not_inferred_from_queued_job(tmp_path: Path,monkeypatch):
    db=setup(tmp_path);service=AcquisitionService(tmp_path)
    collection=service.create_collection(CollectionCreateInput.model_validate(payload()))
    service.report_worker_presence("idle","instance","network","software-host",123,"IDLE")
    with closing(sqlite3.connect(db)) as conn:
        expiry=datetime.fromisoformat(conn.execute("SELECT expires_at FROM acquisition_worker_presence").fetchone()[0])
    monkeypatch.setattr(collection_runtime,"now",lambda:expiry+timedelta(seconds=1))
    progress=service.collection_progress(collection["collection_id"])
    assert progress["workers"][0]["observation"]=="HEARTBEAT_EXPIRED"
    assert progress["frontier_jobs"]==1


def test_search_budget_keeps_original_metadata_candidates_and_resumes_members(tmp_path: Path):
    db=setup(tmp_path);service=AcquisitionService(tmp_path)
    collection=service.create_collection(CollectionCreateInput.model_validate(payload(
        dois=[],queries=["software query"],budget=limits(max_papers=1))))
    cid=collection["collection_id"]
    candidates=[SourceCandidate(source_provider="software",doi=f"10.1234/search-{n}",title=f"Original candidate {n}") for n in range(3)]
    result=service.publish_collection_search_results(cid,"software query",[ProviderResult("software",candidates)])
    assert result["raw_candidates"]==3 and result["new_collection_members"]==1
    progress=service.collection_progress(cid)
    assert progress["budget_held_candidates"]==2 and progress["completion"]=="PARTIAL_BUDGET"
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM metadata_observations").fetchone()[0]==3
        assert conn.execute("SELECT COUNT(*) FROM collection_memberships").fetchone()[0]==1
    changed=update(service,service.get_collection(cid),limits(max_papers=3))
    service.resume_collection(cid,changed["revision"])
    assert service.collection_progress(cid)["budget_held_candidates"]==0
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM collection_memberships").fetchone()[0]==3


def test_resolved_seed_cannot_overrun_budget_when_two_results_publish(tmp_path: Path):
    db=setup(tmp_path);service=AcquisitionService(tmp_path)
    collection=service.create_collection(CollectionCreateInput.model_validate(payload(
        dois=["10.1234/one","10.1234/two"],budget=limits(max_papers=1))))
    first,second=collection["seeds"]
    service.resolve_seed(first["seed_id"],{"doi":"10.1234/one","title":"Original first seed"})
    service.resolve_seed(second["seed_id"],{"doi":"10.1234/two","title":"Original second seed"})
    cid=collection["collection_id"]
    assert service.collection_progress(cid)["budget_held_candidates"]==1
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM collection_memberships").fetchone()[0]==1
        assert conn.execute("SELECT COUNT(*) FROM collection_seeds WHERE paper_id IS NOT NULL").fetchone()[0]==2
        assert conn.execute("SELECT COUNT(*) FROM metadata_observations").fetchone()[0]==2
    changed=update(service,service.get_collection(cid),limits(max_papers=2))
    service.resume_collection(cid,changed["revision"])
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT DISTINCT discovery_kind FROM collection_memberships").fetchall()==[("SEED",)]
        assert conn.execute("SELECT COUNT(*) FROM acquisition_jobs WHERE job_type='LOCATE_PDF'").fetchone()[0]==2
