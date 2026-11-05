"""Read-only operational backup evidence for the server Librarian profile."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


def _connect(path: Path) -> sqlite3.Connection:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Backup ledger is unavailable")
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)


def check_source_freshness(
    source_id: str, scheduled_date_str: str | None, now_dt: datetime | None = None
) -> dict[str, Any]:
    """Evaluate backup freshness and expiration according to scheduled cadence.

    Cadence:
    - 'weekly': sources starting with 'printer-' or ending with '-weekly'.
      Expected every 7 days; expired if > 8 days.
    - 'snapshot': milestone snapshots ('project-*', 'probe', 'librarian-semantic-index').
      Not subject to automated daily expiration.
    - 'daily': all other regular sources. Expected daily at 00:00 (Asia/Singapore).
      If scheduled_date is today: FRESH (not expired).
      If scheduled_date is yesterday:
        OVERDUE (is_expired=True) if current time >= 04:00 (daily run failed/missed),
        else EXPIRING (is_expired=False).
      If scheduled_date is >= 2 days ago: EXPIRED (is_expired=True).
    """
    tz = ZoneInfo("Asia/Singapore")
    now = now_dt.astimezone(tz) if now_dt else datetime.now(tz)
    today = now.date()

    if scheduled_date_str is None:
        return {
            "freshness": "NO_BACKUP",
            "is_expired": True,
            "days_since": None,
            "schedule": "daily",
        }

    try:
        backup_date = date.fromisoformat(scheduled_date_str)
    except ValueError:
        return {
            "freshness": "INVALID_DATE",
            "is_expired": True,
            "days_since": None,
            "schedule": "daily",
        }

    days_since = (today - backup_date).days

    if source_id.startswith("printer-") or source_id.endswith("-weekly"):
        schedule = "weekly"
        if days_since <= 7:
            freshness = "FRESH"
            is_expired = False
        elif days_since == 8:
            freshness = "EXPIRING"
            is_expired = False
        else:
            freshness = "EXPIRED"
            is_expired = True
    elif source_id.startswith("project-") or source_id in {"probe", "librarian-semantic-index"}:
        schedule = "snapshot"
        freshness = "SNAPSHOT"
        is_expired = False
    else:
        schedule = "daily"
        if days_since <= 0:
            freshness = "FRESH"
            is_expired = False
        elif days_since == 1:
            if now.hour >= 4:
                freshness = "OVERDUE"
                is_expired = True
            else:
                freshness = "EXPIRING"
                is_expired = False
        else:
            freshness = "EXPIRED"
            is_expired = True

    return {
        "freshness": freshness,
        "is_expired": is_expired,
        "days_since": days_since,
        "schedule": schedule,
    }


def backup_overview(root: Path) -> dict[str, Any]:
    """Read intake/publication receipts and catalog metadata without opening backup payloads."""
    root = root.resolve(strict=True)
    intake = root / "intake"
    with closing(_connect(intake / "recovery-intake.sqlite")) as db:
        db.execute("BEGIN")
        revisions = db.execute(
            "SELECT batch_id,revision,sha256 FROM manifest_revisions"
        ).fetchall()
        latest = db.execute(
            "SELECT m.raw,m.sha256 FROM manifest_revisions m JOIN "
            "(SELECT batch_id,MAX(revision) revision FROM manifest_revisions GROUP BY batch_id) l "
            "ON m.batch_id=l.batch_id AND m.revision=l.revision"
        ).fetchall()
    published: dict[tuple[str, int], str] = {}
    publication_available = (intake / "recovery-publication.sqlite").is_file()
    if publication_available:
        with closing(_connect(intake / "recovery-publication.sqlite")) as db:
            published = {(batch, rev): digest for batch, rev, digest in db.execute(
                "SELECT batch_id,revision,sha256 FROM publications"
            )}
    matched = sum(published.get((batch, rev)) == digest for batch, rev, digest in revisions)
    per_source: dict[tuple[str, str], dict[str, Any]] = {}
    for raw, digest in latest:
        manifest = json.loads(raw)
        key = (manifest["device"], manifest["source"])
        previous = per_source.get(key)
        if previous and previous["scheduled_date"] >= manifest["scheduled_date"]:
            continue
        entries = manifest["entries"]
        per_source[key] = {
            "device": key[0], "source_id": key[1], "batch_id": manifest["batch_id"],
            "scheduled_date": manifest["scheduled_date"], "coverage": manifest["coverage"],
            "revision": manifest["revision"],
            "captured_entries": sum(e["status"] == "CAPTURED" for e in entries),
            "unavailable_entries": sum(e["status"] == "UNAVAILABLE" for e in entries),
            "nas_publication_receipt": published.get(
                (manifest["batch_id"], manifest["revision"]),
            ) == digest,
            "content_queryable": False,
        }
    policy = json.loads((root / "intake-policy.json").read_text(encoding="utf-8"))
    for device, sources in policy["devices"].items():
        for source in sources:
            per_source.setdefault((device, source), {
                "device": device, "source_id": source, "coverage": "NO_RECEIVED_BACKUP",
                "scheduled_date": None, "nas_publication_receipt": False,
                "content_queryable": False,
            })
    catalog_path = root / "semantic-archive/catalog.json"
    catalog: dict[str, Any] = {"available": False}
    if catalog_path.is_file() and not catalog_path.is_symlink():
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        sources = [s for s in data["sources"] if "librarian" in s["readers"]]
        ids = {s["source_id"] for s in sources}
        records = [r for r in data["records"] if r["source_id"] in ids
                   and "librarian" in r["readers"]]
        catalog = {"available": True, "snapshot_id": data["snapshot_id"],
                   "published_at": data["published_at"], "sources": sources,
                   "record_versions": len(records)}
        for source in per_source.values():
            source["content_queryable"] = source["source_id"] in ids
    now_dt = datetime.now(UTC)
    for source in per_source.values():
        source.update(check_source_freshness(source["source_id"], source.get("scheduled_date"), now_dt=now_dt))
    sorted_sources = [per_source[k] for k in sorted(per_source)]
    issues_count = sum(
        s["coverage"] != "COMPLETE" or not s["nas_publication_receipt"] or s.get("is_expired", False)
        for s in sorted_sources
    )
    return {
        "observed_at": now_dt.isoformat(), "node": "alandelone-server-001",
        "received_batches": len(latest), "received_revisions": len(revisions),
        "nas_published_revisions": matched,
        "nas_pending_revisions": len(revisions) - matched,
        "publication_ledger_available": publication_available,
        "issues_count": issues_count,
        "sources": sorted_sources, "catalog": catalog,
        "evidence_scope": "live_read_of_recorded_receipts; no_payload_rehash_or_restore",
    }


def main() -> None:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    if os.environ.get("UUMA_AGENT_ID") != "librarian":
        raise PermissionError("Trusted launcher must bind Librarian identity")
    root = Path(os.environ["UUMA_LIBRARIAN_OPERATIONS_ROOT"])
    mcp = FastMCP("uuma-librarian-operations")

    @mcp.tool(annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ))
    def librarian_get_operations_status() -> dict[str, Any]:
        """Read backup receipt coverage, NAS publication backlog and readable catalog scope."""
        return backup_overview(root)

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
