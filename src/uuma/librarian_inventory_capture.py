"""Capture explicitly granted inventory shards without claiming unseen coverage."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import Any

from .librarian_delivery import deliver_queued_batch
from .librarian_queue import capture_recovery_batch, retry_partial_batch


def capture_inventory_plan(
    plan: dict[str, Any], queue: Path, device: str, scheduled_date: str,
    public_pem: bytes, *, granted_sources: set[str], retry_partial: bool = False,
    host: str | None = None, identity_file: Path | None = None,
    bytes_per_second: int | None = None,
) -> dict[str, Any]:
    """Capture observed files; an incomplete or non-atomic inventory stays explicit.

    Grants are an explicit caller assertion, not proof of server authorization. A
    successful transfer receipt is needed separately to establish delivery.
    """
    root = Path(plan["root"])
    prefix = plan["source_prefix"]
    shards = plan["shards"]
    if (not root.is_absolute() or not isinstance(prefix, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,72}", prefix)
            or not isinstance(shards, list) or len(shards) > 500):
        raise ValueError("Invalid inventory plan")
    if (host is None) != (identity_file is None):
        raise ValueError("Delivery requires both host and identity file")
    if root.is_symlink() or root.resolve() != root.absolute():
        raise ValueError("Inventory root cannot traverse a link")
    seen: set[str] = set()
    validated: list[tuple[str, list[Path]]] = []
    for index, shard in enumerate(shards, 1):
        source = shard["source_id"]
        if source != f"{prefix}-p{index:05d}" or source not in granted_sources:
            raise ValueError("Invalid or ungranted inventory shard")
        values = shard["relative_paths"]
        if not isinstance(values, list) or not values or len(values) > 10000:
            raise ValueError("Invalid shard paths")
        paths = []
        for value in values:
            if not isinstance(value, str) or not value or "\\" in value:
                raise ValueError("Invalid inventory path")
            relative = Path(value)
            if relative.is_absolute() or not relative.parts or any(
                part in {".", ".."} or ":" in part for part in relative.parts
            ):
                raise ValueError("Invalid inventory path")
            path = root / relative
            key = os.path.normcase(str(path))
            if key in seen:
                raise ValueError("Duplicate inventory path")
            seen.add(key)
            for parent in (path, *path.parents):
                if parent == root.parent:
                    break
                try:
                    info = parent.lstat()
                except FileNotFoundError:
                    continue  # Capture records missing files as unavailable.
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise ValueError("Inventory path traverses a link or reparse point")
            paths.append(path)
        validated.append((source, paths))
    if plan.get("observed_files") != len(seen):
        raise ValueError("Inventory file count does not match shard paths")
    # Identify SQLite before capture. An unreadable file is retained and fails
    # closed during capture instead of being silently omitted.
    all_paths = [path for _, paths in validated for path in paths]
    sqlite_paths: set[Path] = set()
    for path in all_paths:
        try:
            with path.open("rb") as stream:
                if stream.read(16) == b"SQLite format 3\x00":
                    sqlite_paths.add(path)
        except OSError:
            pass
    sidecars = {path for path in all_paths if path.name.endswith(("-wal", "-shm"))
                and path.with_name(path.name[:-4]) in sqlite_paths}
    results = []
    captured_sqlite: set[Path] = set()
    for source, paths in validated:
        selected = [path for path in paths if path not in sidecars]
        if not selected:
            results.append({"source_id": source, "coverage": "SQLITE_SIDECARS_ONLY"})
            continue
        manifest = capture_recovery_batch(
            queue, device, source, scheduled_date, selected, public_pem,
            sqlite_paths=frozenset(sqlite_paths.intersection(selected)),
            bytes_per_second=bytes_per_second,
        )
        # Reusing today's immutable batch is only valid for the same file set.
        if {os.path.normcase(str(Path(e["source_path"]).absolute()))
                for e in manifest["entries"]} != {os.path.normcase(str(p.absolute())) for p in selected}:
            raise ValueError("Existing daily batch has a different inventory")
        if retry_partial and manifest["coverage"] == "PARTIAL":
            manifest = retry_partial_batch(queue, manifest["batch_id"], public_pem,
                                           bytes_per_second=bytes_per_second)
        captured_sqlite.update(
            Path(entry["source_path"]) for entry in manifest["entries"]
            if entry["status"] == "CAPTURED" and entry["capture_method"] == "sqlite_online"
        )
        result: dict[str, Any] = {"source_id": source, "batch_id": manifest["batch_id"],
                                  "coverage": manifest["coverage"],
                                  "revision": manifest.get("revision", 1)}
        if host is not None and identity_file is not None:
            transfer_options = ({"bytes_per_second": bytes_per_second}
                                if bytes_per_second is not None else {})
            result["delivery"] = deliver_queued_batch(queue, manifest["batch_id"], host=host,
                                                       identity_file=identity_file, use_sessions=True,
                                                       **transfer_options)
        results.append(result)
    complete = (plan.get("inventory_status") == "DISCOVERED" and plan.get("finished") is True
                and not plan.get("issues") and all(
                    item["coverage"] in {"COMPLETE", "SQLITE_SIDECARS_ONLY"} for item in results))
    covered_sidecars = {path for path in sidecars
                        if path.with_name(path.name[:-4]) in captured_sqlite}
    return {"inventory_status": plan.get("inventory_status"), "snapshot_consistency": "NON_ATOMIC",
            "capture_coverage": "COMPLETE_OBSERVED_INVENTORY" if complete else "PARTIAL",
            "sqlite_sidecars_covered_by_online_snapshot": [str(p) for p in sorted(covered_sidecars)],
            "sqlite_sidecars_without_snapshot": [str(p) for p in sorted(sidecars - covered_sidecars)],
            "shards": results}
