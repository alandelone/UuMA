"""Local Collection input checks, durable start, and observed task controls."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from .acquisition import AcquisitionService
from .collection_inputs import prepare_inputs
from .models import (
    CollectionBudgetUpdateInput,
    CollectionCreateInput,
    CollectionScopeInput,
    CollectionTargetInput,
    DeepReadRequestInput,
    StrictModel,
)


class CollectionRevisionInput(StrictModel):
    expected_revision: int = Field(ge=1)


class CollectionRetryInput(StrictModel):
    expected_fencing_token: int = Field(ge=0)
    expected_status: Literal["RETRY_WAIT", "RESOURCE_WAIT", "FAILED_TERMINAL"]
    expected_updated_at: str = Field(min_length=1)


@contextmanager
def read_collection_db(path: Path):
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    try:
        yield conn
    finally:
        conn.close()


def collection_router(service: AcquisitionService) -> APIRouter:
    router = APIRouter(prefix="/api/catalog/collections")

    def result(operation, *args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except ValueError as error:
            message = str(error)
            status = 404 if message.startswith("Unknown") else 409 if (
                "changed" in message or "request key" in message or "retried" in message
            ) else 422
            raise HTTPException(status_code=status, detail=message) from error

    def checked(payload: CollectionCreateInput):
        if not payload.topic_id and not payload.track_id:
            raise ValueError("Choose a Topic or Track from the research overview")
        with read_collection_db(service.db_path) as conn:
            topic_id = service.collection_topic(conn, payload)
            service.selected_catalog_papers(conn, payload.paper_ids)
        return topic_id, prepare_inputs(payload.dois, payload.bibtex, payload.queries, allow_catalog_only=bool(payload.paper_ids))

    def preview(payload: CollectionCreateInput):
        topic_id, prepared = checked(payload)
        papers = []
        with read_collection_db(service.db_path) as conn:
            matched = {row["paper_id"]: row for row in service.selected_catalog_papers(conn, payload.paper_ids)}
            for seed in prepared["seeds"]:
                doi = seed["identity"].get("doi")
                if doi:
                    paper = conn.execute("SELECT * FROM papers WHERE doi=?", (doi,)).fetchone()
                    if paper is not None:
                        matched[paper["paper_id"]] = dict(paper)
            for paper in matched.values():
                reuse = False
                review = False
                quarantined = bool(conn.execute("SELECT 1 FROM catalog_quarantine WHERE paper_id=?",
                                                (paper["paper_id"],)).fetchone())
                for file in conn.execute("SELECT * FROM source_file_versions WHERE paper_id=?",
                                         (paper["paper_id"],)):
                    path = Path(file["storage_path"])
                    try:
                        intact = path.is_file() and path.stat().st_size == file["size_bytes"]
                        if intact:
                            with path.open("rb") as stream:
                                intact = hashlib.file_digest(stream, "sha256").hexdigest() == file["sha256"]
                    except OSError:
                        intact = False
                    if intact:
                        reuse |= file["identity_status"] == "VERIFIED" and not quarantined
                        review |= file["identity_status"] != "VERIFIED" or quarantined
                papers.append({"paper_id": paper["paper_id"], "title": paper["title"], "doi": paper["doi"],
                               "reusable_pdf": reuse, "needs_review": review,
                               "quarantined": quarantined})
        return {"field_id": payload.field_id, "topic_id": topic_id, "track_id": payload.track_id,
                "counts": {**prepared["counts"], "catalog_selected": len(payload.paper_ids), "catalog_papers": len(papers),
                           "reusable_pdfs": sum(p["reusable_pdf"] for p in papers),
                           "needs_review": sum(p["needs_review"] or p["quarantined"] for p in papers)},
                "matched_papers": papers, "creates_jobs": False,
                "note": "Title-only BibTeX and new papers still require identity resolution"}

    @router.get("/paper-options")
    def paper_options(field_id: str, topic_id: str | None = None, track_id: str | None = None,
                      q: str = Query(default="", max_length=300),
                      limit: int = Query(default=25, ge=1, le=100),
                      offset: int = Query(default=0, ge=0)):
        if not topic_id and not track_id:
            raise HTTPException(status_code=422, detail="Choose a Topic or Track from the research overview")
        target = CollectionTargetInput(field_id=field_id, topic_id=topic_id, track_id=track_id)
        with read_collection_db(service.db_path) as conn:
            resolved_topic = result(service.collection_topic, conn, target)
            needle = "%" + q.strip() + "%"
            where = "WHERE p.title LIKE ? OR COALESCE(p.doi,'') LIKE ? OR p.authors_json LIKE ?"
            args = (needle, needle, needle)
            total = conn.execute("SELECT COUNT(*) FROM papers p " + where, args).fetchone()[0]
            rows = conn.execute(
                "SELECT p.paper_id,p.title,p.doi,p.published_year,p.authors_json,"
                "(SELECT COUNT(*) FROM source_file_versions f WHERE f.paper_id=p.paper_id AND f.identity_status='VERIFIED') AS registered_verified_files,"
                "(SELECT COUNT(*) FROM source_file_versions f WHERE f.paper_id=p.paper_id AND f.identity_status!='VERIFIED') AS registered_review_files,"
                "EXISTS(SELECT 1 FROM catalog_quarantine x WHERE x.paper_id=p.paper_id) AS quarantined "
                "FROM papers p " + where + " ORDER BY p.normalized_title,p.paper_id LIMIT ? OFFSET ?",
                (*args, limit, offset),
            ).fetchall()
            papers = []
            for row in rows:
                item = dict(row);item["authors"] = json.loads(item.pop("authors_json"));papers.append(item)
        return {"target": {"field_id": field_id, "topic_id": resolved_topic, "track_id": track_id},
                "papers": papers, "total": total, "offset": offset, "limit": limit,
                "has_more": offset + len(papers) < total,
                "note": "File registration is shown here; input preview verifies physical PDF integrity"}

    @router.post("/preview")
    def check_inputs(payload: CollectionCreateInput):
        return result(preview, payload)

    @router.post("", status_code=201)
    def start(payload: CollectionCreateInput):
        if not payload.topic_id and not payload.track_id:
            raise HTTPException(status_code=422, detail="Choose a Topic or Track from the research overview")
        return result(service.create_collection, payload)

    @router.get("/{collection_id}")
    def details(collection_id: str, limit: int = Query(default=100, ge=1, le=500),
                offset: int = Query(default=0, ge=0)):
        with read_collection_db(service.db_path) as conn:
            row = conn.execute("SELECT * FROM collections WHERE collection_id=?", (collection_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Unknown collection")
            collection = dict(row)
            collection.pop("creation_request_json", None)
            collection["scope"] = json.loads(collection.pop("scope_json"))
            counts = [dict(row) for row in conn.execute(
                "SELECT job_type,status,COUNT(*) AS count FROM acquisition_jobs WHERE collection_id=? "
                "GROUP BY job_type,status ORDER BY job_type,status", (collection_id,))]
            jobs = [dict(row) for row in conn.execute(
                "SELECT job_id,paper_id,job_type,queue_class,status,attempts,fencing_token,"
                "lease_owner,lease_expires_at,available_at,last_error_code,last_error_detail,updated_at "
                "FROM acquisition_jobs WHERE collection_id=? ORDER BY updated_at DESC,job_id LIMIT ? OFFSET ?",
                (collection_id, limit, offset))]
            attempts = [dict(row) for row in conn.execute(
                "SELECT a.* FROM acquisition_attempts a JOIN acquisition_jobs j ON j.job_id=a.job_id "
                "WHERE j.collection_id=? ORDER BY a.started_at DESC,a.attempt_id DESC LIMIT 20",
                (collection_id,))]
            papers = conn.execute("SELECT COUNT(*) FROM collection_memberships WHERE collection_id=?",
                                  (collection_id,)).fetchone()[0]
            history = [dict(row) for row in conn.execute(
                "SELECT collection_id,name,status,updated_at FROM collections WHERE field_id=? "
                "AND track_id IS ? AND (track_id IS NOT NULL OR topic_id IS ?) ORDER BY updated_at DESC",
                (collection["field_id"], collection["track_id"], collection["topic_id"]))]
        now = datetime.now(UTC)
        for job in jobs:
            expiry = job["lease_expires_at"]
            try:
                alive = bool(expiry) and datetime.fromisoformat(expiry) > now
            except (ValueError, TypeError):
                alive = False
            job["lease_state"] = "OBSERVED_ACTIVE" if job["status"] == "RUNNING" and alive else (
                "EXPIRED" if job["status"] == "RUNNING" else "NOT_RUNNING")
        return {"collection": collection, "counts": {"papers": papers, "jobs": sum(c["count"] for c in counts)},
                "stages": counts, "jobs": jobs, "recent_attempts": attempts, "history": history,
                "offset": offset, "limit": limit, "has_more": offset + len(jobs) < sum(c["count"] for c in counts),
                "observed_at": now.isoformat(), "worker_observation": "JOB_LEASES_ONLY"}

    @router.post("/{collection_id}/pause")
    def pause(collection_id: str, payload: CollectionRevisionInput):
        return result(service.pause_collection, collection_id, payload.expected_revision)

    @router.post("/{collection_id}/resume")
    def resume(collection_id: str, payload: CollectionRevisionInput):
        return result(service.resume_collection, collection_id, payload.expected_revision)

    @router.get("/{collection_id}/progress")
    def progress(collection_id: str, reference_limit: int = Query(default=50, ge=1, le=200),
                 reference_offset: int = Query(default=0, ge=0)):
        return result(service.collection_progress, collection_id,
                      reference_limit=reference_limit, reference_offset=reference_offset)

    @router.post("/{collection_id}/budget")
    def budget(collection_id: str, payload: CollectionBudgetUpdateInput):
        return result(service.update_collection_budget, collection_id, payload)

    @router.post("/{collection_id}/deep-read", status_code=202)
    def deep_read(collection_id: str, payload: DeepReadRequestInput):
        return result(service.request_deep_read, collection_id, payload)

    @router.post("/{collection_id}/scope")
    def scope(collection_id: str, payload: CollectionScopeInput):
        return result(service.update_scope, collection_id, payload)

    @router.post("/{collection_id}/jobs/{job_id}/retry")
    def retry(collection_id: str, job_id: str, payload: CollectionRetryInput):
        job = result(service.get_job, job_id)
        if job["collection_id"] != collection_id:
            raise HTTPException(status_code=404, detail="Unknown collection job")
        return result(service.retry_step, job_id, payload.expected_fencing_token,
                      expected_status=payload.expected_status, expected_updated_at=payload.expected_updated_at)

    return router
