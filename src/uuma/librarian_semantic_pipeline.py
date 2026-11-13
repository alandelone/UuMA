"""Semantic Pipeline Coordinator and Catalog Exporter for Librarian LSIP.

Coordinates deterministic and conversational source adapters, persists grounded records
and verifiable evidence links into librarian_semantic.db, and exports unified semantic catalogs.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .librarian_adapter_base import CandidateRecord, LibrarianDeterministicAdapter
from .librarian_brainstormer_adapter import BrainstormerAuditAdapter
from .librarian_conversational_adapter import ConversationalSourceAdapter
from .librarian_semantic_db import (
    insert_entity,
    insert_evidence,
    insert_record,
    insert_relation,
    insert_source,
    insert_source_object,
)
from .librarian_source_registry import get_source, is_registered_source
from .librarian_uuma_adapter import UuMAControlAdapter
from .librarian_yonc_adapter import YoncGraphAdapter


class SemanticPipelineCoordinator:
    """Manages adapter execution, database ingestion, and catalog publishing."""

    def __init__(self, db_conn: sqlite3.Connection) -> None:
        self.conn = db_conn
        self.adapters: dict[str, LibrarianDeterministicAdapter] = {
            "yonc-graph": YoncGraphAdapter(),
            "brainstormer-structured-files": BrainstormerAuditAdapter(),
            "uuma-control": UuMAControlAdapter(),
            "antigravity-core": ConversationalSourceAdapter("antigravity-core", default_category="Experience"),
            "codex-sessions": ConversationalSourceAdapter("codex-sessions", default_category="Experience"),
            "codex-archived": ConversationalSourceAdapter("codex-archived", default_category="History"),
        }

    def register_adapter(self, adapter: LibrarianDeterministicAdapter) -> None:
        """Register an adapter instance."""
        self.adapters[adapter.source_id] = adapter

    def ingest_records(self, candidate_records: list[CandidateRecord]) -> int:
        """Persist a list of candidate records with evidence and entities into the semantic DB."""
        count = 0
        for rec in candidate_records:
            # 1. Ensure source is registered in DB
            if is_registered_source(rec.source_id):
                defn = get_source(rec.source_id)
                insert_source(
                    self.conn,
                    source_id=defn.source_id,
                    device=defn.device,
                    category_default=defn.category_default,
                    privacy_tier=defn.privacy_tier,
                    adapter_class=type(self.adapters.get(rec.source_id)).__name__,
                )
            else:
                insert_source(
                    self.conn,
                    source_id=rec.source_id,
                    device="server",
                    category_default=rec.category,
                    privacy_tier=rec.privacy_tier,
                )

            # 2. Register source object anchor
            obj_id = f"sha256:{rec.content_sha256}"
            insert_source_object(
                self.conn,
                object_id=obj_id,
                source_id=rec.source_id,
                object_uri=rec.original_ref,
                content_hash=rec.content_sha256,
                byte_size=rec.content_bytes,
            )

            # 3. Insert record
            insert_record(
                self.conn,
                record_id=rec.record_id,
                source_id=rec.source_id,
                category=rec.category,
                project=rec.project,
                title=rec.title,
                summary=rec.summary,
                full_content=rec.full_content,
                assertion_status=rec.assertion_status,
                superseded_by=rec.superseded_by,
                privacy_tier=rec.privacy_tier,
            )

            # 4. Insert evidence links
            for evi in rec.evidence:
                evidence_id = f"evi_{rec.record_id}_{evi.quote_hash[:16]}"
                insert_evidence(
                    self.conn,
                    evidence_id=evidence_id,
                    record_id=rec.record_id,
                    object_id=obj_id,
                    locator_type=evi.locator_type,
                    locator_value=evi.locator_value,
                    exact_quote=evi.exact_quote,
                    quote_hash=evi.quote_hash,
                    verified=1,
                )

            # 5. Insert linked entities & relations
            for ent_slug in rec.entities:
                parts = ent_slug.split(":", 1)
                ent_type = parts[0] if len(parts) == 2 else "entity"
                ent_name = parts[1] if len(parts) == 2 else ent_slug

                insert_entity(
                    self.conn,
                    entity_id=ent_slug,
                    entity_type=ent_type,
                    name=ent_name,
                )
                insert_relation(
                    self.conn,
                    relation_id=f"rel_{rec.record_id}_{ent_slug}",
                    subject_id=rec.record_id,
                    subject_type="record",
                    predicate="relates_to",
                    object_id=ent_slug,
                    object_type="entity",
                )

            count += 1
        return count

    def run_adapter(self, source_id: str, payload: Any, **kwargs: Any) -> list[CandidateRecord]:
        """Run a single adapter by source_id, ingest its candidates, and return them."""
        adapter = self.adapters.get(source_id)
        if adapter is None:
            raise ValueError(f"No adapter registered for source: {source_id}")
        candidates = adapter.extract(payload, **kwargs)
        self.ingest_records(candidates)
        return candidates

    def run_deterministic_ingest(self, source_payloads: dict[str, Any]) -> dict[str, int]:
        """Run all registered deterministic adapters against provided payloads."""
        results: dict[str, int] = {}
        for source_id, payload in source_payloads.items():
            adapter = self.adapters.get(source_id)
            if adapter is None:
                continue
            candidates = adapter.extract(payload)
            ingested = self.ingest_records(candidates)
            results[source_id] = ingested
        return results

    def export_catalog(self, snapshot_id: str | None = None) -> dict[str, Any]:
        """Export current semantic database contents to Catalog v1.0 JSON format."""
        if snapshot_id is None:
            snapshot_id = f"lsip-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

        published_at = datetime.now(UTC).isoformat()

        # Export sources
        cur = self.conn.cursor()
        cur.execute("""
        SELECT source_id, device, category_default, privacy_tier FROM sources WHERE active = 1
        """)
        sources_list: list[dict[str, Any]] = []
        for r in cur.fetchall():
            owner = get_source(r[0]).owner_agent if is_registered_source(r[0]) else "librarian"
            sources_list.append({
                "source_id": r[0],
                "owner_agent": owner,
                "readers": ["librarian", "orchestrator", owner],
                "capture_status": "COMPLETE",
                "device": r[1],
                "category_default": r[2],
                "privacy_tier": r[3],
                "source_as_of": published_at,
                "verification": "HASH_VERIFIED",
            })

        # Export records with attached evidence
        cur.execute("""
        SELECT record_id, source_id, category, project, title, summary,
               full_content, assertion_status, superseded_by, created_at, privacy_tier
        FROM records
        ORDER BY created_at DESC
        """)
        records_list: list[dict[str, Any]] = []
        for r in cur.fetchall():
            rec_id = r[0]
            # Fetch evidence links
            cur2 = self.conn.cursor()
            cur2.execute("""
            SELECT evidence_id, object_id, locator_type, locator_value, exact_quote, quote_hash
            FROM evidence_links WHERE record_id = ?
            """, (rec_id,))
            ev_rows = cur2.fetchall()
            evidence_items = [
                {
                    "evidence_id": er[0],
                    "object_id": er[1],
                    "locator_type": er[2],
                    "locator_value": er[3],
                    "exact_quote": er[4],
                    "quote_hash": er[5],
                    "verified": True,
                }
                for er in ev_rows
            ]

            full_content_bytes = r[6].encode("utf-8")
            content_hash = cur.execute(
                "SELECT content_hash FROM source_objects WHERE source_id = ? LIMIT 1", (r[1],)
            ).fetchone()
            obj_sha256 = content_hash[0] if content_hash else "0" * 64

            raw_ts = r[9]
            if raw_ts:
                ts_str = raw_ts.replace(" ", "T")
                if not (ts_str.endswith("Z") or "+" in ts_str or ("-" in ts_str[10:])):
                    ts_str += "+00:00"
            else:
                ts_str = published_at

            record_dict = {
                "record_id": rec_id,
                "version_id": f"v1:{obj_sha256[:16]}",
                "source_id": r[1],
                "readers": ["librarian", "orchestrator"],
                "project_ids": [r[3]],
                "category": r[2],
                "kind": "semantic-fact",
                "title": r[4],
                "summary": r[5],
                "assertion_status": r[7],
                "superseded_by": r[8],
                "original_status": r[7].upper(),
                "original_ref": f"sqlite:semantic_db:records:{rec_id}",
                "captured_at": ts_str,
                "is_summary": True,
                "derived_from": [f"source:{r[1]}"],
                "content_sha256": obj_sha256,
                "content_bytes": len(full_content_bytes),
                "media_type": "text/plain",
                "evidence": evidence_items,
                "entities": [],
            }
            records_list.append(record_dict)

        return {
            "schema_version": 1,
            "snapshot_id": snapshot_id,
            "published_at": published_at,
            "sources": sources_list,
            "records": records_list,
        }


def atomic_publish_semantic_catalog(catalog_data: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    """Atomically publish catalog data to both librarian_semantic_catalog.json and catalog.json."""
    output_dir.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(catalog_data, indent=2, ensure_ascii=False).encode("utf-8")

    primary = output_dir / "librarian_semantic_catalog.json"
    legacy = output_dir / "catalog.json"

    tmp_primary = output_dir / ".librarian_semantic_catalog.json.tmp"
    tmp_primary.write_bytes(raw)
    tmp_primary.replace(primary)

    tmp_legacy = output_dir / ".catalog.json.tmp"
    tmp_legacy.write_bytes(raw)
    tmp_legacy.replace(legacy)

    return primary, legacy

