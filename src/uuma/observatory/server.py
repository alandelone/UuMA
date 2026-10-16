"""FastAPI server for UuMA All-in-One Observatory."""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..settings import Settings
from .adapters.registry import AdapterRegistry
from .harvester import Harvester
from .models import (
    ActivityEvent,
    BackfillProgress,
    FleetOverview,
)
from .storage import ObservatoryStorage

logger = logging.getLogger("uuma.observatory.server")

STATIC_DIR = Path(__file__).resolve().parent / "static"
COOKIE_NAME = "uuma_obs_token"


class SSEBroadcaster:
    """Manages active SSE client connections and event dispatch."""

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[dict[str, Any]]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def register_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def connect(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._queues.add(q)
        return q

    def disconnect(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._queues.discard(q)

    def publish_sync(self, event_type: str, data: Any) -> None:
        if not self._loop or not self._queues:
            return
        payload = {"event": event_type, "data": data}
        for q in list(self._queues):
            try:
                self._loop.call_soon_threadsafe(self._push, q, payload)
            except RuntimeError:
                pass

    @staticmethod
    def _push(q: asyncio.Queue[dict[str, Any]], item: dict[str, Any]) -> None:
        try:
            q.put_nowait(item)
        except asyncio.QueueFull:
            pass


def create_observatory_app(
    settings: Settings | None = None,
    auth_token: str | None = None,
    allow_loopback_without_auth: bool = True,
) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.ensure_directories()

    storage = ObservatoryStorage(settings.data_dir / "observatory.db")
    registry = AdapterRegistry(
        data_dir=settings.data_dir,
        uuma_db_path=settings.database_path,
        knowledge_db_path=settings.knowledge_database_path(),
    )
    broadcaster = SSEBroadcaster()

    # Determine or generate auth token
    token_file = settings.data_dir / "observatory.token"
    if auth_token:
        valid_token = auth_token
    elif token_file.exists():
        valid_token = token_file.read_text(encoding="utf-8").strip()
    else:
        valid_token = secrets.token_urlsafe(32)
        try:
            token_file.write_text(valid_token, encoding="utf-8")
        except OSError:
            pass

    def on_new_event(ev: ActivityEvent) -> None:
        broadcaster.publish_sync("activity", ev.model_dump())

    def on_progress(p: BackfillProgress) -> None:
        broadcaster.publish_sync("backfill_progress", p.model_dump())

    harvester = Harvester(
        storage=storage,
        spool_dir=settings.ingest_spool_dir,
        uuma_db_path=settings.database_path,
        on_new_event=on_new_event,
        on_progress=on_progress,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        loop = asyncio.get_running_loop()
        broadcaster.register_loop(loop)
        harvester.start()
        yield
        harvester.stop()

    app = FastAPI(
        title="UuMA All-in-One Observatory",
        description="Local-first read-only observatory for Hermes agents fleet",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.storage = storage
    app.state.registry = registry
    app.state.broadcaster = broadcaster
    app.state.harvester = harvester
    app.state.valid_token = valid_token

    # Middlewares & Static mounting
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8790", "http://localhost:8790"],
        allow_origin_regex=r"https?://.*",
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def disable_static_cache(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    def verify_auth(
        request: Request,
        auth: str | None = Query(default=None),
        uuma_obs_token: str | None = Cookie(default=None),
    ) -> bool:
        client_host = request.client.host if request.client else ""
        if allow_loopback_without_auth and client_host in {"127.0.0.1", "::1", "localhost"}:
            return True

        token = auth or uuma_obs_token or request.headers.get("X-Observatory-Token")
        if not token or not secrets.compare_digest(token, valid_token):
            raise HTTPException(status_code=401, detail="Unauthorized Observatory Access")
        return True

    @app.get("/", response_class=HTMLResponse)
    async def serve_index(
        request: Request,
        response: Response,
        auth: str | None = None,
        uuma_obs_token: str | None = Cookie(default=None),
    ):
        client_host = request.client.host if request.client else ""
        is_loopback = allow_loopback_without_auth and client_host in {"127.0.0.1", "::1", "localhost"}

        token = auth or uuma_obs_token
        is_authed = is_loopback or (token and secrets.compare_digest(token, valid_token))
        if not is_authed:
            return HTMLResponse(
                content="""<!doctype html><html><head><meta charset='utf-8'><title>Observatory 验证</title></head>
                <body style='font-family:sans-serif;display:flex;height:100vh;align-items:center;justify-content:center;background:#0f172a;color:#f8fafc'>
                <div style='background:#1e293b;padding:32px;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.5);max-width:400px;width:100%'>
                <h2 style='margin-top:0'>UuMA 观测台受限访问</h2>
                <p style='color:#94a3b8;font-size:14px'>非本机环回网络访问，请输入查看凭据。</p>
                <form method='GET' action='/'>
                <input name='auth' type='password' placeholder='请输入访问 Token' style='width:100%;padding:10px;border-radius:6px;border:1px solid #334155;background:#0f172a;color:#fff;margin-bottom:12px;box-sizing:border-box;'>
                <button type='submit' style='width:100%;padding:10px;background:#10b981;border:none;border-radius:6px;color:#fff;font-weight:bold;cursor:pointer'>进入观测台</button>
                </form></div></body></html>""",
                status_code=401,
            )

        # Set 8-hour HttpOnly session cookie
        response.set_cookie(
            key=COOKIE_NAME,
            value=valid_token,
            max_age=28800,  # 8 hours
            httponly=True,
            samesite="strict",
            path="/",
        )
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            content = index_file.read_text(encoding="utf-8")
            return HTMLResponse(content=content, headers=dict(response.headers))
        return HTMLResponse("<h2>Observatory 前端静态文件构建中...</h2>")

    @app.get("/api/observatory/agents", response_model=FleetOverview)
    async def get_agents_overview(_authed: bool = Depends(verify_auth)):
        workspaces = registry.get_fleet_workspaces()
        sources = registry.probe_all_sources()

        running = sum(1 for w in workspaces if w.status in {"RUNNING", "ACTIVE"})
        idle = sum(1 for w in workspaces if w.status == "IDLE")
        blocked = sum(1 for w in workspaces if w.status in {"BLOCKED", "ERROR", "WARNING"})

        return FleetOverview(
            total_agents=len(workspaces),
            running_count=running,
            idle_count=idle,
            blocked_count=blocked,
            agents=workspaces,
            backfill=harvester.progress,
            sources=sources,
        )

    @app.get("/api/observatory/agents/{agent_id}/items")
    async def get_agent_items(
        agent_id: str,
        limit: int = Query(default=10, ge=1, le=50),
        offset: int = Query(default=0, ge=0),
        _authed: bool = Depends(verify_auth),
    ):
        adapter = registry.get_adapter(agent_id)
        items = adapter.list_items(limit=limit, offset=offset)
        return {"agent_id": agent_id, "items": items, "count": len(items)}

    @app.get("/api/observatory/agents/{agent_id}")
    async def get_agent_overview(
        agent_id: str,
        _authed: bool = Depends(verify_auth),
    ):
        adapter = registry.get_adapter(agent_id)
        items = adapter.list_items(limit=15)
        health = adapter.probe_health()
        return {
            "agent_id": adapter.agent_id,
            "name": adapter.display_name,
            "role": adapter.role,
            "source_name": adapter.source_name,
            "health": "HEALTHY" if health.is_available else "WARNING",
            "status": items[0].status if items else "IDLE",
            "items": [it.model_dump() for it in items],
            "total_items": len(items),
        }

    @app.get("/api/observatory/items/{item_id}")
    async def get_item_detail(
        item_id: str,
        _authed: bool = Depends(verify_auth),
    ):
        # Look across all adapters
        for adapter in registry.list_all_adapters():
            item = adapter.get_item(item_id)
            if item:
                sessions = adapter.get_sessions(item_id)
                return {"item": item, "sessions": sessions}
        raise HTTPException(status_code=404, detail="Item not found")

    @app.get("/api/observatory/events/{event_id}")
    async def get_event_detail(
        event_id: str,
        _authed: bool = Depends(verify_auth),
    ):
        events, _ = storage.query_events(query=event_id, limit=5)
        for ev in events:
            if ev.event_id == event_id:
                return {"event": ev.model_dump()}
        raise HTTPException(status_code=404, detail="Event not found")

    @app.get("/api/observatory/events")
    async def get_activity_events(
        agent_id: str | None = None,
        query: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        since: str | None = None,
        _authed: bool = Depends(verify_auth),
    ):
        events, total = storage.query_events(
            agent_id=agent_id,
            query=query,
            limit=limit,
            offset=offset,
            since=since,
        )
        return {
            "events": [e.model_dump() for e in events],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/observatory/sources")
    async def get_sources_status(_authed: bool = Depends(verify_auth)):
        return registry.probe_all_sources()

    @app.get("/api/observatory/stream")
    async def event_stream(
        request: Request,
        _authed: bool = Depends(verify_auth),
    ):
        client_q = broadcaster.connect()

        async def sse_generator():
            try:
                # 1. Emit init event on handshake
                workspaces = registry.get_fleet_workspaces()
                sources = registry.probe_all_sources()
                init_data = {
                    "agents": [w.model_dump() for w in workspaces],
                    "sources": {k: v.model_dump() for k, v in sources.items()},
                    "backfill": harvester.progress.model_dump(),
                }
                yield f"event: init\ndata: {json.dumps(init_data, ensure_ascii=False)}\n\n"

                ping_counter = 0
                while True:
                    if await request.is_disconnected():
                        break

                    try:
                        msg = await asyncio.wait_for(client_q.get(), timeout=2.0)
                        yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'], ensure_ascii=False)}\n\n"
                    except TimeoutError:
                        ping_counter += 1
                        if ping_counter >= 7:  # every ~14 seconds
                            yield "event: ping\ndata: {}\n\n"
                            ping_counter = 0
            finally:
                broadcaster.disconnect(client_q)

        return StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app
