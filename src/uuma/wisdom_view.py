from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any
from urllib.parse import quote, urlencode

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .knowledge_service import KnowledgeService
from .settings import Settings
from .wisdom_topics import TopicKnowledgeService, ensure_view_token
from .wisdom_web import render_topic_index, render_topic_page


def create_wisdom_view_app(settings: Settings | None = None) -> FastAPI:
    """Create the loopback-only, read-only Wisdom topic document service."""
    settings = settings or Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("UUMA_WISDOM_VIEW_TOKEN") or ensure_view_token(settings.data_dir)
    base_url = os.environ.get("UUMA_WISDOM_VIEW_BASE_URL", "http://127.0.0.1:8767")
    topics = TopicKnowledgeService(
        KnowledgeService(settings.knowledge_database_path()),
        view_base_url=base_url,
        view_token=token,
    )
    app = FastAPI(
        title="Wisdom-Oldman Topic Documents",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.wisdom_topics = topics

    @app.middleware("http")
    async def repair_escaped_link(request: Request, call_next):
        path = request.url.path
        supplied = request.query_params.get("token", "")
        if (
            request.method == "GET"
            and path.startswith("/wisdom/")
            and ("\\_" in path or "\\_" in supplied)
        ):
            clean_token = supplied.replace("\\_", "_")
            if not hmac.compare_digest(clean_token, token):
                return HTMLResponse("Invalid Wisdom read-only token", status_code=403)
            clean_path = quote(path.replace("\\_", "_"), safe="/")
            query = urlencode([
                (key, clean_token if key == "token" else value)
                for key, value in request.query_params.multi_items()
            ])
            return RedirectResponse(clean_path + "?" + query, status_code=307)
        return await call_next(request)

    def require_token(request: Request) -> None:
        supplied = request.query_params.get("token", "")
        authorization = request.headers.get("authorization", "")
        if authorization.startswith("Bearer "):
            supplied = authorization.removeprefix("Bearer ").strip()
        if not supplied or not hmac.compare_digest(supplied, token):
            raise HTTPException(status_code=403, detail="Invalid Wisdom read-only token")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "wisdom-view",
            "loopback_only": True,
            "token_fingerprint": hashlib.sha256(token.encode("utf-8")).hexdigest()[:12],
        }

    @app.get("/wisdom/topics", response_class=HTMLResponse)
    def topic_index(request: Request) -> HTMLResponse:
        require_token(request)
        records = topics.list_topics(limit=500)["records"]
        return HTMLResponse(render_topic_index(records, token))

    @app.get("/wisdom/topics/{topic_id}", response_class=HTMLResponse)
    def topic_page(topic_id: str, request: Request) -> HTMLResponse:
        require_token(request)
        try:
            data = topics.get_topic(topic_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Wisdom topic not found") from exc
        return HTMLResponse(render_topic_page(data, token))

    @app.get("/wisdom/api/topics")
    def topic_list(request: Request) -> dict[str, Any]:
        require_token(request)
        return topics.list_topics(limit=500)

    @app.get("/wisdom/api/topics/{topic_id}")
    def topic_get(topic_id: str, request: Request) -> dict[str, Any]:
        require_token(request)
        try:
            return topics.get_topic(topic_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Wisdom topic not found") from exc

    @app.get("/wisdom/api/topics/{topic_id}/graph")
    def topic_graph(topic_id: str, request: Request) -> dict[str, Any]:
        require_token(request)
        try:
            return topics.graph(topic_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Wisdom topic not found") from exc

    return app


def main() -> None:
    uvicorn.run(
        "uuma.wisdom_view:create_wisdom_view_app",
        factory=True,
        host="127.0.0.1",
        port=int(os.environ.get("UUMA_WISDOM_VIEW_PORT", "8767")),
    )


if __name__ == "__main__":
    main()
