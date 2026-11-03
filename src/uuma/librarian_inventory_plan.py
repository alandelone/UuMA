"""Bounded, explicitly incomplete-aware inventory plans for large source trees.

Plans are private recovery metadata; they do not authorize intake sources, read
file contents, capture backups, or make records visible to semantic MCP readers.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .librarian_discovery import discover_page
from .librarian_intake import IDENTITY


def plan_inventory(root: Path, source_prefix: str, *,
                   verified_exclusions: frozenset[str] = frozenset(),
                   page_size: int = 1000,
                   max_pages: int = 1000, shard_files: int = 4000,
                   max_shards: int = 500) -> dict[str, Any]:
    """Enumerate a tree into bounded source shards without silently dropping errors.

    A finished scan is non-atomic: files and already-visited directories may change
    during or after traversal. Every path still needs capture-time validation and
    every shard needs an explicit device grant before transfer. A partial plan is
    evidence of observed files, never proof that the root was fully inventoried.
    """
    if (not isinstance(source_prefix, str) or not IDENTITY.fullmatch(source_prefix)
            or len(source_prefix) > 73):
        raise ValueError("Invalid source prefix for bounded shard identities")
    for value, maximum in ((page_size, 10000), (max_pages, 10000),
                           (shard_files, 10000), (max_shards, 500)):
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError("Invalid inventory bound")
    root = Path(root)
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("Registered inventory root must be absolute and not a symbolic link")
    started = datetime.now(UTC).isoformat()
    cursor = None
    paths: list[str] = []
    issues: list[dict[str, str]] = []
    seen: set[str] = set()
    finished = False
    pages = 0
    for _ in range(max_pages):
        try:
            page = discover_page(root, cursor=cursor,
                                 verified_exclusions=verified_exclusions,
                                 max_entries=page_size)
        except (OSError, ValueError, TypeError) as exc:
            issues.append({"path": ".", "error_type": type(exc).__name__, "stage": "discovery"})
            break
        pages += 1
        issues.extend({"path": issue["path"], "error_type": issue["error_type"], "stage": "discovery"}
                      for issue in page["issues"])
        for item in page["files"]:
            value = item.get("relative_path")
            relative = Path(value) if isinstance(value, str) else None
            if (relative is None or relative.is_absolute() or not relative.parts
                    or ".." in relative.parts or "\\" in value):
                raise ValueError("Discovery returned an invalid relative file path")
            key = os.path.normcase(str(relative))
            if key in seen:
                raise ValueError("Discovery returned a duplicate file")
            seen.add(key)
            if len(paths) >= shard_files * max_shards:
                issues.append({"path": ".", "error_type": "SHARD_BOUND_REACHED", "stage": "discovery"})
                break
            paths.append(relative.as_posix())
        if issues and issues[-1]["error_type"] == "SHARD_BOUND_REACHED":
            break
        cursor = page["cursor"]
        if cursor is None:
            finished = True
            break
    else:
        issues.append({"path": ".", "error_type": "PAGE_BOUND_REACHED", "stage": "discovery"})
    shards = [{"source_id": f"{source_prefix}-p{index // shard_files + 1:05d}",
               "relative_paths": paths[index:index + shard_files]}
              for index in range(0, len(paths), shard_files)]
    return {"schema_version": 1, "root": str(root), "source_prefix": source_prefix,
            "inventory_status": "DISCOVERED" if finished and not issues else "PARTIAL",
            "snapshot_consistency": "NON_ATOMIC", "finished": finished,
            "started_at": started, "finished_at": datetime.now(UTC).isoformat(),
            "pages": pages, "observed_files": len(paths), "issues": issues,
            "shards": shards, "capture_status": "NOT_CAPTURED", "server_grants": "NOT_CHECKED"}
