"""Workstation-only procurement browser tools; no Lab ledger or account export."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .lab_crawler import CrawlerConfig, SourcingCrawlerEngine

mcp = FastMCP("uuma-procurement-browser")


def _require_forge() -> None:
    if os.environ.get("UUMA_AGENT_ID", "").strip() != "forge-lab-bot":
        raise PermissionError("Procurement browser tools require authenticated Forge identity")
    if os.environ.get("UUMA_WORKER_MODE", "standard").strip().lower() == "native":
        raise PermissionError("Tool not permitted in native worker mode")


@lru_cache(maxsize=1)
def _engine() -> SourcingCrawlerEngine:
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    data = Path(os.environ.get(
        "UUMA_PROCUREMENT_BROWSER_DATA_DIR", os.environ.get("UUMA_DATA_DIR", local / "UuMA"),
    ))
    return SourcingCrawlerEngine(CrawlerConfig(
        user_data_dir=data / "chrome_profiles" / "procurement",
    ))


@mcp.tool()
def procurement_check_crawler_status() -> dict[str, Any]:
    """Inspect the existing workstation Chrome profile without exporting login state."""
    _require_forge()
    return _engine().check_environment()


@mcp.tool()
def procurement_search_and_harvest(
    query: str, platforms: list[str] | None = None,
    max_per_platform: int = 5, requirement_id: str | None = None,
) -> list[dict[str, Any]]:
    """Read offers through the existing workstation browser; the server records/evaluates them."""
    _require_forge()
    if not query.strip() or len(query) > 2000:
        raise ValueError("A bounded procurement search query is required")
    if not 1 <= max_per_platform <= 50:
        raise ValueError("At most 50 offers per platform may be requested")
    if platforms is not None and (
        not platforms or any(value not in {"taobao", "1688"} for value in platforms)
        or len(platforms) > 2
    ):
        raise ValueError("Only the configured Taobao and 1688 browser searches are available")
    if requirement_id is not None and len(requirement_id) > 200:
        raise ValueError("Invalid requirement identifier")
    return _engine().search_and_harvest(
        query, platforms=platforms, max_per_platform=max_per_platform,
        requirement_id=requirement_id,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
