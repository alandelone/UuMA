from __future__ import annotations

import io
import os
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .database import transaction
from .model_gateway import GatewayDeferredError
from .research_discussion_api import discussion_router
from .research_discussions import ResearchDiscussionService
from .research_workspace import WorkspaceError
from .service import NotFoundError, RevisionConflictError, RSTV4Error
from .studio import WORKFLOW_STAGES, DocumentValidationError, StudioService
from .studio_delivery import PackageUnavailableError


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreateManuscriptRequest(ApiModel):
    track_id: str
    title: str = Field(min_length=1, max_length=1000)
    scope: str | None = Field(default=None, max_length=8000)


class SaveDocumentRequest(ApiModel):
    base_revision: int = Field(ge=0)
    operation_id: str = Field(min_length=8, max_length=200)
    operation_kind: str = Field(default="EDIT", max_length=80)
    document: dict[str, Any]
    inverse: dict[str, Any] | None = None
    comment_ids: list[str] = Field(default_factory=list)


class StageRequest(ApiModel):
    stage: str
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=4000)


class ChatRequest(ApiModel):
    content: str = Field(min_length=1, max_length=12000)
    anchor_type: str = Field(min_length=1, max_length=80)
    anchor_id: str | None = None
    anchor_revision: int = Field(ge=0)
    quote: dict[str, Any] | None = None


class SuggestionDecisionRequest(ApiModel):
    suggestion_id: str
    decision_id: str = Field(min_length=8, max_length=200)
    outcome: str
    base_revision: int = Field(ge=0)
    selected_change_ids: list[str] = Field(default_factory=list, max_length=100)
    confirmed_changed_ids: list[str] = Field(default_factory=list, max_length=100)
    comment_ids: list[str] = Field(default_factory=list, max_length=100)


class JobRequest(ApiModel):
    kind: str
    input_revision: int = Field(ge=0)
    request: dict[str, Any] = Field(default_factory=dict)


class ChangeLinksRequest(ApiModel):
    request_id: str = Field(min_length=8, max_length=200)
    expected_link_revision: int = Field(ge=0, strict=True)
    comment_ids: list[str] = Field(default_factory=list, max_length=100)
    reverses_event_id: str | None = None


class ReviewRoundRequest(ApiModel):
    round_number: int = Field(ge=1)
    venue: str | None = Field(default=None, max_length=1000)
    baseline_manuscript_version_id: str | None = None
    expected_document_revision: int | None = Field(default=None, ge=0)


class CommentImportRequest(ApiModel):
    source: str = Field(default="MANUAL", max_length=200)
    # The service limits selected, nonempty opinions; excluded preview rows retain provenance.
    comments: list[dict[str, Any]]
    import_metadata: dict[str, Any] = Field(default_factory=dict)


class CommentUpdateRequest(ApiModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    edited_text: str | None = Field(default=None, max_length=30000)
    author_decision: str | None = Field(default=None, max_length=12000)
    response_text: str | None = Field(default=None, max_length=30000)
    status: str | None = Field(default=None, max_length=80)
    expected_content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ReplyAssertionRequest(ApiModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    start: int = Field(ge=0, strict=True)
    end: int = Field(ge=1, strict=True)
    text: str = Field(min_length=1, max_length=30000)
    offset_unit: str = Field(pattern=r"^utf16$")
    evidence_ids: list[str] = Field(min_length=1, max_length=100)


class ResponseReviewRequest(ApiModel):
    request_id: str = Field(min_length=8, max_length=200)
    context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: str = Field(pattern=r"^(MODIFIED|EXPLAINED_NO_CHANGE)$")
    claims: list[ReplyAssertionRequest] = Field(default_factory=list, max_length=100)
    acknowledged_all_assertions: bool = Field(strict=True)


class FindingUpdateRequest(ApiModel):
    status: str


class SubmissionEventRequest(ApiModel):
    venue: str = Field(min_length=1, max_length=500)
    round_number: int = Field(default=1, ge=1)
    status: str
    detail: str | None = Field(default=None, max_length=8000)


class TemplateAdoptionRequest(ApiModel):
    source_skeleton_id: str | None = Field(default=None, max_length=500)
    source_version: str | None = Field(default=None, max_length=200)
    adopted: dict[str, Any]


def _extract_review_text(filename: str, content_type: str, content: bytes) -> str:
    suffix = Path(filename).suffix.casefold()
    if len(content) > 10 * 1024 * 1024:
        raise ValueError("Review file exceeds the 10 MB import limit")
    if suffix in {".txt", ".md", ".markdown"} or content_type.startswith("text/"):
        return content.decode("utf-8-sig")
    if suffix == ".docx":
        from docx import Document

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                members = archive.infolist()
                if len(members) > 10_000 or sum(item.file_size for item in members) > 100 * 1024 * 1024:
                    raise ValueError("DOCX expands beyond the safe import limit")
        except zipfile.BadZipFile as exc:
            raise ValueError("Invalid DOCX review file") from exc
        document = Document(io.BytesIO(content))
        return "\n\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise ValueError("Encrypted PDF review files are not supported")
        text = "\n\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
        if not text:
            raise ValueError("The PDF has no extractable text; scanned-document OCR is out of scope")
        return text
    raise ValueError("Review import supports TXT, Markdown, DOCX, and text-based PDF")


def _split_review_comments(text: str) -> list[dict[str, Any]]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    return [
        {"text": part.strip(), "original_text": part.strip(), "include": True}
        for part in re_split_blank_lines(normalized)
        if part.strip()
    ]


def re_split_blank_lines(text: str) -> list[str]:
    import re

    return re.split(r"\n\s*\n+", text)


def create_app(root: str | Path | None = None) -> FastAPI:
    service = StudioService(root)
    discussions = ResearchDiscussionService(service.root)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        service.retry_queued_jobs()
        try:
            yield
        finally:
            discussions.shutdown()
            service._executor.shutdown(wait=False, cancel_futures=False)

    app = FastAPI(title="RSTV4 Writing Studio", version="1.0", lifespan=lifespan)
    app.state.studio = service
    app.state.discussions = discussions
    app.include_router(discussion_router(discussions))
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "If-Match", "X-Operation-Id"],
    )

    @app.exception_handler(NotFoundError)
    async def not_found_handler(_, exc: NotFoundError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"error": "not_found", "detail": str(exc)})

    @app.exception_handler(WorkspaceError)
    async def shared_discussion_handler(_, exc: WorkspaceError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=exc.status, content={"error": "discussion_error", "detail": str(exc)})

    @app.exception_handler(RevisionConflictError)
    async def conflict_handler(_, exc: RevisionConflictError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=409, content={"error": "revision_conflict", "detail": str(exc)})

    @app.exception_handler(DocumentValidationError)
    async def validation_handler(_, exc: DocumentValidationError):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=422,
            content={"error": "generation_incomplete", "detail": str(exc), "issues": exc.issues},
        )

    @app.exception_handler(GatewayDeferredError)
    async def deferred_handler(_, exc: GatewayDeferredError):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            content={"error": "agent_unavailable", "detail": str(exc), "retry_after": exc.retry_after},
        )

    @app.exception_handler(RSTV4Error)
    async def rstv4_handler(_, exc: RSTV4Error):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=422, content={"error": "studio_error", "detail": str(exc)})

    @app.exception_handler(ValueError)
    async def value_error_handler(_, exc: ValueError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=422, content={"error": "invalid_input", "detail": str(exc)})

    @app.exception_handler(TypeError)
    async def type_error_handler(_, exc: TypeError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=422, content={"error": "invalid_input", "detail": str(exc)})

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "workflow_stages": WORKFLOW_STAGES}

    @app.get("/api/tracks")
    def list_tracks() -> list[dict[str, Any]]:
        return service.list_tracks()

    @app.post("/api/manuscripts", status_code=201)
    def create_manuscript(payload: CreateManuscriptRequest) -> dict[str, Any]:
        return service.create_manuscript(payload.track_id, payload.title, payload.scope)

    @app.get("/api/manuscripts/{manuscript_id}/workspace")
    def get_workspace(manuscript_id: str) -> dict[str, Any]:
        return service.get_workspace(manuscript_id)

    @app.get("/api/manuscripts/{manuscript_id}/generated-versions/{version_id}")
    def get_generated_version(manuscript_id: str, version_id: str) -> dict[str, Any]:
        return service.get_generated_version(manuscript_id, version_id)

    @app.get("/api/manuscripts/{manuscript_id}/document-revisions/{revision}")
    def get_document_revision(manuscript_id: str, revision: int) -> dict[str, Any]:
        return service.get_document_revision(manuscript_id, revision)

    @app.get("/api/manuscripts/{manuscript_id}/model-calls")
    def list_model_calls(manuscript_id: str, job_id: str | None = None) -> list[dict[str, Any]]:
        return service.list_model_calls(manuscript_id, job_id=job_id)

    @app.get("/api/manuscripts/{manuscript_id}/changes")
    def list_changes(manuscript_id: str) -> list[dict[str, Any]]:
        return service.list_changes(manuscript_id)

    @app.post("/api/manuscripts/{manuscript_id}/changes/{change_id}/associations")
    def set_change_links(manuscript_id: str, change_id: str, payload: ChangeLinksRequest) -> dict[str, Any]:
        return service.set_change_links(manuscript_id, change_id, **payload.model_dump())

    @app.put("/api/manuscripts/{manuscript_id}/document")
    def save_document(manuscript_id: str, payload: SaveDocumentRequest) -> dict[str, Any]:
        return service.save_document(
            manuscript_id,
            base_revision=payload.base_revision,
            operation_id=payload.operation_id,
            document=payload.document,
            operation_kind=payload.operation_kind,
            inverse=payload.inverse,
            comment_ids=payload.comment_ids,
        )

    @app.post("/api/manuscripts/{manuscript_id}/stage")
    def set_stage(manuscript_id: str, payload: StageRequest) -> dict[str, Any]:
        return service.set_stage(
            manuscript_id,
            payload.stage,
            expected_revision=payload.expected_revision,
            reason=payload.reason,
        )

    @app.get("/api/manuscripts/{manuscript_id}/sources")
    def search_sources(
        manuscript_id: str,
        q: str = "",
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ) -> list[dict[str, Any]]:
        return service.search_sources(manuscript_id, q, limit=limit)

    @app.get("/api/manuscripts/{manuscript_id}/samples")
    def get_samples(
        manuscript_id: str,
        layer: str = "intent",
        anchor_id: str | None = None,
        role: str | None = None,
        intent: str | None = None,
        limit: Annotated[int, Query(ge=1, le=50)] = 12,
    ) -> list[dict[str, Any]]:
        return service.get_samples(
            manuscript_id,
            layer=layer,
            anchor_id=anchor_id,
            role=role,
            intent=intent,
            limit=limit,
        )

    @app.post("/api/manuscripts/{manuscript_id}/template-instances", status_code=201)
    def adopt_template(
        manuscript_id: str,
        payload: TemplateAdoptionRequest,
    ) -> dict[str, Any]:
        return service.adopt_template(
            manuscript_id,
            source_skeleton_id=payload.source_skeleton_id,
            source_version=payload.source_version,
            adopted=payload.adopted,
        )

    @app.post("/api/manuscripts/{manuscript_id}/assets", status_code=201)
    async def upload_asset(
        manuscript_id: str,
        file: Annotated[UploadFile, File()],
    ) -> dict[str, Any]:
        content = await file.read()
        return service.store_asset(manuscript_id, file.filename or "asset", file.content_type, content)

    @app.get("/api/assets/{asset_id}/content")
    def get_asset(asset_id: str) -> FileResponse:
        with transaction(service.db_path) as conn:
            row = conn.execute("SELECT * FROM studio_assets WHERE asset_id=?", (asset_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"Unknown Studio asset: {asset_id}")
        path = Path(row["storage_path"]).resolve()
        if service.storage_root.resolve() not in path.parents or not path.is_file():
            raise HTTPException(status_code=410, detail="Stored asset is unavailable")
        return FileResponse(path, media_type=row["media_type"], filename=row["filename"])

    @app.get("/api/manuscripts/{manuscript_id}/chat")
    def list_chat(
        manuscript_id: str,
        anchor_id: str | None = None,
        before: str | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
        anchor_type: str | None = None,
        anchor_revision: Annotated[int | None, Query(ge=0)] = None,
        generated_version_id: str | None = None,
        before_message_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return service.list_chat(
            manuscript_id, anchor_id=anchor_id, before=before, limit=limit,
            anchor_type=anchor_type, anchor_revision=anchor_revision,
            generated_version_id=generated_version_id, before_message_id=before_message_id,
        )

    @app.post("/api/manuscripts/{manuscript_id}/chat", status_code=201)
    def discuss(manuscript_id: str, payload: ChatRequest) -> dict[str, Any]:
        return service.discuss(manuscript_id, **payload.model_dump())

    @app.get("/api/manuscripts/{manuscript_id}/chat/{message_id}/context")
    def get_chat_context(manuscript_id: str, message_id: str) -> dict[str, Any]:
        return service.get_chat_context(manuscript_id, message_id)

    @app.get("/api/manuscripts/{manuscript_id}/chat/{message_id}/suggestions/{suggestion_id}/preview")
    def suggestion_preview(manuscript_id: str, message_id: str, suggestion_id: str) -> dict[str, Any]:
        return service.suggestion_preview(manuscript_id, message_id, suggestion_id)

    @app.post("/api/manuscripts/{manuscript_id}/chat/{message_id}/decisions", status_code=201)
    def decide_suggestion(manuscript_id: str, message_id: str, payload: SuggestionDecisionRequest) -> dict[str, Any]:
        return service.decide_suggestion(manuscript_id, message_id, **payload.model_dump())

    @app.post("/api/manuscripts/{manuscript_id}/jobs", status_code=202)
    def create_job(manuscript_id: str, payload: JobRequest) -> dict[str, Any]:
        return service.create_job(
            manuscript_id,
            payload.kind,
            input_revision=payload.input_revision,
            request=payload.request,
        )

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        return service.get_job(job_id)

    @app.delete("/api/jobs/{job_id}")
    def cancel_job(job_id: str) -> dict[str, Any]:
        return service.cancel_job(job_id)

    @app.get("/api/artifacts/{artifact_id}")
    def get_artifact(artifact_id: str) -> FileResponse:
        with transaction(service.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM studio_artifacts WHERE artifact_id=?", (artifact_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"Unknown Studio artifact: {artifact_id}")
        path = Path(row["storage_path"]).resolve()
        if service.storage_root.resolve() not in path.parents or not path.is_file():
            raise HTTPException(status_code=410, detail="Generated artifact is unavailable")
        try:
            service._verified_artifact_bytes(row)
        except RSTV4Error as exc:
            raise HTTPException(status_code=410, detail=str(exc)) from exc
        return FileResponse(path, filename=path.name)

    @app.get("/api/manuscripts/{manuscript_id}/packages")
    def list_submission_packages(manuscript_id: str) -> list[dict[str, Any]]:
        return service.list_submission_packages(manuscript_id)

    def package_response(manuscript_id: str, package_id: str, filename: str | None = None) -> Response:
        try:
            raw, name, media_type = service.submission_package_content(manuscript_id, package_id, filename)
        except PackageUnavailableError as exc:
            raise HTTPException(status_code=410, detail=str(exc)) from exc
        return Response(raw, media_type=media_type, headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        })

    @app.get("/api/manuscripts/{manuscript_id}/packages/{package_id}/download")
    def download_submission_package(manuscript_id: str, package_id: str) -> Response:
        return package_response(manuscript_id, package_id)

    @app.get("/api/manuscripts/{manuscript_id}/packages/{package_id}/files/{filename}")
    def download_package_file(manuscript_id: str, package_id: str, filename: str) -> Response:
        return package_response(manuscript_id, package_id, filename)

    @app.patch("/api/findings/{finding_id}")
    def resolve_finding(
        finding_id: str,
        payload: FindingUpdateRequest,
    ) -> dict[str, Any]:
        return service.resolve_finding(finding_id, payload.status)

    @app.post("/api/manuscripts/{manuscript_id}/submission-events", status_code=201)
    def record_submission_event(
        manuscript_id: str,
        payload: SubmissionEventRequest,
    ) -> dict[str, Any]:
        return service.record_submission_event(
            manuscript_id,
            venue=payload.venue,
            round_number=payload.round_number,
            status=payload.status,
            detail=payload.detail,
        )

    @app.get("/api/manuscripts/{manuscript_id}/review-rounds")
    def list_review_rounds(manuscript_id: str) -> list[dict[str, Any]]:
        return service.list_review_rounds(manuscript_id)

    @app.post("/api/manuscripts/{manuscript_id}/review-rounds", status_code=201)
    def create_review_round(
        manuscript_id: str,
        payload: ReviewRoundRequest,
    ) -> dict[str, Any]:
        return service.create_review_round(manuscript_id, **payload.model_dump())

    @app.post("/api/review-rounds/{review_round_id}/comments", status_code=201)
    def import_comments(
        review_round_id: str,
        payload: CommentImportRequest,
    ) -> list[dict[str, Any]]:
        return service.import_comments(
            review_round_id,
            payload.comments,
            source=payload.source,
            import_metadata=payload.import_metadata,
        )

    @app.post("/api/review-comments/preview-file")
    async def preview_comment_file(
        file: Annotated[UploadFile, File()],
    ) -> dict[str, Any]:
        content = await file.read()
        filename = file.filename or "review.txt"
        text = _extract_review_text(filename, file.content_type or "", content)
        return {
            "comments": _split_review_comments(text),
            "metadata": {
                "filename": filename,
                "content_type": file.content_type,
                "size_bytes": len(content),
                "original_text": text,
            },
        }

    @app.post("/api/review-rounds/{review_round_id}/comments/file", status_code=201)
    async def import_comment_file(
        review_round_id: str,
        file: Annotated[UploadFile, File()],
        source: Annotated[str, Form()] = "FILE_IMPORT",
    ) -> list[dict[str, Any]]:
        content = await file.read()
        filename = file.filename or "review.txt"
        text = _extract_review_text(filename, file.content_type or "", content)
        comments = _split_review_comments(text)
        return service.import_comments(
            review_round_id,
            comments,
            source=source,
            import_metadata={
                "filename": filename,
                "content_type": file.content_type,
                "size_bytes": len(content),
                "original_text": text,
            },
        )

    @app.get("/api/manuscripts/{manuscript_id}/comments")
    def list_comments(
        manuscript_id: str,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        return service.list_comments(manuscript_id, include_archived=include_archived)

    @app.patch("/api/comments/{comment_id}")
    def update_comment(comment_id: str, payload: CommentUpdateRequest) -> dict[str, Any]:
        return service.update_comment(comment_id, payload.model_dump(exclude_none=True))

    @app.get("/api/manuscripts/{manuscript_id}/comments/{comment_id}/response-review")
    def response_review(manuscript_id: str, comment_id: str) -> dict[str, Any]:
        return service.response_review_context(manuscript_id, comment_id)

    @app.post("/api/manuscripts/{manuscript_id}/comments/{comment_id}/response-checks")
    def confirm_response_review(manuscript_id: str, comment_id: str, payload: ResponseReviewRequest) -> dict[str, Any]:
        return service.confirm_response_review(manuscript_id, comment_id, payload.model_dump())

    @app.get("/api/manuscripts/{manuscript_id}/comments/{comment_id}/response-checks")
    def response_review_history(manuscript_id: str, comment_id: str) -> dict[str, Any]:
        return service.response_review_history(manuscript_id, comment_id)

    @app.delete("/api/comments/{comment_id}")
    def archive_comment(comment_id: str) -> dict[str, Any]:
        return service.archive_comment(comment_id)

    @app.post("/api/comments/{comment_id}/restore")
    def restore_comment(comment_id: str) -> dict[str, Any]:
        return service.archive_comment(comment_id, restore=True)

    return app


def main() -> None:
    import uvicorn

    uvicorn.run(
        "rstv4.studio_api:create_app",
        factory=True,
        host="127.0.0.1",
        port=int(os.environ.get("RSTV4_STUDIO_PORT", "8874")),
        reload=False,
    )
