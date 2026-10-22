"""Authenticated semantic access to the single Brainstormer domain owner."""

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


class BrainstormerClient:
    def __init__(self, url: str, identity: str, token: str) -> None:
        self.url = validate_endpoint(url) + "/"
        if identity not in {"orchestrator", "brainstormer"} or not token:
            raise PermissionError("Brainstormer access requires an authorized scoped identity")
        self.identity, self._token = identity, token

    @classmethod
    def from_env(cls) -> BrainstormerClient:
        identity, token = credential()
        return cls(os.environ["UUMA_BRAINSTORMER_MCP_URL"], identity, token)

    async def _call_async(self, name: str, arguments: dict) -> Any:
        async with (
            httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self._token}",
                         "X-Uuma-Identity": self.identity},
                timeout=120,
            ) as http,
            streamable_http_client(self.url, http_client=http) as streams,
            ClientSession(
                streams[0], streams[1], read_timeout_seconds=timedelta(seconds=120),
            ) as session,
        ):
            await session.initialize()
            result = await session.call_tool(name, arguments)
            if result.isError:
                raise RuntimeError("Brainstormer owner rejected the semantic operation")
            if result.structuredContent is not None:
                return result.structuredContent
            text = [part.text for part in result.content if part.type == "text"]
            if len(text) != 1:
                raise RuntimeError("Brainstormer owner returned an invalid semantic result")
            return json.loads(text[0])

    def _call(self, name: str, arguments: dict) -> Any:
        # FastMCP can invoke a synchronous tool from its event loop. Own a fresh
        # thread/loop for the official async client, with exactly one call and no retry.
        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(anyio.run, self._call_async, name, arguments).result()

    def get_context(self, project_id: str, topic_id: str | None = None) -> dict:
        return self._call("brainstormer_get_context", {
            "project_id": project_id, "topic_id": topic_id or "",
        })

    def get_decision_map(self, project_id: str, topic_id: str | None = None) -> dict:
        return self._call("brainstormer_get_decision_map", {
            "project_id": project_id, "topic_id": topic_id or "",
        })

    def search_topics(self, query: str, *, limit: int = 20) -> list:
        value = self._call("brainstormer_search_topics", {"query": query, "limit": limit})
        if isinstance(value, dict) and set(value) == {"result"}:
            return value["result"]
        return value

    def review(self, proposal_id: str, *, actor_id: str, approve: bool, note: str) -> dict:
        if actor_id != self.identity or self.identity != "orchestrator":
            raise PermissionError("Brainstormer review requires authenticated Orchestrator authority")
        return self._call("review_brainstormer_transaction", {
            "proposal_id": proposal_id, "approve": approve, "review_note": note,
        })
