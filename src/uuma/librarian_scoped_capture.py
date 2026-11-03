"""Capture explicitly bounded workstation subtrees without changing another queue."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .librarian_delivery import deliver_queued_batch
from .librarian_intake import IDENTITY
from .librarian_queue import capture_recovery_batch
from .librarian_server_daily import _tree
from .librarian_transfer import DEFAULT_BYTES_PER_SECOND


def capture_scopes(
    scopes: list[dict[str, str]], *, queue: Path, public_pem: bytes, device: str,
    day: str, host: str, ssh_identity: Path,
    on_result: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """Capture distinct named roots; each outcome describes that root alone.

    A failed or empty scan does not claim coverage of its parent or siblings. The
    queue belongs exclusively to this operation and retains immutable batches.
    """
    ids = [item.get("source_id") for item in scopes]
    if (not scopes or len(ids) != len(set(ids)) or not IDENTITY.fullmatch(device)
            or any(not isinstance(item, str) or not IDENTITY.fullmatch(item) for item in ids)):
        raise ValueError("Invalid or duplicate scope identities")
    queue = Path(queue)
    queue.mkdir(parents=True, exist_ok=True)
    if queue.is_symlink() or not queue.is_dir():
        raise ValueError("Scope queue must be a real directory")
    results = []
    for spec in scopes:
        source = spec["source_id"]
        try:
            path = Path(spec["path"])
            if not path.is_absolute() or path.is_symlink():
                raise ValueError("Scope path must be absolute and not a symbolic link")
            files, sqlite_paths = _tree(path)
            if not files:
                result = {"source": source, "coverage": "EMPTY", "server_intake": "NOT_APPLICABLE"}
            else:
                batch = capture_recovery_batch(queue, device, source, day, files, public_pem,
                                               sqlite_paths=sqlite_paths,
                                               bytes_per_second=DEFAULT_BYTES_PER_SECOND)
                result = {"source": source, "batch_id": batch["batch_id"],
                          "coverage": batch["coverage"], "entries": len(batch["entries"]),
                          "server_intake": "PENDING", "nas_publication": "NOT_CHECKED"}
                try:
                    receipt = deliver_queued_batch(queue, batch["batch_id"], host=host,
                                                   identity_file=ssh_identity, use_sessions=True)
                    result.update(server_intake="DELIVERED", manifest_sha256=receipt["sha256"])
                except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
                    result["delivery_error_type"] = type(exc).__name__
        except (OSError, ValueError, TypeError, RuntimeError, sqlite3.Error) as exc:
            result = {"source": source, "status": "FAILED", "error_type": type(exc).__name__}
        results.append(result)
        if on_result is not None:
            on_result(result)
    return results
