"""The same source-bound discussion endpoints on Catalog and Studio."""
from fastapi import APIRouter, HTTPException

from .research_context import DiscussionTarget
from .research_discussions import (
    AnnotationInput,
    DiscussionHistoryRequest,
    DiscussionInput,
    ResearchDiscussionService,
)
from .research_workspace import WorkspaceError


def discussion_router(service: ResearchDiscussionService) -> APIRouter:
    router = APIRouter(prefix="/api/research/discussion")
    def result(operation, *args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except WorkspaceError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/context")
    def context(target: DiscussionTarget) -> dict:
        return result(service.context, target)

    @router.post("/history")
    def history(payload: DiscussionHistoryRequest) -> dict:
        return result(service.history, **payload.model_dump(exclude={"target"}), target=payload.target)

    @router.post("/messages", status_code=202)
    def discuss(payload: DiscussionInput) -> dict:
        return result(service.submit, payload)

    @router.post("/annotations", status_code=201)
    def annotate(payload: AnnotationInput) -> dict:
        return result(service.annotate, payload)

    @router.get("/requests/{request_id}")
    def request(request_id: str, scope: str) -> dict:
        return result(service.request, request_id, scope)

    @router.get("/messages/{message_id}/context")
    def historical_context(message_id: str, scope: str) -> dict:
        return result(service.historical_context, scope, message_id)

    return router
