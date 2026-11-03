"""Non-mutating file inventory for explicitly registered backup roots."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

RECOVERY_NAMES = frozenset({"id_rsa", "id_ed25519", "credentials.json", ".netrc"})


def _link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def discover(
    root: Path, *, verified_exclusions: frozenset[str] = frozenset(),
    max_files: int = 10000, max_seconds: float = 5,
) -> dict[str, Any]:
    """Inventory without reading file contents, following links, or asserting access grants.

    Names indicate obvious recovery-only materials. Other files remain UNCLASSIFIED
    until content classification is performed; this function cannot establish that a
    file contains no secrets and never makes records available to MCP callers.
    """
    original = Path(root).absolute()
    if _link(original):
        raise ValueError("Registered source root cannot be a symbolic link")
    actual = original.resolve(strict=True)
    if not actual.is_dir():
        raise ValueError("Registered source root must be a directory")
    if type(max_files) is not int or not 1 <= max_files <= 100000:
        raise ValueError("Inventory file bound must be between 1 and 100000")
    if not 0 < max_seconds <= 60:
        raise ValueError("Inventory deadline must be positive and at most 60 seconds")
    deadline = time.monotonic() + max_seconds
    for exclusion in verified_exclusions:
        candidate = Path(exclusion)
        if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
            raise ValueError("Verified exclusions must be relative source directories")
    files: list[dict[str, Any]] = []
    exclusions: list[str] = []
    issues: list[dict[str, str]] = []

    def onerror(error: OSError) -> None:
        issues.append({"path": str(error.filename or actual), "error_type": type(error).__name__})

    for directory, child_dirs, child_files in os.walk(actual, followlinks=False, onerror=onerror):
        if time.monotonic() >= deadline:
            issues.append({"path": str(actual), "error_type": "INVENTORY_DEADLINE"})
            break
        base = Path(directory)
        keep = []
        for name in sorted(child_dirs):
            path = base / name
            relative = path.relative_to(actual).as_posix()
            if _link(path):
                issues.append({"path": relative, "error_type": "SYMLINK_NOT_FOLLOWED"})
            elif relative in verified_exclusions:
                exclusions.append(relative)
            else:
                keep.append(name)
        child_dirs[:] = keep
        for name in sorted(child_files):
            if len(files) >= max_files or time.monotonic() >= deadline:
                issues.append({"path": str(actual), "error_type": "INVENTORY_BOUND_REACHED"})
                break
            path = base / name
            relative = path.relative_to(actual).as_posix()
            if _link(path):
                issues.append({"path": relative, "error_type": "SYMLINK_NOT_FOLLOWED"})
                continue
            try:
                stat = path.stat()
                if not path.is_file():
                    issues.append({"path": relative, "error_type": "NOT_REGULAR_FILE"})
                    continue
            except OSError as exc:
                issues.append({"path": relative, "error_type": type(exc).__name__})
                continue
            lower = name.casefold()
            sensitive = (lower in RECOVERY_NAMES or lower == ".env" or lower.startswith(".env.")
                         or lower.endswith((".pem", ".key", ".p12", ".pfx")))
            files.append({"relative_path": relative, "bytes": stat.st_size,
                          "mtime_ns": stat.st_mtime_ns,
                          "classification": "RECOVERY_ONLY" if sensitive else "UNCLASSIFIED"})
        if issues and issues[-1]["error_type"] == "INVENTORY_BOUND_REACHED":
            break
    return {"root": str(actual), "files": files, "exclusions": sorted(exclusions),
            "issues": issues, "coverage": "PARTIAL" if issues else "DISCOVERED"}


def discover_page(
    root: Path, *, cursor: list[dict[str, Any]] | None = None,
    verified_exclusions: frozenset[str] = frozenset(), max_entries: int = 1000,
) -> dict[str, Any]:
    """Walk registered files in resumable pages; cursor is private trusted local state.

    Each stack frame binds a directory's observed mtime. Changes to a directory while
    paused invalidate that page sequence, which must restart rather than miss entries.
    File content, size and classification must still be validated during capture.
    """
    original = Path(root).absolute()
    if _link(original):
        raise ValueError("Registered source root cannot be a symbolic link")
    actual = original.resolve(strict=True)
    if not actual.is_dir() or type(max_entries) is not int or not 1 <= max_entries <= 10000:
        raise ValueError("Use a directory root and page size between 1 and 10000")
    for exclusion in verified_exclusions:
        candidate = Path(exclusion)
        if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
            raise ValueError("Verified exclusions must be relative source directories")
    frames = [dict(item) for item in cursor] if cursor is not None else [
        {"directory": "", "after": "", "mtime_ns": actual.stat().st_mtime_ns}
    ]
    if not frames or len(frames) > 256:
        raise ValueError("Invalid discovery cursor")
    parent: Path | None = None
    for frame in frames:
        if set(frame) != {"directory", "after", "mtime_ns"}:
            raise ValueError("Invalid discovery cursor frame")
        relative, after = frame["directory"], frame["after"]
        if not isinstance(relative, str) or not isinstance(after, str):
            raise TypeError("Invalid discovery cursor path")
        part = Path(relative)
        if part.is_absolute() or ".." in part.parts or "/" in after or "\\" in after:
            raise ValueError("Invalid discovery cursor path")
        directory = actual / part
        if parent is not None and directory.parent != parent:
            raise ValueError("Invalid discovery cursor ancestry")
        if parent is None and directory != actual:
            raise ValueError("Discovery cursor must start at the registered root")
        if _link(directory) or not directory.resolve(strict=True).is_relative_to(actual):
            raise ValueError("Discovery cursor escaped registered root")
        if type(frame["mtime_ns"]) is not int or directory.stat().st_mtime_ns != frame["mtime_ns"]:
            raise ValueError("Discovery directory changed; restart its inventory")
        parent = directory
    records: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    exclusions: list[str] = []
    processed = 0
    while frames and processed < max_entries:
        frame = frames[-1]
        if set(frame) != {"directory", "after", "mtime_ns"}:
            raise ValueError("Invalid discovery cursor frame")
        relative = frame["directory"]
        after = frame["after"]
        if not isinstance(relative, str) or not isinstance(after, str):
            raise TypeError("Invalid discovery cursor path")
        part = Path(relative)
        if part.is_absolute() or ".." in part.parts or "/" in after or "\\" in after:
            raise ValueError("Invalid discovery cursor path")
        directory = actual / part
        if _link(directory) or not directory.resolve(strict=True).is_relative_to(actual):
            raise ValueError("Discovery cursor escaped registered root")
        stamp = directory.stat().st_mtime_ns
        if type(frame["mtime_ns"]) is not int or stamp != frame["mtime_ns"]:
            raise ValueError("Discovery directory changed; restart its inventory")
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name)
        if directory.stat().st_mtime_ns != stamp:
            raise ValueError("Discovery directory changed; restart its inventory")
        available = [entry for entry in entries if entry.name > after]
        if not available:
            frames.pop()
            continue
        for entry in available:
            if processed >= max_entries:
                break
            frame["after"] = entry.name
            path = directory / entry.name
            rel = path.relative_to(actual).as_posix()
            processed += 1
            try:
                if _link(path):
                    issues.append({"path": rel, "error_type": "SYMLINK_NOT_FOLLOWED"})
                elif entry.is_dir(follow_symlinks=False):
                    if rel in verified_exclusions:
                        exclusions.append(rel)
                    elif len(frames) >= 256:
                        issues.append({"path": rel, "error_type": "MAXIMUM_DEPTH_EXCEEDED"})
                    else:
                        frames.append({"directory": rel, "after": "", "mtime_ns": path.stat().st_mtime_ns})
                        break
                elif entry.is_file(follow_symlinks=False):
                    stat = entry.stat(follow_symlinks=False)
                    lower = entry.name.casefold()
                    sensitive = (lower in RECOVERY_NAMES or lower == ".env"
                                 or lower.startswith(".env.")
                                 or lower.endswith((".pem", ".key", ".p12", ".pfx")))
                    records.append({"relative_path": rel, "bytes": stat.st_size,
                                    "mtime_ns": stat.st_mtime_ns,
                                    "classification": "RECOVERY_ONLY" if sensitive else "UNCLASSIFIED"})
                else:
                    issues.append({"path": rel, "error_type": "NOT_REGULAR_FILE"})
            except OSError as exc:
                issues.append({"path": rel, "error_type": type(exc).__name__})
        else:
            frames.pop()
    return {"root": str(actual), "files": records, "exclusions": exclusions,
            "issues": issues, "cursor": frames or None, "finished": not frames}
