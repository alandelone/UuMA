"""Librarian's read-only stdio MCP; trusted launcher supplies identity and archive root."""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .librarian_read import LibrarianReader

mcp = FastMCP("uuma-librarian-read")
READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
)


def _reader() -> LibrarianReader:
    root = os.environ.get("UUMA_LIBRARIAN_ARCHIVE_ROOT", "").strip()
    actor = os.environ.get("UUMA_AGENT_ID", "").strip()
    if not root or not actor:
        raise PermissionError("The trusted stdio launcher must configure archive root and identity")
    return LibrarianReader(root, actor)


@mcp.tool(annotations=READ_ONLY)
def librarian_list_sources(expected_snapshot_id: str = "") -> dict[str, Any]:
    """List sources granted to this caller and their recorded capture/verification state."""
    return _reader().list_sources(expected_snapshot_id)


@mcp.tool(annotations=READ_ONLY)
def librarian_search_records(
    query: str = "", project_id: str = "", source_id: str = "", kind: str = "",
    limit: int = 50, offset: int = 0, expected_snapshot_id: str = "",
) -> dict[str, Any]:
    """Search archived metadata, including historical versions, within the caller's scope."""
    return _reader().search_records(
        query, project_id, source_id, kind, limit, offset, expected_snapshot_id,
    )


@mcp.tool(annotations=READ_ONLY)
def librarian_get_record(
    record_id: str, version_id: str, expected_snapshot_id: str = "",
) -> dict[str, Any]:
    """Get one authorized immutable record/version's provenance and original status."""
    return _reader().get_record(record_id, version_id, expected_snapshot_id)


@mcp.tool(annotations=READ_ONLY)
def librarian_read_record(
    record_id: str, version_id: str, offset: int = 0, limit: int = 6000,
    expected_snapshot_id: str = "",
) -> dict[str, Any]:
    """Read a digest-verified UTF-8 text chunk; binary/large records expose metadata only."""
    return _reader().read_record(record_id, version_id, offset, limit, expected_snapshot_id)


@mcp.tool(annotations=READ_ONLY)
def librarian_read_binary_chunk(
    record_id: str, version_id: str, offset: int = 0, limit: int = 262144,
    expected_snapshot_id: str = "",
) -> dict[str, Any]:
    """Read a bounded authenticated byte range of an authorized archive object."""
    return _reader().read_binary_chunk(record_id, version_id, offset, limit, expected_snapshot_id)


@mcp.tool(annotations=READ_ONLY)
def librarian_get_project_context(
    project_id: str, limit: int = 50, offset: int = 0, expected_snapshot_id: str = "",
) -> dict[str, Any]:
    """List latest authorized source versions for a project; no generated or approved summary."""
    return _reader().project_context(project_id, limit, offset, expected_snapshot_id)


@mcp.tool(annotations=READ_ONLY)
def librarian_get_backup_status(expected_snapshot_id: str = "") -> dict[str, Any]:
    """Read recorded backup coverage; never trigger capture, restore, retries, or live probes."""
    return _reader().backup_status(expected_snapshot_id)


def main() -> None:
    if os.environ.get("UUMA_REMOTE_MCP_URL"):
        from .remote_mcp import run_stdio_proxy

        run_stdio_proxy("librarian")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
