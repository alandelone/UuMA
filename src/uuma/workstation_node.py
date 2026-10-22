"""One workstation listener for governed A2A and semantic desktop MCP."""

from __future__ import annotations

from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.routing import Mount

from .a2a_node import create_app as create_a2a_app
from .remote_mcp import create_app as create_mcp_app


def create_app(control, journal, tokens, bindings):
    a2a = create_a2a_app(control, journal, tokens, bindings)
    desktop = create_mcp_app(tokens, services=["chatgpt", "xhs", "procurement"])

    @asynccontextmanager
    async def lifespan(_app):
        async with desktop.router.lifespan_context(desktop):
            yield

    return Starlette(
        routes=[Mount("/mcp", app=desktop), Mount("/", app=a2a)], lifespan=lifespan
    )
