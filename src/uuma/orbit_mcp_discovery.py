"""Read-only supplemental discovery through the Agent's existing XHS MCP binding."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .orbit_discovery import DiscoveryArtifact, DiscoveryOutcome, DiscoveryResponse


class XhsMCPDiscoveryProvider:
    name = "xhs"

    def __init__(self, binding: dict[str, Any]) -> None:
        self.binding = binding

    @classmethod
    def from_profile(cls, profile_home: Path) -> XhsMCPDiscoveryProvider | None:
        import yaml

        path = profile_home / "config.yaml"
        if not path.is_file():
            return None
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        binding = (config.get("mcp_servers") or {}).get("xhs")
        if not isinstance(binding, dict) or binding.get("enabled") is False:
            return None
        if not binding.get("command"):
            return None
        identity = (binding.get("env") or {}).get("UUMA_AGENT_ID", "wisdom-oldman")
        if identity != "wisdom-oldman":
            raise PermissionError("XHS research binding must belong to Wisdom")
        return cls(binding)

    def discover(
        self, query: str, *, limit: int = 5, pending_request_id: str | None = None,
    ) -> DiscoveryResponse:
        try:
            return asyncio.run(self._discover(query, limit, pending_request_id))
        except Exception as exc:  # noqa: BLE001 - optional external MCP boundary
            return DiscoveryResponse(
                [], request_id=pending_request_id,
                outcome=DiscoveryOutcome.TRANSIENT_FAILURE,
                error_detail=f"XHS MCP unavailable ({type(exc).__name__})",
            )

    async def _discover(self, query: str, limit: int, pending: str | None) -> DiscoveryResponse:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=self.binding["command"], args=self.binding.get("args", []),
            env={**os.environ, **self.binding.get("env", {})},
        )
        async with asyncio.timeout(45):
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    # Fixed read-only allowlist; never expose publish/delete/login tools.
                    result = await session.call_tool(
                        "xhs_search_status" if pending else "xhs_search_links",
                        {"job_id": pending} if pending else {"query": query, "limit": limit},
                    )
        if result.isError:
            return DiscoveryResponse([], request_id=pending,
                                     outcome=DiscoveryOutcome.TRANSIENT_FAILURE,
                                     error_detail="XHS MCP search failed")
        payload = {}
        for content in result.content:
            if content.type == "text":
                try:
                    value = json.loads(content.text)
                    if isinstance(value, dict):
                        payload.update(value)
                except ValueError:
                    continue
        return self.parse_result(payload, limit=limit, pending=pending, query=query)

    @classmethod
    def parse_result(
        cls, payload: dict[str, Any], *, limit: int, pending: str | None = None,
        query: str | None = None,
    ) -> DiscoveryResponse:
        job = payload.get("job") or payload.get("current_job") or payload
        status = str(job.get("status") or payload.get("status") or "").lower()
        error = str(job.get("error_code") or payload.get("error_code") or "").lower()
        stage = str(payload.get("stage") or job.get("stage") or "").lower()
        if payload.get("status") == "offline" or status in {
            "offline", "login_required", "awaiting_scan", "auth_required",
        } or any(word in stage for word in ("unpaired", "offline", "awaiting_scan")) or any(
            word in error for word in ("offline", "login", "pair", "auth")
        ):
            return DiscoveryResponse([], request_id=pending, outcome=DiscoveryOutcome.AUTH_REQUIRED,
                                     error_detail="XHS requires its paired Chrome extension or login")
        if query and job.get("query") and job["query"] != query:
            return DiscoveryResponse([], request_id=pending,
                                     outcome=DiscoveryOutcome.TRANSIENT_FAILURE,
                                     error_detail="XHS returned a different search job")
        request_id = job.get("job_id") or payload.get("job_id") or pending
        items = job.get("results") or payload.get("results") or []
        artifacts = []
        for item in items[:max(1, min(limit, 10))]:
            if not isinstance(item, dict):
                continue
            url = urlsplit(str(item.get("url") or ""))
            if url.scheme not in {"http", "https"} or not url.hostname or not any(
                url.hostname == domain or url.hostname.endswith("." + domain)
                for domain in ("xiaohongshu.com", "rednote.com", "xhslink.com")
            ):
                continue
            # Signed browsing tokens remain in the desktop connector, not canonical records.
            locator = urlunsplit((url.scheme, url.netloc, url.path, "", ""))
            artifacts.append(DiscoveryArtifact(
                locator=locator, title=str(item.get("title") or locator), provider=cls.name,
                snippet=str(item.get("description") or ""),
                metadata={"note_id": item.get("note_id"), "author": item.get("author"),
                          "discovery_only": True, "source_class": "community_post"},
            ))
        in_progress = bool(request_id) and status in {
            "queued", "pending", "running", "searching", "browser_opening", "started",
        }
        return DiscoveryResponse(artifacts, request_id=request_id, in_progress=in_progress)
