"""Local UI facade for the authoritative navigation service; owns no domain state."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
BODY_LIMIT = 1024 * 1024
REMOVED_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
    "trailer", "transfer-encoding", "upgrade", "authorization", "www-authenticate",
    "set-cookie", "cookie", "x-uuma-identity", "content-encoding", "content-length",
    "x-api-key", "x-auth-token", "authentication-info", "proxy-authentication-info", "location",
}


def loopback_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http" or parsed.hostname not in LOOPBACK
        or parsed.username or parsed.password or parsed.query or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Navigation proxy requires an explicit loopback HTTP endpoint")
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError("Invalid loopback port")
    return value.rstrip("/")


def create_app(
    upstream: str, token_file: Path, *, allowed_origins: set[str] | None = None,
    port: int = 8772, transport=None,
):
    upstream = loopback_url(upstream)
    token_file = token_file.resolve(strict=True)
    if not token_file.read_text(encoding="utf-8").strip():
        raise ValueError("Navigation proxy requires a scoped Orchestrator token")
    origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
    origins.update(loopback_url(origin) for origin in (allowed_origins or set()))

    async def proxy(request: Request):
        try:
            host = urlsplit("http://" + request.headers.get("host", ""))
            valid_host = (
                host.hostname in LOOPBACK and not host.username and not host.password
                and not host.path and not host.query and not host.fragment
            )
            if host.port is not None and not 1 <= host.port <= 65535:
                valid_host = False
        except ValueError:
            valid_host = False
        origin = request.headers.get("origin")
        if not valid_host or (origin is not None and origin not in origins):
            return JSONResponse({"detail": "Local navigation UI origin required"}, status_code=403)
        path = request.url.path
        if path != "/health" and not path.startswith("/api/v1/"):
            return JSONResponse({"detail": "Unknown navigation route"}, status_code=404)
        cors = {"Access-Control-Allow-Origin": origin, "Vary": "Origin"} if origin else {}
        if request.method == "OPTIONS":
            return Response(status_code=204, headers={
                **cors, "Access-Control-Allow-Methods": "GET, HEAD, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Accept",
            })
        try:
            content_length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "Invalid request size"}, status_code=400, headers=cors)
        if content_length < 0 or content_length > BODY_LIMIT:
            return JSONResponse({"detail": "Navigation request exceeds 1 MB"}, status_code=413, headers=cors)
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > BODY_LIMIT:
                return JSONResponse({"detail": "Navigation request exceeds 1 MB"}, status_code=413,
                                    headers=cors)
            body.extend(chunk)
        try:
            token = token_file.read_text(encoding="utf-8").strip()
            if not token:
                raise ValueError("missing token")
        except (OSError, ValueError):
            return JSONResponse({"detail": "Navigation authorization unavailable; waiting"},
                                status_code=503, headers=cors)
        target = upstream + path
        if request.url.query:
            target += "?" + request.url.query
        client = httpx.AsyncClient(
            timeout=20, follow_redirects=False, trust_env=False, transport=transport,
        )
        try:
            response = await client.send(client.build_request(
                request.method, target, content=bytes(body), headers={
                    "Authorization": "Bearer " + token, "X-Uuma-Identity": "orchestrator",
                    "Content-Type": request.headers.get("content-type", "application/json"),
                    "Accept": request.headers.get("accept", "application/json"),
                },
            ), stream=True)
        except httpx.TransportError:
            await client.aclose()
            return JSONResponse({"detail": "Navigation server unavailable; waiting for reconnection"},
                                status_code=503, headers=cors)
        excluded = REMOVED_HEADERS | {
            header.strip().lower() for header in response.headers.get("connection", "").split(",")
        }
        headers = {name: value for name, value in response.headers.items() if name not in excluded}
        headers.update(cors)

        async def stream():
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        return StreamingResponse(stream(), status_code=response.status_code, headers=headers)

    return Starlette(routes=[Route(
        "/{path:path}", proxy, methods=["GET", "HEAD", "POST", "OPTIONS"],
    )])


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8772)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Invalid loopback port")
    origins = {origin.strip() for origin in os.environ.get(
        "UUMA_NAVIGATION_PROXY_ORIGINS", "",
    ).split(",") if origin.strip()}
    app = create_app(
        os.environ.get("UUMA_NAVIGATION_PROXY_URL", "http://127.0.0.1:18773"),
        Path(os.environ["UUMA_IDENTITY_TOKEN_FILE"]), allowed_origins=origins, port=args.port,
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
