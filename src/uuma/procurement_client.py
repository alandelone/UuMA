"""Keep procurement browser sessions on the workstation and ledger writes on the owner."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

import anyio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .control_client import credential, validate_endpoint
from .lab_crawler import SourcingCrawlerEngine


class RemoteSourcingCrawlerEngine(SourcingCrawlerEngine):
    """Only the browser methods travel; inherited evaluation uses the owner's store."""

    def __init__(self, url: str, identity: str, token: str) -> None:
        self.url = validate_endpoint(url) + "/"
        if identity != "forge-lab-bot" or not token:
            raise PermissionError("Procurement browser access requires Forge's scoped identity")
        self.identity, self._token = identity, token

    @classmethod
    def from_env(cls) -> RemoteSourcingCrawlerEngine:
        identity, token = credential()
        return cls(os.environ["UUMA_PROCUREMENT_MCP_URL"], identity, token)

    async def _call_async(self, name: str, arguments: dict) -> Any:
        try:
            async with (
                httpx.AsyncClient(
                    headers={"Authorization": f"Bearer {self._token}",
                             "X-Uuma-Identity": self.identity},
                    timeout=300,
                    follow_redirects=False,
                    trust_env=False,
                    transport=httpx.AsyncHTTPTransport(retries=0),
                ) as http,
                streamable_http_client(self.url, http_client=http) as streams,
                ClientSession(
                    streams[0], streams[1], read_timeout_seconds=timedelta(seconds=300),
                ) as session,
            ):
                await session.initialize()
                result = await session.call_tool(name, arguments)
                if result.isError:
                    raise RuntimeError("Workstation procurement browser rejected the operation")
                if result.structuredContent is not None:
                    return result.structuredContent
                content = [part.text for part in result.content if part.type == "text"]
                if len(content) != 1:
                    raise RuntimeError("Invalid procurement browser result")
                return json.loads(content[0])
        except (httpx.HTTPError, OSError) as exc:
            raise RuntimeError(
                "desktop_unavailable: procurement is waiting for the workstation; not retried"
            ) from exc

    def _call(self, name: str, arguments: dict) -> Any:
        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(anyio.run, self._call_async, name, arguments).result()

    def check_environment(self) -> dict[str, Any]:
        return self._call("procurement_check_crawler_status", {})

    def search_and_harvest(
        self, query: str, *, platforms: list[str] | None = None,
        max_per_platform: int = 5, requirement_id: str | None = None,
    ) -> list[dict[str, Any]]:
        value = self._call("procurement_search_and_harvest", {
            "query": query, "platforms": platforms,
            "max_per_platform": max_per_platform, "requirement_id": requirement_id,
        })
        # FastMCP wraps list return values in its structured result envelope.
        if isinstance(value, dict) and set(value) == {"result"}:
            value = value["result"]
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise RuntimeError("Invalid procurement browser offer list")
        return value
