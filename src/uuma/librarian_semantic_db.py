"""Canonical Semantic Database (librarian_semantic.db) for Librarian LSIP.

Provides SQLite initialization, DDL schema enforcement, relational operations,
evidence links, entity-relationship graphs, and full-text search (FTS5).
Strictly isolated from uuma.db, wisdom.db, and Hermes state.db schemas.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA_DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    device TEXT NOT NULL,
    category_default TEXT NOT NULL,
    privacy_tier TEXT NOT NULL DEFAULT 'internal',
    adapter_class TEXT NOT NULL,
    manifest_path TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS source_objects (
    object_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    object_uri TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    last_scanned_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS episodes (
    episode_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    object_id TEXT REFERENCES source_objects(object_id),
    title TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    summary TEXT,
    actor_entity TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS records (
    record_id TEXT PRIMARY KEY,
    episode_id TEXT REFERENCES episodes(episode_id),
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    category TEXT NOT NULL CHECK (category IN (
        'Knowledge', 'Experience', 'Decision', 'Work & Artifacts', 'History'
    )),
    project TEXT NOT NULL DEFAULT 'unassigned',
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    full_content TEXT NOT NULL,
    assertion_status TEXT NOT NULL DEFAULT 'proposed' CHECK (assertion_status IN (
        'proposed', 'confirmed', 'historical', 'superseded', 'rejected'
    )),
    superseded_by TEXT,
    valid_from TEXT,
    valid_until TEXT,
    privacy_tier TEXT NOT NULL DEFAULT 'internal' CHECK (privacy_tier IN (
        'public', 'internal', 'restricted', 'honc_private'
    )),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS evidence_links (
    evidence_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES records(record_id) ON DELETE CASCADE,
    object_id TEXT NOT NULL REFERENCES source_objects(object_id),
    locator_type TEXT NOT NULL,
    locator_value TEXT NOT NULL,
    exact_quote TEXT NOT NULL,
    quote_hash TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    aliases_json TEXT
);

CREATE TABLE IF NOT EXISTS relations (
    relation_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_id TEXT NOT NULL,
    object_type TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    evidence_id TEXT REFERENCES evidence_links(evidence_id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS extraction_runs (
    run_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    model_name TEXT,
    items_scanned INTEGER DEFAULT 0,
    claims_extracted INTEGER DEFAULT 0,
    claims_verified INTEGER DEFAULT 0,
    token_usage_json TEXT,
    error_log TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_records USING fts5(
    record_id UNINDEXED,
    title,
    summary,
    full_content,
    project,
    category,
    content='records',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS records_ai AFTER INSERT ON records BEGIN
    INSERT INTO fts_records(rowid, record_id, title, summary, full_content, project, category)
    VALUES (new.rowid, new.record_id, new.title, new.summary, new.full_content, new.project, new.category);
END;

CREATE TRIGGER IF NOT EXISTS records_ad AFTER DELETE ON records BEGIN
    INSERT INTO fts_records(fts_records, rowid, record_id, title, summary, full_content, project, category)
    VALUES ('delete', old.rowid, old.record_id, old.title, old.summary, old.full_content, old.project, old.category);
END;

CREATE TRIGGER IF NOT EXISTS records_au AFTER UPDATE ON records BEGIN
    INSERT INTO fts_records(fts_records, rowid, record_id, title, summary, full_content, project, category)
    VALUES ('delete', old.rowid, old.record_id, old.title, old.summary, old.full_content, old.project, old.category);
    INSERT INTO fts_records(rowid, record_id, title, summary, full_content, project, category)
    VALUES (new.rowid, new.record_id, new.title, new.summary, new.full_content, new.project, new.category);
END;
"""


def init_semantic_db(db_path: Path | str) -> sqlite3.Connection:
    """Initialize the canonical semantic SQLite database with full schema DDL."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.executescript(SCHEMA_DDL)
    conn.commit()
    return conn


def insert_source(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    device: str,
    category_default: str,
    privacy_tier: str = "internal",
    adapter_class: str = "BaseSourceAdapter",
    manifest_path: str | None = None,
    active: int = 1,
) -> None:
    """Insert or update a registered source definition."""
    sql = """
    INSERT INTO sources (source_id, device, category_default, privacy_tier, adapter_class, manifest_path, active)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(source_id) DO UPDATE SET
        device=excluded.device,
        category_default=excluded.category_default,
        privacy_tier=excluded.privacy_tier,
        adapter_class=excluded.adapter_class,
        manifest_path=excluded.manifest_path,
        active=excluded.active,
        updated_at=datetime('now')
    """
    conn.execute(sql, (source_id, device, category_default, privacy_tier, adapter_class, manifest_path, active))
    conn.commit()


def insert_source_object(
    conn: sqlite3.Connection,
    *,
    object_id: str,
    source_id: str,
    object_uri: str,
    content_hash: str,
    byte_size: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Register a concrete source object (file, session, table) as an evidence anchor."""
    meta_json = json.dumps(metadata) if metadata is not None else None
    sql = """
    INSERT OR REPLACE INTO source_objects (object_id, source_id, object_uri, content_hash, byte_size, metadata_json)
    VALUES (?, ?, ?, ?, ?, ?)
    """
    conn.execute(sql, (object_id, source_id, object_uri, content_hash, byte_size, meta_json))
    conn.commit()


def insert_episode(
    conn: sqlite3.Connection,
    *,
    episode_id: str,
    source_id: str,
    title: str,
    started_at: str | None = None,
    ended_at: str | None = None,
    summary: str | None = None,
    actor_entity: str | None = None,
    object_id: str | None = None,
) -> None:
    """Record an episode representing a coherent interaction or session boundary."""
    sql = """
    INSERT OR REPLACE INTO episodes (episode_id, source_id, object_id, title, started_at, ended_at, summary, actor_entity)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    conn.execute(sql, (episode_id, source_id, object_id, title, started_at, ended_at, summary, actor_entity))
    conn.commit()


def insert_record(
    conn: sqlite3.Connection,
    *,
    record_id: str,
    source_id: str,
    category: str,
    title: str,
    summary: str,
    full_content: str,
    project: str = "unassigned",
    episode_id: str | None = None,
    assertion_status: str = "proposed",
    superseded_by: str | None = None,
    valid_from: str | None = None,
    valid_until: str | None = None,
    privacy_tier: str = "internal",
) -> None:
    """Insert or update a semantic record."""
    sql = """
    INSERT INTO records (
        record_id, episode_id, source_id, category, project, title, summary,
        full_content, assertion_status, superseded_by, valid_from, valid_until, privacy_tier
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(record_id) DO UPDATE SET
        episode_id=excluded.episode_id,
        source_id=excluded.source_id,
        category=excluded.category,
        project=excluded.project,
        title=excluded.title,
        summary=excluded.summary,
        full_content=excluded.full_content,
        assertion_status=excluded.assertion_status,
        superseded_by=excluded.superseded_by,
        valid_from=excluded.valid_from,
        valid_until=excluded.valid_until,
        privacy_tier=excluded.privacy_tier,
        updated_at=datetime('now')
    """
    conn.execute(sql, (
        record_id, episode_id, source_id, category, project, title, summary,
        full_content, assertion_status, superseded_by, valid_from, valid_until, privacy_tier
    ))
    conn.commit()


def insert_evidence(
    conn: sqlite3.Connection,
    *,
    evidence_id: str,
    record_id: str,
    object_id: str,
    locator_type: str,
    locator_value: str,
    exact_quote: str,
    quote_hash: str | None = None,
    verified: int = 1,
) -> None:
    """Link a semantic record to immutable evidence from a source object."""
    if quote_hash is None:
        quote_hash = hashlib.sha256(exact_quote.encode("utf-8")).hexdigest()
    sql = """
    INSERT OR REPLACE INTO evidence_links (
        evidence_id, record_id, object_id, locator_type, locator_value, exact_quote, quote_hash, verified
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    conn.execute(sql, (
        evidence_id, record_id, object_id, locator_type, locator_value, exact_quote, quote_hash, verified
    ))
    conn.commit()


def insert_entity(
    conn: sqlite3.Connection,
    *,
    entity_id: str,
    entity_type: str,
    name: str,
    description: str | None = None,
    aliases: list[str] | None = None,
) -> None:
    """Record a system, agent, project, or domain entity."""
    aliases_json = json.dumps(aliases) if aliases is not None else None
    sql = """
    INSERT OR REPLACE INTO entities (entity_id, entity_type, name, description, aliases_json)
    VALUES (?, ?, ?, ?, ?)
    """
    conn.execute(sql, (entity_id, entity_type, name, description, aliases_json))
    conn.commit()


def insert_relation(
    conn: sqlite3.Connection,
    *,
    relation_id: str,
    subject_id: str,
    subject_type: str,
    predicate: str,
    object_id: str,
    object_type: str,
    confidence: float = 1.0,
    evidence_id: str | None = None,
) -> None:
    """Record an entity-to-entity or record-to-entity relation."""
    sql = """
    INSERT OR REPLACE INTO relations (
        relation_id, subject_id, subject_type, predicate, object_id, object_type, confidence, evidence_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    conn.execute(sql, (
        relation_id, subject_id, subject_type, predicate, object_id, object_type, confidence, evidence_id
    ))
    conn.commit()


def search_records(
    conn: sqlite3.Connection,
    query: str,
    *,
    category: str | None = None,
    project: str | None = None,
    assertion_status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search semantic records using FTS5 with optional category and project filtering."""
    clauses: list[str] = []
    params: list[Any] = []

    # Clean query for FTS5 (escape special syntax)
    clean_query = query.replace('"', '""').strip()
    if clean_query:
        clauses.append("r.rowid IN (SELECT rowid FROM fts_records WHERE fts_records MATCH ?)")
        params.append(f'"{clean_query}"')

    if category:
        clauses.append("r.category = ?")
        params.append(category)
    if project:
        clauses.append("r.project = ?")
        params.append(project)
    if assertion_status:
        clauses.append("r.assertion_status = ?")
        params.append(assertion_status)

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)

    sql = f"""
    SELECT r.record_id, r.category, r.project, r.title, r.summary,
           r.full_content, r.assertion_status, r.source_id, r.privacy_tier, r.created_at
    FROM records r
    {where_sql}
    ORDER BY r.created_at DESC
    LIMIT ?
    """
    cursor = conn.cursor()
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    return [
        {
            "record_id": row[0],
            "category": row[1],
            "project": row[2],
            "title": row[3],
            "summary": row[4],
            "full_content": row[5],
            "assertion_status": row[6],
            "source_id": row[7],
            "privacy_tier": row[8],
            "created_at": row[9],
        }
        for row in rows
    ]


def get_record(conn: sqlite3.Connection, record_id: str) -> dict[str, Any] | None:
    """Retrieve full record by its unique record_id."""
    sql = """
    SELECT record_id, episode_id, source_id, category, project, title, summary,
           full_content, assertion_status, superseded_by, valid_from, valid_until,
           privacy_tier, created_at, updated_at
    FROM records WHERE record_id = ?
    """
    cursor = conn.cursor()
    cursor.execute(sql, (record_id,))
    row = cursor.fetchone()
    if not row:
        return None
    return {
        "record_id": row[0],
        "episode_id": row[1],
        "source_id": row[2],
        "category": row[3],
        "project": row[4],
        "title": row[5],
        "summary": row[6],
        "full_content": row[7],
        "assertion_status": row[8],
        "superseded_by": row[9],
        "valid_from": row[10],
        "valid_until": row[11],
        "privacy_tier": row[12],
        "created_at": row[13],
        "updated_at": row[14],
    }


def get_evidence_for_record(conn: sqlite3.Connection, record_id: str) -> list[dict[str, Any]]:
    """Retrieve all evidence links verifying a given record."""
    sql = """
    SELECT e.evidence_id, e.object_id, o.source_id, o.object_uri,
           e.locator_type, e.locator_value, e.exact_quote, e.quote_hash, e.verified
    FROM evidence_links e
    JOIN source_objects o ON e.object_id = o.object_id
    WHERE e.record_id = ?
    """
    cursor = conn.cursor()
    cursor.execute(sql, (record_id,))
    rows = cursor.fetchall()
    return [
        {
            "evidence_id": row[0],
            "object_id": row[1],
            "source_id": row[2],
            "object_uri": row[3],
            "locator_type": row[4],
            "locator_value": row[5],
            "exact_quote": row[6],
            "quote_hash": row[7],
            "verified": bool(row[8]),
        }
        for row in rows
    ]


def migrate_from_catalog(conn: sqlite3.Connection, catalog: dict[str, Any]) -> int:
    """Migrate legacy catalog dictionary records into the canonical semantic database."""
    migrated_count = 0

    # Ensure all sources in catalog are registered
    for source in catalog.get("sources", []):
        src_id = source.get("source_id")
        category_default = source.get("category_default", "Knowledge")
        device = source.get("device", "server")
        privacy_tier = source.get("privacy_tier", "internal")
        insert_source(
            conn,
            source_id=src_id,
            device=device,
            category_default=category_default,
            privacy_tier=privacy_tier,
        )

    for record in catalog.get("records", []):
        rec_id = record.get("record_id")
        ver_id = record.get("version_id", "v1")
        src_id = record.get("source_id", "unknown-source")

        # Ensure source exists in DB
        insert_source(
            conn,
            source_id=src_id,
            device="server",
            category_default="Knowledge",
        )

        title = record.get("title", rec_id)
        kind = record.get("kind", "index")
        category = record.get("category")
        if not category:
            if "brainstormer" in src_id or "yonc" in src_id:
                category = "Decision"
            else:
                category = "Knowledge"

        project_ids = record.get("project_ids", [])
        project = project_ids[0] if project_ids else "unassigned"

        content_sha256 = record.get("content_sha256", "0" * 64)
        content_bytes = record.get("content_bytes", 0)
        obj_id = f"sha256:{content_sha256}"
        obj_uri = record.get("original_ref") or f"catalog://{rec_id}/{ver_id}"

        # Register source object anchor
        insert_source_object(
            conn,
            object_id=obj_id,
            source_id=src_id,
            object_uri=obj_uri,
            content_hash=content_sha256,
            byte_size=content_bytes,
        )

        # Insert record
        summary = record.get("summary") or title
        full_content = record.get("full_content") or f"Kind: {kind}\nTitle: {title}\nRef: {obj_uri}"
        assertion_status = record.get("assertion_status", "confirmed")

        insert_record(
            conn,
            record_id=rec_id,
            source_id=src_id,
            category=category,
            project=project,
            title=title,
            summary=summary,
            full_content=full_content,
            assertion_status=assertion_status,
        )

        # Register traceable evidence link
        evidence_id = f"evi_{rec_id}_{ver_id}"
        insert_evidence(
            conn,
            evidence_id=evidence_id,
            record_id=rec_id,
            object_id=obj_id,
            locator_type="catalog_record",
            locator_value=f"{rec_id}:{ver_id}",
            exact_quote=title,
            verified=1,
        )
        migrated_count += 1

    return migrated_count

