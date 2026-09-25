"""Loopback account dashboard and authenticated agent API."""
from __future__ import annotations

import hmac
import os
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from .auth import TOKEN_ROLES, TokenRegistry
from .chatgpt_bridge import PERMISSIONS, BridgeStore, Consultation
from .chatgpt_browser import BridgeRunner, ChatGPTBrowser
from .chatgpt_extension import ExtensionBroker
from .chrome_profiles import chrome_profiles, open_chrome_profile, validate_chrome_profile


class AccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alias: str
    identity: str
    workspace: str


class ActionInput(BaseModel):
    action: str


class BrowserProfileInput(BaseModel):
    profile: str = Field(default="", max_length=80)


class CapabilityInput(BaseModel):
    capability: str = Field(max_length=40)
    enabled: bool


class ExtensionPollInput(BaseModel):
    alias: str = Field(max_length=40)
    token: str = Field(max_length=200)


class ExtensionResultInput(ExtensionPollInput):
    command_id: str = Field(max_length=64)
    result: dict


class BindingInput(BaseModel):
    agent: str
    account: str


class ThreadInput(BindingInput):
    project: str = "general"
    thread: str = "main"
    url: str


class LoginInput(BaseModel):
    token: str = Field(max_length=200)


def admin_secret(data_dir: Path):
    path = data_dir / "chatgpt-bridge" / "dashboard.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as handle:
                handle.write(secrets.token_urlsafe(48))
        except FileExistsError:
            pass
    return path.read_text().strip()


def create_app(data_dir: Path, *, port: int = 8787, start_worker: bool = True,
               browser=None) -> FastAPI:
    store = BridgeStore(data_dir / "uuma.db")
    tokens = TokenRegistry(data_dir / "tokens.json")
    secret = admin_secret(data_dir)
    extension = ExtensionBroker(data_dir / "chatgpt-bridge" / "extension-pairs.json")
    extension_path = Path(__file__).parents[2] / "integrations" / "chrome" / "uuma-chatgpt-bridge"
    runner = BridgeRunner(
        store,
        browser or ChatGPTBrowser(data_dir / "chatgpt-bridge" / "profiles", extension=extension),
    )

    def signed_session(expires: int, csrf: str) -> str:
        payload = f"{expires}.{csrf}"
        signature = hmac.new(secret.encode(), payload.encode(), "sha256").hexdigest()
        return f"{payload}.{signature}"

    def verified_session(cookie: str) -> tuple[float, str] | None:
        try:
            expiry_text, csrf, signature = cookie.split(".", 2)
            payload = f"{expiry_text}.{csrf}"
            expected = hmac.new(secret.encode(), payload.encode(), "sha256").hexdigest()
            expiry = int(expiry_text)
        except (AttributeError, TypeError, ValueError):
            return None
        if expiry < time.time() or not hmac.compare_digest(signature, expected):
            return None
        return float(expiry), csrf

    @asynccontextmanager
    async def lifespan(app):
        worker = threading.Thread(target=runner.run, name="chatgpt-browser", daemon=True)
        if start_worker:
            worker.start()
        yield
        runner.stop_event.set()
        if start_worker:
            worker.join(timeout=15)

    app = FastAPI(title="UuMA ChatGPT Bridge", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store, app.state.runner, app.state.extension = store, runner, extension

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host = request.headers.get("host", "")
        origin = request.headers.get("origin")
        extension_request = bool(
            request.url.path.startswith("/extension/")
            and origin
            and re.fullmatch(r"chrome-extension://[a-p]{32}", origin)
        )
        if host not in allowed_hosts or (
            origin and origin not in {f"http://{h}" for h in allowed_hosts}
            and not extension_request
        ):
            return JSONResponse({"detail": "Loopback origin required"}, status_code=403)
        response = (
            Response(status_code=204)
            if request.method == "OPTIONS" and extension_request
            else await call_next(request)
        )
        if extension_request:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Headers"] = "content-type"
            response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
            response.headers["Vary"] = "Origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(PermissionError)
    async def permission_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=403)

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    def agent_auth(request: Request):
        identity = request.headers.get("x-uuma-identity", "")
        bearer = request.headers.get("authorization", "")
        if not bearer.startswith("Bearer ") or not tokens.verify(
                identity, bearer[7:], TOKEN_ROLES.get(identity, "")):
            raise HTTPException(401, "Valid UuMA identity and token required")
        store.authorize(identity)
        return identity

    def human_auth(request: Request):
        session = verified_session(request.cookies.get("bridge_session", ""))
        if not session:
            raise HTTPException(401, "Open the dashboard using the local bridge shortcut")
        if (
            request.method not in {"GET", "HEAD"}
            and (
                not request.headers.get("origin")
                or not hmac.compare_digest(
                    request.headers.get("x-bridge-csrf", ""), session[1]
                )
            )
        ):
            raise HTTPException(403, "Dashboard CSRF check failed")
        return session

    @app.get("/health")
    def health():
        return {"service": "uuma-chatgpt-bridge", "worker_healthy":
                bool(runner.last_tick and time.time() - runner.last_tick < 90),
                "last_error": runner.last_error}

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        return (Path(__file__).with_name("chatgpt_dashboard.html")).read_text(encoding="utf-8")

    @app.get("/dashboard.js")
    def javascript():
        from fastapi.responses import Response

        return Response(Path(__file__).with_name("chatgpt_dashboard.js").read_text(encoding="utf-8"),
                        media_type="application/javascript")

    @app.post("/human/login")
    def login(body: LoginInput, request: Request):
        if not request.headers.get("origin") or not hmac.compare_digest(body.token, secret):
            raise HTTPException(401, "Open the dashboard using the local bridge shortcut")
        csrf = secrets.token_urlsafe(32)
        sid = signed_session(int(time.time()) + 28800, csrf)
        response = JSONResponse({"csrf": csrf})
        response.set_cookie("bridge_session", sid, httponly=True, samesite="strict", max_age=28800)
        return response

    @app.get("/human/state")
    def state(session=Depends(human_auth)):  # noqa: B008 - FastAPI dependency injection
        accounts = store.accounts()
        for account in accounts:
            account["extension_connected"] = extension.connected(account["alias"])
        return {"csrf": session[1], "accounts": accounts, "routes": store.routes(),
                "requests": store.recent(), "permissions": {k: sorted(v) for k, v in PERMISSIONS.items()},
                "threads": [t for a in PERMISSIONS for t in store.threads(a)],
                "chrome_profiles": chrome_profiles(), "extension_path": str(extension_path)}

    @app.post("/human/accounts", dependencies=[Depends(human_auth)])
    def add_account(body: AccountInput):
        store.add_account(body.alias, body.identity, body.workspace)
        return {"ok": True}

    @app.post("/human/accounts/{alias}", dependencies=[Depends(human_auth)])
    def account_action(alias: str, body: ActionInput):
        store.account_action(alias, body.action)
        return {"ok": True}

    @app.post("/human/accounts/{alias}/browser", dependencies=[Depends(human_auth)])
    def configure_account_browser(alias: str, body: BrowserProfileInput):
        profile = validate_chrome_profile(body.profile) if body.profile else None
        if profile:
            selected = next(item for item in chrome_profiles() if item["directory"] == profile)
            account = next((item for item in store.accounts() if item["alias"] == alias), None)
            if not account:
                raise ValueError("Unknown account.")
            if selected["email"] and selected["email"].casefold() != account["identity"].casefold():
                raise ValueError("The Chrome profile email does not match this bridge account.")
        store.configure_browser(alias, profile)
        return {"ok": True}

    @app.post("/human/accounts/{alias}/extension-pair", dependencies=[Depends(human_auth)])
    def pair_extension(alias: str):
        account = next((item for item in store.accounts() if item["alias"] == alias), None)
        if not account or not account.get("chrome_profile"):
            raise ValueError("Select and save a normal Chrome profile first.")
        return {"alias": alias, "token": extension.pair(alias), "port": port,
                "extension_path": str(extension_path)}

    @app.post("/human/accounts/{alias}/capabilities", dependencies=[Depends(human_auth)])
    def confirm_account_capability(alias: str, body: CapabilityInput):
        store.confirm_capability(alias, body.capability, body.enabled)
        return {"ok": True}

    @app.post("/human/accounts/{alias}/open-dashboard", dependencies=[Depends(human_auth)])
    def open_account_dashboard(alias: str):
        account = next((item for item in store.accounts() if item["alias"] == alias), None)
        if not account or not account.get("chrome_profile"):
            raise ValueError("Select and save a normal Chrome profile first.")
        url = (f"http://127.0.0.1:{port}/?launch={secrets.token_urlsafe(8)}"
               f"&connect={alias}#token={secret}")
        open_chrome_profile(account["chrome_profile"], url)
        return {"ok": True, "url": url}

    @app.post("/extension/poll")
    def extension_poll(body: ExtensionPollInput):
        return extension.poll(body.alias, body.token)

    @app.post("/extension/result")
    def extension_result(body: ExtensionResultInput):
        extension.complete(body.alias, body.token, body.command_id, body.result)
        return {"ok": True}

    @app.post("/human/routes", dependencies=[Depends(human_auth)])
    def bind(body: BindingInput):
        store.bind(body.agent, body.account)
        return {"ok": True}

    @app.post("/human/threads", dependencies=[Depends(human_auth)])
    def bind_thread(body: ThreadInput):
        store.bind_thread(body.account, body.agent, body.project, body.thread, body.url)
        return {"ok": True}

    @app.post("/human/requests/{rid}", dependencies=[Depends(human_auth)])
    def request_action(rid: str, body: ActionInput):
        if body.action == "resume":
            store.resume(rid)
        elif body.action == "cancel":
            rows = [r for r in store.recent() if r["id"] == rid]
            if not rows:
                raise ValueError("Request not found")
            store.cancel(rows[0]["agent"], rid)
        else:
            raise ValueError("Unknown request action")
        return {"ok": True}

    @app.post("/agent/requests")
    def submit(
        body: Consultation,
        agent=Depends(agent_auth),  # noqa: B008 - FastAPI dependency injection
    ):
        return store.request(agent, body)

    @app.get("/agent/requests/{rid}")
    def result(
        rid: str,
        agent=Depends(agent_auth),  # noqa: B008 - FastAPI dependency injection
    ):
        return store.get(agent, rid)

    @app.post("/agent/requests/{rid}/cancel")
    def cancel(
        rid: str,
        agent=Depends(agent_auth),  # noqa: B008 - FastAPI dependency injection
    ):
        return store.cancel(agent, rid)

    @app.get("/agent/threads")
    def threads(agent=Depends(agent_auth)):  # noqa: B008 - FastAPI dependency injection
        return store.threads(agent)

    return app
