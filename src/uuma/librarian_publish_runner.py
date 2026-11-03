"""Process pending recovery publications without triggering new captures."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from .librarian_publish import publish_batch


def publish_pending(intake: Path, archive: Path, *, limit: int = 20) -> dict[str, Any]:
    """Publish at most `limit` outstanding batch IDs; existing receipts are reused."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Publication batch limit must be between 1 and 100")
    intake = Path(intake).resolve(strict=True)
    archive = Path(archive).resolve(strict=True)
    source = intake / "recovery-intake.sqlite"
    ledger = intake / "recovery-publication.sqlite"
    if source.is_symlink() or ledger.is_symlink():
        raise ValueError("Recovery ledgers cannot be symbolic links")
    if not source.is_file():
        raise FileNotFoundError("Private intake ledger does not exist")
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as db:
        received = db.execute("SELECT batch_id,revision,sha256 FROM manifest_revisions").fetchall()
    published: dict[tuple[str, int], str] = {}
    if ledger.exists():
        with closing(sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True)) as db:
            published = {(batch, revision): digest for batch, revision, digest in db.execute(
                "SELECT batch_id,revision,sha256 FROM publications"
            )}
    outstanding = sorted({batch for batch, revision, digest in received
                          if published.get((batch, revision)) != digest})
    results: list[dict[str, Any]] = []
    for batch_id in outstanding[:limit]:
        try:
            results.append(publish_batch(intake, archive, batch_id))
        except (OSError, ValueError, sqlite3.Error) as exc:
            results.append({"batch_id": batch_id, "status": "FAILED", "error_type": type(exc).__name__})
    return {"attempted": len(results), "remaining": max(0, len(outstanding) - len(results)),
            "failed": sum(item.get("status") == "FAILED" for item in results), "results": results}
