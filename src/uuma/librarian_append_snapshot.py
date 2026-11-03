"""Bounded, verified prefix snapshots for explicitly registered JSONL histories."""

from __future__ import annotations

import hashlib
import os
import time
from datetime import UTC, datetime
from pathlib import Path

CHUNK = 1024 * 1024


def _prefix_hash(stream, size: int, throttle) -> tuple[str, bytes]:
    digest = hashlib.sha256()
    remaining = size
    last = b""
    while remaining:
        block = stream.read(min(CHUNK, remaining))
        if not block:
            raise ValueError("History was truncated during snapshot")
        digest.update(block)
        remaining -= len(block)
        last = block[-1:]
        throttle(len(block))
    return digest.hexdigest(), last


def snapshot_append_only_jsonl(source: Path, destination: Path, *,
                               bytes_per_second: int | None = None) -> dict[str, object]:
    """Copy the initial complete-line prefix and verify it remained byte-identical.

    New appended records do not invalidate the snapshot. In-place changes, replacement,
    truncation and an incomplete initial line do; none may be reported as captured.
    Caller confines the temporary plaintext destination to its private recovery queue.
    """
    source, destination = Path(source), Path(destination)
    if source.suffix.casefold() != ".jsonl" or source.is_symlink():
        raise ValueError("Expected an explicitly registered non-symlink JSONL source")
    if bytes_per_second is not None and (
        type(bytes_per_second) is not int or not 1 <= bytes_per_second <= 1024 * 1024 * 1024
    ):
        raise ValueError("Invalid snapshot bandwidth")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    start = time.monotonic()
    processed = 0

    def throttle(size: int) -> None:
        nonlocal processed
        processed += size
        if bytes_per_second is not None:
            delay = processed / bytes_per_second - (time.monotonic() - start)
            while delay > 0:
                time.sleep(min(delay, 1.0))
                delay = processed / bytes_per_second - (time.monotonic() - start)

    with source.open("rb") as inp:
        before = os.fstat(inp.fileno())
        cutoff_observed_at = datetime.now(UTC).isoformat()
        size = before.st_size
        digest = hashlib.sha256()
        remaining = size
        last = b""
        with destination.open("xb") as out:
            while remaining:
                block = inp.read(min(CHUNK, remaining))
                if not block:
                    raise ValueError("History was truncated during snapshot")
                out.write(block)
                digest.update(block)
                remaining -= len(block)
                last = block[-1:]
                throttle(len(block))
            out.flush()
            os.fsync(out.fileno())
        if size and last != b"\n":
            raise ValueError("History ended in an incomplete JSONL line")
        inp.seek(0)
        verified, _ = _prefix_hash(inp, size, throttle)
        after_handle = os.fstat(inp.fileno())
    after_path = source.stat()
    identity = (before.st_dev, before.st_ino)
    if ((after_handle.st_dev, after_handle.st_ino) != identity
            or (after_path.st_dev, after_path.st_ino) != identity
            or after_handle.st_size < size or after_path.st_size < size
            or digest.hexdigest() != verified):
        raise ValueError("History prefix changed or source was replaced during snapshot")
    return {"snapshot_bytes": size, "snapshot_sha256": verified,
            "snapshot_cutoff_observed_at": cutoff_observed_at,
            "snapshot_semantics": "verified-complete-jsonl-prefix"}
