"""Owner-side semantic reads and Orchestrator review, independent of control SQLite."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .brainstormer_state import BrainstormerStore

mcp = FastMCP("uuma-brainstormer-read")


def _store() -> BrainstormerStore:
    if os.environ.get("UUMA_AGENT_ID", "") not in {"orchestrator", "brainstormer"}:
        raise PermissionError("Brainstormer reads require an authorized domain identity")
    configured = os.environ.get("UUMA_DATA_DIR", "").strip()
    if not configured:
        raise RuntimeError("Domain owner data root must be explicit")
    root = Path(configured) / "brainstormer"
    if not all((root / name).is_dir() for name in ("projects", "proposals")):
        raise RuntimeError("Brainstormer domain is unavailable; refusing to create empty data")
    return BrainstormerStore(root)


@mcp.tool()
def brainstormer_get_context(project_id: str, topic_id: str = "") -> dict[str, Any]:
    """Read a project or topic from its owner; references are domain IDs, never file paths."""
    return _store().get_context(project_id, topic_id or None)


@mcp.tool()
def brainstormer_search_topics(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search existing owner-side topics without changing decisions or history."""
    if not 1 <= limit <= 100:
        raise ValueError("Topic result limit must be between 1 and 100")
    return _store().search_topics(query, limit=limit)


@mcp.tool()
def brainstormer_get_decision_map(project_id: str, topic_id: str = "") -> dict[str, Any]:
    """Read the existing decision map; does not dispatch or approve knowledge changes."""
    return _store().get_decision_map(project_id, topic_id or None)


def review_brainstormer_transaction(
    proposal_id: str, approve: bool, review_note: str,
) -> dict[str, Any]:
    """Review a proposed transaction using this authenticated process's identity."""
    if os.environ.get("UUMA_AGENT_ID", "").strip() != "orchestrator":
        raise PermissionError("Brainstormer review requires Orchestrator authority")
    return _store().review(
        proposal_id, actor_id="orchestrator", approve=approve, note=review_note,
    )


# Each owner child has one fixed authenticated identity for its entire lifetime.
# Specialist discovery exposes only reads; even a manually named call is denied.
if os.environ.get("UUMA_AGENT_ID", "").strip() == "orchestrator":
    mcp.tool()(review_brainstormer_transaction)


def main() -> None:
    if os.environ.get("UUMA_REMOTE_MCP_URL"):
        from .remote_mcp import run_stdio_proxy

        run_stdio_proxy("brainstormer")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
