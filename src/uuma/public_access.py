"""Loopback-only authenticated ingress for the three published browser applications."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import time
from contextlib import asynccontextmanager
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from starlette.background import BackgroundTask
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from .browser_sessions import SESSION_MAX_AGE

COOKIE = "__Host-uuma_access"
TTL = SESSION_MAX_AGE
SITES = {
    "live.95963210.xyz": ("Live Agent", "http://127.0.0.1:5173"),
    "hermes.95963210.xyz": ("Hermes", "http://127.0.0.1:9119"),
    "scholar.95963210.xyz": ("Scholar", "http://127.0.0.1:8875"),
    "bttcb1.95963210.xyz": ("BTTCB1 3D Printer", "http://192.168.55.2:8082"),
    "vcore.95963210.xyz": ("V-Core 3D Printer", "http://192.168.55.2:8083"),
    "3dp.95963210.xyz": ("3D Printers Dashboard", "http://192.168.55.2:8082"),
}
# Preserve the existing Hermes tunnel's explicit HTTP Host Header override.
HOST_ALIASES = {"localhost:9119": "hermes.95963210.xyz"}
HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade",
}
PRIVATE = {"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"}


def signature(token: str, host: str, expires: int) -> str:
    return hmac.new(token.encode(), f"public-access-v1:{host}:{expires}".encode(),
                    hashlib.sha256).hexdigest()


def valid_cookie(value: str, token: str, host: str) -> bool:
    try:
        expires_text, digest = value.split(".", 1)
        expires = int(expires_text)
        now = int(time.time())
        return now < expires <= now + TTL and hmac.compare_digest(
            digest, signature(token, host, expires)
        )
    except (ValueError, TypeError):
        return False


def filtered_headers(headers: list[tuple[str, str]]) -> list[tuple[str, str]]:
    hop = HOP.copy()
    for name, value in headers:
        if name.lower() == "connection":
            hop.update(item.strip().lower() for item in value.split(","))
    return [(name, value) for name, value in headers if name.lower() not in hop]


def create_app(token_file: Path | None = None, transport=None) -> FastAPI:
    if token_file is None:
        from .settings import Settings
        token_file = Settings.from_env().data_dir / "observatory.token"
    # Fail closed before listening if the existing credential is unavailable.
    if len(token_file.read_text(encoding="utf-8").strip()) < 32:
        raise ValueError("Existing Observatory access credential is missing or invalid")

    client = httpx.AsyncClient(
        transport=transport, trust_env=False, follow_redirects=False,
        timeout=httpx.Timeout(connect=10, read=None, write=60, pool=10),
    )

    @asynccontextmanager
    async def lifespan(_app):
        yield
        await client.aclose()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    def identity(connection):
        host = connection.headers.get("host", "").lower()
        host = HOST_ALIASES.get(host, host)
        return host if host in SITES else None

    def credential():
        try:
            return token_file.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def authenticated(connection, host, token):
        return len(token) >= 32 and valid_cookie(
            connection.cookies.get(COOKIE, ""), token, host
        )

    def same_origin(connection, host):
        origin = connection.headers.get("origin")
        return origin is None or origin == f"https://{host}" or origin in {f"https://{site}" for site in SITES}

    def upstream_headers(connection, host):
        values = filtered_headers(list(connection.headers.items()))
        values = [(k, v) for k, v in values if k.lower() not in {
            "cookie", "forwarded", "x-forwarded-host", "x-forwarded-for", "x-forwarded-proto",
        }]
        # Keep application cookies while withholding the ingress session from the app.
        cookies = SimpleCookie()
        cookies.load(connection.headers.get("cookie", ""))
        if COOKIE in cookies:
            del cookies[COOKIE]
        if cookies:
            values.append(("cookie", cookies.output(header="", sep=";").strip()))
        values.extend([("x-forwarded-proto", "https"), ("x-forwarded-host", host)])
        return values

    async def http(request: Request):
        host = identity(request)
        if host is None:
            return JSONResponse({"detail": "Unknown site"}, status_code=404, headers=PRIVATE)
        token = credential()
        auth_values = request.query_params.getlist("auth")
        if auth_values:
            if request.method not in {"GET", "HEAD"} or len(auth_values) != 1 or not (
                len(token) >= 32 and hmac.compare_digest(auth_values[0], token)
            ):
                return JSONResponse({"detail": "Invalid access token"}, 401, headers=PRIVATE)
            # Relative redirect keeps navigation on this origin and removes the credential.
            path = request.scope.get("raw_path", b"/").decode("ascii")
            path = "/" + path.lstrip("/")
            query = urlencode([(k, v) for k, v in request.query_params.multi_items() if k != "auth"])
            response = RedirectResponse(path + ("?" + query if query else ""), 303,
                                        headers=PRIVATE)
            expires = int(time.time()) + TTL
            response.set_cookie(COOKIE, f"{expires}.{signature(token, host, expires)}",
                                max_age=TTL, secure=True, httponly=True, samesite="strict", path="/")
            return response
        if not authenticated(request, host, token):
            if request.method in {"GET", "HEAD"} and (
                request.url.path == "/" or "text/html" in request.headers.get("accept", "")
            ):
                title = html.escape(SITES[host][0])
                action = html.escape("/" + request.url.path.lstrip("/"), quote=True)
                hidden = "".join(
                    f'<input type="hidden" name="{html.escape(k, quote=True)}" '
                    f'value="{html.escape(v, quote=True)}">'
                    for k, v in request.query_params.multi_items()
                )
                return HTMLResponse(
                    '<!doctype html><html lang="en"><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width,initial-scale=1">'
                    f'<title>{title} · Access required</title><style>'
                    'body{font:16px system-ui;background:#0f172a;color:#f8fafc;display:grid;'
                    'place-items:center;min-height:95vh;margin:0}main{padding:32px;'
                    'background:#1e293b;border-radius:12px;max-width:360px;margin:16px}'
                    'input,button{box-sizing:border-box;width:100%;padding:12px;margin-top:12px;'
                    'border-radius:6px;border:1px solid #475569;font:inherit}'
                    'button{background:#10b981;color:#082f23;font-weight:600;cursor:pointer}'
                    'p{color:#cbd5e1;line-height:1.5}</style>'
                    f'<main><h1>{title}</h1><p>Open your private access link, or enter your '
                    'access token. This browser stays signed in for six months (180 days).</p>'
                    f'<form method="get" action="{action}">{hidden}'
                    '<label for="auth">Access token</label><input id="auth" name="auth" '
                    'type="password" required autocomplete="off">'
                    '<button type="submit">Continue</button></form></main></html>',
                    status_code=401, headers={**PRIVATE, "Content-Security-Policy":
                    "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
                    "frame-ancestors 'none'; base-uri 'none'"},
                )
            return JSONResponse({"detail": "Access token required"}, 401, headers=PRIVATE)
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not same_origin(request, host):
            return JSONResponse({"detail": "Invalid origin"}, 403, headers=PRIVATE)
        raw_path = request.scope.get("raw_path", b"/").decode("ascii")
        target = SITES[host][1] + raw_path
        if request.scope["query_string"]:
            target += "?" + request.scope["query_string"].decode("ascii")
        try:
            upstream = await client.send(client.build_request(
                request.method, target, headers=upstream_headers(request, host),
                content=request.stream(),
            ), stream=True)
        except httpx.HTTPError:
            return JSONResponse({"detail": "Application temporarily unavailable"}, 502,
                                headers=PRIVATE)
        response = StreamingResponse(upstream.aiter_raw(), status_code=upstream.status_code,
                                     background=BackgroundTask(upstream.aclose))
        response.raw_headers = [
            (k.encode("latin-1"), v.encode("latin-1"))
            for k, v in filtered_headers(list(upstream.headers.multi_items()))
            if k.lower() not in {"cache-control", "referrer-policy"}
        ]
        for key, value in PRIVATE.items():
            response.headers[key] = value
        return response

    async def websocket(socket: WebSocket):
        host = identity(socket)
        if not host or not authenticated(socket, host, credential()) or not same_origin(socket, host):
            await socket.close(code=1008)
            return
        # URL credentials are consumed only through the HTTP login flow.
        if "auth" in socket.query_params:
            await socket.close(code=1008)
            return
        target = SITES[host][1].replace("http://", "ws://", 1)
        target += socket.scope.get("raw_path", b"/").decode("ascii")
        if socket.scope["query_string"]:
            target += "?" + socket.scope["query_string"].decode("ascii")
        headers = [(k, v) for k, v in upstream_headers(socket, host)
                   if not k.lower().startswith("sec-websocket-") and k.lower() not in {"origin", "host"}]
        try:
            async with connect(target, additional_headers=headers,
                               origin=socket.headers.get("origin"),
                               subprotocols=socket.scope.get("subprotocols") or None,
                               proxy=None, max_size=None, open_timeout=15) as upstream:
                await socket.accept(subprotocol=upstream.subprotocol)

                async def to_upstream():
                    while True:
                        message = await socket.receive()
                        if message["type"] == "websocket.disconnect":
                            return
                        await upstream.send(message.get("bytes") if message.get("bytes") is not None
                                            else message["text"])

                async def to_browser():
                    async for message in upstream:
                        if isinstance(message, bytes):
                            await socket.send_bytes(message)
                        else:
                            await socket.send_text(message)

                tasks = [asyncio.create_task(to_upstream()), asyncio.create_task(to_browser())]
                try:
                    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        except (OSError, WebSocketException, WebSocketDisconnect):
            pass
        finally:
            try:
                await socket.close()
            except RuntimeError:
                pass

    app.add_api_route("/", http, methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    app.add_api_route("/{path:path}", http,
                      methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    app.add_api_websocket_route("/", websocket)
    app.add_api_websocket_route("/{path:path}", websocket)
    return app


def main() -> None:
    import uvicorn
    # URLs carry credentials. Never enable request/access logging on this ingress.
    uvicorn.run(create_app(), host="127.0.0.1", port=8791, access_log=False,
                proxy_headers=False, log_level="warning")


if __name__ == "__main__":
    main()
