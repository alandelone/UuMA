"""Local browser view of the authoritative Paper Catalog and review findings."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from functools import cmp_to_key
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from pypdf import PdfReader
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .acquisition import AcquisitionService
from .catalog_annotations import (
    ReviewAnnotationInput,
    list_review_annotations,
    record_review_annotation,
)
from .catalog_review import (
    ReviewFindingInput,
    list_review_findings,
    record_review_finding,
)
from .catalog_review_workflow import (
    CatalogReviewWorkflow,
    ReviewActionInput,
    file_integrity,
)
from .collection_web import collection_router
from .fieldkg_workspace import FieldKGAction, record_fieldkg_action
from .manuscript_scientific_review import (
    ManuscriptScientificReview,
    ScientificBindingReviewInput,
)
from .research_context import DiscussionTarget
from .research_discussion_api import discussion_router
from .research_discussions import (
    AnnotationInput,
    DiscussionHistoryRequest,
    DiscussionInput,
    ResearchDiscussionService,
)
from .research_views import available_skeletons, field_workspace, track_workspace
from .research_workspace import (
    WorkspaceAction,
    WorkspaceError,
    metadata_digest,
    record_workspace_action,
)
from .scope_literature import LiteratureScope, ScopeLiteratureIndex

TEXT_FIELDS = {"title", "authors", "doi", "source", "abstract", "pdf_status",
               "parse_status", "brief_status", "skeleton_status", "review_status"}
NUMBER_FIELDS = {"published_year", "pdf_count", "verified_count", "review_count",
                 "parse_count", "reference_count", "brief_count", "skeleton_count",
                 "human_count", "collection_count"}
DATE_FIELDS = {"created_at", "updated_at"}
FILTER_FIELDS = TEXT_FIELDS | NUMBER_FIELDS | DATE_FIELDS
SORT_FIELDS = FILTER_FIELDS
FILTER_OPERATORS = {"is", "is_not", "contains", "does_not_contain", "is_empty",
                    "is_not_empty", "before", "after", "on_or_before", "on_or_after"}


class SortRule(BaseModel):
    field: str
    direction: str = "asc"


class PaperQuery(BaseModel):
    scope: LiteratureScope | None = None
    filter: dict[str, Any] | None = None
    sorts: list[SortRule] = Field(default_factory=list, max_length=5)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


@contextmanager
def _read_catalog(path: Path) -> Iterator[sqlite3.Connection]:
    if not path.is_file():
        raise HTTPException(status_code=503, detail="Catalog database is unavailable")
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN")
        yield conn
    finally:
        conn.close()


PAPER_ROWS_SQL = """
WITH files AS (
  SELECT paper_id, COUNT(*) AS pdf_count,
         SUM(CASE WHEN identity_status='VERIFIED' THEN 1 ELSE 0 END) AS verified_count,
         SUM(CASE WHEN identity_status='NEEDS_REVIEW' THEN 1 ELSE 0 END) AS review_count
  FROM source_file_versions GROUP BY paper_id
), parses AS (
  SELECT sf.paper_id, COUNT(DISTINCT pr.parse_run_id) AS parse_count
  FROM parse_runs pr JOIN source_file_versions sf ON sf.file_version_id=pr.file_version_id
  WHERE pr.status='SUCCEEDED' GROUP BY sf.paper_id
), refs AS (
  SELECT citing_paper_id AS paper_id, COUNT(*) AS reference_count
  FROM reference_entries GROUP BY citing_paper_id
), briefs AS (
  SELECT paper_id, COUNT(*) AS brief_count FROM paper_assessments
  WHERE assessment_type='QUICK_READ' AND status='COMPLETED' GROUP BY paper_id
), skeletons AS (
  SELECT pv.paper_id, COUNT(*) AS skeleton_count FROM paper_skeletons ps
  JOIN paper_versions pv ON pv.paper_version_id=ps.paper_version_id
  GROUP BY pv.paper_id
), waits AS (
  SELECT paper_id, COUNT(*) AS human_count FROM acquisition_jobs
  WHERE status='NEEDS_HUMAN' GROUP BY paper_id
), sources AS (
  SELECT paper_id, GROUP_CONCAT(DISTINCT provider) AS source
  FROM paper_sources GROUP BY paper_id
), local_roots AS (
  SELECT paper_id, GROUP_CONCAT(DISTINCT root_path) AS source
  FROM local_pdf_imports WHERE paper_id IS NOT NULL GROUP BY paper_id
), memberships AS (
  SELECT paper_id, COUNT(*) AS collection_count
  FROM collection_memberships GROUP BY paper_id
)
SELECT p.paper_id, p.title, p.authors_json, p.published_year, p.doi,
       p.created_at, p.updated_at, p.abstract,
       COALESCE(f.pdf_count,0) AS pdf_count,
       COALESCE(f.verified_count,0) AS verified_count,
       COALESCE(f.review_count,0) AS review_count,
       COALESCE(pa.parse_count,0) AS parse_count,
       COALESCE(r.reference_count,0) AS reference_count,
       COALESCE(b.brief_count,0) AS brief_count,
       COALESCE(s.skeleton_count,0) AS skeleton_count,
       COALESCE(w.human_count,0) AS human_count,
       COALESCE(m.collection_count,0) AS collection_count,
       COALESCE(lr.source,src.source,'Local PDF') AS source
FROM papers p
LEFT JOIN files f ON f.paper_id=p.paper_id
LEFT JOIN parses pa ON pa.paper_id=p.paper_id
LEFT JOIN refs r ON r.paper_id=p.paper_id
LEFT JOIN briefs b ON b.paper_id=p.paper_id
LEFT JOIN skeletons s ON s.paper_id=p.paper_id
LEFT JOIN waits w ON w.paper_id=p.paper_id
LEFT JOIN sources src ON src.paper_id=p.paper_id
LEFT JOIN local_roots lr ON lr.paper_id=p.paper_id
LEFT JOIN memberships m ON m.paper_id=p.paper_id
WHERE NOT EXISTS (SELECT 1 FROM catalog_quarantine q WHERE q.paper_id=p.paper_id)
"""


def _decode_authors(raw: str) -> list[str]:
    value: Any = json.loads(raw)
    for _ in range(4):
        candidate = value[0] if isinstance(value, list) and len(value) == 1 else value
        if not isinstance(candidate, str) or not candidate.lstrip().startswith(("[", '"')):
            break
        try:
            decoded = json.loads(candidate)
        except json.JSONDecodeError:
            break
        if decoded == value:
            break
        value = decoded
    if isinstance(value, list):
        return [str(author) for author in value if author]
    return [value] if isinstance(value, str) and value else []


def _paper_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = []
    for item in conn.execute(PAPER_ROWS_SQL):
        row = dict(item)
        row["authors"] = ", ".join(_decode_authors(row.pop("authors_json")))
        row["pdf_status"] = (
            "NEEDS_REVIEW" if row["review_count"] else
            "VERIFIED" if row["verified_count"] else "NO_PDF"
        )
        row["parse_status"] = (
            "NEEDS_HUMAN" if row["human_count"] else
            "PARSED" if row["parse_count"] else "NOT_STARTED"
        )
        row["brief_status"] = "AVAILABLE" if row["brief_count"] else "NOT_STARTED"
        row["skeleton_status"] = "AVAILABLE" if row["skeleton_count"] else "NOT_STARTED"
        row["review_status"] = (
            "NEEDS_REVIEW" if row["review_count"] or row["human_count"] else "CLEAR"
        )
        rows.append(row)
    return rows


def _validate_filter(node: dict[str, Any] | None, depth: int = 0) -> int:
    if node is None:
        return 0
    if not isinstance(node, dict) or depth > 4:
        raise ValueError("Filter nesting is invalid or too deep")
    kind = node.get("type")
    if kind == "group":
        if node.get("operator") not in {"and", "or"}:
            raise ValueError("Filter group must use and or or")
        children = node.get("filters")
        if not isinstance(children, list) or not children:
            raise ValueError("Filter group needs at least one rule")
        count = sum(_validate_filter(child, depth + 1) for child in children)
        if count > 30:
            raise ValueError("Filter has too many rules")
        return count
    if kind != "rule" or node.get("field") not in FILTER_FIELDS:
        raise ValueError("Unknown filter field")
    operator = node.get("operator")
    if operator not in FILTER_OPERATORS:
        raise ValueError("Unknown filter operator")
    field = node["field"]
    if operator in {"before", "after", "on_or_before", "on_or_after"} and (
        field not in NUMBER_FIELDS | DATE_FIELDS
    ):
        raise ValueError("Ordered comparison requires a number or date")
    if operator in {"contains", "does_not_contain"} and field not in TEXT_FIELDS:
        raise ValueError("Contains requires text")
    if operator not in {"is_empty", "is_not_empty"} and node.get("value") is None:
        raise ValueError("Filter value is required")
    return 1


def _match(node: dict[str, Any] | None, row: dict[str, Any]) -> bool:
    if node is None:
        return True
    if node["type"] == "group":
        matches = (_match(child, row) for child in node["filters"])
        return all(matches) if node["operator"] == "and" else any(matches)
    value = row[node["field"]]
    expected = node.get("value")
    operator = node["operator"]
    if operator == "is_empty":
        return value is None or value == ""
    if operator == "is_not_empty":
        return value is not None and value != ""
    if node["field"] in NUMBER_FIELDS:
        try:
            value = float(value) if value is not None else None
            expected = float(expected)
        except (TypeError, ValueError) as exc:
            raise ValueError("Number filter requires a number") from exc
    else:
        value = str(value or "").casefold()
        expected = str(expected).casefold()
        if node["field"] in DATE_FIELDS and len(expected) == 10:
            value = value[:10]
    if operator == "is":
        return value == expected
    if operator == "is_not":
        return value != expected
    if operator == "contains":
        return expected in value
    if operator == "does_not_contain":
        return expected not in value
    if value is None:
        return False
    if operator == "before":
        return value < expected
    if operator == "after":
        return value > expected
    if operator == "on_or_before":
        return value <= expected
    return value >= expected


def _compare_values(a: Any, b: Any) -> int:
    if a is None and b is None:
        return 0
    if a is None:
        return 1
    if b is None:
        return -1
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return (a > b) - (a < b)
    left, right = str(a).casefold(), str(b).casefold()
    return (left > right) - (left < right)


def query_papers(rows: list[dict[str, Any]], request: PaperQuery) -> dict[str, Any]:
    _validate_filter(request.filter)
    sorts = request.sorts or [SortRule(field="updated_at", direction="desc")]
    for rule in sorts:
        if rule.field not in SORT_FIELDS or rule.direction not in {"asc", "desc"}:
            raise ValueError("Unknown sort field or direction")
    matched = [row for row in rows if _match(request.filter, row)]

    def compare(a: dict[str, Any], b: dict[str, Any]) -> int:
        for rule in sorts:
            if a[rule.field] is None or b[rule.field] is None:
                null_order = _compare_values(a[rule.field], b[rule.field])
                if null_order:
                    return null_order
            result = _compare_values(a[rule.field], b[rule.field])
            if result:
                return result if rule.direction == "asc" else -result
        return _compare_values(a["paper_id"], b["paper_id"])

    matched.sort(key=cmp_to_key(compare))
    start = (request.page - 1) * request.page_size
    return {
        "items": matched[start:start + request.page_size],
        "total": len(matched),
        "page": request.page,
        "page_size": request.page_size,
        "has_more": start + request.page_size < len(matched),
    }


def _decode_json_rows(rows: sqlite3.Cursor, *keys: str) -> list[dict[str, Any]]:
    result = []
    for item in rows:
        row = dict(item)
        for key in keys:
            if row.get(key):
                row[key.removesuffix("_json")] = json.loads(row.pop(key))
        result.append(row)
    return result


def create_app(root: str | Path | None = None) -> FastAPI:
    root_path = Path(root or os.environ.get("RSTV4_ROOT") or Path(__file__).resolve().parents[2])
    root_path = root_path.resolve()
    db_path = root_path / "data" / "catalog.db"
    page_path = Path(__file__).with_name("catalog_web.html")
    discussions = ResearchDiscussionService(root_path)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            discussions.shutdown()

    app = FastAPI(title="Paper Catalog", version="1.0", lifespan=lifespan)
    app.state.discussions = discussions
    app.include_router(discussion_router(discussions))
    acquisition = AcquisitionService(root_path)
    review_workflow = CatalogReviewWorkflow(acquisition)
    scientific_review = ManuscriptScientificReview(db_path)
    app.include_router(collection_router(acquisition))
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(page_path, media_type="text/html")

    def discussion_result(operation, *args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except WorkspaceError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/catalog/discussion/context")
    def discussion_context(target: DiscussionTarget) -> dict:
        return discussion_result(discussions.context, target)

    @app.post("/api/catalog/discussion/history")
    def discussion_history(payload: DiscussionHistoryRequest) -> dict:
        return discussion_result(discussions.history, **payload.model_dump(exclude={"target"}), target=payload.target)

    @app.post("/api/catalog/discussion/messages", status_code=202)
    def send_discussion(payload: DiscussionInput) -> dict:
        return discussion_result(discussions.submit, payload)

    @app.post("/api/catalog/discussion/annotations", status_code=201)
    def save_discussion_annotation(payload: AnnotationInput) -> dict:
        return discussion_result(discussions.annotate, payload)

    @app.get("/api/catalog/discussion/requests/{request_id}")
    def discussion_request(request_id: str, scope: str) -> dict:
        return discussion_result(discussions.request, request_id, scope)

    @app.get("/api/catalog/discussion/messages/{message_id}/context")
    def discussion_original_context(message_id: str, scope: str) -> dict:
        return discussion_result(discussions.historical_context, scope, message_id)

    @app.get("/catalog-research-overview.js")
    def overview_script() -> FileResponse:
        return FileResponse(page_path.with_name("catalog_research_overview.js"),
                            media_type="text/javascript")

    @app.get("/catalog-research-workspaces.js")
    def workspaces_script() -> FileResponse:
        return FileResponse(page_path.with_name("catalog_research_workspaces.js"),
                            media_type="text/javascript")

    @app.get("/catalog-research-chat.js")
    def research_chat_script() -> FileResponse:
        return FileResponse(page_path.with_name("catalog_research_chat.js"),
                            media_type="text/javascript")

    @app.get("/catalog-collections.js")
    def collections_script() -> FileResponse:
        return FileResponse(page_path.with_name("catalog_collections.js"), media_type="text/javascript")

    @app.get("/catalog-review-workflow.js")
    def review_workflow_script() -> FileResponse:
        return FileResponse(page_path.with_name("catalog_review_workflow.js"), media_type="text/javascript")

    @app.get("/catalog-scientific-review.js")
    def scientific_review_script() -> FileResponse:
        return FileResponse(page_path.with_name("catalog_scientific_review.js"), media_type="text/javascript")

    @app.get("/api/catalog/research/skeletons")
    def research_skeletons() -> dict[str, Any]:
        with _read_catalog(db_path) as conn:
            return {"sources": available_skeletons(conn)}

    @app.get("/api/catalog/fields/{field_id}/workspace")
    def field_view(field_id: str, snapshot: str | None = None) -> dict[str, Any]:
        try:
            with _read_catalog(db_path) as conn:
                return field_workspace(conn, field_id, snapshot)
        except WorkspaceError as error:
            raise HTTPException(status_code=error.status, detail=str(error)) from error

    @app.get("/api/catalog/tracks/{track_id}/workspace")
    def track_view(track_id: str) -> dict[str, Any]:
        try:
            with _read_catalog(db_path) as conn:
                return track_workspace(conn, track_id)
        except WorkspaceError as error:
            raise HTTPException(status_code=error.status, detail=str(error)) from error

    @app.post("/api/catalog/fieldkg-actions")
    def fieldkg_action(action: FieldKGAction) -> dict[str, Any]:
        try:
            return record_fieldkg_action(db_path, action)
        except WorkspaceError as error:
            raise HTTPException(status_code=error.status, detail=str(error)) from error

    @app.post("/api/catalog/research-actions")
    def research_action(action: WorkspaceAction) -> dict[str, Any]:
        try:
            return record_workspace_action(db_path, action)
        except WorkspaceError as error:
            raise HTTPException(status_code=error.status, detail=str(error)) from error

    @app.get("/api/catalog/summary")
    def summary() -> dict[str, int]:
        with _read_catalog(db_path) as conn:
            rows = _paper_rows(conn)
            file_cases = conn.execute(
                """SELECT COUNT(*) FROM source_file_versions sf
                   WHERE identity_status='NEEDS_REVIEW' AND NOT EXISTS(
                     SELECT 1 FROM catalog_quarantine q WHERE q.paper_id=sf.paper_id)"""
            ).fetchone()[0]
            parser_cases = conn.execute("SELECT COUNT(*) FROM acquisition_jobs j WHERE j.status='NEEDS_HUMAN' AND j.job_type='PARSE_PDF' AND NOT EXISTS(SELECT 1 FROM catalog_quarantine q WHERE q.paper_id=j.paper_id)").fetchone()[0]
        return {
            "papers": len(rows),
            "papers_with_pdf_review": sum(row["review_count"] > 0 for row in rows),
            "pdf_review_cases": file_cases,
            "parser_review_cases": parser_cases,
        }

    @app.get("/api/catalog/research-overview")
    def research_overview() -> dict[str, Any]:
        """Read the actual research hierarchy without inventing paper classifications."""
        queries = {
            "fields": "SELECT * FROM research_fields ORDER BY name,field_id",
            "topics": "SELECT * FROM topics ORDER BY name,topic_id",
            "field_topics": "SELECT field_id,topic_id FROM field_topics",
            "tracks": "SELECT * FROM research_tracks ORDER BY title,track_id",
            "questions": """SELECT node_id,track_id,statement,status FROM research_nodes
                           WHERE lower(node_type)='research_question' AND status!='SUPERSEDED'
                           ORDER BY created_at""",
            "manuscripts": """SELECT manuscript_id,track_id,title,workflow_stage,updated_at,
                                    needs_scientific_review,blocker
                             FROM manuscripts ORDER BY updated_at DESC""",
            "manuscript_questions": """SELECT mn.manuscript_id,n.node_id FROM manuscript_nodes mn
                                      JOIN research_nodes n ON n.node_id=mn.node_id
                                      WHERE lower(n.node_type)='research_question'""",
            "collections": """SELECT collection_id,field_id,topic_id,track_id,name,status,updated_at
                             FROM collections ORDER BY updated_at DESC""",
            "collection_jobs": """SELECT collection_id,status,COUNT(*) AS count,
                                 MAX(updated_at) AS latest_job_at FROM acquisition_jobs
                                 GROUP BY collection_id,status""",
        }
        with _read_catalog(db_path) as conn:
            data = {
                name: [dict(row) for row in conn.execute(query)]
                for name, query in queries.items()
            }
            for collection, kind in [("fields", "field"), ("topics", "topic"), ("tracks", "track")]:
                for row in data[collection]:
                    row["metadata_digest"] = metadata_digest(conn, kind, row)
            data["workspace_id"] = hashlib.sha256(str(db_path).encode()).hexdigest()
            data["literature_counts"] = ScopeLiteratureIndex(conn).overview_counts()
            return data

    @app.get("/api/catalog/manuscripts/{manuscript_id}/scientific-review")
    def manuscript_review_context(manuscript_id: str) -> dict:
        try:
            return scientific_review.context(manuscript_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/catalog/manuscripts/{manuscript_id}/scientific-review/proposals", status_code=201)
    def manuscript_review_propose(manuscript_id: str, payload: ScientificBindingReviewInput, request: Request) -> dict:
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            raise HTTPException(status_code=403, detail="Cross-origin scientific review changes are not allowed")
        try:
            return scientific_review.propose(manuscript_id, payload)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/catalog/manuscripts/{manuscript_id}/scientific-review/{review_id}/apply", status_code=201)
    def manuscript_review_apply(manuscript_id: str, review_id: str, request: Request) -> dict:
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            raise HTTPException(status_code=403, detail="Cross-origin scientific review changes are not allowed")
        try:
            return scientific_review.apply(manuscript_id, review_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/catalog/papers/query")
    def list_papers(request: PaperQuery) -> dict[str, Any]:
        try:
            with _read_catalog(db_path) as conn:
                papers = _paper_rows(conn)
                if request.scope is None:
                    return query_papers(papers, request)
                scoped = ScopeLiteratureIndex(conn).read(request.scope)
                by_id = {row["paper_id"]: row for row in scoped["associations"]}
                selected = [{**paper, "scope_association": by_id[paper["paper_id"]]}
                            for paper in papers if paper["paper_id"] in by_id]
                result = query_papers(selected, request)
                result["scope"] = {key: value for key, value in scoped.items()
                                   if key != "associations"}
                result["scope"]["paper_count"] = len(by_id)
                return result
        except WorkspaceError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/catalog/papers/{paper_id}")
    def get_paper(paper_id: str) -> dict[str, Any]:
        with _read_catalog(db_path) as conn:
            paper = conn.execute("SELECT * FROM papers WHERE paper_id=?", (paper_id,)).fetchone()
            if paper is None:
                raise HTTPException(status_code=404, detail="Paper not found")
            result = dict(paper)
            result["authors"] = _decode_authors(result.pop("authors_json"))
            result["catalog_status"] = "QUARANTINED" if conn.execute(
                "SELECT 1 FROM catalog_quarantine WHERE paper_id=?", (paper_id,)
            ).fetchone() else "ACTIVE"
            result["files"] = _decode_json_rows(conn.execute(
                "SELECT * FROM source_file_versions WHERE paper_id=? ORDER BY created_at DESC",
                (paper_id,),
            ), "validation_json")
            result["sources"] = _decode_json_rows(conn.execute(
                "SELECT * FROM paper_sources WHERE paper_id=? ORDER BY retrieved_at DESC",
                (paper_id,),
            ), "raw_json")
            result["parse_runs"] = _decode_json_rows(conn.execute(
                """SELECT pr.* FROM parse_runs pr JOIN source_file_versions sf
                   ON sf.file_version_id=pr.file_version_id
                   WHERE sf.paper_id=? ORDER BY pr.started_at DESC""",
                (paper_id,),
            ), "artifact_manifest_json")
            result["references"] = _decode_json_rows(conn.execute(
                "SELECT * FROM reference_entries WHERE citing_paper_id=? ORDER BY created_at",
                (paper_id,),
            ), "location_json")
            result["assessments"] = _decode_json_rows(conn.execute(
                "SELECT * FROM paper_assessments WHERE paper_id=? ORDER BY created_at DESC",
                (paper_id,),
            ), "result_json", "evidence_json")
            result["skeletons"] = [dict(row) for row in conn.execute(
                """SELECT ps.* FROM paper_skeletons ps JOIN paper_versions pv
                   ON pv.paper_version_id=ps.paper_version_id WHERE pv.paper_id=?
                   ORDER BY ps.created_at DESC""",
                (paper_id,),
            )]
            result["processing"] = [dict(row) for row in conn.execute(
                "SELECT * FROM acquisition_jobs WHERE paper_id=? ORDER BY created_at DESC",
                (paper_id,),
            )]
            from .acquisition_model_calls import list_calls
            result["model_calls"] = list_calls(conn, paper_id, include_details=False)
            result["collections"] = [dict(row) for row in conn.execute("SELECT c.collection_id,c.name,c.status,c.field_id,c.topic_id,c.track_id FROM collections c JOIN collection_memberships m ON m.collection_id=c.collection_id WHERE m.paper_id=? ORDER BY c.updated_at DESC,c.collection_id", (paper_id,))]
            return result

    @app.get("/api/catalog/papers/{paper_id}/model-calls/{call_id}")
    def acquisition_model_call(paper_id: str, call_id: str) -> dict:
        from .acquisition_model_calls import list_calls
        with _read_catalog(db_path) as conn:
            calls = list_calls(conn, paper_id, call_id=call_id)
        if not calls:
            raise HTTPException(status_code=404, detail="Model call does not belong to this paper")
        return calls[0]

    @app.get("/api/catalog/review/cases")
    def review_cases() -> list[dict[str, Any]]:
        with _read_catalog(db_path) as conn:
            files = conn.execute(
                """SELECT sf.*,p.title,p.doi FROM source_file_versions sf
                   JOIN papers p ON p.paper_id=sf.paper_id
                   WHERE sf.identity_status='NEEDS_REVIEW' AND NOT EXISTS(
                     SELECT 1 FROM catalog_quarantine q WHERE q.paper_id=sf.paper_id)
                   ORDER BY sf.created_at, sf.file_version_id"""
            )
            cases = [
                {"kind": "PDF_IDENTITY", "case_id": row["file_version_id"],
                 "paper_id": row["paper_id"], "title": row["title"], "doi": row["doi"],
                 "created_at": row["created_at"], "file_version_id": row["file_version_id"],
                 "storage_path": row["storage_path"], "detail": json.loads(row["validation_json"])}
                for row in files
            ]
            jobs = conn.execute(
                """SELECT j.*,p.title,p.doi FROM acquisition_jobs j
                   JOIN papers p ON p.paper_id=j.paper_id
                    WHERE j.status='NEEDS_HUMAN' AND j.job_type='PARSE_PDF' AND NOT EXISTS(
                     SELECT 1 FROM catalog_quarantine q WHERE q.paper_id=j.paper_id)
                   ORDER BY j.updated_at,j.job_id"""
            )
            cases.extend(
                {"kind": "PARSER", "case_id": row["job_id"],
                 "paper_id": row["paper_id"], "title": row["title"], "doi": row["doi"],
                 "created_at": row["updated_at"], "file_version_id":
                 json.loads(row["input_json"]).get("file_version_id"),
                 "storage_path": None, "detail": row["last_error_detail"]}
                for row in jobs
            )
            return cases

    @app.get("/api/catalog/review/cases/{case_id}/findings")
    def review_findings(case_id: str) -> list[dict[str, Any]]:
        return list_review_findings(db_path, case_id)

    @app.get("/api/catalog/review/cases/{case_id}/workflow")
    def review_context(case_id: str) -> dict:
        try:
            return review_workflow.context(case_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/catalog/review/cases/{case_id}/actions", status_code=201)
    def review_action(case_id: str, payload: ReviewActionInput, request: Request) -> dict:
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            raise HTTPException(status_code=403, detail="Cross-origin review changes are not allowed")
        try:
            return review_workflow.act(case_id, payload, lambda file_id, page: paper_page_text(file_id, page)["words"])
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (ValueError, sqlite3.IntegrityError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/api/catalog/review/cases/{case_id}/annotations")
    def review_annotations(case_id: str) -> list[dict[str, Any]]:
        return list_review_annotations(db_path, case_id)

    @app.post("/api/catalog/review/cases/{case_id}/annotations", status_code=201)
    def save_review_annotation(
        case_id: str, annotation: ReviewAnnotationInput, request: Request
    ) -> dict[str, Any]:
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            raise HTTPException(status_code=403, detail="Cross-origin review changes are not allowed")
        try:
            words = None
            if annotation.decision == "FOUND":
                words = paper_page_text(case_id, annotation.page_number)["words"]
            saved = record_review_annotation(db_path, case_id, annotation, words)
            with _read_catalog(db_path) as conn:
                paper = conn.execute(
                    "SELECT title,doi FROM papers WHERE paper_id=?", (saved["paper_id"],)
                ).fetchone()
            return {**saved, "catalog_title": paper["title"], "catalog_doi": paper["doi"]}
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, sqlite3.IntegrityError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/catalog/review/cases/{case_id}/findings", status_code=201)
    def save_review_finding(
        case_id: str, finding: ReviewFindingInput, request: Request
    ) -> dict[str, Any]:
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            raise HTTPException(status_code=403, detail="Cross-origin review changes are not allowed")
        try:
            return record_review_finding(db_path, case_id, finding)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/catalog/files/{file_version_id}/pdf")
    def paper_pdf(file_version_id: str) -> FileResponse:
        path = registered_pdf(file_version_id)
        return FileResponse(path, media_type="application/pdf", filename=path.name,
                            content_disposition_type="inline")

    def registered_pdf(file_version_id: str) -> Path:
        with _read_catalog(db_path) as conn:
            row = conn.execute(
                "SELECT * FROM source_file_versions WHERE file_version_id=?",
                (file_version_id,),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="PDF version not found")
        path = Path(row["storage_path"]).resolve()
        if row["mime_type"] != "application/pdf" or not path.is_file():
            raise HTTPException(status_code=410, detail="PDF file is unavailable")
        if not file_integrity(dict(row)):
            raise HTTPException(status_code=409, detail="Original PDF content changed; use a new registered file version")
        return path

    @app.get("/api/catalog/files/{file_version_id}/pdf-info")
    def paper_pdf_info(file_version_id: str) -> dict[str, Any]:
        path = registered_pdf(file_version_id)
        try:
            reader = PdfReader(path, strict=False)
            return {
                "pages": len(reader.pages),
                "page_sizes": [
                    {"width": float(page.mediabox.width),
                     "height": float(page.mediabox.height)}
                    for page in reader.pages
                ],
            }
        except Exception as exc:
            raise HTTPException(status_code=422, detail="PDF pages cannot be read") from exc

    @app.get("/api/catalog/files/{file_version_id}/pages/{page_number}.png")
    def paper_page_image(file_version_id: str, page_number: int) -> Response:
        path = registered_pdf(file_version_id)
        if page_number < 1:
            raise HTTPException(status_code=404, detail="PDF page not found")
        renderer = shutil.which("pdftoppm")
        if renderer is None:
            raise HTTPException(status_code=503, detail="PDF preview renderer is unavailable")
        try:
            pages = len(PdfReader(path, strict=False).pages)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="PDF pages cannot be read") from exc
        if page_number > pages:
            raise HTTPException(status_code=404, detail="PDF page not found")
        try:
            render = subprocess.run(
                [renderer, "-f", str(page_number), "-l", str(page_number),
                 "-scale-to", "1600", "-singlefile", "-png", str(path)],
                capture_output=True, check=False, timeout=45,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise HTTPException(status_code=503, detail="PDF preview could not be rendered") from exc
        if render.returncode != 0 or not render.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(status_code=422, detail="PDF preview could not be rendered")
        return Response(render.stdout, media_type="image/png",
                        headers={"Cache-Control": "private, max-age=3600"})

    @app.get("/api/catalog/files/{file_version_id}/pages/{page_number}/text")
    def paper_page_text(file_version_id: str, page_number: int) -> dict[str, Any]:
        path = registered_pdf(file_version_id)
        if page_number < 1:
            raise HTTPException(status_code=404, detail="PDF page not found")
        extractor = shutil.which("pdftotext")
        if extractor is None:
            raise HTTPException(status_code=503, detail="PDF text extractor is unavailable")
        try:
            pages = len(PdfReader(path, strict=False).pages)
            if page_number > pages:
                raise HTTPException(status_code=404, detail="PDF page not found")
            extracted = subprocess.run(
                [extractor, "-f", str(page_number), "-l", str(page_number),
                 "-bbox-layout", "-enc", "UTF-8", str(path), "-"],
                capture_output=True, check=False, timeout=45,
            )
        except HTTPException:
            raise
        except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="PDF text could not be extracted") from exc
        if extracted.returncode != 0:
            raise HTTPException(status_code=422, detail="PDF text could not be extracted")
        try:
            document = ET.fromstring(extracted.stdout)
            namespace = {"x": "http://www.w3.org/1999/xhtml"}
            page = document.find(".//x:page", namespace)
            if page is None:
                raise ValueError("No page in extracted PDF text")
            width, height = float(page.attrib["width"]), float(page.attrib["height"])
            words = []
            for word in page.findall(".//x:word", namespace):
                value = "".join(word.itertext()).strip()
                if not value:
                    continue
                left = float(word.attrib["xMin"])
                top = float(word.attrib["yMin"])
                right = float(word.attrib["xMax"])
                bottom = float(word.attrib["yMax"])
                words.append({"text": value, "x": left, "y": top,
                              "width": right - left, "height": bottom - top})
            return {"width": width, "height": height, "words": words}
        except (ET.ParseError, KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="PDF text layout is unavailable") from exc

    return app


def main() -> None:
    import uvicorn

    uvicorn.run("rstv4.catalog_web:create_app", factory=True, host="127.0.0.1",
                port=int(os.environ.get("RSTV4_CATALOG_PORT", "8875")), reload=False)


if __name__ == "__main__":
    main()
