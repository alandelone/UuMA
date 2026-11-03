"""Semantic MCP transport. Each child has one fixed, authenticated Agent identity."""

from __future__ import annotations

import argparse
import contextlib
import contextvars
import os
import sys
from pathlib import Path

import anyio
import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount

from .auth import TokenRegistry
from .chatgpt_bridge import PERMISSIONS as CHATGPT_PERMISSIONS
from .control_client import credential, validate_endpoint
from .settings import Settings

CALLER: contextvars.ContextVar[str] = contextvars.ContextVar("mcp_caller")
MODULES = {
    "brainstormer": "uuma.mcp_brainstormer",
    "control": "uuma.mcp_control", "knowledge": "uuma.mcp_knowledge",
    "chatgpt": "uuma.mcp_chatgpt",
    "librarian": "uuma.mcp_librarian",
    "xhs": "workstation_external_xhs",
    "procurement": "uuma.mcp_procurement",
}
ALLOWED = {
    "brainstormer": {"orchestrator", "brainstormer"},
    "control": {"orchestrator"}, "knowledge": {"orchestrator", "wisdom-oldman"},
    "chatgpt": set(CHATGPT_PERMISSIONS),
    # Authentication admits known agents to the transport only. The archive
    # reader independently enforces explicit source and record grants.
    "librarian": {"orchestrator", "brainstormer", "yonc", "forge-lab-bot", "honc",
                  "wisdom-oldman", "scholar", "librarian"},
    "xhs": {"orchestrator", "wisdom-oldman"},
    "procurement": {"forge-lab-bot"},
}


class AgentAuthentication:
    def __init__(self, app, tokens: TokenRegistry, *, allowed=None):
        self.app, self.tokens = app, tokens
        self.allowed = {"orchestrator"} if allowed is None else set(allowed)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        identity = headers.get("x-uuma-identity", "")
        authorization = headers.get("authorization", "")
        if not identity and authorization.startswith("Bearer "):
            matches = [
                candidate
                for candidate in self.allowed
                if self.tokens.verify(
                    candidate,
                    authorization[7:],
                    "control" if candidate == "orchestrator" else "worker",
                )
            ]
            identity = matches[0] if len(matches) == 1 else ""
        role = "control" if identity == "orchestrator" else "worker"
        if (
            identity not in self.allowed
            or not authorization.startswith("Bearer ")
            or not self.tokens.verify(identity, authorization[7:], role)
        ):
            return await JSONResponse({"detail": "Invalid Agent identity"}, 403)(
                scope, receive, send
            )
        token = CALLER.set(identity)
        try:
            await self.app(scope, receive, send)
        finally:
            CALLER.reset(token)


@contextlib.asynccontextmanager
async def owner_session(service: str):
    identity = CALLER.get()
    if identity not in ALLOWED[service]:
        raise PermissionError("Agent cannot access this semantic service")
    environment = os.environ.copy()
    environment.pop("UUMA_REMOTE_MCP_URL", None)
    environment["UUMA_AGENT_ID"] = identity
    # A child cannot inherit another Agent's scoped credential.
    token_dir = os.environ.get("UUMA_IDENTITY_TOKEN_DIR", "")
    if token_dir:
        environment["UUMA_IDENTITY_TOKEN_FILE"] = str(Path(token_dir) / f"{identity}.token")
    elif environment.get("UUMA_CONTROL_URL"):
        raise RuntimeError("Server semantic MCP requires scoped identity token directory")
    if service == "xhs":
        executable = os.environ.get("UUMA_DESKTOP_XHS_PYTHON", "")
        script = os.environ.get("UUMA_DESKTOP_XHS_SCRIPT", "")
        if not executable or not script or not Path(script).is_file():
            raise RuntimeError("Workstation XHS connector is not configured")
        # This external MCP owns its Conda runtime. UuMA's copied Python dependency
        # path can otherwise mix incompatible pydantic/pydantic_core binaries.
        for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
            environment.pop(key, None)
        params = StdioServerParameters(command=executable, args=[script], env=environment)
    else:
        params = StdioServerParameters(
            command=sys.executable, args=["-m", MODULES[service]], env=environment
        )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        yield session


def proxy_server(name: str, session_factory) -> Server:
    server = Server(name)

    @server.list_tools()
    async def list_tools():
        async with session_factory() as session:
            return (await session.list_tools()).tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        async with session_factory() as session:
            return await session.call_tool(name, arguments)

    return server


def create_app(tokens: TokenRegistry | None = None, *, services=None):
    tokens = tokens or TokenRegistry(Settings.from_env().token_file())
    managers = {}
    for service in (services if services is not None else ["control", "knowledge"]):
        if service not in MODULES:
            raise ValueError("Unknown semantic service")
        server = proxy_server(f"uuma-{service}-remote", lambda s=service: owner_session(s))
        managers[service] = StreamableHTTPSessionManager(server, stateless=True, json_response=True)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with contextlib.AsyncExitStack() as stack:
            for manager in managers.values():
                await stack.enter_async_context(manager.run())
            yield

    routes = []
    for service, manager in managers.items():
        routes.append(
            Mount(
                f"/{service}",
                app=AgentAuthentication(
                    manager.handle_request,
                    tokens,
                    allowed=ALLOWED[service],
                ),
            )
        )
    return Starlette(routes=routes, lifespan=lifespan)


def run_stdio_proxy(service: str) -> None:
    if service not in MODULES:
        raise ValueError("Unknown semantic MCP service")
    identity, token = credential()
    if identity not in ALLOWED[service]:
        raise PermissionError("Agent cannot access this semantic service")
    base = validate_endpoint(os.environ["UUMA_REMOTE_MCP_URL"])

    @contextlib.asynccontextmanager
    async def remote_session():
        async with (
            httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Uuma-Identity": identity,
                },
                timeout=120,
            ) as client,
            streamable_http_client(f"{base}/{service}/", http_client=client) as streams,
            ClientSession(streams[0], streams[1]) as session,
        ):
            await session.initialize()
            yield session

    async def run():
        server = proxy_server(f"uuma-{service}-proxy", remote_session)
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(run)


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8769)
    parser.add_argument("--token-registry", type=Path,
                        help="Existing node identity registry, independent of domain data root")
    parser.add_argument("--services", nargs="+", choices=sorted(MODULES),
                        default=["control", "knowledge"])
    parser.add_argument("--proxy", choices=sorted(MODULES))
    args = parser.parse_args()
    if args.proxy:
        run_stdio_proxy(args.proxy)
    else:
        if args.token_registry and not args.token_registry.is_file():
            parser.error("The semantic MCP identity registry must already exist")
        tokens = TokenRegistry(args.token_registry) if args.token_registry else None
        uvicorn.run(create_app(tokens=tokens, services=args.services),
                    host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
